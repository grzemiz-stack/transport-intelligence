"""System health and status endpoints.

/api/system/health — unauthenticated, for monitoring tools
/api/system/status — authenticated, detailed system info
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text

from src.api.auth import get_current_user
from src.db.postgres import async_session

router = APIRouter()


@router.get("/health")
async def system_health():
    """Lightweight health check — no auth required."""
    components = {}

    # 1. Database
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        components["database"] = {"status": "ok"}
    except Exception as e:
        components["database"] = {"status": "critical", "detail": str(e)}

    # 2. Scheduler
    from src.agents.watchdog import get_scheduler_ref

    sched = get_scheduler_ref()
    if sched:
        count = sched.active_jobs_count
        if count >= 5:
            components["scheduler"] = {"status": "ok", "active_jobs": count}
        elif count > 0:
            components["scheduler"] = {"status": "warning", "active_jobs": count}
        else:
            components["scheduler"] = {"status": "critical", "active_jobs": 0}
    else:
        components["scheduler"] = {"status": "unknown", "detail": "No scheduler ref"}

    # 3. Event freshness (last 30 min)
    try:
        from src.db.models import Event

        cutoff = datetime.utcnow() - timedelta(minutes=30)
        async with async_session() as session:
            result = await session.execute(
                select(func.count(Event.id)).where(Event.date_collected >= cutoff)
            )
            count = result.scalar() or 0
        if count > 0:
            components["events"] = {"status": "ok", "last_30m": count}
        else:
            components["events"] = {"status": "warning", "last_30m": 0}
    except Exception as e:
        components["events"] = {"status": "critical", "detail": str(e)}

    # Overall
    statuses = [c["status"] for c in components.values()]
    if "critical" in statuses:
        overall = "critical"
    elif "warning" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "timestamp": datetime.utcnow().isoformat(),
        "components": components,
        "version": "1.0.0",
    }


@router.get("/status")
async def system_status(user=Depends(get_current_user)):
    """Detailed system status — requires authentication."""
    from src.db.models import AgentStatus, Event
    from src.agents.watchdog import get_scheduler_ref

    data = {
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": None,
        "scheduler": None,
        "events": {},
        "agents": {},
    }

    # Scheduler info
    sched = get_scheduler_ref()
    if sched:
        data["uptime_seconds"] = sched.uptime_seconds
        data["scheduler"] = {
            "active_jobs": sched.active_jobs_count,
            "total_events": sched.total_events,
            "summary": sched.get_stats_summary(),
        }

    # Event counts
    try:
        now = datetime.utcnow()
        async with async_session() as session:
            r1h = await session.execute(
                select(func.count(Event.id)).where(
                    Event.date_collected >= now - timedelta(hours=1)
                )
            )
            r24h = await session.execute(
                select(func.count(Event.id)).where(
                    Event.date_collected >= now - timedelta(hours=24)
                )
            )
            data["events"] = {
                "last_hour": r1h.scalar() or 0,
                "last_24h": r24h.scalar() or 0,
            }
    except Exception as e:
        data["events"] = {"error": str(e)}

    # Agent breakdown
    try:
        async with async_session() as session:
            total = await session.execute(select(func.count(AgentStatus.id)))
            running = await session.execute(
                select(func.count(AgentStatus.id)).where(
                    AgentStatus.status == "running"
                )
            )
            errors = await session.execute(
                select(func.count(AgentStatus.id)).where(
                    AgentStatus.status == "error"
                )
            )
            stopped = await session.execute(
                select(func.count(AgentStatus.id)).where(
                    AgentStatus.status == "stopped"
                )
            )
            data["agents"] = {
                "total": total.scalar() or 0,
                "running": running.scalar() or 0,
                "error": errors.scalar() or 0,
                "stopped": stopped.scalar() or 0,
            }
    except Exception as e:
        data["agents"] = {"error": str(e)}

    return data
