"""AgentScheduler — zarzadza automatycznym uruchamianiem agentow 24/7.

Uzywa APScheduler (AsyncIOScheduler) z rozlozeniem jobow w czasie (jitter).
Kazdy job jest odporny na bledy — awaria jednego nie zabija schedulera.
Status jobow zapisywany do tabeli agent_statuses w PostgreSQL.
"""

import logging
import random
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("scheduler")

CONFIG_PATH = Path(__file__).parent / "daemon_config.yaml"


def load_config() -> dict:
    """Wczytaj konfiguracje schedulera z YAML."""
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


class AgentScheduler:
    """Scheduler zarzadzajacy wszystkimi agentami zbierajacymi dane.

    Funkcjonalnosc:
    - Uruchamia joby z roznymi interwałami (police 30 min, news 15 min, itd.)
    - Kazdy job ma max_instances=1 (skip jesli poprzedni jeszcze trwa)
    - Pierwszy run: losowe opoznienie 0-jitter_seconds
    - Loguje wyniki kazdego joba do agent_statuses
    - alert_check: wykrywa wzorce i generuje alerty
    - health_check: monitoruje status agentow
    """

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._start_time = time.time()
        # Track job stats: {job_id: {runs, events, errors, last_run, last_duration}}
        self._job_stats: dict[str, dict] = defaultdict(
            lambda: {"runs": 0, "events": 0, "errors": 0,
                      "last_run": None, "last_duration": 0.0}
        )
        self._total_events_collected = 0

    def start(self):
        """Uruchom scheduler z wszystkimi jobami."""
        jobs_cfg = self.config.get("jobs", {})
        jitter = self.config.get("scheduler", {}).get("jitter_seconds", 60)

        for job_id, job_cfg in jobs_cfg.items():
            if not job_cfg.get("enabled", True):
                logger.info("Job '%s' disabled — skipping", job_id)
                continue

            interval_minutes = job_cfg.get("interval_minutes", 30)
            max_instances = job_cfg.get("max_instances", 1)

            # Map job_id to handler function
            handler = self._get_handler(job_id)
            if handler is None:
                logger.warning("No handler for job '%s' — skipping", job_id)
                continue

            # Random initial delay to avoid flooding sources on startup
            initial_delay = random.randint(5, max(6, jitter))

            self.scheduler.add_job(
                handler,
                "interval",
                minutes=interval_minutes,
                id=job_id,
                name=job_cfg.get("description", job_id),
                max_instances=max_instances,
                next_run_time=datetime.utcnow() + timedelta(seconds=initial_delay),
                kwargs={"job_cfg": job_cfg},
            )
            logger.info(
                "Scheduled job '%s': every %d min, first run in %ds — %s",
                job_id, interval_minutes, initial_delay,
                job_cfg.get("description", ""),
            )

        self.scheduler.start()
        active = len(self.scheduler.get_jobs())
        logger.info("Scheduler started: %d active jobs", active)

    def shutdown(self, wait: bool = True):
        """Graceful shutdown — czeka na zakonczenie aktualnych jobow (max 30s)."""
        logger.info("Scheduler shutting down (wait=%s)...", wait)
        self.scheduler.shutdown(wait=wait)
        logger.info("Scheduler stopped.")

    @property
    def active_jobs_count(self) -> int:
        return len(self.scheduler.get_jobs())

    @property
    def total_events(self) -> int:
        return self._total_events_collected

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    def get_stats_summary(self) -> str:
        """Zwraca podsumowanie statusu schedulera."""
        uptime = self.uptime_seconds
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        return (
            f"Uptime: {hours}h {minutes}m | "
            f"Jobs: {self.active_jobs_count} active | "
            f"Events collected: {self._total_events_collected} | "
            f"Errors: {sum(s['errors'] for s in self._job_stats.values())}"
        )

    # ── Handler mapping ──────────────────────────────────────────────────

    def _get_handler(self, job_id: str):
        handlers = {
            "rss_police": self._job_rss_police,
            "rss_news": self._job_rss_news,
            "rss_reddit": self._job_rss_reddit,
            "rss_financial": self._job_rss_financial,
            "bundespolizei": self._job_bundespolizei,
            "all_police_scrapers": self._job_all_police_scrapers,
            "pl_financial": self._job_pl_financial,
            "forums": self._job_forums,
            "google_news": self._job_google_news,
            "telegram_scan": self._job_telegram_scan,
            "telegram_discovery": self._job_telegram_discovery,
            "financial_scrapers": self._job_financial_scrapers,
            "debt_registries": self._job_debt_registries,
            "alert_check": self._job_alert_check,
            "intelligence_classify": self._job_intelligence_classify,
            "correlation": self._job_correlation,
            "health_check": self._job_health_check,
            "watchdog": self._job_watchdog,
            "dashboard_stats": self._job_dashboard_stats,
            "daily_digest": self._job_daily_digest,
            "biweekly_report": self._job_biweekly_report,
            "monthly_report": self._job_monthly_report,
            "discord_publish": self._job_discord_publish,
            "discord_daily_summary": self._job_discord_daily_summary,
        }
        return handlers.get(job_id)

    # ── RSS Jobs ─────────────────────────────────────────────────────────

    async def _job_rss_police(self, job_cfg: dict):
        """Zbieranie z feedow policyjnych — wszystkie kraje."""
        await self._run_rss_job("rss_police", source_type="police", job_cfg=job_cfg)

    async def _job_rss_news(self, job_cfg: dict):
        """Zbieranie z feedow mediow — wszystkie kraje."""
        await self._run_rss_job("rss_news", source_type="news", job_cfg=job_cfg)

    async def _job_rss_reddit(self, job_cfg: dict):
        """Zbieranie z Reddit RSS."""
        job_id = "rss_reddit"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.rss_runner import run_reddit
            await run_reddit(dry_run=False)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs", job_id, duration)
            await self._update_agent_status(job_id, "running", duration=duration)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))
            await self._maybe_retry(job_id, job_cfg, self._job_rss_reddit)

    async def _job_rss_financial(self, job_cfg: dict):
        """Zbieranie z feedow finansowych."""
        await self._run_rss_job("rss_financial", source_type="financial", job_cfg=job_cfg)

    async def _run_rss_job(self, job_id: str, source_type: str, job_cfg: dict):
        """Wspolna logika dla jobow RSS."""
        start = time.time()
        logger.info("[%s] START — source_type=%s", job_id, source_type)

        try:
            from src.agents.rss_runner import (
                _create_pipeline,
                _create_translator,
                get_feeds_for_country,
                load_feeds,
                run_feed,
            )

            all_feeds = load_feeds()
            from src.agents.rss_runner import COUNTRY_CODE_MAP

            pipeline = _create_pipeline()
            translator = _create_translator()
            total_events = 0
            total_errors = 0

            for country_name in all_feeds:
                code = COUNTRY_CODE_MAP.get(country_name)
                if not code:
                    continue
                feeds = get_feeds_for_country(all_feeds, code, source_type)
                if not feeds:
                    continue

                for feed_cfg_item in feeds:
                    try:
                        result = await run_feed(feed_cfg_item, pipeline, dry_run=False, translator=translator)
                        total_events += result.get("saved", 0)
                        if result.get("error"):
                            total_errors += 1
                    except Exception as feed_err:
                        logger.error("[%s] Feed error %s: %s",
                                     job_id, feed_cfg_item.get("name"), feed_err)
                        total_errors += 1

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["events"] += total_events
            self._job_stats[job_id]["errors"] += total_errors
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            self._total_events_collected += total_events

            logger.info("[%s] DONE in %.1fs — %d events, %d errors",
                        job_id, duration, total_events, total_errors)
            await self._update_agent_status(
                job_id, "running", events=total_events, errors=total_errors,
                duration=duration,
            )
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))

    # ── Bundespolizei Job ────────────────────────────────────────────────

    async def _job_bundespolizei(self, job_cfg: dict):
        """Uruchamia Bundespolizei scraper."""
        job_id = "bundespolizei"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.runner import run_agent
            await run_agent(country="DE", agent_name="police", once=True, dry_run=False)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs", job_id, duration)
            await self._update_agent_status(job_id, "running", duration=duration)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))
            await self._maybe_retry(job_id, job_cfg, self._job_bundespolizei)

    # ── All Police Scrapers Job ─────────────────────────────────────────

    async def _job_all_police_scrapers(self, job_cfg: dict):
        """Uruchamia police scrapery dla wszystkich krajow po kolei z rate limiting."""
        job_id = "all_police_scrapers"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.runner import run_all_police
            await run_all_police(once=True, dry_run=False)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs", job_id, duration)
            await self._update_agent_status(job_id, "running", duration=duration)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))
            await self._maybe_retry(job_id, job_cfg, self._job_all_police_scrapers)

    # ── PL Financial Job ─────────────────────────────────────────────────

    async def _job_pl_financial(self, job_cfg: dict):
        """Uruchamia Polish Financial scraper (Monitor Sadowy)."""
        job_id = "pl_financial"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.runner import run_agent
            await run_agent(country="PL", agent_name="financial", once=True, dry_run=False)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs", job_id, duration)
            await self._update_agent_status(job_id, "running", duration=duration)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))
            await self._maybe_retry(job_id, job_cfg, self._job_pl_financial)

    # ── Financial Scrapers Job ──────────────────────────────────────────

    async def _job_financial_scrapers(self, job_cfg: dict):
        """Uruchamia wszystkie financial scrapers (DE, PL, GB, FR, AT)."""
        job_id = "financial_scrapers"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.financial.financial_runner import run_all_financial
            await run_all_financial(once=True, dry_run=False)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs", job_id, duration)
            await self._update_agent_status(job_id, "running", duration=duration)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))
            await self._maybe_retry(job_id, job_cfg, self._job_financial_scrapers)

    # ── Debt Registries Job ────────────────────────────────────────────

    async def _job_debt_registries(self, job_cfg: dict):
        """Uruchamia EU Debt Registries scraper (KRD, BIG, Bundesanzeiger, BODACC, Gazette, OpenCorporates)."""
        job_id = "debt_registries"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.financial.financial_runner import run_financial_agent
            await run_financial_agent(country="EU", agent_name="debt_registries", once=True, dry_run=False)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs", job_id, duration)
            await self._update_agent_status(job_id, "running", duration=duration)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))
            await self._maybe_retry(job_id, job_cfg, self._job_debt_registries)

    # ── Forums Job ───────────────────────────────────────────────────────

    async def _job_forums(self, job_cfg: dict):
        """Scrapuje fora kierowcow i transportu — wszystkie kraje."""
        job_id = "forums"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.forum_runner import (
                _create_pipeline,
                _create_translator,
                get_forums_for_country,
                load_forum_feeds,
                run_forum,
                COUNTRY_CODE_MAP,
            )

            all_feeds = load_forum_feeds()
            pipeline = _create_pipeline()
            translator = _create_translator()
            total_events = 0
            total_errors = 0

            for country_name in all_feeds:
                code = COUNTRY_CODE_MAP.get(country_name)
                if not code:
                    continue
                forums = get_forums_for_country(all_feeds, code)
                if not forums:
                    continue

                for forum_cfg_item in forums:
                    try:
                        result = await run_forum(forum_cfg_item, pipeline, dry_run=False, translator=translator)
                        total_events += result.get("saved", 0)
                        if result.get("error"):
                            total_errors += 1
                    except Exception as forum_err:
                        logger.error("[%s] Forum error %s: %s",
                                     job_id, forum_cfg_item.get("name"), forum_err)
                        total_errors += 1

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["events"] += total_events
            self._job_stats[job_id]["errors"] += total_errors
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            self._total_events_collected += total_events

            logger.info("[%s] DONE in %.1fs — %d events, %d errors",
                        job_id, duration, total_events, total_errors)
            await self._update_agent_status(
                job_id, "running", events=total_events, errors=total_errors,
                duration=duration,
            )
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))

    # ── Google News Job ──────────────────────────────────────────────────

    async def _job_google_news(self, job_cfg: dict):
        """Zbieranie z Google News RSS — wszystkie kraje/regiony."""
        job_id = "google_news"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.google_news_runner import (
                _create_pipeline,
                _create_translator,
                get_regions_for_country,
                load_feeds,
                run_region,
                COUNTRY_CODE_MAP,
                RATE_LIMIT_BETWEEN_REGIONS,
                RATE_LIMIT_BETWEEN_COUNTRIES,
            )
            import asyncio

            all_feeds = load_feeds()
            pipeline = _create_pipeline()
            translator = _create_translator()
            total_events = 0
            total_errors = 0
            country_count = 0

            for country_name in all_feeds:
                code = COUNTRY_CODE_MAP.get(country_name)
                if not code:
                    continue
                regions = get_regions_for_country(all_feeds, code)
                if not regions:
                    continue

                country_count += 1

                for i, region_cfg in enumerate(regions):
                    try:
                        result = await run_region(region_cfg, pipeline, dry_run=False, translator=translator)
                        total_events += result.get("saved", 0)
                        if result.get("error"):
                            total_errors += 1
                    except Exception as region_err:
                        logger.error("[%s] Region error %s: %s",
                                     job_id, region_cfg.get("name"), region_err)
                        total_errors += 1

                    # Rate limit between regions
                    if i < len(regions) - 1:
                        await asyncio.sleep(RATE_LIMIT_BETWEEN_REGIONS)

                # Rate limit between countries
                await asyncio.sleep(RATE_LIMIT_BETWEEN_COUNTRIES)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["events"] += total_events
            self._job_stats[job_id]["errors"] += total_errors
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            self._total_events_collected += total_events

            logger.info("[%s] DONE in %.1fs — %d countries, %d events, %d errors",
                        job_id, duration, country_count, total_events, total_errors)
            await self._update_agent_status(
                job_id, "running", events=total_events, errors=total_errors,
                duration=duration,
            )
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))

    # ── Telegram Scan Job ────────────────────────────────────────────────

    async def _job_telegram_scan(self, job_cfg: dict):
        """Skanuje kanaly Telegram — scan-once mode."""
        job_id = "telegram_scan"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.telegram_runner import scan_once
            await scan_once(country_filter=None, dry_run=False)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs", job_id, duration)
            await self._update_agent_status(job_id, "running", duration=duration)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))

    # ── Telegram Discovery Job ────────────────────────────────────────────

    async def _job_telegram_discovery(self, job_cfg: dict):
        """Wyszukuje nowe kanaly/grupy Telegram z transportem."""
        job_id = "telegram_discovery"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.telegram_discovery_runner import run_discovery
            await run_discovery(discover=True, full=False)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs", job_id, duration)
            await self._update_agent_status(job_id, "running", duration=duration)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.warning("[%s] completed with issues after %.1fs: %s", job_id, duration, e)
            await self._update_agent_status(job_id, "idle", error=str(e))

    # ── Intelligence Classification Job ─────────────────────────────────

    async def _job_intelligence_classify(self, job_cfg: dict):
        """Klasyfikuje nowe eventy do intelligence tier 1-4."""
        job_id = "intelligence_classify"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.pipeline.intelligence_classifier import run_classification
            stats = await run_classification()

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["events"] += stats.get("processed", 0)
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info(
                "[%s] DONE in %.1fs — %d classified (T1:%d T2:%d T3:%d T4:%d)",
                job_id, duration, stats["processed"],
                stats["tier_1"], stats["tier_2"], stats["tier_3"], stats["tier_4"],
            )
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)

    # ── Alert Check Job ──────────────────────────────────────────────────

    async def _job_alert_check(self, job_cfg: dict):
        """Sprawdza nowe eventy i generuje alerty.

        Reguly:
        - >= 3 eventy w tym samym regionie/kraju w 30 min → THEFT_SPIKE
        - Event CRITICAL severity → natychmiastowy alert
        """
        job_id = "alert_check"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from sqlalchemy import select

            from src.db.models import Alert, Event
            from src.db.postgres import async_session

            cutoff = datetime.utcnow() - timedelta(minutes=30)
            alerts_created = 0

            async with async_session() as session:
                # 1. Find events from last 30 minutes
                result = await session.execute(
                    select(Event).where(Event.date_collected >= cutoff)
                )
                recent_events = result.scalars().all()

                if not recent_events:
                    logger.info("[%s] No recent events", job_id)
                    duration = time.time() - start
                    self._job_stats[job_id]["runs"] += 1
                    self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
                    return

                # 2. Check for CRITICAL events → immediate alert
                for ev in recent_events:
                    if ev.severity == "critical":
                        # Check if alert already exists for this event
                        existing = await session.execute(
                            select(Alert.id).where(
                                Alert.related_event_ids.contains([ev.id]),
                                Alert.alert_type == "theft_spike",
                            ).limit(1)
                        )
                        if existing.scalar_one_or_none():
                            continue

                        alert = Alert(
                            id=uuid.uuid4(),
                            alert_type="theft_spike",
                            severity="critical",
                            title=f"CRITICAL event: {ev.title[:200]}",
                            description=f"Critical severity event detected in {ev.country_code}",
                            country_codes=[ev.country_code],
                            region=ev.region,
                            is_active=True,
                            related_event_ids=[ev.id],
                        )
                        session.add(alert)
                        alerts_created += 1
                        logger.warning("[%s] CRITICAL alert created: %s", job_id, ev.title[:80])

                # 3. Check for regional spikes (>= 3 events same country+region)
                region_counts: dict[tuple, list] = defaultdict(list)
                for ev in recent_events:
                    key = (ev.country_code, ev.region or "unknown")
                    region_counts[key].append(ev)

                for (country, region), events_list in region_counts.items():
                    if len(events_list) >= 3:
                        event_ids = [e.id for e in events_list]
                        # Check if spike alert already exists
                        existing = await session.execute(
                            select(Alert.id).where(
                                Alert.alert_type == "theft_spike",
                                Alert.is_active.is_(True),
                                Alert.country_codes.contains([country]),
                                Alert.triggered_at >= cutoff,
                            ).limit(1)
                        )
                        if existing.scalar_one_or_none():
                            continue

                        alert = Alert(
                            id=uuid.uuid4(),
                            alert_type="theft_spike",
                            severity="high",
                            title=f"Spike: {len(events_list)} events in {country}/{region}",
                            description=(
                                f"Detected {len(events_list)} events in {country}/{region} "
                                f"within last 30 minutes"
                            ),
                            country_codes=[country],
                            region=region if region != "unknown" else None,
                            is_active=True,
                            related_event_ids=event_ids[:10],
                        )
                        session.add(alert)
                        alerts_created += 1
                        logger.warning(
                            "[%s] SPIKE alert: %d events in %s/%s",
                            job_id, len(events_list), country, region,
                        )

                if alerts_created:
                    await session.commit()

                    # Wyslij notyfikacje email dla nowych alertow CRITICAL/HIGH
                    try:
                        from src.notifications.notification_manager import NotificationManager
                        nm = NotificationManager()
                        # Pobierz swiezo utworzone alerty (nie wyslane jeszcze)
                        new_alerts_result = await session.execute(
                            select(Alert).where(
                                Alert.notification_sent.is_(False),
                                Alert.is_active.is_(True),
                                Alert.severity.in_(["critical", "high"]),
                                Alert.triggered_at >= cutoff,
                            )
                        )
                        new_alerts = new_alerts_result.scalars().all()
                        for new_alert in new_alerts:
                            await nm.notify_alert(new_alert, db=session)
                    except Exception as notif_err:
                        logger.error("[%s] Notification error: %s", job_id, notif_err)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            logger.info("[%s] DONE in %.1fs — %d alerts created, %d recent events checked",
                        job_id, duration, alerts_created, len(recent_events))
        except Exception as e:
            logger.error("[%s] ERROR: %s", job_id, e, exc_info=True)
            self._job_stats[job_id]["errors"] += 1

    # ── Correlation Job ──────────────────────────────────────────────────

    async def _job_correlation(self, job_cfg: dict):
        """Wykrywa korelacje miedzy eventami.

        Szuka wzorcow:
        - Ten sam kraj + typ eventu w krotkim czasie → SAME_LOCATION
        - Wiele eventow z tego samego zrodla → SAME_TIME_PATTERN
        """
        job_id = "correlation"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from sqlalchemy import func, select

            from src.db.models import Event, EventCorrelation
            from src.db.postgres import async_session

            cutoff = datetime.utcnow() - timedelta(hours=2)
            correlations_created = 0

            async with async_session() as session:
                # Find events from last 2 hours grouped by country+event_type
                result = await session.execute(
                    select(
                        Event.country_code,
                        Event.event_type,
                        func.count(Event.id).label("cnt"),
                        func.array_agg(Event.id).label("event_ids"),
                    )
                    .where(Event.date_collected >= cutoff)
                    .group_by(Event.country_code, Event.event_type)
                    .having(func.count(Event.id) >= 3)
                )
                clusters = result.all()

                for row in clusters:
                    country_code, event_type, cnt, event_ids = row
                    # Check if correlation already exists
                    existing = await session.execute(
                        select(EventCorrelation.id).where(
                            EventCorrelation.correlation_type == "same_location",
                            EventCorrelation.country_codes.contains([country_code]),
                            EventCorrelation.detected_at >= cutoff,
                        ).limit(1)
                    )
                    if existing.scalar_one_or_none():
                        continue

                    corr = EventCorrelation(
                        id=uuid.uuid4(),
                        correlation_type="same_location",
                        event_ids=event_ids[:20],
                        description=(
                            f"{cnt} events of type '{event_type}' "
                            f"in {country_code} within last 2 hours"
                        ),
                        confidence=min(0.9, 0.3 + cnt * 0.1),
                        country_codes=[country_code],
                        pattern_description=f"Cluster: {event_type} in {country_code}",
                        is_active=True,
                    )
                    session.add(corr)
                    correlations_created += 1

                if correlations_created:
                    await session.commit()

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            logger.info("[%s] DONE in %.1fs — %d correlations",
                        job_id, duration, correlations_created)
        except Exception as e:
            logger.error("[%s] ERROR: %s", job_id, e, exc_info=True)
            self._job_stats[job_id]["errors"] += 1

    # ── Health Check Job ─────────────────────────────────────────────────

    async def _job_health_check(self, job_cfg: dict):
        """Monitoruje status agentow i systemu."""
        job_id = "health_check"
        start = time.time()

        try:
            from sqlalchemy import func, select, text

            from src.db.models import AgentStatus, Event
            from src.db.postgres import async_session

            async with async_session() as session:
                # Check DB connectivity
                await session.execute(text("SELECT 1"))

                # Count events from last hour
                hour_ago = datetime.utcnow() - timedelta(hours=1)
                result = await session.execute(
                    select(func.count(Event.id)).where(Event.date_collected >= hour_ago)
                )
                events_last_hour = result.scalar() or 0

                # Check agent statuses for errors
                result = await session.execute(
                    select(AgentStatus).where(AgentStatus.status == "error")
                )
                error_agents = result.scalars().all()

                if error_agents:
                    for agent in error_agents:
                        logger.warning(
                            "[health] Agent %s/%s in ERROR state: %s",
                            agent.country_code, agent.agent_type,
                            (agent.last_error or "")[:100],
                        )

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()

            logger.info(
                "[health] DB: OK | Events last hour: %d | Error agents: %d | "
                "Scheduler: %s",
                events_last_hour, len(error_agents) if error_agents else 0,
                self.get_stats_summary(),
            )
        except Exception as e:
            logger.error("[health] System health check FAILED: %s", e)
            self._job_stats[job_id]["errors"] += 1

    # ── Watchdog Job ─────────────────────────────────────────────────────

    async def _job_watchdog(self, job_cfg: dict):
        """System watchdog — auto-healing monitoring."""
        job_id = "watchdog"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.watchdog import SystemWatchdog, set_scheduler_ref

            # Expose scheduler reference for /api/system/ endpoints
            set_scheduler_ref(self)

            if not hasattr(self, "_watchdog_instance"):
                self._watchdog_instance = SystemWatchdog(scheduler=self)

            report = await self._watchdog_instance.run_checks()

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs — status: %s",
                        job_id, duration, report.get("status"))
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)

    # ── Dashboard Stats Job ──────────────────────────────────────────────

    async def _job_dashboard_stats(self, job_cfg: dict):
        """Przelicza statystyki dashboardu i aktualizuje hotspoty."""
        job_id = "dashboard_stats"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from sqlalchemy import func, select

            from src.db.models import CrimeHotspot, Event
            from src.db.postgres import async_session

            async with async_session() as session:
                # Calculate hotspots: regions with >= 5 events in last 7 days
                week_ago = datetime.utcnow() - timedelta(days=7)
                result = await session.execute(
                    select(
                        Event.country_code,
                        Event.region,
                        Event.event_type,
                        func.count(Event.id).label("cnt"),
                    )
                    .where(
                        Event.date_collected >= week_ago,
                        Event.region.isnot(None),
                    )
                    .group_by(Event.country_code, Event.region, Event.event_type)
                    .having(func.count(Event.id) >= 5)
                )
                hotspot_data = result.all()

                hotspots_updated = 0
                for row in hotspot_data:
                    country_code, region, event_type, cnt = row

                    # Update or create hotspot
                    existing = await session.execute(
                        select(CrimeHotspot).where(
                            CrimeHotspot.country_code == country_code,
                            CrimeHotspot.region == region,
                        ).limit(1)
                    )
                    hotspot = existing.scalar_one_or_none()
                    if hotspot:
                        hotspot.event_count = cnt
                        hotspot.last_calculated = datetime.utcnow()
                        if cnt >= 10:
                            hotspot.severity = "high"
                            hotspot.trend = "rising"
                        elif cnt >= 7:
                            hotspot.severity = "medium"
                    hotspots_updated += 1

                if hotspots_updated:
                    await session.commit()

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            logger.info("[%s] DONE in %.1fs — %d hotspots updated",
                        job_id, duration, hotspots_updated)
        except Exception as e:
            logger.error("[%s] ERROR: %s", job_id, e, exc_info=True)
            self._job_stats[job_id]["errors"] += 1

    # ── Daily Digest Job ────────────────────────────────────────────────

    async def _job_daily_digest(self, job_cfg: dict):
        """Wysyla dzienny digest zdarzen do subskrybentow (co 24h o 7:00 UTC)."""
        job_id = "daily_digest"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.notifications.notification_manager import NotificationManager
            nm = NotificationManager()
            sent = await nm.send_daily_digest()

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs — %d digests sent", job_id, duration, sent)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)

    # ── Report Generation Jobs ───────────────────────────────────────────

    async def _job_biweekly_report(self, job_cfg: dict):
        """Generuje raport dwutygodniowy i wysyla notyfikacje."""
        job_id = "biweekly_report"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.reports.live_generator import LiveReportGenerator
            gen = LiveReportGenerator()
            pdf_path = await gen.generate_biweekly_report(language="pl")

            # Notify subscribers
            try:
                from src.notifications.notification_manager import NotificationManager
                nm = NotificationManager()
                await nm.notify_report(
                    {
                        "title": "Raport Dwutygodniowy Transport Intelligence",
                        "report_type": "biweekly",
                        "countries": ["PL", "DE", "CZ", "SK"],
                    },
                    pdf_path=pdf_path,
                )
            except Exception as notif_err:
                logger.error("[%s] Notification error: %s", job_id, notif_err)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs — PDF: %s", job_id, duration, pdf_path)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)

    async def _job_monthly_report(self, job_cfg: dict):
        """Generuje raport miesieczny i wysyla notyfikacje."""
        job_id = "monthly_report"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.reports.live_generator import LiveReportGenerator
            gen = LiveReportGenerator()
            pdf_path = await gen.generate_monthly_report(language="pl")

            # Notify subscribers
            try:
                from src.notifications.notification_manager import NotificationManager
                nm = NotificationManager()
                await nm.notify_report(
                    {
                        "title": "Raport Miesieczny Transport Intelligence",
                        "report_type": "monthly",
                        "countries": ["PL", "DE", "CZ", "SK", "AT", "HU"],
                    },
                    pdf_path=pdf_path,
                )
            except Exception as notif_err:
                logger.error("[%s] Notification error: %s", job_id, notif_err)

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs — PDF: %s", job_id, duration, pdf_path)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)

    # ── Discord Publisher Jobs ───────────────────────────────────────────

    async def _job_discord_publish(self, job_cfg: dict):
        """Publish T1/T2 events to Discord server."""
        job_id = "discord_publish"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.discord_publisher import DiscordPublisher, load_own_server_config
            from src.config import settings

            token = settings.discord_bot_token
            if not token:
                logger.warning("[%s] DISCORD_BOT_TOKEN not configured — skipping", job_id)
                return

            server_config = load_own_server_config()
            if not server_config:
                logger.warning("[%s] own_server config not found — skipping", job_id)
                return

            publisher = DiscordPublisher(bot_token=token, server_config=server_config)
            count = await publisher.publish_events()

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["events"] += count
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs — %d events published", job_id, duration, count)
            await self._update_agent_status(job_id, "running", events=count, duration=duration)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))
            await self._maybe_retry(job_id, job_cfg, self._job_discord_publish)

    async def _job_discord_daily_summary(self, job_cfg: dict):
        """Post daily summary to Discord #general-chat."""
        job_id = "discord_daily_summary"
        start = time.time()
        logger.info("[%s] START", job_id)

        try:
            from src.agents.discord_publisher import DiscordPublisher, load_own_server_config
            from src.config import settings

            token = settings.discord_bot_token
            if not token:
                logger.warning("[%s] DISCORD_BOT_TOKEN not configured — skipping", job_id)
                return

            server_config = load_own_server_config()
            if not server_config:
                logger.warning("[%s] own_server config not found — skipping", job_id)
                return

            publisher = DiscordPublisher(bot_token=token, server_config=server_config)
            success = await publisher.publish_daily_summary()

            duration = time.time() - start
            self._job_stats[job_id]["runs"] += 1
            self._job_stats[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._job_stats[job_id]["last_duration"] = duration
            logger.info("[%s] DONE in %.1fs — success=%s", job_id, duration, success)
            await self._update_agent_status(job_id, "running", duration=duration)
        except Exception as e:
            duration = time.time() - start
            self._job_stats[job_id]["errors"] += 1
            logger.error("[%s] ERROR after %.1fs: %s", job_id, duration, e, exc_info=True)
            await self._update_agent_status(job_id, "error", error=str(e))
            await self._maybe_retry(job_id, job_cfg, self._job_discord_daily_summary)

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _update_agent_status(
        self,
        job_id: str,
        status: str,
        events: int = 0,
        errors: int = 0,
        error: str | None = None,
        duration: float = 0.0,
    ):
        """Zapisuje status joba do tabeli agent_statuses."""
        try:
            from sqlalchemy import select

            from src.db.models import AgentStatus
            from src.db.postgres import async_session

            # Map job_id to agent_type and country_code
            agent_map = {
                "rss_police": ("rss_police", "XX"),
                "rss_news": ("rss_news", "XX"),
                "rss_reddit": ("reddit", "XX"),
                "rss_financial": ("rss_financial", "XX"),
                "bundespolizei": ("police", "DE"),
                "all_police_scrapers": ("police_all", "XX"),
                "pl_financial": ("financial", "PL"),
                "forums": ("forum", "XX"),
                "google_news": ("google_news", "XX"),
                "telegram_scan": ("telegram", "EU"),
                "telegram_discovery": ("telegram_discovery", "EU"),
                "financial_scrapers": ("financial_all", "EU"),
                "debt_registries": ("debt_registry", "EU"),
                "discord_publish": ("discord_publish", "XX"),
                "discord_daily_summary": ("discord_summary", "XX"),
            }
            agent_type, country_code = agent_map.get(job_id, ("news", "XX"))

            async with async_session() as session:
                result = await session.execute(
                    select(AgentStatus).where(
                        AgentStatus.country_code == country_code,
                        AgentStatus.agent_type == agent_type,
                    )
                )
                agent_status = result.scalar_one_or_none()

                if agent_status is None:
                    agent_status = AgentStatus(
                        id=uuid.uuid4(),
                        country_code=country_code,
                        agent_type=agent_type,
                        status=status,
                        last_heartbeat=datetime.utcnow(),
                        events_collected_today=events,
                        errors_today=errors,
                        last_error=error,
                        uptime_seconds=int(self.uptime_seconds),
                    )
                    session.add(agent_status)
                else:
                    agent_status.status = status
                    agent_status.last_heartbeat = datetime.utcnow()
                    agent_status.events_collected_today = (
                        (agent_status.events_collected_today or 0) + events
                    )
                    agent_status.errors_today = (
                        (agent_status.errors_today or 0) + errors
                    )
                    if error:
                        agent_status.last_error = error
                    agent_status.uptime_seconds = int(self.uptime_seconds)

                await session.commit()
        except Exception as e:
            # Don't let status update failures break the scheduler
            logger.debug("Failed to update agent_status for %s: %s", job_id, e)

    async def _maybe_retry(self, job_id: str, job_cfg: dict, handler):
        """Ponawia job jesli konfiguracja na to pozwala."""
        if not job_cfg.get("retry_on_error", False):
            return
        max_retries = job_cfg.get("max_retries", 0)
        current_errors = self._job_stats[job_id]["errors"]
        if current_errors > max_retries:
            logger.warning("[%s] Max retries (%d) exceeded — skipping retry",
                           job_id, max_retries)
            return

        delay = job_cfg.get("retry_delay_seconds", 60)
        logger.info("[%s] Scheduling retry in %ds (attempt %d/%d)",
                    job_id, delay, current_errors, max_retries)

        import asyncio
        await asyncio.sleep(delay)

        try:
            await handler(job_cfg=job_cfg)
        except Exception as e:
            logger.error("[%s] Retry also failed: %s", job_id, e)
