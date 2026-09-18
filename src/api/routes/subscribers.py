"""Endpointy REST API do zarzadzania subskrybentami raportow."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user, require_role
from src.api.schemas import (
    SubscriberCreate,
    SubscriberListResponse,
    SubscriberResponse,
    SubscriberUpdate,
)
from src.api.serializers import subscriber_to_dict
from src.db.models import Subscriber, User, UserRole
from src.db.postgres import get_session
from src.db.queries import get_subscribers, get_subscriber_by_id

router = APIRouter()


@router.get("/", response_model=SubscriberListResponse)
async def list_subscribers(db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Lista subskrybentow."""
    subs = await get_subscribers(db, active_only=True)
    return SubscriberListResponse(
        total=len(subs),
        subscribers=[SubscriberResponse(**subscriber_to_dict(s)) for s in subs],
    )


@router.post("/", response_model=SubscriberResponse, status_code=201)
async def create_subscriber(body: SubscriberCreate, db: AsyncSession = Depends(get_session), _user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST))):
    """Dodaj nowego subskrybenta."""
    new_sub = Subscriber(
        company_name=body.company_name,
        contact_email=body.email,
        subscription_tier=body.tier.value,
        subscribed_countries=body.countries,
        language_preference=body.language,
        is_active=True,
        subscription_start=date.today(),
        monthly_fee_eur=0.0,
    )
    db.add(new_sub)
    await db.commit()
    await db.refresh(new_sub)
    return SubscriberResponse(**subscriber_to_dict(new_sub))


@router.get("/{subscriber_id}", response_model=SubscriberResponse)
async def get_subscriber(subscriber_id: str, db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Szczegoly subskrybenta."""
    sub = await get_subscriber_by_id(db, subscriber_id)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Subscriber {subscriber_id} not found")
    return SubscriberResponse(**subscriber_to_dict(sub))


@router.put("/{subscriber_id}", response_model=SubscriberResponse)
async def update_subscriber(
    subscriber_id: str, body: SubscriberUpdate,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST)),
):
    """Update subskrybenta."""
    sub = await get_subscriber_by_id(db, subscriber_id)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Subscriber {subscriber_id} not found")

    if body.company_name is not None:
        sub.company_name = body.company_name
    if body.email is not None:
        sub.contact_email = body.email
    if body.tier is not None:
        sub.subscription_tier = body.tier.value
    if body.countries is not None:
        sub.subscribed_countries = body.countries
    if body.language is not None:
        sub.language_preference = body.language

    await db.commit()
    await db.refresh(sub)
    return SubscriberResponse(**subscriber_to_dict(sub))


@router.delete("/{subscriber_id}", response_model=SubscriberResponse)
async def delete_subscriber(subscriber_id: str, db: AsyncSession = Depends(get_session), _user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST))):
    """Dezaktywuj subskrybenta (soft delete)."""
    sub = await get_subscriber_by_id(db, subscriber_id)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Subscriber {subscriber_id} not found")

    sub.is_active = False
    await db.commit()
    await db.refresh(sub)
    return SubscriberResponse(**subscriber_to_dict(sub))
