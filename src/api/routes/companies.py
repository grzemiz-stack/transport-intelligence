"""Endpointy REST API do zarzadzania danymi firm transportowych."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user
from src.api.schemas import (
    CompanyAtRiskResponse, CompanyDetailResponse, CompanyListResponse,
    CompanyResponse, CompanyTimelineResponse, EarlyWarningsListResponse,
    EarlyWarningResponse, EventResponse, InsolvencyAnalysisResponse,
    VATCheckResponse,
)
from src.api.serializers import company_to_dict, event_to_dict
from src.db.models import User
from src.db.postgres import get_session
from src.db.queries import (
    get_companies, get_companies_at_risk, get_company_by_id,
    get_company_events, get_company_financials,
)

router = APIRouter()


@router.get("/at-risk", response_model=CompanyAtRiskResponse)
async def companies_at_risk(db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    at_risk = await get_companies_at_risk(db)
    return CompanyAtRiskResponse(
        total=len(at_risk),
        companies=[CompanyResponse(**company_to_dict(c)) for c in at_risk],
    )


@router.get("/", response_model=CompanyListResponse)
async def list_companies(
    country_code: str | None = None,
    company_type: str | None = None,
    financial_status: str | None = None,
    risk_score_min: float | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    companies, total = await get_companies(
        db, country_code=country_code, company_type=company_type,
        financial_status=financial_status, risk_score_min=risk_score_min,
        limit=limit, offset=offset,
    )
    return CompanyListResponse(
        total=total, limit=limit, offset=offset,
        companies=[CompanyResponse(**company_to_dict(c)) for c in companies],
    )


@router.get("/{company_id}/insolvency-analysis", response_model=InsolvencyAnalysisResponse)
async def insolvency_analysis(
    company_id: str,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Pelna analiza upadlosci firmy — premium product."""
    company = await get_company_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    from src.analytics.insolvency_analyzer import InsolvencyAnalyzer
    analyzer = InsolvencyAnalyzer()

    # Fetch company events for analysis
    events = await get_company_events(db, company_id)
    event_dicts = [
        {
            "date": str(e.date_occurred) if e.date_occurred else "",
            "event_type": e.event_type,
            "severity": (e.severity or "medium").upper(),
            "title": e.title,
            "description": e.description or "",
        }
        for e in events
    ]

    financials = await get_company_financials(db, company_id)
    financials_dict = {
        "financial_status": company.financial_status,
        "risk_score": company.risk_score,
        "company_type": company.company_type,
        "history": [
            {
                "date": str(f.date_occurred) if f.date_occurred else "",
                "metric": f.event_type,
                "value": f.amount_eur or 0,
            }
            for f in financials
        ],
    }

    insolvency_data = {
        "events": event_dicts,
        "financials": financials_dict,
        "date": "",
        "court": "",
        "type": company.financial_status or "",
        "description": "",
    }

    result = await analyzer.analyze_insolvency(
        company_name=company.name,
        country=company.country_code,
        insolvency_data=insolvency_data,
    )
    return InsolvencyAnalysisResponse(**result)


@router.get("/{company_id}/early-warnings", response_model=EarlyWarningsListResponse)
async def early_warnings(
    company_id: str,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Sygnaly ostrzegawcze dla firmy — analiza wzorcow."""
    company = await get_company_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    from src.analytics.insolvency_analyzer import InsolvencyAnalyzer
    analyzer = InsolvencyAnalyzer()

    events = await get_company_events(db, company_id)
    event_dicts = [
        {
            "date": str(e.date_occurred) if e.date_occurred else "",
            "event_type": e.event_type,
            "severity": (e.severity or "medium").upper(),
            "title": e.title,
            "description": e.description or "",
        }
        for e in events
    ]

    warnings = await analyzer.detect_early_warnings(event_dicts)
    return EarlyWarningsListResponse(
        company_id=str(company.id),
        company_name=company.name,
        warnings=[EarlyWarningResponse(**w) for w in warnings],
        total=len(warnings),
    )


@router.get("/{company_id}/vat-check", response_model=VATCheckResponse)
async def check_company_vat(
    company_id: str,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    company = await get_company_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    if not company.vat_id:
        raise HTTPException(status_code=400, detail="Company has no VAT number")

    # Extract country code from VAT (first 2 chars)
    country_code = company.vat_id[:2].upper()
    vat_number = company.vat_id[2:]

    from src.agents.financial.vies_checker import VIESChecker
    checker = VIESChecker()
    result = await checker.check_vat(country_code, vat_number)
    return VATCheckResponse(**result)


@router.get("/{company_id}/timeline", response_model=CompanyTimelineResponse)
async def company_timeline(company_id: str, db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    company = await get_company_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    financials = await get_company_financials(db, company_id)
    events = [
        {
            "date": str(f.date_occurred),
            "type": f.event_type,
            "description": f.description,
        }
        for f in financials
    ]

    return CompanyTimelineResponse(
        company_id=str(company.id), company_name=company.name, events=events,
    )


@router.get("/{company_id}", response_model=CompanyDetailResponse)
async def get_company(company_id: str, db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    company = await get_company_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    financials = await get_company_financials(db, company_id)
    financial_history = [
        {"date": str(f.date_occurred), "metric": f.event_type, "value": f.amount_eur or 0}
        for f in financials
    ]

    related = await get_company_events(db, company_id)
    related_events = [EventResponse(**event_to_dict(e)) for e in related]

    risk_breakdown = {
        "financial_events": min(40, (company.risk_score or 0) * 0.4),
        "operational_events": min(30, (company.risk_score or 0) * 0.3),
        "combined_bonus": 20.0 if (company.risk_score or 0) > 60 else 0.0,
        "total": company.risk_score or 0,
    }

    base = company_to_dict(company)
    return CompanyDetailResponse(
        **base,
        financial_history=financial_history,
        related_events=related_events,
        risk_breakdown=risk_breakdown,
    )
