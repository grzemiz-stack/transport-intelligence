"""LiveReportGenerator — generuje raporty PDF z danych live z PostgreSQL.

Pobiera zdarzenia, alerty, firmy, hotspoty i korelacje z bazy,
buduje sekcje przez ReportSectionBuilder i renderuje PDF przez PdfRenderer.
"""

import logging
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.db.models import (
    Alert,
    Company,
    CompanyFinancial,
    CrimeHotspot,
    Event,
    EventCorrelation,
    Report,
)
from src.db.postgres import async_session
from src.reports.disclaimer import DisclaimerGenerator
from src.reports.pdf_renderer import PdfRenderer
from src.reports.report_sections import ReportSectionBuilder

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "reports" / "output"


class LiveReportGenerator:
    """Generuje raporty PDF z prawdziwych danych z PostgreSQL."""

    def __init__(self):
        self._sections = ReportSectionBuilder()
        self._disclaimer = DisclaimerGenerator()
        self._pdf = PdfRenderer()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # Lazy init for PatternAnalyzer (only when needed)
        self._analyzer = None

    def _get_analyzer(self):
        if self._analyzer is None:
            from src.analytics.pattern_analyzer import PatternAnalyzer
            self._analyzer = PatternAnalyzer()
        return self._analyzer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_biweekly_report(
        self,
        countries: list[str] | None = None,
        language: str = "pl",
    ) -> str:
        """Generuje raport 2-tygodniowy.

        Returns: sciezka do wygenerowanego pliku PDF.
        """
        now = datetime.utcnow()
        period_end = now.date()
        period_start = period_end - timedelta(days=14)

        async with async_session() as session:
            events = await self._fetch_events(session, period_start, period_end, countries)
            prev_events = await self._fetch_events(
                session,
                period_start - timedelta(days=14),
                period_start,
                countries,
            )
            hotspots = await self._fetch_hotspots(session, countries)
            alerts = await self._fetch_alerts(session, period_start, period_end, countries)
            correlations = await self._fetch_correlations(session, period_start, period_end, countries)
            companies_at_risk = await self._fetch_companies_at_risk(session, countries)

            # Convert ORM to dicts
            event_dicts = [self._event_to_dict(e) for e in events]
            prev_dicts = [self._event_to_dict(e) for e in prev_events]

            # Build sections
            context = self._build_context(
                event_dicts=event_dicts,
                prev_dicts=prev_dicts,
                hotspots=hotspots,
                alerts=alerts,
                correlations=correlations,
                companies_at_risk=companies_at_risk,
                countries=countries or self._extract_countries(events),
                report_type="biweekly",
                period_start=period_start,
                period_end=period_end,
                language=language,
            )

            # Render PDF
            report_id = uuid.uuid4()
            filename = f"biweekly_{period_start.isoformat()}_{period_end.isoformat()}_{report_id.hex[:8]}.pdf"
            pdf_path = str(OUTPUT_DIR / filename)
            self._pdf.render(context, pdf_path)

            # Save report record
            await self._save_report_record(
                session,
                report_id=report_id,
                report_type="biweekly",
                title=context["title"],
                period_start=period_start,
                period_end=period_end,
                countries=context["countries"],
                language=language,
                file_path=pdf_path,
                total_events=len(events),
                confirmed_events=len(context["confirmed"].events),
                signal_events=len(context["signals"].events),
                disclaimer_text=context.get("disclaimer", ""),
            )

        logger.info("Biweekly report generated: %s (%d events)", pdf_path, len(events))
        return pdf_path

    async def generate_monthly_report(
        self,
        countries: list[str] | None = None,
        language: str = "pl",
    ) -> str:
        """Generuje raport miesieczny — bardziej szczegolowy.

        Returns: sciezka do wygenerowanego pliku PDF.
        """
        now = datetime.utcnow()
        period_end = now.date()
        period_start = period_end - timedelta(days=30)

        async with async_session() as session:
            events = await self._fetch_events(session, period_start, period_end, countries)
            prev_events = await self._fetch_events(
                session,
                period_start - timedelta(days=30),
                period_start,
                countries,
            )
            hotspots = await self._fetch_hotspots(session, countries)
            alerts = await self._fetch_alerts(session, period_start, period_end, countries)
            correlations = await self._fetch_correlations(session, period_start, period_end, countries)
            companies_at_risk = await self._fetch_companies_at_risk(session, countries)

            event_dicts = [self._event_to_dict(e) for e in events]
            prev_dicts = [self._event_to_dict(e) for e in prev_events]

            context = self._build_context(
                event_dicts=event_dicts,
                prev_dicts=prev_dicts,
                hotspots=hotspots,
                alerts=alerts,
                correlations=correlations,
                companies_at_risk=companies_at_risk,
                countries=countries or self._extract_countries(events),
                report_type="monthly",
                period_start=period_start,
                period_end=period_end,
                language=language,
            )

            # Monthly extras
            from src.reports.generator import ReportGenerator
            gen = ReportGenerator()
            context["recommendations"] = gen._build_recommendations(
                event_dicts, context.get("correlations", []),
            )

            report_id = uuid.uuid4()
            filename = f"monthly_{period_start.isoformat()}_{period_end.isoformat()}_{report_id.hex[:8]}.pdf"
            pdf_path = str(OUTPUT_DIR / filename)
            self._pdf.render(context, pdf_path)

            await self._save_report_record(
                session,
                report_id=report_id,
                report_type="monthly",
                title=context["title"],
                period_start=period_start,
                period_end=period_end,
                countries=context["countries"],
                language=language,
                file_path=pdf_path,
                total_events=len(events),
                confirmed_events=len(context["confirmed"].events),
                signal_events=len(context["signals"].events),
                disclaimer_text=context.get("disclaimer", ""),
            )

        logger.info("Monthly report generated: %s (%d events)", pdf_path, len(events))
        return pdf_path

    async def generate_alert_report(
        self,
        alert_id: str,
        language: str = "pl",
    ) -> str:
        """Generuje raport dla konkretnego alertu.

        Returns: sciezka do wygenerowanego pliku PDF.
        """
        async with async_session() as session:
            # Fetch alert
            result = await session.execute(
                select(Alert).where(Alert.id == alert_id)
            )
            alert = result.scalar_one_or_none()
            if not alert:
                raise ValueError(f"Alert {alert_id} not found")

            # Fetch related events
            related_events = []
            if alert.related_event_ids:
                ev_result = await session.execute(
                    select(Event)
                    .options(joinedload(Event.source), joinedload(Event.company))
                    .where(Event.id.in_(alert.related_event_ids))
                )
                related_events = ev_result.unique().scalars().all()

            # Build context
            alert_dict = {
                "id": str(alert.id),
                "alert_type": alert.alert_type,
                "severity": (alert.severity or "high").upper(),
                "title": alert.title,
                "description": alert.description,
                "country_codes": alert.country_codes or [],
                "region": alert.region,
                "triggered_at": (
                    alert.triggered_at.strftime("%Y-%m-%d %H:%M UTC")
                    if alert.triggered_at else ""
                ),
            }

            related_dicts = [self._event_to_dict(e) for e in related_events]

            from src.reports.generator import ReportGenerator
            gen = ReportGenerator()
            recommended_actions = gen._build_alert_actions(alert_dict, related_dicts)

            disclaimer = self._disclaimer.generate_disclaimer(
                "alert", alert.country_codes or [], language,
            )

            context = {
                "alert": alert_dict,
                "related_events": related_dicts,
                "severity": alert_dict["severity"],
                "recommended_actions": recommended_actions,
                "disclaimer": disclaimer,
                "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                "year": datetime.utcnow().year,
                "language": language,
            }

            report_id = uuid.uuid4()
            filename = f"alert_{alert_id}_{report_id.hex[:8]}.pdf"
            pdf_path = str(OUTPUT_DIR / filename)
            self._pdf.render_alert(context, pdf_path)

            # Save report record
            await self._save_report_record(
                session,
                report_id=report_id,
                report_type="alert",
                title=f"Alert: {alert.title}",
                period_start=datetime.utcnow().date(),
                period_end=datetime.utcnow().date(),
                countries=alert.country_codes or [],
                language=language,
                file_path=pdf_path,
                total_events=len(related_events),
                confirmed_events=0,
                signal_events=0,
                disclaimer_text=disclaimer,
            )

        logger.info("Alert report generated: %s", pdf_path)
        return pdf_path

    # ------------------------------------------------------------------
    # Insolvency Report
    # ------------------------------------------------------------------

    async def generate_insolvency_report(
        self,
        company_name: str,
        country: str,
        insolvency_data: dict | None = None,
    ) -> str:
        """Generuje premium raport o upadlosci firmy transportowej.

        Returns: sciezka do wygenerowanego pliku PDF.
        """
        from src.analytics.insolvency_analyzer import InsolvencyAnalyzer
        analyzer = InsolvencyAnalyzer()
        return await analyzer.generate_insolvency_report(
            company_name=company_name,
            country=country,
            insolvency_data=insolvency_data,
        )

    # ------------------------------------------------------------------
    # Sales / Client Reports
    # ------------------------------------------------------------------

    async def generate_sales_report(
        self,
        period_days: int = 14,
        language: str = "pl",
        countries: list[str] | None = None,
    ) -> str:
        """Generuje sales intelligence report z AI-powered analysis.

        Returns: sciezka do wygenerowanego pliku PDF.
        """
        analyzer = self._get_analyzer()
        now = datetime.utcnow()
        period_end = now.date()
        period_start = period_end - timedelta(days=period_days)

        async with async_session() as session:
            events = await self._fetch_events(session, period_start, period_end, countries)
            await self._fetch_hotspots(session, countries)
            companies_at_risk = await self._fetch_companies_at_risk(session, countries)

            event_dicts = [self._event_to_dict(e) for e in events]

            # --- AI Analyses ---

            # 1. Executive summary
            ai_executive_summary = await analyzer.generate_executive_summary(
                event_dicts, period_days,
            )

            # 2. Country analyses — top 5 countries by event count
            country_groups = self._group_events_by_country(event_dicts)
            top_countries = sorted(
                country_groups.items(), key=lambda x: len(x[1]), reverse=True,
            )[:5]
            ai_country_analyses = []
            for cc, cc_events in top_countries:
                analysis_text = await analyzer.generate_country_analysis(cc_events, cc)
                severity_dist = {}
                for e in cc_events:
                    sev = (e.get("severity") or "MEDIUM").upper()
                    severity_dist[sev] = severity_dist.get(sev, 0) + 1
                regions = {}
                for e in cc_events:
                    r = e.get("region", "")
                    if r:
                        regions[r] = regions.get(r, 0) + 1
                top_locs = sorted(regions, key=regions.get, reverse=True)[:5]
                ai_country_analyses.append({
                    "country_code": cc,
                    "event_count": len(cc_events),
                    "severity_distribution": severity_dist,
                    "top_locations": top_locs,
                    "analysis": analysis_text,
                })

            # 3. Hotspot analyses — top 15 regions
            region_groups = self._group_events_by_region(event_dicts)
            top_regions = sorted(
                region_groups.items(), key=lambda x: len(x[1]), reverse=True,
            )[:15]
            ai_hotspots = []
            for region_key, region_events in top_regions:
                hotspot_result = await analyzer.analyze_hotspot(region_events)
                ai_hotspots.append(hotspot_result)

            # 4. Corridor analyses — top 10
            corridors = self._identify_corridors(event_dicts)
            ai_corridors = []
            for corridor_events in corridors[:10]:
                corridor_result = await analyzer.analyze_corridor(corridor_events)
                ai_corridors.append(corridor_result)

            # 5. Company analyses — top 10 at-risk
            ai_companies = []
            for company in companies_at_risk[:10]:
                c_events = await self._fetch_company_events(session, company.id)
                c_events_dicts = [self._event_to_dict(e) for e in c_events]
                c_financials = await self._fetch_company_financials(session, company.id)
                financials_dict = {
                    "name": company.name,
                    "country_code": company.country_code,
                    "financial_status": company.financial_status,
                    "risk_score": company.risk_score,
                    "company_type": company.company_type,
                    "events": [
                        {
                            "event_type": f.event_type,
                            "date": f.date_occurred.isoformat() if f.date_occurred else "",
                            "description": f.description,
                        }
                        for f in c_financials[:10]
                    ],
                }
                company_result = await analyzer.analyze_company(c_events_dicts, financials_dict)
                ai_companies.append(company_result)

            # Build disclaimer
            all_countries = countries or self._extract_countries(events)
            disclaimer = self._disclaimer.generate_disclaimer("sales", all_countries, language)

            # Build context
            context = {
                "title": "European Transport Risk Report",
                "subtitle": "Biweekly Intelligence Briefing",
                "report_type": "sales",
                "language": language,
                "period": f"{period_start.isoformat()} \u2014 {period_end.isoformat()}",
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "countries": all_countries,
                "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
                "year": now.year,
                "total_events": len(event_dicts),
                "source_count": 50,
                # AI sections
                "ai_executive_summary": ai_executive_summary,
                "ai_country_analyses": ai_country_analyses,
                "ai_hotspots": ai_hotspots,
                "ai_corridors": ai_corridors,
                "ai_companies": ai_companies,
                # Legal
                "disclaimer": disclaimer,
            }

            # Render PDF
            report_id = uuid.uuid4()
            filename = f"sales_{period_start.isoformat()}_{period_end.isoformat()}_{report_id.hex[:8]}.pdf"
            pdf_path = str(OUTPUT_DIR / filename)
            self._pdf.render_sales(context, pdf_path)

            # Save report record
            await self._save_report_record(
                session,
                report_id=report_id,
                report_type="sales",
                title="European Transport Risk Report",
                period_start=period_start,
                period_end=period_end,
                countries=all_countries,
                language=language,
                file_path=pdf_path,
                total_events=len(events),
                confirmed_events=0,
                signal_events=0,
                disclaimer_text=disclaimer,
            )

        logger.info("Sales report generated: %s (%d events)", pdf_path, len(events))
        return pdf_path

    async def generate_client_report(
        self,
        client_name: str,
        client_countries: list[str],
        client_corridors: list[str] | None = None,
        period_days: int = 14,
        language: str = "en",
    ) -> str:
        """Generuje client-specific report filtered to client's countries/corridors.

        Returns: sciezka do wygenerowanego pliku PDF.
        """
        analyzer = self._get_analyzer()
        now = datetime.utcnow()
        period_end = now.date()
        period_start = period_end - timedelta(days=period_days)

        async with async_session() as session:
            events = await self._fetch_events(session, period_start, period_end, client_countries)
            companies_at_risk = await self._fetch_companies_at_risk(session, client_countries)

            event_dicts = [self._event_to_dict(e) for e in events]

            # AI analyses (same flow, filtered)
            ai_executive_summary = await analyzer.generate_executive_summary(
                event_dicts, period_days,
            )

            country_groups = self._group_events_by_country(event_dicts)
            ai_country_analyses = []
            for cc in client_countries:
                cc_events = country_groups.get(cc.upper(), [])
                if not cc_events:
                    continue
                analysis_text = await analyzer.generate_country_analysis(cc_events, cc)
                severity_dist = {}
                for e in cc_events:
                    sev = (e.get("severity") or "MEDIUM").upper()
                    severity_dist[sev] = severity_dist.get(sev, 0) + 1
                regions = {}
                for e in cc_events:
                    r = e.get("region", "")
                    if r:
                        regions[r] = regions.get(r, 0) + 1
                top_locs = sorted(regions, key=regions.get, reverse=True)[:5]
                ai_country_analyses.append({
                    "country_code": cc,
                    "event_count": len(cc_events),
                    "severity_distribution": severity_dist,
                    "top_locations": top_locs,
                    "analysis": analysis_text,
                })

            region_groups = self._group_events_by_region(event_dicts)
            top_regions = sorted(
                region_groups.items(), key=lambda x: len(x[1]), reverse=True,
            )[:15]
            ai_hotspots = []
            for _, region_events in top_regions:
                ai_hotspots.append(await analyzer.analyze_hotspot(region_events))

            corridors = self._identify_corridors(event_dicts)
            ai_corridors = []
            for corridor_events in corridors[:10]:
                ai_corridors.append(await analyzer.analyze_corridor(corridor_events))

            ai_companies = []
            for company in companies_at_risk[:10]:
                c_events = await self._fetch_company_events(session, company.id)
                c_events_dicts = [self._event_to_dict(e) for e in c_events]
                c_financials = await self._fetch_company_financials(session, company.id)
                financials_dict = {
                    "name": company.name,
                    "country_code": company.country_code,
                    "financial_status": company.financial_status,
                    "risk_score": company.risk_score,
                    "company_type": company.company_type,
                    "events": [
                        {
                            "event_type": f.event_type,
                            "date": f.date_occurred.isoformat() if f.date_occurred else "",
                            "description": f.description,
                        }
                        for f in c_financials[:10]
                    ],
                }
                ai_companies.append(await analyzer.analyze_company(c_events_dicts, financials_dict))

            disclaimer = self._disclaimer.generate_disclaimer("sales", client_countries, language)

            context = {
                "title": "Transport Risk Report",
                "subtitle": f"Intelligence Briefing for {client_name}",
                "client_name": client_name,
                "report_type": "sales",
                "language": language,
                "period": f"{period_start.isoformat()} \u2014 {period_end.isoformat()}",
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "countries": client_countries,
                "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
                "year": now.year,
                "total_events": len(event_dicts),
                "source_count": 50,
                "ai_executive_summary": ai_executive_summary,
                "ai_country_analyses": ai_country_analyses,
                "ai_hotspots": ai_hotspots,
                "ai_corridors": ai_corridors,
                "ai_companies": ai_companies,
                "disclaimer": disclaimer,
            }

            report_id = uuid.uuid4()
            filename = f"client_{client_name.replace(' ', '_')}_{period_start.isoformat()}_{report_id.hex[:8]}.pdf"
            pdf_path = str(OUTPUT_DIR / filename)
            self._pdf.render_client(context, pdf_path)

            await self._save_report_record(
                session,
                report_id=report_id,
                report_type="sales",
                title=f"Client Report: {client_name}",
                period_start=period_start,
                period_end=period_end,
                countries=client_countries,
                language=language,
                file_path=pdf_path,
                total_events=len(events),
                confirmed_events=0,
                signal_events=0,
                disclaimer_text=disclaimer,
            )

        logger.info("Client report generated: %s (%d events)", pdf_path, len(events))
        return pdf_path

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    async def _fetch_events(
        self,
        session: AsyncSession,
        period_start: date,
        period_end: date,
        countries: list[str] | None = None,
    ) -> list[Event]:
        q = (
            select(Event)
            .options(joinedload(Event.source), joinedload(Event.company))
            .where(Event.date_occurred >= datetime.combine(period_start, datetime.min.time()))
            .where(Event.date_occurred <= datetime.combine(period_end, datetime.max.time()))
            .order_by(desc(Event.date_occurred))
        )
        if countries:
            q = q.where(Event.country_code.in_([c.upper() for c in countries]))
        result = await session.execute(q)
        return list(result.unique().scalars().all())

    async def _fetch_hotspots(
        self,
        session: AsyncSession,
        countries: list[str] | None = None,
    ) -> list[CrimeHotspot]:
        q = select(CrimeHotspot).order_by(desc(CrimeHotspot.event_count))
        if countries:
            q = q.where(CrimeHotspot.country_code.in_([c.upper() for c in countries]))
        result = await session.execute(q)
        return list(result.scalars().all())

    async def _fetch_alerts(
        self,
        session: AsyncSession,
        period_start: date,
        period_end: date,
        countries: list[str] | None = None,
    ) -> list[Alert]:
        q = (
            select(Alert)
            .where(Alert.is_active.is_(True))
            .where(Alert.triggered_at >= datetime.combine(period_start, datetime.min.time()))
            .order_by(desc(Alert.triggered_at))
        )
        result = await session.execute(q)
        return list(result.scalars().all())

    async def _fetch_correlations(
        self,
        session: AsyncSession,
        period_start: date,
        period_end: date,
        countries: list[str] | None = None,
    ) -> list[EventCorrelation]:
        q = (
            select(EventCorrelation)
            .where(EventCorrelation.is_active.is_(True))
            .where(EventCorrelation.detected_at >= datetime.combine(period_start, datetime.min.time()))
            .order_by(desc(EventCorrelation.confidence))
        )
        result = await session.execute(q)
        return list(result.scalars().all())

    async def _fetch_companies_at_risk(
        self,
        session: AsyncSession,
        countries: list[str] | None = None,
    ) -> list[Company]:
        risk_statuses = ["warning", "critical", "bankrupt", "restructuring"]
        q = (
            select(Company)
            .where(Company.financial_status.in_(risk_statuses))
            .order_by(desc(Company.risk_score))
            .limit(20)
        )
        if countries:
            q = q.where(Company.country_code.in_([c.upper() for c in countries]))
        result = await session.execute(q)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def _build_context(
        self,
        event_dicts: list[dict],
        prev_dicts: list[dict],
        hotspots: list[CrimeHotspot],
        alerts: list[Alert],
        correlations: list[EventCorrelation],
        companies_at_risk: list[Company],
        countries: list[str],
        report_type: str,
        period_start: date,
        period_end: date,
        language: str,
    ) -> dict:
        """Buduje kontekst dla PDF renderera."""
        # Build sections
        confirmed = self._sections.build_confirmed_section(event_dicts, language)
        signals = self._sections.build_signals_section(event_dicts, language)
        financial = self._sections.build_financial_section(event_dicts, language)
        risk_map = self._sections.build_risk_map_section(event_dicts, language)
        trends = self._sections.build_trends_section(event_dicts, prev_dicts or None, language)

        # Convert correlations to dicts
        corr_dicts = [
            {
                "type": c.correlation_type,
                "description": c.description,
                "confidence": c.confidence,
                "event_count": len(c.event_ids) if c.event_ids else 0,
                "event_ids": [str(eid) for eid in (c.event_ids or [])],
                "country_codes": c.country_codes or [],
                "countries": c.country_codes or [],
                "pattern_description": c.pattern_description,
            }
            for c in correlations
        ]

        # Disclaimer
        disclaimer = self._disclaimer.generate_disclaimer(report_type, countries, language)

        # Executive summary
        from src.reports.generator import ReportGenerator
        gen = ReportGenerator()
        executive_summary = gen._build_executive_summary(
            event_dicts, countries, period_start, period_end,
        )
        statistics = gen._build_statistics(event_dicts)

        title_map = {
            "biweekly": {
                "en": "Bi-Weekly Transport Intelligence Report",
                "pl": "Raport Dwutygodniowy Transport Intelligence",
                "de": "Zweiwochentlicher Transport Intelligence Bericht",
            },
            "monthly": {
                "en": "Monthly Transport Intelligence Report",
                "pl": "Raport Miesieczny Transport Intelligence",
                "de": "Monatlicher Transport Intelligence Bericht",
            },
        }
        title = title_map.get(report_type, {}).get(language, title_map.get(report_type, {}).get("en", "Report"))

        return {
            "title": title,
            "report_type": report_type,
            "language": language,
            "period": f"{period_start.isoformat()} \u2014 {period_end.isoformat()}",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "countries": countries,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "year": datetime.utcnow().year,
            # Sections
            "confirmed": confirmed,
            "signals": signals,
            "financial": financial,
            "risk_map": risk_map,
            "trends": trends,
            # Summaries
            "executive_summary": executive_summary,
            "statistics": statistics,
            "correlations": corr_dicts,
            "total_events": len(event_dicts),
            # Legal
            "disclaimer": disclaimer,
            "disclaimer_short": {
                "en": "Based on publicly available information only.",
                "pl": "Na podstawie wylacznie publicznie dostepnych informacji.",
                "de": "Basierend ausschliesslich auf oeffentlich zugaenglichen Informationen.",
            }.get(language, "Based on publicly available information only."),
        }

    # ------------------------------------------------------------------
    # ORM to dict conversion
    # ------------------------------------------------------------------

    def _event_to_dict(self, e: Event) -> dict:
        """Konwertuje Event ORM do dict kompatybilnego z ReportSectionBuilder."""
        is_official = e.source.is_official if e.source else False
        return {
            "id": str(e.id),
            "event_type": e.event_type,
            "severity": (e.severity or "medium").upper(),
            "title": e.title,
            "description": e.description or e.processed_text or e.title,
            "processed_text": e.processed_text,
            "date": e.date_occurred.strftime("%Y-%m-%d") if e.date_occurred else "",
            "date_occurred": e.date_occurred,
            "country_code": e.country_code,
            "region": e.region,
            "location": {
                "country": e.country_code,
                "region": e.region,
                "city": e.city,
                "latitude": e.latitude,
                "longitude": e.longitude,
            },
            "source_name": e.source.name if e.source else "",
            "source_url": e.source_url or "",
            "trust_score": e.trust_score or 0.0,
            "is_official": is_official,
            "is_verified": e.is_verified,
            "company_name": e.company.name if e.company else "",
            "company": e.company.name if e.company else "",
            "tags": e.tags or [],
            "financial_impact_eur": e.financial_impact_eur,
            "language": e.language,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_countries(self, events: list[Event]) -> list[str]:
        """Wyciaga unikalne kody krajow z eventow."""
        return sorted(set(e.country_code for e in events if e.country_code))

    async def _fetch_company_events(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
    ) -> list[Event]:
        """Fetch events associated with a specific company."""
        q = (
            select(Event)
            .options(joinedload(Event.source), joinedload(Event.company))
            .where(Event.company_id == company_id)
            .order_by(desc(Event.date_occurred))
            .limit(30)
        )
        result = await session.execute(q)
        return list(result.unique().scalars().all())

    async def _fetch_company_financials(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
    ) -> list[CompanyFinancial]:
        """Fetch financial records for a specific company."""
        q = (
            select(CompanyFinancial)
            .where(CompanyFinancial.company_id == company_id)
            .order_by(desc(CompanyFinancial.date_occurred))
            .limit(20)
        )
        result = await session.execute(q)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Grouping helpers for sales reports
    # ------------------------------------------------------------------

    @staticmethod
    def _group_events_by_country(event_dicts: list[dict]) -> dict[str, list[dict]]:
        """Group events by country_code."""
        groups: dict[str, list[dict]] = {}
        for e in event_dicts:
            cc = e.get("country_code", "")
            if cc:
                groups.setdefault(cc, []).append(e)
        return groups

    @staticmethod
    def _group_events_by_region(event_dicts: list[dict]) -> dict[str, list[dict]]:
        """Group events by country+region key."""
        groups: dict[str, list[dict]] = {}
        for e in event_dicts:
            cc = e.get("country_code", "")
            region = e.get("region", "")
            if cc and region:
                key = f"{cc}/{region}"
                groups.setdefault(key, []).append(e)
        return groups

    @staticmethod
    def _identify_corridors(event_dicts: list[dict]) -> list[list[dict]]:
        """Identify cross-country corridor patterns from events.

        Groups events that share similar region patterns across countries.
        Returns list of event groups, sorted by size.
        """
        if not event_dicts:
            return []

        # Group by pairs of countries that have events
        country_events: dict[str, list[dict]] = {}
        for e in event_dicts:
            cc = e.get("country_code", "")
            if cc:
                country_events.setdefault(cc, []).append(e)

        countries = sorted(country_events.keys())
        corridors = []

        # Create corridors from country pairs with shared borders / routes
        for i in range(len(countries)):
            for j in range(i + 1, len(countries)):
                c1, c2 = countries[i], countries[j]
                combined = country_events[c1] + country_events[c2]
                if len(combined) >= 3:
                    corridors.append(combined)

        # Sort by event count descending
        corridors.sort(key=len, reverse=True)
        return corridors

    async def _save_report_record(
        self,
        session: AsyncSession,
        report_id: uuid.UUID,
        report_type: str,
        title: str,
        period_start: date,
        period_end: date,
        countries: list[str],
        language: str,
        file_path: str,
        total_events: int,
        confirmed_events: int,
        signal_events: int,
        disclaimer_text: str,
    ):
        """Zapisuje rekord raportu w tabeli reports."""
        report = Report(
            id=report_id,
            report_type=report_type,
            title=title,
            period_start=period_start,
            period_end=period_end,
            countries=countries,
            language=language,
            status="generated",
            file_path=file_path,
            total_events=total_events,
            confirmed_events=confirmed_events,
            signal_events=signal_events,
            disclaimer_text=disclaimer_text,
            generated_by="live_generator",
        )
        session.add(report)
        await session.commit()
        logger.info("Report record saved: %s (%s)", report_id, report_type)
