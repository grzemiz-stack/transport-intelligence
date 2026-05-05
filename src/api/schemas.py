"""Pydantic models (schemas) dla Transport Intelligence API."""

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EventTypeEnum(str, Enum):
    THEFT_CARGO = "theft_cargo"
    THEFT_FUEL = "theft_fuel"
    THEFT_VEHICLE = "theft_vehicle"
    DAMAGE = "damage"
    DELAY = "delay"
    STRIKE = "strike"
    PAYMENT_ISSUE = "payment_issue"
    BANKRUPTCY = "bankruptcy"
    RESTRUCTURING = "restructuring"
    LICENSE_REVOKED = "license_revoked"
    ROUTE_CLOSURE = "route_closure"
    OTHER = "other"


class SeverityEnum(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ReportTypeEnum(str, Enum):
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    ALERT = "alert"
    SALES = "sales"
    INSOLVENCY = "insolvency"
    DUE_DILIGENCE = "due_diligence"


class ReportStatusEnum(str, Enum):
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStatusEnum(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    STARTING = "starting"


class FinancialStatusEnum(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    BANKRUPT = "BANKRUPT"
    RESTRUCTURING = "RESTRUCTURING"


class SubscriberTierEnum(str, Enum):
    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------

class LocationSchema(BaseModel):
    country: str | None = None
    region: str | None = None
    city: str | None = None
    road: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class PaginatedMeta(BaseModel):
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class EventResponse(BaseModel):
    id: str
    event_type: str
    severity: str
    title: str
    description: str | None = None
    country_code: str
    location: LocationSchema | None = None
    date: str | None = None
    trust_score: float = 0.0
    is_official: bool = False
    is_verified: bool = False
    source_name: str | None = None
    source_url: str | None = None
    company_name: str | None = None
    tags: list[str] = []
    financial_impact_eur: float | None = None
    cargo_type: str | None = None
    modus_operandi: str | None = None
    location_detail: str | None = None
    vehicle_country: str | None = None
    language: str | None = None
    translated_title: str | None = None
    translated_description: str | None = None
    is_translated: bool = False
    intelligence_tier: int | None = None
    intelligence_category: str | None = None
    intelligence_confidence: float | None = None
    created_at: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "id": "evt-001",
                "event_type": "theft_cargo",
                "severity": "HIGH",
                "title": "Cargo theft on A2 near Poznan",
                "description": "Electronics cargo stolen from parked truck at rest area.",
                "country_code": "PL",
                "location": {
                    "country": "Poland",
                    "region": "Wielkopolska",
                    "city": "Poznan",
                    "road": "A2",
                    "latitude": 52.4064,
                    "longitude": 16.9252,
                },
                "date": "2026-03-15T03:20:00Z",
                "trust_score": 0.92,
                "is_official": True,
                "is_verified": True,
                "source_name": "Policja Wielkopolska",
                "source_url": "https://policja.gov.pl/wlkp/12345",
                "company_name": "TransEuropa GmbH",
                "tags": ["nocna", "autostrada", "elektronika"],
                "financial_impact_eur": 85000.0,
                "language": "pl",
                "created_at": "2026-03-15T06:00:00Z",
            }],
        },
    }


class EventListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    filters_applied: dict[str, Any] = {}
    events: list[EventResponse]


class EventStatsResponse(BaseModel):
    total_events: int
    per_country: dict[str, int]
    per_event_type: dict[str, int]
    per_severity: dict[str, int]
    daily_counts_30d: list[dict[str, Any]]
    top_hotspots: list[dict[str, Any]]


class EventTimelineResponse(BaseModel):
    period: str
    grouping: str
    data: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

class ReportResponse(BaseModel):
    id: str
    report_type: str
    status: str
    language: str = "en"
    countries: list[str] = []
    period_start: str | None = None
    period_end: str | None = None
    file_path: str | None = None
    file_size_bytes: int | None = None
    created_at: str | None = None
    completed_at: str | None = None


class ReportListResponse(BaseModel):
    total: int
    reports: list[ReportResponse]


class ReportGenerateRequest(BaseModel):
    report_type: ReportTypeEnum
    countries: list[str] = Field(default_factory=lambda: ["PL", "DE", "CZ"])
    language: str = "en"

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "report_type": "biweekly",
                "countries": ["PL", "DE", "CZ", "SK"],
                "language": "en",
            }],
        },
    }


class ReportGenerateResponse(BaseModel):
    report_id: str
    status: str = "generating"
    message: str = "Report generation started"


class ScheduledJobResponse(BaseModel):
    job_id: str
    type: str
    countries: list[str] = []
    language: str = ""
    last_run: str | None = None
    next_run: str | None = None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardOverview(BaseModel):
    events_today: int
    events_this_week: int
    events_this_month: int
    events_by_severity: dict[str, int]
    active_alerts_count: int
    agents_summary: dict[str, int]
    top_countries: list[dict[str, Any]]
    latest_events: list[EventResponse]


class MapHotspot(BaseModel):
    latitude: float
    longitude: float
    event_count: int
    severity: str
    event_type: str
    radius_km: float = 30.0
    label: str = ""


class DashboardMapData(BaseModel):
    hotspots: list[MapHotspot]
    active_alerts: list[dict[str, Any]]
    event_density_per_country: dict[str, int]


class DashboardTrends(BaseModel):
    period_days: int = 90
    daily_counts: list[dict[str, Any]]
    per_event_type: dict[str, list[dict[str, Any]]]
    per_country: dict[str, list[dict[str, Any]]]
    week_over_week: list[dict[str, Any]]


class DashboardFinancial(BaseModel):
    companies_at_risk: list[dict[str, Any]]
    recent_bankruptcies: list[dict[str, Any]]
    recent_license_revocations: list[dict[str, Any]]
    payment_issues_trend: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class AgentInfo(BaseModel):
    agent_type: str
    status: str
    last_heartbeat: str | None = None
    events_today: int = 0
    errors_today: int = 0


class CountryAgentStatus(BaseModel):
    country_code: str
    country_name: str
    supervisor_status: str
    agents: list[AgentInfo]


class AgentStatusResponse(BaseModel):
    summary: dict[str, int]
    countries: list[CountryAgentStatus]


class AgentHealthResponse(BaseModel):
    total_agents: int
    healthy: int
    unhealthy: int
    issues: list[dict[str, Any]]


class AgentLogEntry(BaseModel):
    timestamp: str
    country_code: str
    agent_type: str
    level: str
    message: str


class AgentActionResponse(BaseModel):
    country_code: str
    action: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

class CompanyResponse(BaseModel):
    id: str
    name: str
    country_code: str
    company_type: str | None = None
    financial_status: str = "OK"
    risk_score: float = 0.0
    address: str | None = None
    registry_id: str | None = None
    employee_count: int | None = None
    fleet_size: int | None = None
    created_at: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "id": "comp-001",
                "name": "TransEuropa GmbH",
                "country_code": "DE",
                "company_type": "carrier",
                "financial_status": "OK",
                "risk_score": 15.0,
                "address": "Industriestr. 42, 40210 Duesseldorf",
                "registry_id": "HRB 123456",
                "employee_count": 320,
                "fleet_size": 180,
            }],
        },
    }


class CompanyDetailResponse(CompanyResponse):
    financial_history: list[dict[str, Any]] = []
    related_events: list[EventResponse] = []
    risk_breakdown: dict[str, Any] = {}


class CompanyListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    companies: list[CompanyResponse]


class CompanyAtRiskResponse(BaseModel):
    total: int
    companies: list[CompanyResponse]


class CompanyTimelineResponse(BaseModel):
    company_id: str
    company_name: str
    events: list[dict[str, Any]]


class VATCheckResponse(BaseModel):
    valid: bool
    country_code: str
    vat_number: str
    company_name: str = ""
    company_address: str = ""
    request_date: str = ""


class InsolvencyAnalysisResponse(BaseModel):
    company_name: str
    country: str
    analyzed_at: str = ""
    executive_summary: str = ""
    causes: dict[str, Any] = {}
    payment_chain: dict[str, Any] = {}
    early_warnings: list[dict[str, Any]] = []
    market_impact: dict[str, Any] = {}
    domino_effect: dict[str, Any] = {}
    lessons: list[str] = []
    recommendations: dict[str, Any] = {}
    confidence_score: float = 0.0
    news_articles_found: int = 0


class EarlyWarningResponse(BaseModel):
    signal: str
    confidence: float = 0.0
    source: str = ""
    description: str = ""
    event_count: int = 0
    first_seen: str = ""


class EarlyWarningsListResponse(BaseModel):
    company_id: str
    company_name: str
    warnings: list[EarlyWarningResponse]
    total: int


class InsolvencyReportRequest(BaseModel):
    company_name: str
    country: str
    insolvency_date: str = ""
    court: str = ""
    insolvency_type: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class AlertResponse(BaseModel):
    id: str
    alert_type: str
    severity: str
    title: str
    description: str | None = None
    country_code: str | None = None
    is_active: bool = True
    created_at: str | None = None
    resolved_at: str | None = None
    related_event_ids: list[str] = []

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "id": "alert-001",
                "alert_type": "theft_cluster",
                "severity": "HIGH",
                "title": "Theft cluster detected near Poznan A2",
                "description": "4 cargo theft incidents within 30km radius in last 7 days.",
                "country_code": "PL",
                "is_active": True,
                "created_at": "2026-03-18T10:00:00Z",
                "related_event_ids": ["evt-001", "evt-003", "evt-007", "evt-012"],
            }],
        },
    }


class AlertListResponse(BaseModel):
    total: int
    alerts: list[AlertResponse]


class AlertResolveRequest(BaseModel):
    resolution_note: str = ""


class AlertStatsResponse(BaseModel):
    active_per_severity: dict[str, int]
    per_country: dict[str, int]
    average_resolution_hours: float
    total_active: int
    total_resolved: int


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------

class SubscriberCreate(BaseModel):
    company_name: str
    email: str
    tier: SubscriberTierEnum = SubscriberTierEnum.STANDARD
    countries: list[str] = Field(default_factory=lambda: ["PL", "DE"])
    language: str = "en"

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "company_name": "Acme Logistics GmbH",
                "email": "alerts@acme-logistics.de",
                "tier": "premium",
                "countries": ["DE", "PL", "CZ", "AT"],
                "language": "de",
            }],
        },
    }


class SubscriberUpdate(BaseModel):
    company_name: str | None = None
    email: str | None = None
    tier: SubscriberTierEnum | None = None
    countries: list[str] | None = None
    language: str | None = None


class SubscriberResponse(BaseModel):
    id: str
    company_name: str
    email: str
    tier: str
    countries: list[str]
    language: str
    is_active: bool = True
    created_at: str | None = None


class SubscriberListResponse(BaseModel):
    total: int
    subscribers: list[SubscriberResponse]


# ---------------------------------------------------------------------------
# Integration API
# ---------------------------------------------------------------------------

class CompanyCheckAlert(BaseModel):
    type: str
    severity: str
    message: str
    details: dict[str, Any] = {}


class CompanyCheckResult(BaseModel):
    company_name: str
    country: str | None = None
    found_in_db: bool = False
    company_id: str | None = None
    financial_status: str | None = None
    tax_id: str | None = None
    risk_score: float = 0.0
    risk_level: str = "unknown"
    related_events_count: int = 0
    recent_events_90d: int = 0
    alerts: list[CompanyCheckAlert] = []
    vat_check: dict[str, Any] | None = None
    recommendation: str = ""
    checked_at: str = ""


class CompanyCheckResponse(BaseModel):
    status: str = "ok"
    results: list[CompanyCheckResult] = []


class RouteHotspot(BaseModel):
    latitude: float
    longitude: float
    event_count: int
    event_types: list[str] = []
    severity: str = "medium"
    radius_km: float = 25.0


class RouteRiskResponse(BaseModel):
    status: str = "ok"
    route: dict[str, Any] = {}
    estimated_distance_km: float = 0.0
    hotspots: list[RouteHotspot] = []
    active_alerts: list[dict[str, Any]] = []
    road_alerts: list[dict[str, Any]] = []
    safe_parking: list[dict[str, Any]] = []
    recommendations: list[str] = []


class AlertSubscribeRequest(BaseModel):
    callback_url: str
    api_key: str = ""
    countries: list[str] = []
    alert_types: list[str] = []
    min_severity: str = "medium"


class AlertsFeedResponse(BaseModel):
    status: str = "ok"
    since: str = ""
    alerts: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    total: int = 0


class BulkCompanyCheckRequest(BaseModel):
    companies: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Deep Investigation (Due Diligence)
# ---------------------------------------------------------------------------

class DeepInvestigateRequest(BaseModel):
    company_name: str = Field(..., min_length=2)
    country: str = Field(..., min_length=2, max_length=2)
    vat_number: str | None = None
    registration_number: str | None = None  # KRS, HRB, etc.


class DeepInvestigateResponse(BaseModel):
    status: str = "ok"
    company_name: str = ""
    country: str = ""
    investigated_at: str = ""
    overall_risk: dict[str, Any] = {}
    basic_info: dict[str, Any] = {}
    licenses: list[dict[str, Any]] = []
    financial_health: dict[str, Any] = {}
    risk_signals: list[dict[str, Any]] = []
    related_companies: list[dict[str, Any]] = []
    board_members: list[dict[str, Any]] = []
    transport_events: dict[str, Any] = {}
    media_sentiment: dict[str, Any] = {}
    ai_recommendation: dict[str, Any] = {}
    sources_consulted: list[dict[str, Any]] = []
    confidence_score: float = 0.0


class DueDiligenceReportRequest(BaseModel):
    company_name: str
    country: str
    vat_number: str | None = None
    registration_number: str | None = None
