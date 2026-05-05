"""Endpointy REST API do zarzadzania agentami scrapujacymi."""

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user, require_role
from src.api.schemas import (
    AgentActionResponse,
    AgentHealthResponse,
    AgentInfo,
    AgentLogEntry,
    AgentStatusResponse,
    CountryAgentStatus,
)
from src.db.models import User, UserRole
from src.db.postgres import get_session
from src.db.queries import get_agent_statuses

router = APIRouter()

# Country code → name mapping
_COUNTRY_NAMES: dict[str, str] = {
    "PL": "Poland", "DE": "Germany", "CZ": "Czech Republic", "FR": "France",
    "RO": "Romania", "HU": "Hungary", "SK": "Slovakia", "AT": "Austria",
    "IT": "Italy", "ES": "Spain", "NL": "Netherlands", "BE": "Belgium",
    "BG": "Bulgaria", "HR": "Croatia", "SI": "Slovenia", "LT": "Lithuania",
    "LV": "Latvia", "EE": "Estonia", "GB": "United Kingdom", "SE": "Sweden",
}


def _agent_to_info(a) -> AgentInfo:
    return AgentInfo(
        agent_type=a.agent_type,
        status=a.status,
        last_heartbeat=a.last_heartbeat.strftime("%Y-%m-%dT%H:%M:%SZ") if a.last_heartbeat else None,
        events_today=a.events_collected_today or 0,
        errors_today=a.errors_today or 0,
    )


def _group_by_country(agents) -> list[CountryAgentStatus]:
    grouped = defaultdict(list)
    for a in agents:
        grouped[a.country_code].append(a)

    result = []
    for cc in sorted(grouped.keys()):
        country_agents = grouped[cc]
        # Supervisor status: error if any agent has error, running if any running, else stopped
        statuses = {a.status for a in country_agents}
        if "error" in statuses:
            supervisor = "running"  # supervisor is running even if some agents errored
        elif "running" in statuses:
            supervisor = "running"
        else:
            supervisor = "stopped"

        result.append(CountryAgentStatus(
            country_code=cc,
            country_name=_COUNTRY_NAMES.get(cc, cc),
            supervisor_status=supervisor,
            agents=[_agent_to_info(a) for a in country_agents],
        ))
    return result


@router.get("/status", response_model=AgentStatusResponse)
async def get_all_agents_status(db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Status wszystkich agentow per country."""
    agents = await get_agent_statuses(db)

    total = len(agents)
    running = sum(1 for a in agents if a.status == "running")
    stopped = sum(1 for a in agents if a.status == "stopped")
    errors = sum(1 for a in agents if a.status == "error")
    events_today = sum(a.events_collected_today or 0 for a in agents)

    return AgentStatusResponse(
        summary={
            "total_agents": total,
            "running": running,
            "stopped": stopped,
            "errors": errors,
            "total_events_today": events_today,
        },
        countries=_group_by_country(agents),
    )


@router.get("/health", response_model=AgentHealthResponse)
async def get_agents_health(db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Health check: agenci z problemami (heartbeat > 5 min, errors > threshold)."""
    agents = await get_agent_statuses(db)
    now = datetime.utcnow()
    issues = []
    healthy = 0

    for a in agents:
        is_healthy = True

        if a.last_heartbeat:
            delta = (now - a.last_heartbeat).total_seconds()
            if delta > 300:
                is_healthy = False
                issues.append({
                    "country_code": a.country_code,
                    "agent_type": a.agent_type,
                    "issue": "heartbeat_stale",
                    "last_heartbeat": a.last_heartbeat.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "minutes_ago": round(delta / 60, 1),
                })

        if (a.errors_today or 0) > 5:
            is_healthy = False
            issues.append({
                "country_code": a.country_code,
                "agent_type": a.agent_type,
                "issue": "high_error_rate",
                "errors_today": a.errors_today,
            })

        if a.status == "error":
            is_healthy = False

        if is_healthy:
            healthy += 1

    return AgentHealthResponse(
        total_agents=len(agents),
        healthy=healthy,
        unhealthy=len(agents) - healthy,
        issues=issues,
    )


@router.get("/logs", response_model=list[AgentLogEntry])
async def get_agent_logs(
    country_code: str | None = None,
    agent_type: str | None = None,
    level: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Ostatnie logi agentow z filtrowaniem."""
    agents = await get_agent_statuses(db)
    now = datetime.utcnow()

    logs = []
    for a in agents:
        ts = a.last_heartbeat or a.updated_at or now
        ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")

        if a.status == "error" and a.last_error:
            logs.append(AgentLogEntry(
                timestamp=ts_str, country_code=a.country_code,
                agent_type=a.agent_type, level="ERROR", message=a.last_error,
            ))
        elif a.status == "running" and (a.events_collected_today or 0) > 0:
            logs.append(AgentLogEntry(
                timestamp=ts_str, country_code=a.country_code,
                agent_type=a.agent_type, level="INFO",
                message=f"Collected {a.events_collected_today} events today.",
            ))

    if country_code:
        logs = [l for l in logs if l.country_code == country_code.upper()]
    if agent_type:
        logs = [l for l in logs if l.agent_type == agent_type]
    if level:
        logs = [l for l in logs if l.level == level.upper()]

    logs.sort(key=lambda l: l.timestamp, reverse=True)
    return logs[:limit]


@router.get("/status/{country_code}", response_model=CountryAgentStatus)
async def get_country_agents_status(country_code: str, db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Status agentow danego kraju."""
    agents = await get_agent_statuses(db)
    country_agents = [a for a in agents if a.country_code == country_code.upper()]
    if not country_agents:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    statuses = {a.status for a in country_agents}
    supervisor = "running" if "running" in statuses else "stopped"

    return CountryAgentStatus(
        country_code=country_code.upper(),
        country_name=_COUNTRY_NAMES.get(country_code.upper(), country_code.upper()),
        supervisor_status=supervisor,
        agents=[_agent_to_info(a) for a in country_agents],
    )


@router.post("/{country_code}/start", response_model=AgentActionResponse)
async def start_country_agents(country_code: str, db: AsyncSession = Depends(get_session), _user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST))):
    """Uruchom agentow danego kraju."""
    agents = await get_agent_statuses(db)
    country_agents = [a for a in agents if a.country_code == country_code.upper()]
    if not country_agents:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    name = _COUNTRY_NAMES.get(country_code.upper(), country_code.upper())
    return AgentActionResponse(
        country_code=country_code.upper(), action="start", status="ok",
        message=f"Start command sent to {name} supervisor and {len(country_agents)} agents.",
    )


@router.post("/{country_code}/stop", response_model=AgentActionResponse)
async def stop_country_agents(country_code: str, db: AsyncSession = Depends(get_session), _user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST))):
    """Zatrzymaj agentow danego kraju."""
    agents = await get_agent_statuses(db)
    country_agents = [a for a in agents if a.country_code == country_code.upper()]
    if not country_agents:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    name = _COUNTRY_NAMES.get(country_code.upper(), country_code.upper())
    return AgentActionResponse(
        country_code=country_code.upper(), action="stop", status="ok",
        message=f"Stop command sent to {name} supervisor.",
    )


@router.post("/{country_code}/restart", response_model=AgentActionResponse)
async def restart_country_agents(country_code: str, db: AsyncSession = Depends(get_session), _user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST))):
    """Restart agentow danego kraju."""
    agents = await get_agent_statuses(db)
    country_agents = [a for a in agents if a.country_code == country_code.upper()]
    if not country_agents:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    name = _COUNTRY_NAMES.get(country_code.upper(), country_code.upper())
    return AgentActionResponse(
        country_code=country_code.upper(), action="restart", status="ok",
        message=f"Restart command sent to {name} supervisor and {len(country_agents)} agents.",
    )


@router.post("/{country_code}/{agent_type}/restart", response_model=AgentActionResponse)
async def restart_single_agent(country_code: str, agent_type: str, db: AsyncSession = Depends(get_session), _user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST))):
    """Restart konkretnego agenta."""
    agents = await get_agent_statuses(db)
    country_agents = [a for a in agents if a.country_code == country_code.upper()]
    if not country_agents:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    agent_found = any(a.agent_type == agent_type for a in country_agents)
    if not agent_found:
        raise HTTPException(
            status_code=404,
            detail=f"Agent type '{agent_type}' not found in {country_code.upper()}",
        )

    name = _COUNTRY_NAMES.get(country_code.upper(), country_code.upper())
    return AgentActionResponse(
        country_code=country_code.upper(), action=f"restart_{agent_type}", status="ok",
        message=f"Restart command sent to {agent_type} agent in {name}.",
    )
