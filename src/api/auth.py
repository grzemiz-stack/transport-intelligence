"""Modul autentykacji JWT — tworzenie/weryfikacja tokenow, hashowanie hasel.

Uzycie w endpointach:
    from src.api.auth import get_current_user, require_role
    @router.get("/")
    async def endpoint(user: User = Depends(get_current_user)): ...
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import User, UserRole
from src.db.postgres import async_session

security = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict) -> str:
    """Create JWT access token with expiration."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> dict:
    """Verify JWT token and return payload. Raises HTTPException 401 on failure."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidlowy lub wygasly token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """FastAPI dependency — extract and verify user from Bearer token."""
    payload = verify_token(credentials.credentials)
    user_email: str | None = payload.get("sub")
    if user_email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidlowy token — brak sub",
        )

    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == user_email))
        user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Uzytkownik nie istnieje lub jest nieaktywny",
        )
    return user


def require_role(*roles: UserRole):
    """FastAPI dependency factory — require specific role(s)."""
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in [r.value for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Brak uprawnien do tej operacji",
            )
        return user
    return _check
