"""Road Alerts REST API — serves road_alerts.jsonl data to CargoControl.

Endpoints:
- GET  /                Read alerts with filters (country, hours, type, geo)
- GET  /route           Alerts along a route corridor
- POST /webhook         Register webhook URL for push notifications
"""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.auth import get_current_user
from src.db.models import User

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
ROAD_ALERTS_FILE = DATA_DIR / "road_alerts.jsonl"
WEBHOOKS_FILE = DATA_DIR / "webhooks.json"


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in km between two points using haversine formula."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_to_segment_distance(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float,
) -> float:
    """Approximate distance (km) from point (px,py) to line segment (ax,ay)-(bx,by).

    Uses projection onto the segment then haversine for the closest point.
    """
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return _haversine(px, py, ax, ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    proj_lat = ax + t * dx
    proj_lon = ay + t * dy
    return _haversine(px, py, proj_lat, proj_lon)


def _read_alerts(
    hours: int = 24,
    country: str | None = None,
    alert_type: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Read and filter alerts from JSONL file."""
    if not ROAD_ALERTS_FILE.exists():
        return []

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    alerts = []

    with open(ROAD_ALERTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                alert = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Time filter
            ts = alert.get("timestamp", "")
            try:
                alert_time = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, TypeError):
                continue
            if alert_time < cutoff:
                continue

            # Country filter
            if country and alert.get("country", "").upper() != country.upper():
                continue

            # Type filter
            if alert_type and alert.get("type", "") != alert_type:
                continue

            alert["_parsed_time"] = alert_time
            alerts.append(alert)

    # Sort by timestamp descending
    alerts.sort(key=lambda a: a.get("_parsed_time", datetime.min), reverse=True)

    # Clean internal field and limit
    for a in alerts:
        a.pop("_parsed_time", None)

    return alerts[:limit]


@router.get("/")
async def get_road_alerts(
    country: str | None = Query(None, description="Filter by country code (e.g. DE, PL)"),
    hours: int = Query(24, ge=1, le=720, description="Last N hours"),
    type: str | None = Query(None, description="Filter by alert type"),
    lat: float | None = Query(None, description="Latitude for geo filter"),
    lon: float | None = Query(None, description="Longitude for geo filter"),
    radius: int = Query(50, ge=1, le=500, description="Radius in km for geo filter"),
    limit: int = Query(100, ge=1, le=1000, description="Max alerts to return"),
):
    """Read road alerts with optional country/time/type/geo filters."""
    alerts = _read_alerts(hours=hours, country=country, alert_type=type, limit=limit if not lat else 10000)

    # Geo filter (if lat/lon provided, match against alerts with parseable locations)
    if lat is not None and lon is not None:
        # For now, geo filtering requires alerts to have lat/lon fields
        # (future: geocode location strings)
        geo_filtered = []
        for a in alerts:
            a_lat = a.get("lat")
            a_lon = a.get("lon")
            if a_lat is not None and a_lon is not None:
                dist = _haversine(lat, lon, float(a_lat), float(a_lon))
                if dist <= radius:
                    a["distance_km"] = round(dist, 1)
                    geo_filtered.append(a)
            else:
                # Include alerts without coordinates (can't filter them out)
                geo_filtered.append(a)
        alerts = geo_filtered[:limit]

    return {"total": len(alerts), "alerts": alerts}


@router.get("/route")
async def get_route_alerts(
    from_lat: float = Query(..., description="Route start latitude"),
    from_lon: float = Query(..., description="Route start longitude"),
    to_lat: float = Query(..., description="Route end latitude"),
    to_lon: float = Query(..., description="Route end longitude"),
    buffer_km: int = Query(50, ge=1, le=200, description="Corridor width in km"),
    hours: int = Query(48, ge=1, le=720, description="Last N hours"),
):
    """Return alerts along a route corridor between two points."""
    alerts = _read_alerts(hours=hours, limit=10000)

    route_alerts = []
    for a in alerts:
        a_lat = a.get("lat")
        a_lon = a.get("lon")
        if a_lat is not None and a_lon is not None:
            dist = _point_to_segment_distance(
                float(a_lat), float(a_lon),
                from_lat, from_lon,
                to_lat, to_lon,
            )
            if dist <= buffer_km:
                a["distance_km"] = round(dist, 1)
                route_alerts.append(a)
        else:
            # Include alerts without coordinates (user can filter client-side)
            route_alerts.append(a)

    # Sort by distance if available
    route_alerts.sort(key=lambda a: a.get("distance_km", 9999))

    return {"total": len(route_alerts), "alerts": route_alerts}


class WebhookRegister(BaseModel):
    url: str
    filters: dict | None = None  # e.g. {"country": "DE", "types": ["accident"]}


@router.post("/webhook")
async def register_webhook(
    body: WebhookRegister,
    _user: User = Depends(get_current_user),
):
    """Register a webhook URL for push notifications on new road alerts."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    webhooks = []
    if WEBHOOKS_FILE.exists():
        try:
            webhooks = json.loads(WEBHOOKS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            webhooks = []

    # Check for duplicate URL
    for wh in webhooks:
        if wh.get("url") == body.url:
            raise HTTPException(status_code=409, detail="Webhook URL already registered")

    webhooks.append({
        "url": body.url,
        "filters": body.filters,
        "registered_at": datetime.utcnow().isoformat() + "Z",
        "registered_by": str(_user.id),
    })

    WEBHOOKS_FILE.write_text(
        json.dumps(webhooks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {"status": "registered", "url": body.url}
