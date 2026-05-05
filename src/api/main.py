"""Glowna aplikacja FastAPI - punkt wejscia REST API.

Transport Intelligence API — European Transport Risk Intelligence Platform.
Uruchomienie: uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware import RateLimitMiddleware, RequestLoggingMiddleware
from src.api.routes import agents, alerts, auth_routes, companies, dashboard, events, integration, notifications, reports, road_alerts, subscribers, system
from src.api.auth_apikey import admin_router as admin_apikeys_router
from sqlalchemy import text

from src.db.postgres import engine, async_session
from src.db.models import Base

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("Transport Intelligence API starting up...")

    # Verify database connection (tables managed by Alembic migrations)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified.")
    except Exception as e:
        logger.warning("Database not available: %s — running in degraded mode", e)

    logger.info("Startup complete.")
    yield

    # Shutdown
    logger.info("Shutting down...")
    await engine.dispose()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Transport Intelligence API",
    description="European Transport Risk Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=100)

# --- Routers ---
app.include_router(auth_routes.router, prefix="/api/auth", tags=["auth"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(companies.router, prefix="/api/companies", tags=["companies"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(subscribers.router, prefix="/api/subscribers", tags=["subscribers"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(road_alerts.router, prefix="/api/road-alerts", tags=["road-alerts"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(integration.router, prefix="/api/integration", tags=["integration"])
app.include_router(admin_apikeys_router, prefix="/api/admin", tags=["admin"])


@app.get("/", tags=["health"])
async def health():
    return {"status": "ok", "version": "1.0.0", "database": "postgresql"}
