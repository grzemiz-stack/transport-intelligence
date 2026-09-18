"""Reusable async query functions for all API route handlers."""

from datetime import datetime, timedelta

from sqlalchemy import func, select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.db.models import (
    Event, Company, Alert, CrimeHotspot, Report,
    Subscriber, AgentStatus, CompanyFinancial,
)


# ── EVENTS ───────────────────────────────────────────────

async def get_events(
    session: AsyncSession,
    country_code: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    trust_score_min: float = 0.0,
    is_verified: bool | None = None,
    tier: int | None = None,
    tier_max: int | None = None,
    include_low: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Event], int]:
    q = select(Event).options(
        joinedload(Event.source), joinedload(Event.company)
    )
    count_q = select(func.count(Event.id))
    filters = []

    if country_code:
        filters.append(Event.country_code == country_code.upper())
    if event_type:
        filters.append(Event.event_type == event_type)
    if severity:
        filters.append(Event.severity == severity.lower())
    if date_from:
        filters.append(Event.date_occurred >= date_from)
    if date_to:
        filters.append(Event.date_occurred <= date_to)
    if trust_score_min > 0:
        filters.append(Event.trust_score >= trust_score_min)
    if is_verified is not None:
        filters.append(Event.is_verified == is_verified)

    # Intelligence tier filtering
    if tier is not None:
        filters.append(Event.intelligence_tier == tier)
    elif tier_max is not None:
        filters.append(Event.intelligence_tier <= tier_max)
    elif not include_low:
        # Default: show tier 1+2 only (when classified)
        filters.append(
            (Event.intelligence_tier <= 2) | (Event.intelligence_tier.is_(None))
        )

    if filters:
        q = q.where(and_(*filters))
        count_q = count_q.where(and_(*filters))

    total = (await session.execute(count_q)).scalar() or 0
    q = q.order_by(desc(Event.date_occurred)).limit(limit).offset(offset)
    result = await session.execute(q)
    events = result.unique().scalars().all()
    return list(events), total


async def get_event_by_id(session: AsyncSession, event_id) -> Event | None:
    q = select(Event).options(
        joinedload(Event.source), joinedload(Event.company)
    ).where(Event.id == event_id)
    result = await session.execute(q)
    return result.unique().scalar_one_or_none()


async def get_event_stats(session: AsyncSession) -> dict:
    # Counts per country
    q_country = select(Event.country_code, func.count()).group_by(Event.country_code)
    per_country = dict((await session.execute(q_country)).all())

    # Counts per type
    q_type = select(Event.event_type, func.count()).group_by(Event.event_type)
    per_type = dict((await session.execute(q_type)).all())

    # Counts per severity
    q_sev = select(Event.severity, func.count()).group_by(Event.severity)
    per_severity = dict((await session.execute(q_sev)).all())

    # Total
    total = sum(per_country.values())

    # Daily counts 30d
    thirty_ago = datetime.utcnow() - timedelta(days=30)
    q_daily = (
        select(
            func.date(Event.date_occurred).label("day"),
            func.count().label("cnt"),
        )
        .where(Event.date_occurred >= thirty_ago)
        .group_by("day")
        .order_by("day")
    )
    daily_rows = (await session.execute(q_daily)).all()
    daily_map = {str(r.day): r.cnt for r in daily_rows}

    today = datetime.utcnow().date()
    daily_counts = []
    for i in range(30):
        d = today - timedelta(days=29 - i)
        daily_counts.append({"date": str(d), "count": daily_map.get(str(d), 0)})

    # Top hotspots from CrimeHotspot table
    q_hs = select(CrimeHotspot).order_by(desc(CrimeHotspot.event_count)).limit(10)
    hotspots = (await session.execute(q_hs)).scalars().all()
    top_hotspots = [
        {"region": h.region, "count": h.event_count,
         "latitude": h.latitude, "longitude": h.longitude}
        for h in hotspots
    ]

    return {
        "total_events": total,
        "per_country": per_country,
        "per_event_type": per_type,
        "per_severity": {k.upper() if k else k: v for k, v in per_severity.items()},
        "daily_counts_30d": daily_counts,
        "top_hotspots": top_hotspots,
    }


# ── COMPANIES ────────────────────────────────────────────

async def get_companies(
    session: AsyncSession,
    country_code: str | None = None,
    company_type: str | None = None,
    financial_status: str | None = None,
    risk_score_min: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Company], int]:
    q = select(Company)
    count_q = select(func.count(Company.id))
    filters = []

    if country_code:
        filters.append(Company.country_code == country_code.upper())
    if company_type:
        filters.append(Company.company_type == company_type)
    if financial_status:
        filters.append(Company.financial_status == financial_status.lower())
    if risk_score_min is not None:
        filters.append(Company.risk_score >= risk_score_min)

    if filters:
        q = q.where(and_(*filters))
        count_q = count_q.where(and_(*filters))

    total = (await session.execute(count_q)).scalar() or 0
    q = q.order_by(desc(Company.risk_score)).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all()), total


async def get_companies_at_risk(session: AsyncSession) -> list[Company]:
    risk_statuses = ["warning", "critical", "bankrupt", "restructuring"]
    q = (
        select(Company)
        .where(Company.financial_status.in_(risk_statuses))
        .order_by(desc(Company.risk_score))
    )
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_company_by_id(session: AsyncSession, company_id) -> Company | None:
    q = select(Company).where(Company.id == company_id)
    result = await session.execute(q)
    return result.scalar_one_or_none()


# ── ALERTS ───────────────────────────────────────────────

async def get_alerts(
    session: AsyncSession,
    is_active: bool | None = None,
    severity: str | None = None,
    alert_type: str | None = None,
    country: str | None = None,
) -> list[Alert]:
    q = select(Alert)
    filters = []

    if is_active is not None:
        filters.append(Alert.is_active == is_active)
    if severity:
        filters.append(Alert.severity == severity.lower())
    if alert_type:
        filters.append(Alert.alert_type == alert_type)
    if country:
        filters.append(Alert.country_codes.any(country.upper()))

    if filters:
        q = q.where(and_(*filters))

    q = q.order_by(desc(Alert.triggered_at))
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_alert_by_id(session: AsyncSession, alert_id) -> Alert | None:
    q = select(Alert).where(Alert.id == alert_id)
    result = await session.execute(q)
    return result.scalar_one_or_none()


# ── DASHBOARD ────────────────────────────────────────────

async def get_dashboard_overview(session: AsyncSession) -> dict:
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    # Only count tier 1+2 events (actionable intelligence) for dashboard
    tier_filter = (Event.intelligence_tier <= 2) | (Event.intelligence_tier.is_(None))

    events_today = (await session.execute(
        select(func.count(Event.id)).where(Event.date_occurred >= today_start, tier_filter)
    )).scalar() or 0

    events_week = (await session.execute(
        select(func.count(Event.id)).where(Event.date_occurred >= week_start, tier_filter)
    )).scalar() or 0

    events_month = (await session.execute(
        select(func.count(Event.id)).where(Event.date_occurred >= month_start, tier_filter)
    )).scalar() or 0

    # Severity breakdown
    q_sev = select(Event.severity, func.count()).group_by(Event.severity)
    sev_rows = (await session.execute(q_sev)).all()
    events_by_severity = {k.upper() if k else "UNKNOWN": v for k, v in sev_rows}

    # Active alerts
    active_alerts = (await session.execute(
        select(func.count(Alert.id)).where(Alert.is_active == True)
    )).scalar() or 0

    # Agent summary
    q_agents = select(AgentStatus.status, func.count()).group_by(AgentStatus.status)
    agent_rows = (await session.execute(q_agents)).all()
    agents_summary = {"total": sum(v for _, v in agent_rows)}
    for status, cnt in agent_rows:
        agents_summary[status] = cnt

    # Top countries
    q_top = (
        select(Event.country_code, func.count().label("cnt"))
        .group_by(Event.country_code)
        .order_by(desc("cnt"))
        .limit(10)
    )
    top_countries = [
        {"country_code": cc, "count": cnt}
        for cc, cnt in (await session.execute(q_top)).all()
    ]

    # Latest events
    q_latest = (
        select(Event)
        .options(joinedload(Event.source), joinedload(Event.company))
        .order_by(desc(Event.date_occurred))
        .limit(10)
    )
    latest = (await session.execute(q_latest)).unique().scalars().all()

    return {
        "events_today": events_today,
        "events_this_week": events_week,
        "events_this_month": events_month,
        "events_by_severity": events_by_severity,
        "active_alerts_count": active_alerts,
        "agents_summary": agents_summary,
        "top_countries": top_countries,
        "latest_events": latest,
    }


async def get_hotspots(session: AsyncSession) -> list[CrimeHotspot]:
    q = select(CrimeHotspot).order_by(desc(CrimeHotspot.event_count))
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_agent_statuses(session: AsyncSession) -> list[AgentStatus]:
    q = select(AgentStatus).order_by(AgentStatus.country_code, AgentStatus.agent_type)
    result = await session.execute(q)
    return list(result.scalars().all())


async def update_agent_status(
    country_code: str,
    agent_type: str,
    events_count: int = 0,
    errors_count: int = 0,
    status: str = "running",
    error_message: str | None = None,
):
    """Upsert agent status — INSERT ON CONFLICT UPDATE.

    Call after each runner finishes processing a country.
    Uses its own session (standalone, not request-scoped).
    """
    import uuid
    from src.db.postgres import async_session

    try:
        async with async_session() as session:
            result = await session.execute(
                select(AgentStatus).where(
                    AgentStatus.country_code == country_code,
                    AgentStatus.agent_type == agent_type,
                )
            )
            agent = result.scalar_one_or_none()

            if agent is None:
                agent = AgentStatus(
                    id=uuid.uuid4(),
                    country_code=country_code,
                    agent_type=agent_type,
                    status=status,
                    last_heartbeat=datetime.utcnow(),
                    events_collected_today=events_count,
                    errors_today=errors_count,
                    last_error=error_message,
                    uptime_seconds=0,
                )
                session.add(agent)
            else:
                agent.status = status
                agent.last_heartbeat = datetime.utcnow()
                agent.events_collected_today = (
                    (agent.events_collected_today or 0) + events_count
                )
                agent.errors_today = (agent.errors_today or 0) + errors_count
                if error_message:
                    agent.last_error = error_message

            await session.commit()
    except Exception as e:
        import logging
        logging.getLogger("queries").debug(
            "Failed to update agent_status %s/%s: %s", country_code, agent_type, e
        )


# ── REPORTS ──────────────────────────────────────────────

async def get_reports(
    session: AsyncSession,
    report_type: str | None = None,
    status: str | None = None,
) -> list[Report]:
    q = select(Report)
    filters = []
    if report_type:
        filters.append(Report.report_type == report_type)
    if status:
        filters.append(Report.status == status)
    if filters:
        q = q.where(and_(*filters))
    q = q.order_by(desc(Report.created_at))
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_report_by_id(session: AsyncSession, report_id) -> Report | None:
    q = select(Report).where(Report.id == report_id)
    result = await session.execute(q)
    return result.scalar_one_or_none()


# ── SUBSCRIBERS ──────────────────────────────────────────

async def get_subscribers(session: AsyncSession, active_only: bool = True) -> list[Subscriber]:
    q = select(Subscriber)
    if active_only:
        q = q.where(Subscriber.is_active == True)
    q = q.order_by(Subscriber.company_name)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_subscriber_by_id(session: AsyncSession, sub_id) -> Subscriber | None:
    q = select(Subscriber).where(Subscriber.id == sub_id)
    result = await session.execute(q)
    return result.scalar_one_or_none()


# ── COMPANY FINANCIALS ───────────────────────────────────

async def get_company_financials(session: AsyncSession, company_id) -> list[CompanyFinancial]:
    q = (
        select(CompanyFinancial)
        .where(CompanyFinancial.company_id == company_id)
        .order_by(desc(CompanyFinancial.date_occurred))
    )
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_company_events(session: AsyncSession, company_id) -> list[Event]:
    q = (
        select(Event)
        .options(joinedload(Event.source))
        .where(Event.company_id == company_id)
        .order_by(desc(Event.date_occurred))
    )
    result = await session.execute(q)
    return list(result.unique().scalars().all())
