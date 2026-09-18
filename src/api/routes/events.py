"""Endpointy REST API do zarzadzania zdarzeniami transportowymi."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user
from src.api.schemas import (
    EventListResponse, EventResponse, EventStatsResponse, EventTimelineResponse,
)
from src.api.serializers import event_to_dict
from src.db.models import User
from src.db.postgres import get_session
from src.db.queries import get_events, get_event_by_id, get_event_stats

router = APIRouter()


@router.get("/stats", response_model=EventStatsResponse)
async def event_stats(db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    stats = await get_event_stats(db)
    return EventStatsResponse(**stats)


@router.get("/timeline", response_model=EventTimelineResponse)
async def event_timeline(
    grouping: str = Query("day", pattern="^(day|week)$"),
    country_code: str | None = None,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    events, _ = await get_events(db, country_code=country_code, limit=500)
    from collections import Counter

    if grouping == "day":
        counts = Counter(
            e.date_occurred.strftime("%Y-%m-%d") for e in events if e.date_occurred
        )
    else:
        counts = Counter(
            e.date_occurred.strftime("%Y-W%W") for e in events if e.date_occurred
        )

    data = [{"period": k, "count": v} for k, v in sorted(counts.items())]
    return EventTimelineResponse(
        period=f"Last data ({len(events)} events)", grouping=grouping, data=data,
    )


@router.get("/", response_model=EventListResponse)
async def list_events(
    country_code: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    trust_score_min: float = 0.0,
    is_verified: bool | None = None,
    tier: int | None = Query(None, ge=1, le=4, description="Filter by exact intelligence tier (1-4)"),
    include_low: bool = Query(False, description="Include tier 3+4 events (default: tier 1+2 only)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    events, total = await get_events(
        db, country_code=country_code, event_type=event_type,
        severity=severity, date_from=date_from, date_to=date_to,
        trust_score_min=trust_score_min, is_verified=is_verified,
        tier=tier, include_low=include_low,
        limit=limit, offset=offset,
    )
    filters = {}
    if country_code: filters["country_code"] = country_code.upper()
    if event_type: filters["event_type"] = event_type
    if severity: filters["severity"] = severity.upper()
    if tier: filters["tier"] = tier
    if include_low: filters["include_low"] = True

    return EventListResponse(
        total=total, limit=limit, offset=offset,
        filters_applied=filters,
        events=[EventResponse(**event_to_dict(e)) for e in events],
    )


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(event_id: str, db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    event = await get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return EventResponse(**event_to_dict(event))


@router.post("/{event_id}/translate")
async def translate_event(
    event_id: str,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Translate event title/description to Polish using Claude API."""

    event = await get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    # Return cached translation if already translated
    if event.translated_title:
        return {
            "translated_title": event.translated_title,
            "translated_description": event.translated_description,
            "is_translated": True,
        }

    # Translate via Claude API
    from src.pipeline.translator import EventTranslator

    translator = EventTranslator()
    lang = event.language or ""

    translated_title = await translator.translate_to_polish(event.title or "", lang)
    translated_desc = await translator.translate_to_polish(event.description or "", lang)

    # Save to DB
    event.translated_title = translated_title[:500] if translated_title else None
    event.translated_description = translated_desc
    event.is_translated = True
    await db.commit()

    return {
        "translated_title": event.translated_title,
        "translated_description": event.translated_description,
        "is_translated": True,
    }
