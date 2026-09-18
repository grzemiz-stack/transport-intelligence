"""Integration API endpoints for machine-to-machine communication.

Endpoints:
- GET  /company-check       Single company risk check
- POST /company-check-bulk  Bulk company risk check (max 50)
- GET  /route-risk           Route corridor risk analysis
- POST /subscribe-alerts     Register webhook for alert notifications
- GET  /alerts-feed          Query alerts/events feed
- GET  /road-alerts          Road alerts from JSONL data
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select

from src.api.auth_apikey import APIClient, require_permission
from src.api.routes.road_alerts import _haversine, _point_to_segment_distance, _read_alerts
from src.api.schemas import (
    AlertsFeedResponse,
    AlertSubscribeRequest,
    BulkCompanyCheckRequest,
    CompanyCheckAlert,
    CompanyCheckResponse,
    CompanyCheckResult,
    DeepInvestigateRequest,
    DeepInvestigateResponse,
    RouteHotspot,
    RouteRiskResponse,
)
from src.db.models import Alert, Company, CompanyFinancial, CrimeHotspot, Event
from src.db.postgres import async_session

logger = logging.getLogger(__name__)

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
WEBHOOKS_FILE = DATA_DIR / "integration_webhooks.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_risk(alerts: list[CompanyCheckAlert]) -> tuple[float, str]:
    """Compute risk score (0-100) and level from alerts."""
    if not alerts:
        return 0.0, "low"

    severity_weights = {"critical": 40, "high": 25, "medium": 10, "low": 5}
    score = 0.0
    for a in alerts:
        score += severity_weights.get(a.severity, 5)
    score = min(score, 100.0)

    if score >= 70:
        level = "critical"
    elif score >= 40:
        level = "high"
    elif score >= 20:
        level = "medium"
    else:
        level = "low"

    return round(score, 1), level


def _build_recommendation(alerts: list[CompanyCheckAlert]) -> str:
    """Generate recommendation text based on highest severity alert."""
    if not alerts:
        return "No significant risk indicators found. Standard due diligence recommended."

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    worst = min(alerts, key=lambda a: severity_order.get(a.severity, 99))

    if worst.severity == "critical":
        return f"CRITICAL RISK: {worst.message}. Immediate review required before any business engagement."
    elif worst.severity == "high":
        return f"HIGH RISK: {worst.message}. Enhanced due diligence strongly recommended."
    elif worst.severity == "medium":
        return f"MODERATE RISK: {worst.message}. Standard due diligence with monitoring recommended."
    else:
        return "Low risk profile. Standard business procedures apply."


async def _check_single_company(
    name: str,
    country: str | None = None,
    vat: str | None = None,
) -> CompanyCheckResult:
    """Core company check logic used by single and bulk endpoints."""
    now = datetime.now(timezone.utc)
    alerts: list[CompanyCheckAlert] = []
    company_data = None
    company_id = None

    async with async_session() as session:
        # 1. Search companies table
        q = select(Company).where(Company.name.ilike(f"%{name}%"))
        if country:
            q = q.where(Company.country_code == country.upper())
        if vat:
            q = q.where(Company.tax_id == vat)
        result = await session.execute(q)
        company_data = result.scalar_one_or_none()

        if company_data:
            company_id = str(company_data.id)

            # Check financial status
            if company_data.financial_status in ("bankrupt", "critical"):
                alerts.append(CompanyCheckAlert(
                    type="financial_status",
                    severity="critical",
                    message=f"Company financial status: {company_data.financial_status}",
                    details={"status": company_data.financial_status},
                ))
            elif company_data.financial_status in ("warning", "restructuring"):
                alerts.append(CompanyCheckAlert(
                    type="financial_status",
                    severity="high",
                    message=f"Company financial status: {company_data.financial_status}",
                    details={"status": company_data.financial_status},
                ))

        # 2. Search events mentioning company name
        cutoff_90d = now - timedelta(days=90)
        events_q = select(func.count()).select_from(Event).where(
            or_(
                Event.title.ilike(f"%{name}%"),
                Event.description.ilike(f"%{name}%"),
            )
        )
        if company_data:
            events_q = select(func.count()).select_from(Event).where(
                or_(
                    Event.company_id == company_data.id,
                    Event.title.ilike(f"%{name}%"),
                    Event.description.ilike(f"%{name}%"),
                )
            )
        total_events_result = await session.execute(events_q)
        total_related = total_events_result.scalar() or 0

        # Recent events (90d)
        recent_q = events_q.where(Event.date_occurred >= cutoff_90d)
        recent_result = await session.execute(recent_q)
        recent_count = recent_result.scalar() or 0

        if recent_count >= 5:
            alerts.append(CompanyCheckAlert(
                type="event_frequency",
                severity="high",
                message=f"{recent_count} related incidents in last 90 days",
                details={"count": recent_count, "period": "90d"},
            ))
        elif recent_count >= 2:
            alerts.append(CompanyCheckAlert(
                type="event_frequency",
                severity="medium",
                message=f"{recent_count} related incidents in last 90 days",
                details={"count": recent_count, "period": "90d"},
            ))

        # 3. Check company_financials for critical events
        if company_data:
            fin_q = select(CompanyFinancial).where(
                CompanyFinancial.company_id == company_data.id,
                CompanyFinancial.event_type.in_([
                    "bankruptcy_filing", "license_revoked", "license_suspended",
                ]),
            )
            fin_result = await session.execute(fin_q)
            fin_events = fin_result.scalars().all()
            for fe in fin_events:
                alerts.append(CompanyCheckAlert(
                    type="financial_event",
                    severity="critical",
                    message=f"Financial event: {fe.event_type} on {fe.date_occurred}",
                    details={
                        "event_type": fe.event_type,
                        "date": str(fe.date_occurred),
                        "description": fe.description or "",
                    },
                ))

        # 4. Check events with insolvency/bankruptcy category
        insolvency_q = select(func.count()).select_from(Event).where(
            or_(
                Event.title.ilike(f"%{name}%"),
                Event.description.ilike(f"%{name}%"),
            ),
            or_(
                Event.intelligence_category == "insolvency",
                Event.event_type == "bankruptcy",
            ),
        )
        insolvency_result = await session.execute(insolvency_q)
        insolvency_count = insolvency_result.scalar() or 0
        if insolvency_count > 0:
            alerts.append(CompanyCheckAlert(
                type="insolvency_signal",
                severity="critical",
                message=f"{insolvency_count} insolvency/bankruptcy events found",
                details={"count": insolvency_count},
            ))

        # 5. Payment issues (early warnings)
        payment_q = select(func.count()).select_from(Event).where(
            or_(
                Event.title.ilike(f"%{name}%"),
                Event.description.ilike(f"%{name}%"),
            ),
            Event.event_type == "payment_issue",
        )
        payment_result = await session.execute(payment_q)
        payment_count = payment_result.scalar() or 0
        if payment_count > 0:
            alerts.append(CompanyCheckAlert(
                type="payment_warning",
                severity="high" if payment_count >= 3 else "medium",
                message=f"{payment_count} payment issue event(s) found",
                details={"count": payment_count},
            ))

        # 6. Check for debt registry events
        debt_q = select(func.count()).select_from(Event).where(
            or_(
                Event.title.ilike(f"%{name}%"),
                Event.description.ilike(f"%{name}%"),
            ),
            Event.tags.any("debt_registry"),
        )
        debt_result = await session.execute(debt_q)
        debt_count = debt_result.scalar() or 0
        if debt_count > 0:
            alerts.append(CompanyCheckAlert(
                type="debt_registry",
                severity="critical" if debt_count >= 3 else "high",
                message=f"Found in {debt_count} debt registry/registries",
                details={"count": debt_count},
            ))

    # 7. VAT check (if provided)
    vat_result = None
    if vat and len(vat) >= 4:
        try:
            from src.agents.financial.vies_checker import VIESChecker
            checker = VIESChecker()
            country_code = vat[:2]
            vat_number = vat[2:]
            vat_result = await checker.check_vat(country_code, vat_number)
            if vat_result and not vat_result.get("valid", False):
                alerts.append(CompanyCheckAlert(
                    type="vat_invalid",
                    severity="high",
                    message=f"VAT number {vat} is not valid according to VIES",
                    details=vat_result,
                ))
        except Exception as e:
            logger.warning("VAT check failed for %s: %s", vat, e)
            vat_result = {"error": str(e), "valid": False}

    # Compute risk
    risk_score, risk_level = _compute_risk(alerts)

    # Use company's own risk score if higher
    if company_data and company_data.risk_score > risk_score:
        risk_score = company_data.risk_score
        if risk_score >= 70:
            risk_level = "critical"
        elif risk_score >= 40:
            risk_level = "high"
        elif risk_score >= 20:
            risk_level = "medium"

    return CompanyCheckResult(
        company_name=company_data.name if company_data else name,
        country=company_data.country_code if company_data else country,
        found_in_db=company_data is not None,
        company_id=company_id,
        financial_status=company_data.financial_status if company_data else None,
        tax_id=company_data.tax_id if company_data else vat,
        risk_score=risk_score,
        risk_level=risk_level,
        related_events_count=total_related,
        recent_events_90d=recent_count,
        alerts=alerts,
        vat_check=vat_result,
        recommendation=_build_recommendation(alerts),
        checked_at=now.isoformat(),
    )


# ---------------------------------------------------------------------------
# ENDPOINT 1: Company Check
# ---------------------------------------------------------------------------

@router.get("/company-check", response_model=CompanyCheckResponse)
async def company_check(
    name: str = Query(..., min_length=2, description="Company name to check"),
    country: str | None = Query(None, description="Country code (e.g. DE, PL)"),
    vat: str | None = Query(None, description="VAT/tax ID to validate"),
    client: APIClient = Depends(require_permission("company_check")),
):
    """Check a company's risk profile, financial status, and related events."""
    result = await _check_single_company(name, country, vat)
    return CompanyCheckResponse(results=[result])


# ---------------------------------------------------------------------------
# ENDPOINT 5: Bulk Company Check
# ---------------------------------------------------------------------------

@router.post("/company-check-bulk", response_model=CompanyCheckResponse)
async def company_check_bulk(
    body: BulkCompanyCheckRequest,
    client: APIClient = Depends(require_permission("company_check")),
):
    """Bulk company risk check (max 50 companies)."""
    if len(body.companies) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 companies per request",
        )

    results = []
    for entry in body.companies:
        name = entry.get("name", "")
        if not name:
            continue
        country = entry.get("country")
        vat = entry.get("vat")
        result = await _check_single_company(name, country, vat)
        results.append(result)

    return CompanyCheckResponse(results=results)


# ---------------------------------------------------------------------------
# ENDPOINT 6: Deep Due Diligence Investigation
# ---------------------------------------------------------------------------

@router.post("/deep-investigate", response_model=DeepInvestigateResponse)
async def deep_investigate(
    body: DeepInvestigateRequest,
    client: APIClient = Depends(require_permission("company_check")),
):
    """Deep due diligence — all public sources. Takes 30-60s."""
    from src.analytics.company_investigator import CompanyInvestigator
    investigator = CompanyInvestigator()
    result = await investigator.investigate(
        company_name=body.company_name,
        country=body.country,
        vat_number=body.vat_number,
        registration_number=body.registration_number,
    )
    return DeepInvestigateResponse(status="ok", **result)


# ---------------------------------------------------------------------------
# ENDPOINT 2: Route Risk
# ---------------------------------------------------------------------------

@router.get("/route-risk", response_model=RouteRiskResponse)
async def route_risk(
    from_lat: float = Query(..., description="Route start latitude"),
    from_lon: float = Query(..., description="Route start longitude"),
    to_lat: float = Query(..., description="Route end latitude"),
    to_lon: float = Query(..., description="Route end longitude"),
    buffer_km: int = Query(50, ge=1, le=500, description="Corridor buffer in km"),
    client: APIClient = Depends(require_permission("route_risk")),
):
    """Analyze risk along a route corridor: hotspots, alerts, road alerts."""
    now = datetime.now(timezone.utc)
    cutoff_90d = now - timedelta(days=90)

    estimated_distance = round(_haversine(from_lat, from_lon, to_lat, to_lon), 1)

    hotspots: list[RouteHotspot] = []
    active_alerts: list[dict] = []
    road_alerts_list: list[dict] = []
    recommendations: list[str] = []

    async with async_session() as session:
        # 1. Query theft events with coordinates in last 90 days within corridor
        theft_types = ["theft_cargo", "theft_fuel", "theft_vehicle"]
        events_q = select(Event).where(
            Event.event_type.in_(theft_types),
            Event.latitude.isnot(None),
            Event.longitude.isnot(None),
            Event.date_occurred >= cutoff_90d,
        )
        events_result = await session.execute(events_q)
        theft_events = events_result.scalars().all()

        # Filter by corridor distance and aggregate into hotspot clusters
        corridor_events = []
        for ev in theft_events:
            dist = _point_to_segment_distance(
                ev.latitude, ev.longitude,
                from_lat, from_lon, to_lat, to_lon,
            )
            if dist <= buffer_km:
                corridor_events.append(ev)

        # Simple clustering: group events within 25km of each other
        used = set()
        for i, ev in enumerate(corridor_events):
            if i in used:
                continue
            cluster = [ev]
            used.add(i)
            for j, ev2 in enumerate(corridor_events):
                if j in used:
                    continue
                if _haversine(ev.latitude, ev.longitude, ev2.latitude, ev2.longitude) <= 25:
                    cluster.append(ev2)
                    used.add(j)

            if cluster:
                avg_lat = sum(e.latitude for e in cluster) / len(cluster)
                avg_lon = sum(e.longitude for e in cluster) / len(cluster)
                event_types = list(set(e.event_type for e in cluster))
                severity = "high" if len(cluster) >= 3 else "medium"
                hotspots.append(RouteHotspot(
                    latitude=round(avg_lat, 4),
                    longitude=round(avg_lon, 4),
                    event_count=len(cluster),
                    event_types=event_types,
                    severity=severity,
                    radius_km=25.0,
                ))

        # 2. Query active alerts
        alerts_q = select(Alert).where(Alert.is_active == True)  # noqa: E712
        alerts_result = await session.execute(alerts_q)
        db_alerts = alerts_result.scalars().all()
        for a in db_alerts:
            active_alerts.append({
                "id": str(a.id),
                "alert_type": a.alert_type,
                "severity": a.severity,
                "title": a.title,
                "description": a.description,
                "country_codes": a.country_codes or [],
                "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
            })

        # 3. Query crime_hotspots table (for when it has data)
        hotspots_q = select(CrimeHotspot).where(
            CrimeHotspot.latitude.isnot(None),
            CrimeHotspot.longitude.isnot(None),
        )
        hotspots_result = await session.execute(hotspots_q)
        db_hotspots = hotspots_result.scalars().all()
        for h in db_hotspots:
            dist = _point_to_segment_distance(
                h.latitude, h.longitude,
                from_lat, from_lon, to_lat, to_lon,
            )
            if dist <= buffer_km:
                hotspots.append(RouteHotspot(
                    latitude=round(h.latitude, 4),
                    longitude=round(h.longitude, 4),
                    event_count=h.event_count,
                    event_types=[h.hotspot_type],
                    severity=h.severity,
                    radius_km=h.radius_km,
                ))

    # 4. Road alerts from JSONL
    all_road_alerts = _read_alerts(hours=48, limit=10000)
    for ra in all_road_alerts:
        ra_lat = ra.get("lat")
        ra_lon = ra.get("lon")
        if ra_lat is not None and ra_lon is not None:
            dist = _point_to_segment_distance(
                float(ra_lat), float(ra_lon),
                from_lat, from_lon, to_lat, to_lon,
            )
            if dist <= buffer_km:
                ra["distance_km"] = round(dist, 1)
                road_alerts_list.append(ra)
        else:
            # Include alerts without coordinates
            road_alerts_list.append(ra)

    road_alerts_list.sort(key=lambda a: a.get("distance_km", 9999))

    # 5. Build recommendations
    if hotspots:
        recommendations.append(
            f"{len(hotspots)} theft hotspot(s) detected along the route corridor. "
            "Consider avoiding overnight stops in these areas."
        )
    if len(corridor_events) >= 5:
        recommendations.append(
            f"High incident density ({len(corridor_events)} events in 90 days). "
            "Enhanced security measures recommended."
        )
    if road_alerts_list:
        recommendations.append(
            f"{len(road_alerts_list)} active road alert(s) along the route. "
            "Check for delays and alternative routes."
        )
    if not recommendations:
        recommendations.append(
            "No significant risks detected along this route. Standard precautions apply."
        )

    return RouteRiskResponse(
        route={
            "from": {"lat": from_lat, "lon": from_lon},
            "to": {"lat": to_lat, "lon": to_lon},
            "buffer_km": buffer_km,
        },
        estimated_distance_km=estimated_distance,
        hotspots=hotspots,
        active_alerts=active_alerts,
        road_alerts=road_alerts_list,
        safe_parking=[],  # TODO: no parking-specific data available yet
        recommendations=recommendations,
    )


# ---------------------------------------------------------------------------
# ENDPOINT 3: Subscribe Alerts (webhook)
# ---------------------------------------------------------------------------

@router.post("/subscribe-alerts")
async def subscribe_alerts(
    body: AlertSubscribeRequest,
    client: APIClient = Depends(require_permission("alerts")),
):
    """Register a webhook URL for alert push notifications."""
    # Validate callback_url format
    if not body.callback_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="callback_url must be a valid HTTP(S) URL")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    webhooks = []
    if WEBHOOKS_FILE.exists():
        try:
            webhooks = json.loads(WEBHOOKS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            webhooks = []

    # Check for duplicate
    for wh in webhooks:
        if wh.get("callback_url") == body.callback_url:
            raise HTTPException(status_code=409, detail="Webhook URL already registered")

    webhooks.append({
        "callback_url": body.callback_url,
        "client_name": client.client_name,
        "countries": body.countries,
        "alert_types": body.alert_types,
        "min_severity": body.min_severity,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    })

    WEBHOOKS_FILE.write_text(
        json.dumps(webhooks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {"status": "subscribed", "callback_url": body.callback_url}


# ---------------------------------------------------------------------------
# ENDPOINT 3b: Alerts Feed
# ---------------------------------------------------------------------------

@router.get("/alerts-feed", response_model=AlertsFeedResponse)
async def alerts_feed(
    since: str = Query(..., description="ISO datetime to fetch alerts since"),
    countries: str | None = Query(None, description="Comma-separated country codes"),
    client: APIClient = Depends(require_permission("alerts")),
):
    """Query alerts and events feed since a given datetime."""
    try:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid 'since' datetime format. Use ISO 8601.")

    country_list = [c.strip().upper() for c in countries.split(",")] if countries else []

    alerts_data = []
    events_data = []

    async with async_session() as session:
        # Query alerts
        alerts_q = select(Alert).where(Alert.triggered_at >= since_dt)
        if country_list:
            alerts_q = alerts_q.where(Alert.country_codes.overlap(country_list))
        alerts_result = await session.execute(alerts_q)
        db_alerts = alerts_result.scalars().all()

        for a in db_alerts:
            alerts_data.append({
                "id": str(a.id),
                "alert_type": a.alert_type,
                "severity": a.severity,
                "title": a.title,
                "description": a.description,
                "country_codes": a.country_codes or [],
                "is_active": a.is_active,
                "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
            })

        # Query recent events
        events_q = select(Event).where(Event.date_occurred >= since_dt)
        if country_list:
            events_q = events_q.where(Event.country_code.in_(country_list))
        events_q = events_q.order_by(Event.date_occurred.desc()).limit(200)
        events_result = await session.execute(events_q)
        db_events = events_result.scalars().all()

        for ev in db_events:
            events_data.append({
                "id": str(ev.id),
                "event_type": ev.event_type,
                "severity": ev.severity,
                "title": ev.title,
                "description": ev.description,
                "country_code": ev.country_code,
                "date_occurred": ev.date_occurred.isoformat() if ev.date_occurred else None,
                "latitude": ev.latitude,
                "longitude": ev.longitude,
            })

    return AlertsFeedResponse(
        since=since,
        alerts=alerts_data,
        events=events_data,
        total=len(alerts_data) + len(events_data),
    )


# ---------------------------------------------------------------------------
# ENDPOINT 4: Road Alerts
# ---------------------------------------------------------------------------

@router.get("/road-alerts")
async def integration_road_alerts(
    country: str | None = Query(None, description="Filter by country code"),
    hours: int = Query(24, ge=1, le=720, description="Last N hours"),
    type: str | None = Query(None, description="Filter by alert type"),
    client: APIClient = Depends(require_permission("road_alerts")),
):
    """Road alerts from JSONL data with country/time/type filters."""
    alerts = _read_alerts(hours=hours, country=country, alert_type=type, limit=500)
    return {"status": "ok", "total": len(alerts), "alerts": alerts}
