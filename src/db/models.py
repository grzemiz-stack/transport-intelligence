"""Pelny schemat bazy danych PostgreSQL dla systemu Transport Intelligence.

Modele SQLAlchemy 2.0 (mapped_column, Mapped) z async.
Wszystkie modele maja created_at i updated_at.
Enum klasy jako osobne Python Enum.
Indeksy na kluczowych kolumnach.
Relacje miedzy modelami.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ─────────────────────────────────────────────
# Enum definitions
# ─────────────────────────────────────────────


class EventType(str, enum.Enum):
    """Typ zdarzenia transportowego."""

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


class Severity(str, enum.Enum):
    """Poziom waznosci zdarzenia lub alertu."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class SourceType(str, enum.Enum):
    """Typ zrodla danych."""

    POLICE = "police"
    NEWS = "news"
    FORUM = "forum"
    TELEGRAM = "telegram"
    REDDIT = "reddit"
    ALERTS = "alerts"
    FINANCIAL = "financial"


class CompanyType(str, enum.Enum):
    """Typ firmy transportowej."""

    CARRIER = "carrier"
    FORWARDER = "forwarder"
    MANUFACTURER = "manufacturer"
    LEASING = "leasing"
    INSURANCE = "insurance"
    OTHER = "other"


class FinancialStatus(str, enum.Enum):
    """Status finansowy firmy."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    BANKRUPT = "bankrupt"
    RESTRUCTURING = "restructuring"
    UNKNOWN = "unknown"


class ReportType(str, enum.Enum):
    """Typ raportu."""

    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    ALERT = "alert"
    CUSTOM = "custom"
    DUE_DILIGENCE = "due_diligence"


class ReportStatus(str, enum.Enum):
    """Status raportu w cyklu zycia."""

    DRAFT = "draft"
    GENERATED = "generated"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AlertType(str, enum.Enum):
    """Typ alertu real-time."""

    THEFT_SPIKE = "theft_spike"
    ROUTE_DANGER = "route_danger"
    COMPANY_RISK = "company_risk"
    STRIKE = "strike"
    PAYMENT_WARNING = "payment_warning"
    FINANCIAL_DISTRESS = "financial_distress"


class HotspotType(str, enum.Enum):
    """Typ hotspotu kryminalnego."""

    THEFT_CARGO = "theft_cargo"
    THEFT_FUEL = "theft_fuel"
    THEFT_VEHICLE = "theft_vehicle"
    MIXED = "mixed"


class Trend(str, enum.Enum):
    """Kierunek trendu."""

    RISING = "rising"
    STABLE = "stable"
    DECLINING = "declining"


class CompanyFinancialEventType(str, enum.Enum):
    """Typ zdarzenia finansowego firmy."""

    BANKRUPTCY_FILING = "bankruptcy_filing"
    RESTRUCTURING = "restructuring"
    PAYMENT_DELAY = "payment_delay"
    LICENSE_REVOKED = "license_revoked"
    LICENSE_SUSPENDED = "license_suspended"
    OWNERSHIP_CHANGE = "ownership_change"
    ADDRESS_CHANGE = "address_change"
    DEBT_REGISTERED = "debt_registered"
    DEBT_REMOVED = "debt_removed"


class CorrelationType(str, enum.Enum):
    """Typ korelacji miedzy zdarzeniami."""

    SAME_LOCATION = "same_location"
    SAME_COMPANY = "same_company"
    SAME_TIME_PATTERN = "same_time_pattern"
    SAME_CARGO_TYPE = "same_cargo_type"
    CROSS_COUNTRY_ROUTE = "cross_country_route"
    FINANCIAL_OPERATIONAL = "financial_operational"


class AuditAction(str, enum.Enum):
    """Typ akcji w logu audytowym."""

    COLLECTED = "collected"
    ANONYMIZED = "anonymized"
    PII_REMOVED = "pii_removed"
    LEGAL_FILTERED = "legal_filtered"
    GDPR_REJECTED = "gdpr_rejected"
    COMPANY_NAME_REMOVED = "company_name_removed"
    SOURCE_BLOCKED = "source_blocked"
    MANUAL_REVIEW = "manual_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class LegalReviewReason(str, enum.Enum):
    """Powod skierowania do weryfikacji prawnej."""

    COMPANY_NAMED_UNOFFICIAL_SOURCE = "company_named_unofficial_source"
    HIGH_SEVERITY_UNVERIFIED = "high_severity_unverified"
    POTENTIAL_DEFAMATION = "potential_defamation"
    PII_DETECTED = "pii_detected"
    GDPR_CONCERN = "gdpr_concern"
    CROSS_BORDER_LEGAL = "cross_border_legal"


class LegalReviewStatus(str, enum.Enum):
    """Status weryfikacji prawnej."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class SubscriptionTier(str, enum.Enum):
    """Poziom subskrypcji klienta."""

    BASIC_REPORTS = "basic_reports"
    PREMIUM_ALERTS = "premium_alerts"
    ENTERPRISE_API = "enterprise_api"
    CUSTOM = "custom"


class AgentType(str, enum.Enum):
    """Typ agenta w systemie monitoringu."""

    POLICE = "police"
    NEWS = "news"
    FORUM = "forum"
    TELEGRAM = "telegram"
    REDDIT = "reddit"
    ALERTS = "alerts"
    FINANCIAL = "financial"
    SUPERVISOR = "supervisor"


class AgentStatusEnum(str, enum.Enum):
    """Status agenta."""

    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    RESTARTING = "restarting"


class UserRole(str, enum.Enum):
    """Rola uzytkownika w systemie."""

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


# ─────────────────────────────────────────────
# Base class
# ─────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────


class Source(Base):
    """Zrodlo danych scrapowane przez agentow."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(50))
    url: Mapped[str] = mapped_column(String(2000))
    country_code: Mapped[str] = mapped_column(String(2))
    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scraped: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scrape_interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    total_events_collected: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # relationships
    events: Mapped[list["Event"]] = relationship(back_populates="source")
    company_financials: Mapped[list["CompanyFinancial"]] = relationship(
        back_populates="source"
    )

    __table_args__ = (
        Index("ix_sources_country_code", "country_code"),
        Index("ix_sources_source_type", "source_type"),
    )


class Company(Base):
    """Firma transportowa zidentyfikowana w systemie."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(500))
    company_type: Mapped[str] = mapped_column(String(50), default=CompanyType.OTHER.value)
    country_code: Mapped[str] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(200), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    financial_status: Mapped[str] = mapped_column(
        String(50), default=FinancialStatus.UNKNOWN.value
    )
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    first_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_from_official_source: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # relationships
    events: Mapped[list["Event"]] = relationship(back_populates="company")
    financials: Mapped[list["CompanyFinancial"]] = relationship(
        back_populates="company"
    )
    alerts: Mapped[list["Alert"]] = relationship(back_populates="related_company")

    __table_args__ = (
        Index("ix_companies_country_code", "country_code"),
        Index("ix_companies_financial_status", "financial_status"),
        Index("ix_companies_name", "name"),
    )


class Event(Base):
    """Zdarzenie transportowe (kradziez, uszkodzenie, upadlosc itp.)."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(
        String(20), default=Severity.MEDIUM.value
    )
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_occurred: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_collected: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    country_code: Mapped[str] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id"), nullable=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True
    )
    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_anonymized: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    language: Mapped[str | None] = mapped_column(String(5), nullable=True)
    translated_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    translated_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_translated: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    financial_impact_eur: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    cargo_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    modus_operandi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vehicle_country: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # Intelligence tier classification (1=CRITICAL, 2=HIGH, 3=MEDIUM, 4=LOW)
    intelligence_tier: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    intelligence_category: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    intelligence_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # relationships
    source: Mapped["Source | None"] = relationship(back_populates="events")
    company: Mapped["Company | None"] = relationship(back_populates="events")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="event")
    legal_reviews: Mapped[list["LegalReview"]] = relationship(
        back_populates="event"
    )

    __table_args__ = (
        Index("ix_events_country_code", "country_code"),
        Index("ix_events_event_type", "event_type"),
        Index("ix_events_date_occurred", "date_occurred"),
        Index("ix_events_trust_score", "trust_score"),
        Index("ix_events_severity", "severity"),
        Index("ix_events_source_id", "source_id"),
        Index("ix_events_company_id", "company_id"),
        Index("ix_events_intelligence_tier", "intelligence_tier"),
    )


class Report(Base):
    """Wygenerowany raport zbiorczy."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(500))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    countries: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    language: Mapped[str] = mapped_column(String(5), default="en")
    status: Mapped[str] = mapped_column(
        String(20), default=ReportStatus.DRAFT.value
    )
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_events: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_events: Mapped[int] = mapped_column(Integer, default=0)
    signal_events: Mapped[int] = mapped_column(Integer, default=0)
    disclaimer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(100), default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_reports_report_type", "report_type"),
        Index("ix_reports_status", "status"),
    )


class Alert(Base):
    """Alert real-time o zdarzeniu lub wzorcu."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    alert_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(
        String(20), default=Severity.MEDIUM.value
    )
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_codes: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    region: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    related_event_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    related_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True
    )
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # relationships
    related_company: Mapped["Company | None"] = relationship(
        back_populates="alerts"
    )

    __table_args__ = (
        Index("ix_alerts_is_active", "is_active"),
        Index("ix_alerts_alert_type", "alert_type"),
        Index("ix_alerts_severity", "severity"),
    )


class CrimeHotspot(Base):
    """Hotspot kryminalny — region ze zwiekszona liczba zdarzen."""

    __tablename__ = "crime_hotspots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    country_code: Mapped[str] = mapped_column(String(2))
    region: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float)
    hotspot_type: Mapped[str] = mapped_column(String(50))
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    severity: Mapped[str] = mapped_column(
        String(20), default=Severity.MEDIUM.value
    )
    peak_hours: Mapped[str | None] = mapped_column(String(50), nullable=True)
    common_targets: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    trend: Mapped[str] = mapped_column(String(20), default=Trend.STABLE.value)
    last_calculated: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_crime_hotspots_country_code", "country_code"),
        Index("ix_crime_hotspots_hotspot_type", "hotspot_type"),
        Index("ix_crime_hotspots_severity", "severity"),
    )


class CompanyFinancial(Base):
    """Zdarzenie finansowe dotyczace firmy (upadlosc, zaleglosc, zmiana)."""

    __tablename__ = "company_financials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id")
    )
    event_type: Mapped[str] = mapped_column(String(50))
    date_occurred: Mapped[date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id"), nullable=True
    )
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    amount_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # relationships
    company: Mapped["Company"] = relationship(back_populates="financials")
    source: Mapped["Source | None"] = relationship(
        back_populates="company_financials"
    )

    __table_args__ = (
        Index("ix_company_financials_company_id", "company_id"),
        Index("ix_company_financials_event_type", "event_type"),
    )


class EventCorrelation(Base):
    """Korelacja miedzy zdarzeniami — wykryte wzorce i powiazania."""

    __tablename__ = "event_correlations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    correlation_type: Mapped[str] = mapped_column(String(50))
    event_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    company_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    country_codes: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    pattern_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_event_correlations_correlation_type", "correlation_type"),
        Index("ix_event_correlations_is_active", "is_active"),
    )


class AuditLog(Base):
    """Log audytowy kazdego przetworzenia danych — wymog GDPR art. 30.

    Rejestruje co zostalo przetworzone, jaka akcje podjeto, dlaczego,
    oraz hash oryginalnych danych (bez przechowywania samych danych).
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text)
    original_data_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    processed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # relationships
    event: Mapped["Event | None"] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_log_event_id", "event_id"),
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_timestamp", "timestamp"),
    )


class LegalReview(Base):
    """Eventy skierowane do manualnej weryfikacji prawnej.

    Zdarzenia ktore przeszly pipeline ale wymagaja dodatkowej oceny prawnika
    przed publikacja lub dalszym przetwarzaniem.
    """

    __tablename__ = "legal_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id")
    )
    reason: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(20), default=LegalReviewStatus.PENDING.value
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auto_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # relationships
    event: Mapped["Event"] = relationship(back_populates="legal_reviews")

    __table_args__ = (
        Index("ix_legal_reviews_status", "status"),
        Index("ix_legal_reviews_event_id", "event_id"),
    )


class Subscriber(Base):
    """Klient subskrybujacy raporty i alerty."""

    __tablename__ = "subscribers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_name: Mapped[str] = mapped_column(String(500))
    contact_email: Mapped[str] = mapped_column(String(300))
    subscription_tier: Mapped[str] = mapped_column(String(50))
    subscribed_countries: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    language_preference: Mapped[str] = mapped_column(String(5), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    subscription_start: Mapped[date] = mapped_column(Date)
    subscription_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    monthly_fee_eur: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_subscribers_is_active", "is_active"),
    )


class AgentStatus(Base):
    """Status agenta scrapujacego — monitoring i metryki."""

    __tablename__ = "agent_statuses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    country_code: Mapped[str] = mapped_column(String(2))
    agent_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(20), default=AgentStatusEnum.STOPPED.value
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    events_collected_today: Mapped[int] = mapped_column(Integer, default=0)
    errors_today: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uptime_seconds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_agent_statuses_country_code", "country_code"),
        Index("ix_agent_statuses_status", "status"),
        Index(
            "ix_agent_statuses_country_agent",
            "country_code",
            "agent_type",
            unique=True,
        ),
    )


class User(Base):
    """Uzytkownik systemu Transport Intelligence."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(300), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.VIEWER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_users_email", "email", unique=True),
    )


class APIKey(Base):
    """Klucz API do integracji machine-to-machine (np. CargoControl)."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(128))
    client_name: Mapped[str] = mapped_column(String(100))
    permissions: Mapped[dict] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    last_used: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_api_keys_key_hash", "key_hash"),
        Index("ix_api_keys_is_active", "is_active"),
    )
