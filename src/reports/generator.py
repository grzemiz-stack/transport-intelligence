"""Generowanie raportow PDF i HTML z danymi o zdarzeniach transportowych.

Wykorzystuje szablony Jinja2 i WeasyPrint do tworzenia profesjonalnych raportow
z wykresami, mapami, podsumowaniami oraz obowiazkowymi sekcjami prawnymi
(disclaimer, podzial na Potwierdzone vs Sygnaly).
"""

import logging
import os
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.reports.disclaimer import DisclaimerGenerator
from src.reports.report_sections import ReportSectionBuilder

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "reports"


class ReportGenerator:
    """Generator raportow zbiorczych z sekcjami prawnymi."""

    def __init__(self):
        self._disclaimer = DisclaimerGenerator()
        self._sections = ReportSectionBuilder()
        self._template_dir = TEMPLATES_DIR
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(self._template_dir)),
            autoescape=True,
        )
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_biweekly(
        self,
        events: list[dict],
        countries: list[str],
        period_start: date,
        period_end: date,
        language: str = "en",
    ) -> str:
        """Generuje raport 2-tygodniowy ze wszystkimi sekcjami prawnymi.

        Zwraca sciezke do wygenerowanego pliku PDF.
        """
        context = self._build_report_context(
            events, countries, "biweekly", period_start, period_end, language,
        )
        html = await self.render_html("biweekly.html", context)
        pdf_bytes = await self.html_to_pdf(html)

        filename = f"biweekly_{period_start.isoformat()}_{period_end.isoformat()}_{uuid.uuid4().hex[:8]}.pdf"
        path = OUTPUT_DIR / filename
        path.write_bytes(pdf_bytes)
        logger.info("Biweekly report generated: %s", path)
        return str(path)

    async def generate_monthly(
        self,
        events: list[dict],
        countries: list[str],
        period_start: date,
        period_end: date,
        language: str = "en",
    ) -> str:
        """Generuje raport miesieczny (bardziej szczegolowy).

        Zwraca sciezke do wygenerowanego pliku PDF.
        """
        context = self._build_report_context(
            events, countries, "monthly", period_start, period_end, language,
        )
        # Monthly extras
        context["recommendations"] = self._build_recommendations(
            events, context.get("correlations", []),
        )
        html = await self.render_html("monthly.html", context)
        pdf_bytes = await self.html_to_pdf(html)

        filename = f"monthly_{period_start.isoformat()}_{period_end.isoformat()}_{uuid.uuid4().hex[:8]}.pdf"
        path = OUTPUT_DIR / filename
        path.write_bytes(pdf_bytes)
        logger.info("Monthly report generated: %s", path)
        return str(path)

    async def generate_alert_report(
        self,
        alert: dict,
        related_events: list[dict],
        language: str = "en",
    ) -> str:
        """Generuje krotki raport alertowy (1-2 strony). Zwraca sciezke do PDF."""
        disclaimer = self._disclaimer.generate_disclaimer("alert", [], language)
        severity = alert.get("severity", "HIGH")
        severity_color = {
            "CRITICAL": "#b71c1c",
            "HIGH": "#e65100",
            "MEDIUM": "#f9a825",
            "LOW": "#2e7d32",
            "INFO": "#1565c0",
        }.get(severity, "#e65100")

        recommended_actions = self._build_alert_actions(alert, related_events)

        context = {
            "alert": alert,
            "related_events": related_events,
            "severity": severity,
            "severity_color": severity_color,
            "recommended_actions": recommended_actions,
            "disclaimer": disclaimer,
            "disclaimer_short": "Based on publicly available information only.",
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "year": datetime.utcnow().year,
            "language": language,
        }
        html = await self.render_html("alert.html", context)
        pdf_bytes = await self.html_to_pdf(html)

        filename = f"alert_{uuid.uuid4().hex[:8]}.pdf"
        path = OUTPUT_DIR / filename
        path.write_bytes(pdf_bytes)
        logger.info("Alert report generated: %s", path)
        return str(path)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    async def render_html(self, template_name: str, context: dict) -> str:
        """Renderuje szablon HTML z danymi (Jinja2)."""
        template = self._jinja_env.get_template(template_name)
        return template.render(**context)

    async def html_to_pdf(self, html: str) -> bytes:
        """Konwertuje HTML do PDF za pomoca WeasyPrint."""
        from weasyprint import HTML  # lazy import

        pdf_bytes = HTML(string=html, base_url=str(self._template_dir)).write_pdf()
        return pdf_bytes

    # ------------------------------------------------------------------
    # Context builders
    # ------------------------------------------------------------------

    def _build_report_context(
        self,
        events: list[dict],
        countries: list[str],
        report_type: str,
        period_start: date,
        period_end: date,
        language: str = "en",
    ) -> dict:
        """Buduje kontekst danych dla szablonu raportu."""
        confirmed = self._sections.build_confirmed_section(events)
        signals = self._sections.build_signals_section(events)
        financial = self._sections.build_financial_section(events)
        risk_map = self._sections.build_risk_map_section(events)
        trends = self._sections.build_trends_section(events)

        disclaimer = self._disclaimer.generate_disclaimer(report_type, countries, language)
        executive_summary = self._build_executive_summary(events, countries, period_start, period_end)
        statistics = self._build_statistics(events)

        # Correlations (import lazily to avoid circular imports)
        correlations = []
        try:
            from src.pipeline.correlator import EventCorrelator
            correlator = EventCorrelator()
            correlations = correlator.correlate(events)
        except Exception:
            logger.debug("Correlator not available, skipping correlations")

        title_map = {
            "biweekly": "Bi-Weekly Transport Intelligence Report",
            "monthly": "Monthly Transport Intelligence Report",
            "alert": "Alert Report",
        }

        return {
            "title": title_map.get(report_type, "Transport Intelligence Report"),
            "report_type": report_type,
            "language": language,
            "period": f"{period_start.isoformat()} \u2014 {period_end.isoformat()}",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "countries": countries,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "year": datetime.utcnow().year,
            # Sections (ReportSection dataclass)
            "confirmed": confirmed,
            "signals": signals,
            "financial": financial,
            "risk_map": risk_map,
            "trends": trends,
            # Summaries
            "executive_summary": executive_summary,
            "statistics": statistics,
            "correlations": correlations,
            "total_events": len(events),
            # Legal
            "disclaimer": disclaimer,
            "disclaimer_short": "Based on publicly available information only. Does not constitute legal advice.",
        }

    def _build_executive_summary(
        self,
        events: list[dict],
        countries: list[str],
        period_start: date,
        period_end: date,
    ) -> dict:
        """Executive Summary: totals, breakdown, hotspots, top companies, trend."""
        total = len(events)

        # Breakdown per type
        type_counts: Counter = Counter(ev.get("event_type", "other") for ev in events)
        # Breakdown per country
        country_counts: Counter = Counter(ev.get("country_code", "??") for ev in events)
        # Breakdown per severity
        severity_counts: Counter = Counter(ev.get("severity", "UNKNOWN") for ev in events)

        # Top 3 hotspots (country+region with most events)
        region_counts: Counter = Counter()
        for ev in events:
            cc = ev.get("country_code", "??")
            loc = ev.get("location", {})
            region = loc.get("region", "") if isinstance(loc, dict) else ""
            key = f"{cc}/{region}" if region else cc
            region_counts[key] += 1
        top_hotspots = [
            {"region": r, "count": c} for r, c in region_counts.most_common(3)
        ]

        # Top 3 companies with financial problems
        financial_types = {"bankruptcy", "restructuring", "payment_issue", "license_revoked"}
        company_issues: Counter = Counter()
        for ev in events:
            if ev.get("event_type") in financial_types:
                company = ev.get("company_name") or ev.get("company")
                if company and ev.get("is_official"):
                    company_issues[company] += 1
        top_financial = [
            {"company": c, "issues": n} for c, n in company_issues.most_common(3)
        ]

        return {
            "total_events": total,
            "period": f"{period_start.isoformat()} \u2014 {period_end.isoformat()}",
            "countries_covered": len(countries),
            "type_breakdown": dict(type_counts.most_common()),
            "country_breakdown": dict(country_counts.most_common()),
            "severity_breakdown": dict(severity_counts.most_common()),
            "top_hotspots": top_hotspots,
            "top_financial_companies": top_financial,
        }

    def _build_statistics(self, events: list[dict]) -> dict:
        """Szczegolowe statystyki: per country, type, severity, trust, sources."""
        country_counts = Counter(ev.get("country_code", "??") for ev in events)
        type_counts = Counter(ev.get("event_type", "other") for ev in events)
        severity_counts = Counter(ev.get("severity", "UNKNOWN") for ev in events)

        trust_scores = [ev.get("trust_score", 0) for ev in events if ev.get("trust_score") is not None]
        avg_trust = round(sum(trust_scores) / len(trust_scores), 2) if trust_scores else 0.0

        source_counts = Counter(ev.get("source_name", "unknown") for ev in events)

        return {
            "events_per_country": dict(country_counts.most_common()),
            "events_per_type": dict(type_counts.most_common()),
            "events_per_severity": dict(severity_counts),
            "average_trust_score": avg_trust,
            "top_sources": dict(source_counts.most_common(10)),
        }

    def _build_recommendations(
        self, events: list[dict], correlations: list[dict],
    ) -> list[str]:
        """Rekomendacje na podstawie hotspotow, trendow, finansowych.

        NEUTRALNY jezyk, bez oskarzen.
        """
        recommendations: list[str] = []

        # Hotspot-based
        region_night: Counter = Counter()
        for ev in events:
            if ev.get("event_type", "").startswith("theft"):
                cc = ev.get("country_code", "??")
                loc = ev.get("location", {})
                region = loc.get("region", "") if isinstance(loc, dict) else ""
                key = f"{cc}/{region}" if region else cc
                region_night[key] += 1
        for region, count in region_night.most_common(3):
            if count >= 3:
                recommendations.append(
                    f"Consider increased security measures for night routes in {region} "
                    f"area ({count} theft incidents recorded)."
                )

        # Fuel theft trend
        fuel_thefts = [ev for ev in events if ev.get("event_type") == "theft_fuel"]
        if len(fuel_thefts) >= 5:
            countries_affected = {ev.get("country_code") for ev in fuel_thefts}
            recommendations.append(
                f"Fuel theft activity elevated ({len(fuel_thefts)} incidents) across "
                f"{', '.join(c for c in countries_affected if c)}. "
                f"Consider anti-siphoning devices and secure parking."
            )

        # Financial signals
        financial_types = {"bankruptcy", "restructuring", "payment_issue"}
        company_issues: Counter = Counter()
        for ev in events:
            if ev.get("event_type") in financial_types:
                company = ev.get("company_name") or ev.get("company")
                if company:
                    company_issues[company] += 1
        for company, count in company_issues.most_common(3):
            if count >= 2:
                recommendations.append(
                    f"Company \"{company}\" shows signs of financial difficulties "
                    f"({count} related events). Exercise due diligence in business dealings."
                )

        # Correlation-based
        for corr in correlations:
            if corr.get("type") == "CROSS_COUNTRY_ROUTE":
                corridor = corr.get("corridor", "unknown corridor")
                countries = ", ".join(corr.get("countries", []))
                recommendations.append(
                    f"Incident pattern detected along {corridor} corridor ({countries}). "
                    f"Monitor shipments on this route."
                )
            elif corr.get("type") == "SAME_TIME_PATTERN":
                day = corr.get("day_of_week", "")
                window = corr.get("time_window", "")
                recommendations.append(
                    f"Recurring pattern: incidents on {day} during {window}. "
                    f"Consider adjusting schedules."
                )

        if not recommendations:
            recommendations.append("No specific recommendations for this reporting period.")

        return recommendations

    def _build_alert_actions(self, alert: dict, related_events: list[dict]) -> list[str]:
        """Recommended actions for an alert report."""
        actions: list[str] = []
        event_type = alert.get("event_type", "")
        severity = alert.get("severity", "MEDIUM")

        if event_type.startswith("theft"):
            actions.append("Notify fleet management and security team immediately.")
            actions.append("File a police report if not already done.")
            actions.append("Review security procedures for the affected route/parking area.")
            if severity == "CRITICAL":
                actions.append("Consider temporary route change for high-value cargo.")

        elif event_type in ("bankruptcy", "restructuring", "payment_issue"):
            actions.append("Review outstanding contracts and receivables with the affected company.")
            actions.append("Assess alternative partners/subcontractors for continuity.")
            actions.append("Monitor official registry for further proceedings.")

        elif event_type == "license_revoked":
            actions.append("Cease any ongoing cooperation with the affected entity immediately.")
            actions.append("Verify subcontractor compliance and license status.")

        elif event_type in ("route_closure", "delay"):
            actions.append("Plan alternative routes for affected corridors.")
            actions.append("Notify dispatchers and drivers of the disruption.")

        elif event_type == "strike":
            actions.append("Monitor strike developments and negotiate contingency plans.")
            actions.append("Consider pre-positioning inventory before disruption worsens.")

        else:
            actions.append("Review the incident details and assess impact on operations.")
            actions.append("Monitor for further developments.")

        if related_events:
            actions.append(
                f"Note: {len(related_events)} related event(s) detected. "
                f"This may indicate a broader pattern."
            )

        return actions
