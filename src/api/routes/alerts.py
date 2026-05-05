"""Endpointy REST API do zarzadzania alertami."""

from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user, require_role
from src.api.schemas import (
    AlertListResponse,
    AlertResolveRequest,
    AlertResponse,
    AlertStatsResponse,
)
from src.api.serializers import alert_to_dict
from src.db.models import User, UserRole
from src.db.postgres import get_session
from src.db.queries import get_alerts, get_alert_by_id

router = APIRouter()


@router.get("/stats", response_model=AlertStatsResponse)
async def get_alert_stats(db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Statystyki alertow: per severity, per country, avg resolution time."""
    all_alerts = await get_alerts(db)

    active = [a for a in all_alerts if a.is_active]
    resolved = [a for a in all_alerts if not a.is_active]

    active_per_severity = Counter(
        (a.severity or "medium").upper() for a in active
    )
    per_country = Counter(
        a.country_codes[0] for a in all_alerts if a.country_codes
    )

    resolution_hours: list[float] = []
    for a in resolved:
        if a.triggered_at and a.resolved_at:
            hours = (a.resolved_at - a.triggered_at).total_seconds() / 3600
            resolution_hours.append(hours)
    avg_hours = round(sum(resolution_hours) / len(resolution_hours), 1) if resolution_hours else 0.0

    return AlertStatsResponse(
        active_per_severity=dict(active_per_severity),
        per_country=dict(per_country),
        average_resolution_hours=avg_hours,
        total_active=len(active),
        total_resolved=len(resolved),
    )


@router.get("/active", response_model=AlertListResponse)
async def get_active_alerts(db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Tylko aktywne alerty (shortcut)."""
    active = await get_alerts(db, is_active=True)
    return AlertListResponse(
        total=len(active),
        alerts=[AlertResponse(**alert_to_dict(a)) for a in active],
    )


@router.get("/", response_model=AlertListResponse)
async def list_alerts(
    is_active: bool | None = None,
    severity: str | None = None,
    alert_type: str | None = None,
    country: str | None = None,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Lista alertow z filtrami."""
    alerts = await get_alerts(
        db, is_active=is_active, severity=severity,
        alert_type=alert_type, country=country,
    )
    return AlertListResponse(
        total=len(alerts),
        alerts=[AlertResponse(**alert_to_dict(a)) for a in alerts],
    )


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: str, body: AlertResolveRequest,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST)),
):
    """Oznacz alert jako resolved."""
    alert = await get_alert_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    if not alert.is_active:
        raise HTTPException(status_code=400, detail=f"Alert {alert_id} is already resolved")

    alert.is_active = False
    alert.resolved_at = datetime.utcnow()
    await db.commit()
    await db.refresh(alert)
    return AlertResponse(**alert_to_dict(alert))


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str, db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Szczegoly alertu z powiazanymi eventami."""
    alert = await get_alert_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return AlertResponse(**alert_to_dict(alert))
