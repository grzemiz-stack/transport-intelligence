"""API Key authentication for machine-to-machine integration.

Provides:
- APIKeyManager: create, verify, list, deactivate API keys
- get_api_client: FastAPI dependency (X-API-Key header or JWT fallback)
- admin_router: admin endpoints for API key management (POST/GET/DELETE)
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user, require_role
from src.db.models import APIKey, User, UserRole
from src.db.postgres import async_session, get_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# APIClient dataclass returned by get_api_client
# ---------------------------------------------------------------------------

@dataclass
class APIClient:
    client_name: str
    permissions: list[str]
    source: str  # "api_key" | "jwt"


# ---------------------------------------------------------------------------
# API Key Manager
# ---------------------------------------------------------------------------

class APIKeyManager:
    """Manages API keys: create, verify, list, deactivate."""

    @staticmethod
    def _hash_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()

    async def create_key(
        self, client_name: str, permissions: list[str]
    ) -> str:
        """Generate a new API key. Returns the plaintext key (shown once)."""
        raw_key = f"ti_apikey_{secrets.token_hex(32)}"
        key_hash = self._hash_key(raw_key)

        async with async_session() as session:
            db_key = APIKey(
                key_hash=key_hash,
                client_name=client_name,
                permissions=permissions,
                is_active=True,
            )
            session.add(db_key)
            await session.commit()
            await session.refresh(db_key)
            logger.info("API key created for client=%s id=%s", client_name, db_key.id)

        return raw_key

    async def verify_key(self, api_key: str) -> APIKey | None:
        """Verify an API key. Returns the APIKey record or None."""
        key_hash = self._hash_key(api_key)
        async with async_session() as session:
            result = await session.execute(
                select(APIKey).where(
                    APIKey.key_hash == key_hash,
                    APIKey.is_active == True,  # noqa: E712
                )
            )
            db_key = result.scalar_one_or_none()
            if db_key is None:
                return None

            # Update last_used
            await session.execute(
                update(APIKey)
                .where(APIKey.id == db_key.id)
                .values(last_used=datetime.now(timezone.utc))
            )
            await session.commit()
            return db_key

    async def list_keys(self) -> list[dict]:
        """List all API keys (no secret values)."""
        async with async_session() as session:
            result = await session.execute(select(APIKey).order_by(APIKey.id))
            keys = result.scalars().all()
            return [
                {
                    "id": k.id,
                    "client_name": k.client_name,
                    "permissions": k.permissions,
                    "created_at": k.created_at.isoformat() if k.created_at else None,
                    "last_used": k.last_used.isoformat() if k.last_used else None,
                    "is_active": k.is_active,
                }
                for k in keys
            ]

    async def deactivate_key(self, key_id: int) -> bool:
        """Deactivate an API key by id. Returns True if found."""
        async with async_session() as session:
            result = await session.execute(
                update(APIKey)
                .where(APIKey.id == key_id)
                .values(is_active=False)
            )
            await session.commit()
            return result.rowcount > 0


_manager = APIKeyManager()


# ---------------------------------------------------------------------------
# FastAPI dependency: get_api_client
# ---------------------------------------------------------------------------

async def get_api_client(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
) -> APIClient:
    """Authenticate via X-API-Key header (preferred) or Bearer JWT fallback.

    Returns an APIClient with client_name, permissions, and auth source.
    """
    # 1. Try API key first
    if x_api_key:
        db_key = await _manager.verify_key(x_api_key)
        if db_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive API key",
            )
        return APIClient(
            client_name=db_key.client_name,
            permissions=db_key.permissions or [],
            source="api_key",
        )

    # 2. Fallback to JWT Bearer token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
        from src.api.auth import verify_token
        payload = verify_token(token)
        user_email = payload.get("sub")
        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid JWT token",
            )
        async with async_session() as session:
            from src.db.models import User
            result = await session.execute(
                select(User).where(User.email == user_email)
            )
            user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        # JWT users get all permissions
        return APIClient(
            client_name=user.email,
            permissions=["company_check", "route_risk", "alerts", "road_alerts"],
            source="jwt",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication. Provide X-API-Key header or Authorization: Bearer <token>",
    )


def require_permission(permission: str):
    """FastAPI dependency factory — checks API client has required permission."""
    async def _check(client: APIClient = Depends(get_api_client)) -> APIClient:
        if permission not in client.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing required permission: {permission}",
            )
        return client
    return _check


# ---------------------------------------------------------------------------
# Admin router for API key management
# ---------------------------------------------------------------------------

admin_router = APIRouter()


class CreateAPIKeyRequest(BaseModel):
    client_name: str
    permissions: list[str] = []


class CreateAPIKeyResponse(BaseModel):
    id: int | None = None
    client_name: str
    api_key: str
    permissions: list[str]
    message: str = "Store this key securely — it will not be shown again."


@admin_router.post("/api-keys", response_model=CreateAPIKeyResponse)
async def create_api_key(
    body: CreateAPIKeyRequest,
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Create a new API key. Returns the plaintext key once."""
    raw_key = await _manager.create_key(body.client_name, body.permissions)

    # Fetch the id
    key_hash = APIKeyManager._hash_key(raw_key)
    async with async_session() as session:
        result = await session.execute(
            select(APIKey).where(APIKey.key_hash == key_hash)
        )
        db_key = result.scalar_one_or_none()

    return CreateAPIKeyResponse(
        id=db_key.id if db_key else None,
        client_name=body.client_name,
        api_key=raw_key,
        permissions=body.permissions,
    )


@admin_router.get("/api-keys")
async def list_api_keys(
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """List all API keys (hashes hidden)."""
    keys = await _manager.list_keys()
    return {"keys": keys, "total": len(keys)}


@admin_router.delete("/api-keys/{key_id}")
async def deactivate_api_key(
    key_id: int,
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Deactivate an API key."""
    found = await _manager.deactivate_key(key_id)
    if not found:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "deactivated", "key_id": key_id}
