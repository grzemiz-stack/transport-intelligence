"""Endpointy autentykacji — login, register, me, change-password."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from src.db.models import User, UserRole
from src.db.postgres import async_session

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "viewer"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ── Endpoints ─────────────────────────────────────────────────────


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Logowanie — zwraca JWT token."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == body.email))
        user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidlowy email lub haslo",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Konto jest nieaktywne",
        )

    # Update last_login
    async with async_session() as session:
        await session.execute(
            update(User).where(User.id == user.id).values(last_login=datetime.utcnow())
        )
        await session.commit()

    token = create_access_token({"sub": user.email, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            last_login=str(user.last_login) if user.last_login else None,
            created_at=str(user.created_at) if user.created_at else None,
        ),
    )


@router.post("/register", response_model=UserResponse)
async def register(
    body: RegisterRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Rejestracja nowego uzytkownika — tylko ADMIN."""
    if body.role not in [r.value for r in UserRole]:
        raise HTTPException(status_code=400, detail=f"Nieprawidlowa rola: {body.role}")

    async with async_session() as session:
        existing = await session.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Uzytkownik z tym emailem juz istnieje")

        user = User(
            email=body.email,
            password_hash=hash_password(body.password),
            full_name=body.full_name,
            role=body.role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=str(user.created_at) if user.created_at else None,
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """Zwraca dane zalogowanego uzytkownika."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        last_login=str(current_user.last_login) if current_user.last_login else None,
        created_at=str(current_user.created_at) if current_user.created_at else None,
    )


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
):
    """Zmiana hasla zalogowanego uzytkownika."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Nieprawidlowe obecne haslo")

    async with async_session() as session:
        await session.execute(
            update(User)
            .where(User.id == current_user.id)
            .values(password_hash=hash_password(body.new_password))
        )
        await session.commit()

    return {"detail": "Haslo zostalo zmienione"}
