"""Convert SQLAlchemy models to Pydantic-compatible dicts for API responses."""

from src.db.models import Event, Company, Alert, CrimeHotspot, Report, Subscriber, AgentStatus


def event_to_dict(e: Event) -> dict:
    return {
        "id": str(e.id),
        "event_type": e.event_type,
        "severity": (e.severity or "medium").upper(),
        "title": e.title,
        "description": e.description,
        "country_code": e.country_code,
        "location": {
            "country": e.country_code,
            "region": e.region,
            "city": e.city,
            "latitude": e.latitude,
            "longitude": e.longitude,
        } if e.region or e.city else None,
        "date": e.date_occurred.strftime("%Y-%m-%dT%H:%M:%SZ") if e.date_occurred else None,
        "trust_score": e.trust_score or 0.0,
        "is_official": e.source.is_official if e.source else False,
        "is_verified": e.is_verified,
        "source_name": e.source.name if e.source else None,
        "source_url": e.source_url,
        "company_name": e.company.name if e.company else None,
        "tags": e.tags or [],
        "financial_impact_eur": e.financial_impact_eur,
        "cargo_type": e.cargo_type,
        "modus_operandi": e.modus_operandi,
        "location_detail": e.location_detail,
        "vehicle_country": e.vehicle_country,
        "language": e.language,
        "translated_title": e.translated_title,
        "translated_description": e.translated_description,
        "is_translated": e.is_translated or False,
        "intelligence_tier": e.intelligence_tier,
        "intelligence_category": e.intelligence_category,
        "intelligence_confidence": e.intelligence_confidence,
        "created_at": e.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if e.created_at else None,
    }


def company_to_dict(c: Company) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "country_code": c.country_code,
        "company_type": c.company_type,
        "financial_status": (c.financial_status or "unknown").upper(),
        "risk_score": c.risk_score or 0.0,
        "address": None,
        "registry_id": c.registration_number,
        "employee_count": None,
        "fleet_size": None,
        "created_at": c.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if c.created_at else None,
    }


def alert_to_dict(a: Alert) -> dict:
    return {
        "id": str(a.id),
        "alert_type": a.alert_type,
        "severity": (a.severity or "medium").upper(),
        "title": a.title,
        "description": a.description,
        "country_code": a.country_codes[0] if a.country_codes else None,
        "is_active": a.is_active,
        "created_at": a.triggered_at.strftime("%Y-%m-%dT%H:%M:%SZ") if a.triggered_at else None,
        "resolved_at": a.resolved_at.strftime("%Y-%m-%dT%H:%M:%SZ") if a.resolved_at else None,
        "related_event_ids": [str(eid) for eid in (a.related_event_ids or [])],
    }


def report_to_dict(r: Report) -> dict:
    return {
        "id": str(r.id),
        "report_type": r.report_type,
        "status": r.status,
        "language": r.language,
        "countries": r.countries or [],
        "period_start": str(r.period_start) if r.period_start else None,
        "period_end": str(r.period_end) if r.period_end else None,
        "file_path": r.file_path,
        "file_size_bytes": None,
        "created_at": r.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if r.created_at else None,
        "completed_at": r.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if r.created_at else None,
    }


def subscriber_to_dict(s: Subscriber) -> dict:
    return {
        "id": str(s.id),
        "company_name": s.company_name,
        "email": s.contact_email,
        "tier": s.subscription_tier,
        "countries": s.subscribed_countries or [],
        "language": s.language_preference,
        "is_active": s.is_active,
        "created_at": s.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if s.created_at else None,
    }


def hotspot_to_map_dict(h: CrimeHotspot) -> dict:
    return {
        "latitude": h.latitude,
        "longitude": h.longitude,
        "event_count": h.event_count,
        "severity": (h.severity or "medium").upper(),
        "event_type": h.hotspot_type,
        "radius_km": h.radius_km,
        "label": h.region,
    }
