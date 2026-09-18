"""SystemWatchdog — proactive monitoring with auto-healing.

Runs every 2 minutes via scheduler. Checks API, DB, scheduler, event
freshness, and agent statuses. Auto-heals where possible, sends alerts
when not.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import yaml
from sqlalchemy import func, select, text

logger = logging.getLogger("watchdog")

# ── Module-level scheduler reference (avoids circular imports) ──────────

_scheduler_ref = None


def set_scheduler_ref(scheduler) -> None:
    global _scheduler_ref
    _scheduler_ref = scheduler


def get_scheduler_ref():
    return _scheduler_ref


# ── Health JSON output path ─────────────────────────────────────────────

HEALTH_JSON_PATH = Path("/var/www/transport-intelligence/data/health.json")

# ── Config path (same as scheduler.py) ──────────────────────────────────

CONFIG_PATH = Path(__file__).parent / "daemon_config.yaml"


def _get_api_port() -> int:
    """Read api.port from daemon_config.yaml, default 8000."""
    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("api", {}).get("port", 8000)
    except Exception:
        return 8000


class SystemWatchdog:
    """Runs 5 health checks, auto-heals, writes health.json, sends alerts."""

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self._heal_attempts: dict[str, int] = {}
        self._last_email_sent: datetime | None = None

    # ── Main entry ──────────────────────────────────────────────────────

    async def run_checks(self) -> dict:
        results = {}
        results["api"] = await self._check_api()
        results["database"] = await self._check_database()
        results["scheduler"] = self._check_scheduler()
        results["event_freshness"] = await self._check_event_freshness()
        results["agent_statuses"] = await self._check_agent_statuses()

        # Derive overall status
        statuses = [r["status"] for r in results.values()]
        if "critical" in statuses:
            overall = "critical"
        elif "warning" in statuses:
            overall = "degraded"
        else:
            overall = "healthy"

        report = {
            "status": overall,
            "timestamp": datetime.utcnow().isoformat(),
            "components": results,
        }

        logger.info(
            "[watchdog] %s — API:%s DB:%s Sched:%s Events:%s Agents:%s",
            overall.upper(),
            results["api"]["status"],
            results["database"]["status"],
            results["scheduler"]["status"],
            results["event_freshness"]["status"],
            results["agent_statuses"]["status"],
        )

        # Write health.json (non-blocking)
        await self._write_health_json(report)

        # Alert on degraded/critical
        if overall in ("degraded", "critical"):
            await self._send_alert_email(report)

        # Escalate if repeated heal failures
        await self._maybe_escalate(report)

        return report

    # ── Individual checks ───────────────────────────────────────────────

    async def _check_api(self) -> dict:
        port = _get_api_port()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"http://127.0.0.1:{port}/")
            if resp.status_code == 200:
                return {"status": "ok", "detail": "API responding"}
            return {"status": "warning", "detail": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.error("[watchdog] API unreachable: %s", e)
            return {"status": "critical", "detail": f"Connection error: {e}"}

    async def _check_database(self) -> dict:
        try:
            from src.db.postgres import async_session

            async with async_session() as session:
                await session.execute(text("SELECT 1"))
            self._heal_attempts.pop("database", None)
            return {"status": "ok", "detail": "DB responding"}
        except Exception as e:
            logger.error("[watchdog] DB check failed: %s", e)
            # Auto-heal
            self._heal_attempts["database"] = self._heal_attempts.get("database", 0) + 1
            try:
                from src.agents.db_reconnector import DBReconnector

                ok = await DBReconnector().check_and_reconnect()
                if ok:
                    return {"status": "warning", "detail": "DB recovered after reconnect"}
            except Exception as heal_err:
                logger.error("[watchdog] DB heal failed: %s", heal_err)
            return {"status": "critical", "detail": f"DB down: {e}"}

    def _check_scheduler(self) -> dict:
        count = self.scheduler.active_jobs_count
        if count >= 5:
            return {"status": "ok", "detail": f"{count} active jobs"}
        if count > 0:
            return {"status": "warning", "detail": f"Only {count} active jobs"}
        return {"status": "critical", "detail": "0 active jobs"}

    async def _check_event_freshness(self) -> dict:
        try:
            from src.db.models import Event
            from src.db.postgres import async_session

            now = datetime.utcnow()
            cutoff_30 = now - timedelta(minutes=30)
            cutoff_60 = now - timedelta(minutes=60)

            async with async_session() as session:
                r30 = await session.execute(
                    select(func.count(Event.id)).where(
                        Event.date_collected >= cutoff_30
                    )
                )
                count_30 = r30.scalar() or 0

                r60 = await session.execute(
                    select(func.count(Event.id)).where(
                        Event.date_collected >= cutoff_60
                    )
                )
                count_60 = r60.scalar() or 0

            if count_30 > 0:
                return {"status": "ok", "detail": f"{count_30} events in last 30m"}
            if count_60 > 0:
                return {
                    "status": "warning",
                    "detail": f"0 events in 30m, {count_60} in 60m",
                }
            # Critical — no events in 60 min, send alert
            return {"status": "critical", "detail": "No events in last 60 minutes"}
        except Exception as e:
            return {"status": "critical", "detail": f"Event freshness check failed: {e}"}

    async def _check_agent_statuses(self) -> dict:
        try:
            from src.db.models import AgentStatus
            from src.db.postgres import async_session

            async with async_session() as session:
                result = await session.execute(
                    select(AgentStatus).where(AgentStatus.status == "error")
                )
                error_agents = result.scalars().all()

            error_count = len(error_agents)
            if error_count == 0:
                return {"status": "ok", "detail": "All agents healthy"}
            if error_count <= 3:
                # Try to reschedule crashed jobs
                await self._reschedule_crashed(error_agents)
                return {
                    "status": "warning",
                    "detail": f"{error_count} agents in error state (reschedule attempted)",
                }
            await self._reschedule_crashed(error_agents)
            return {
                "status": "critical",
                "detail": f"{error_count} agents in error state",
            }
        except Exception as e:
            return {"status": "critical", "detail": f"Agent status check failed: {e}"}

    # ── Auto-heal helpers ───────────────────────────────────────────────

    async def _reschedule_crashed(self, error_agents) -> None:
        """Reschedule crashed jobs by setting next_run_time to now."""
        for agent in error_agents:
            job_id_candidates = [
                agent.agent_type,
                f"{agent.agent_type}_{agent.country_code.lower()}",
            ]
            for candidate in job_id_candidates:
                job = self.scheduler.scheduler.get_job(candidate)
                if job:
                    try:
                        job.modify(next_run_time=datetime.utcnow())
                        logger.info(
                            "[watchdog] Rescheduled job '%s' for agent %s/%s",
                            candidate, agent.country_code, agent.agent_type,
                        )
                    except Exception as e:
                        logger.warning(
                            "[watchdog] Failed to reschedule '%s': %s", candidate, e,
                        )
                    break

    # ── Health JSON writer ──────────────────────────────────────────────

    async def _write_health_json(self, report: dict) -> None:
        """Atomic write: .tmp → rename."""
        try:
            data = json.dumps(report, indent=2, default=str)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_atomic, data)
        except Exception as e:
            logger.warning("[watchdog] Failed to write health.json: %s", e)

    @staticmethod
    def _write_atomic(data: str) -> None:
        HEALTH_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = HEALTH_JSON_PATH.with_suffix(".tmp")
        tmp_path.write_text(data)
        tmp_path.rename(HEALTH_JSON_PATH)

    # ── Alert email ─────────────────────────────────────────────────────

    async def _send_alert_email(self, report: dict) -> None:
        """Send alert email with 30-min cooldown."""
        now = datetime.utcnow()
        if self._last_email_sent and (now - self._last_email_sent) < timedelta(minutes=30):
            return

        try:
            from src.notifications.email_sender import EmailSender

            sender = EmailSender()
            components = report["components"]
            lines = [f"System status: {report['status'].upper()}"]
            for name, info in components.items():
                lines.append(f"  {name}: {info['status']} — {info['detail']}")

            await sender.send_raw_email(
                subject=f"[TI Watchdog] System {report['status'].upper()}",
                body_text="\n".join(lines),
                recipients=["kontakt@agentro.pl"],
            )
            self._last_email_sent = now
            logger.info("[watchdog] Alert email sent")
        except Exception as e:
            logger.error("[watchdog] Failed to send alert email: %s", e)

    # ── Escalation ──────────────────────────────────────────────────────

    async def _maybe_escalate(self, report: dict) -> None:
        """If any component exceeds 3 heal attempts, send escalation."""
        escalations = {k: v for k, v in self._heal_attempts.items() if v > 3}
        if not escalations:
            return

        try:
            from src.notifications.email_sender import EmailSender

            sender = EmailSender()
            lines = ["ESCALATION — repeated heal failures:"]
            for comp, count in escalations.items():
                lines.append(f"  {comp}: {count} failed heal attempts")

            await sender.send_raw_email(
                subject="[TI Watchdog] ESCALATION — auto-heal failing",
                body_text="\n".join(lines),
                recipients=["kontakt@agentro.pl"],
            )
            logger.warning("[watchdog] Escalation email sent: %s", escalations)
        except Exception as e:
            logger.error("[watchdog] Escalation email failed: %s", e)
