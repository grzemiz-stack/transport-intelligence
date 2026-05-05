"""Endpointy REST API do generowania i pobierania raportow."""

import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user, require_role
from src.api.schemas import (
    DueDiligenceReportRequest,
    InsolvencyReportRequest,
    ReportGenerateRequest,
    ReportGenerateResponse,
    ReportListResponse,
    ReportResponse,
    ScheduledJobResponse,
)
from src.api.serializers import report_to_dict
from src.db.models import User, UserRole
from src.db.postgres import get_session
from src.db.queries import get_reports, get_report_by_id

router = APIRouter()

# Static schedule data (no dedicated DB table for schedules yet)
_SCHEDULES: list[dict] = [
    {
        "job_id": "biweekly_en",
        "type": "biweekly",
        "countries": ["PL", "DE", "CZ", "SK"],
        "language": "en",
        "last_run": "2026-03-17T06:00:00Z",
        "next_run": "2026-03-31T06:00:00Z",
    },
    {
        "job_id": "monthly_pl",
        "type": "monthly",
        "countries": ["PL", "DE", "CZ", "SK", "AT", "HU"],
        "language": "pl",
        "last_run": "2026-03-01T06:00:00Z",
        "next_run": "2026-04-01T06:00:00Z",
    },
    {
        "job_id": "alert_check",
        "type": "alert_check",
        "countries": [],
        "language": "",
        "last_run": "2026-03-19T10:15:00Z",
        "next_run": "2026-03-19T10:30:00Z",
    },
    {
        "job_id": "sales_pl",
        "type": "sales",
        "countries": ["PL", "DE", "CZ", "SK", "AT", "HU"],
        "language": "pl",
        "last_run": "2026-03-15T06:00:00Z",
        "next_run": "2026-04-01T06:00:00Z",
    },
]


@router.get("/schedule", response_model=list[ScheduledJobResponse])
async def get_report_schedule(_user: User = Depends(get_current_user)):
    """Lista zaplanowanych raportow."""
    return [ScheduledJobResponse(**s) for s in _SCHEDULES]


@router.get("/", response_model=ReportListResponse)
async def list_reports(
    report_type: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Lista wygenerowanych raportow z filtrami."""
    reports = await get_reports(db, report_type=report_type, status=status)

    # Additional date filtering in Python (simple approach)
    if date_from:
        reports = [
            r for r in reports
            if r.created_at and r.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") >= date_from
        ]
    if date_to:
        reports = [
            r for r in reports
            if r.created_at and r.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") <= date_to
        ]

    return ReportListResponse(
        total=len(reports),
        reports=[ReportResponse(**report_to_dict(r)) for r in reports],
    )


@router.post("/generate", response_model=ReportGenerateResponse)
async def generate_report(
    body: ReportGenerateRequest,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST)),
):
    """Trigger generowania raportu (async background task)."""
    from src.reports.live_generator import LiveReportGenerator

    report_id = f"rpt-{uuid.uuid4().hex[:8]}"

    async def _generate():
        gen = LiveReportGenerator()
        try:
            if body.report_type.value == "biweekly":
                await gen.generate_biweekly_report(
                    countries=body.countries, language=body.language,
                )
            elif body.report_type.value == "monthly":
                await gen.generate_monthly_report(
                    countries=body.countries, language=body.language,
                )
            elif body.report_type.value == "sales":
                await gen.generate_sales_report(
                    countries=body.countries, language=body.language,
                )
            elif body.report_type.value == "insolvency":
                # Insolvency report — use first country
                await gen.generate_insolvency_report(
                    company_name="",
                    country=body.countries[0] if body.countries else "PL",
                )
            elif body.report_type.value == "due_diligence":
                from src.analytics.company_investigator import CompanyInvestigator
                investigator = CompanyInvestigator()
                await investigator.generate_due_diligence_report(
                    company_name="",
                    country=body.countries[0] if body.countries else "PL",
                )
            elif body.report_type.value == "alert":
                # alert report requires alert_id — use first country as fallback id
                pass
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Report generation failed: %s", e, exc_info=True)

    background_tasks.add_task(_generate)

    return ReportGenerateResponse(
        report_id=report_id,
        status="generating",
        message=f"Report generation started: {body.report_type.value} for {', '.join(body.countries)} in {body.language}",
    )


@router.post("/generate-sales", response_model=ReportGenerateResponse)
async def generate_sales_report(
    body: ReportGenerateRequest,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Trigger generowania sales intelligence report (ADMIN only)."""
    from src.reports.live_generator import LiveReportGenerator

    report_id = f"rpt-{uuid.uuid4().hex[:8]}"

    async def _generate():
        gen = LiveReportGenerator()
        try:
            await gen.generate_sales_report(
                countries=body.countries, language=body.language,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Sales report generation failed: %s", e, exc_info=True)

    background_tasks.add_task(_generate)

    return ReportGenerateResponse(
        report_id=report_id,
        status="generating",
        message=f"Sales report generation started for {', '.join(body.countries)} in {body.language}",
    )


@router.post("/generate-insolvency", response_model=ReportGenerateResponse)
async def generate_insolvency_report(
    body: InsolvencyReportRequest,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST)),
):
    """Generuj raport o upadlosci firmy — premium product."""
    report_id = f"rpt-{uuid.uuid4().hex[:8]}"

    async def _generate():
        from src.analytics.insolvency_analyzer import InsolvencyAnalyzer
        analyzer = InsolvencyAnalyzer()
        try:
            insolvency_data = {
                "date": body.insolvency_date,
                "court": body.court,
                "type": body.insolvency_type,
                "description": body.description,
            }
            await analyzer.generate_insolvency_report(
                company_name=body.company_name,
                country=body.country,
                insolvency_data=insolvency_data,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                "Insolvency report generation failed: %s", e, exc_info=True,
            )

    background_tasks.add_task(_generate)

    return ReportGenerateResponse(
        report_id=report_id,
        status="generating",
        message=f"Insolvency report generation started for {body.company_name} ({body.country})",
    )


@router.post("/generate-due-diligence", response_model=ReportGenerateResponse)
async def generate_due_diligence_report(
    body: DueDiligenceReportRequest,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST)),
):
    """Generate due diligence PDF report — background task."""
    report_id = f"rpt-{uuid.uuid4().hex[:8]}"

    async def _generate():
        from src.analytics.company_investigator import CompanyInvestigator
        investigator = CompanyInvestigator()
        try:
            await investigator.generate_due_diligence_report(
                company_name=body.company_name,
                country=body.country,
                vat_number=body.vat_number,
                registration_number=body.registration_number,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                "Due diligence report generation failed: %s", e, exc_info=True,
            )

    background_tasks.add_task(_generate)

    return ReportGenerateResponse(
        report_id=report_id,
        status="generating",
        message=f"Due diligence report started for {body.company_name} ({body.country})",
    )


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Download PDF raportu."""
    report = await get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    file_path = report.file_path
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"PDF file not found on disk: {file_path}",
        )

    filename = os.path.basename(file_path)
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(report_id: str, db: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Szczegoly raportu."""
    report = await get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return ReportResponse(**report_to_dict(report))
