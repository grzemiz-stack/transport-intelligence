"""Profesjonalny renderer PDF oparty na reportlab.

Generuje raporty A4 z:
- Header: logo placeholder, tytul, okres
- Sekcje z tabelami i kolorami severity
- Polskie znaki (Arial Unicode / DejaVu)
- Disclaimer na koncu
"""

import logging
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Font registration — try Arial Unicode (Polish support), fallback to Helvetica
# ---------------------------------------------------------------------------

_FONT_NAME = "Helvetica"
_FONT_NAME_BOLD = "Helvetica-Bold"

_FONT_PATHS = [
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]

for _path in _FONT_PATHS:
    if os.path.exists(_path):
        try:
            pdfmetrics.registerFont(TTFont("UniFont", _path))
            _FONT_NAME = "UniFont"
            _FONT_NAME_BOLD = "UniFont"  # no separate bold variant
            logger.info("Registered Unicode font: %s", _path)
            break
        except Exception as e:
            logger.debug("Could not register font %s: %s", _path, e)

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

NAVY = colors.HexColor("#1a237e")
DARK_NAVY = colors.HexColor("#0d1642")
LIGHT_GRAY = colors.HexColor("#f5f5f5")
MEDIUM_GRAY = colors.HexColor("#e0e0e0")
WHITE = colors.white
BLACK = colors.black

SEVERITY_COLORS = {
    "critical": colors.HexColor("#b71c1c"),
    "high": colors.HexColor("#e65100"),
    "medium": colors.HexColor("#f9a825"),
    "low": colors.HexColor("#2e7d32"),
    "info": colors.HexColor("#1565c0"),
}

SEVERITY_BG = {
    "critical": colors.HexColor("#ffcdd2"),
    "high": colors.HexColor("#ffe0b2"),
    "medium": colors.HexColor("#fff9c4"),
    "low": colors.HexColor("#c8e6c9"),
    "info": colors.HexColor("#bbdefb"),
}

TREND_ARROWS = {"rising": "\u2191", "declining": "\u2193", "stable": "\u2192", "new": "\u2605"}


class PdfRenderer:
    """Renderuje kontekst raportu do PDF za pomoca reportlab."""

    def __init__(self):
        self._styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        """Definiuje style uzywane w raporcie."""
        self._styles.add(ParagraphStyle(
            "ReportTitle",
            parent=self._styles["Title"],
            fontName=_FONT_NAME_BOLD,
            fontSize=22,
            textColor=WHITE,
            alignment=TA_CENTER,
            spaceAfter=6,
        ))
        self._styles.add(ParagraphStyle(
            "ReportSubtitle",
            parent=self._styles["Normal"],
            fontName=_FONT_NAME,
            fontSize=11,
            textColor=colors.HexColor("#b0bec5"),
            alignment=TA_CENTER,
            spaceAfter=4,
        ))
        self._styles.add(ParagraphStyle(
            "SectionTitle",
            parent=self._styles["Heading1"],
            fontName=_FONT_NAME_BOLD,
            fontSize=14,
            textColor=NAVY,
            spaceBefore=16,
            spaceAfter=8,
            borderWidth=0,
            borderPadding=0,
        ))
        self._styles.add(ParagraphStyle(
            "SectionDesc",
            parent=self._styles["Normal"],
            fontName=_FONT_NAME,
            fontSize=9,
            textColor=colors.HexColor("#616161"),
            spaceAfter=8,
        ))
        self._styles.add(ParagraphStyle(
            "WarningBox",
            parent=self._styles["Normal"],
            fontName=_FONT_NAME_BOLD,
            fontSize=9,
            textColor=colors.HexColor("#e65100"),
            backColor=colors.HexColor("#fff3e0"),
            borderWidth=1,
            borderColor=colors.HexColor("#e65100"),
            borderPadding=6,
            spaceAfter=8,
        ))
        self._styles.add(ParagraphStyle(
            "BodyText9",
            parent=self._styles["Normal"],
            fontName=_FONT_NAME,
            fontSize=9,
            leading=12,
        ))
        self._styles.add(ParagraphStyle(
            "DisclaimerText",
            parent=self._styles["Normal"],
            fontName=_FONT_NAME,
            fontSize=7,
            textColor=colors.HexColor("#757575"),
            leading=10,
        ))
        self._styles.add(ParagraphStyle(
            "FooterText",
            parent=self._styles["Normal"],
            fontName=_FONT_NAME,
            fontSize=7,
            textColor=colors.HexColor("#9e9e9e"),
            alignment=TA_CENTER,
        ))
        # Sales report styles
        self._styles.add(ParagraphStyle(
            "TitlePageTitle",
            parent=self._styles["Title"],
            fontName=_FONT_NAME_BOLD,
            fontSize=28,
            textColor=WHITE,
            alignment=TA_CENTER,
            spaceAfter=8,
        ))
        self._styles.add(ParagraphStyle(
            "TitlePageSubtitle",
            parent=self._styles["Normal"],
            fontName=_FONT_NAME,
            fontSize=14,
            textColor=colors.HexColor("#b0bec5"),
            alignment=TA_CENTER,
            spaceAfter=6,
        ))
        self._styles.add(ParagraphStyle(
            "ConfidentialBanner",
            parent=self._styles["Normal"],
            fontName=_FONT_NAME_BOLD,
            fontSize=10,
            textColor=colors.HexColor("#b71c1c"),
            borderWidth=1,
            borderColor=colors.HexColor("#b71c1c"),
            borderPadding=4,
            alignment=TA_CENTER,
        ))
        self._styles.add(ParagraphStyle(
            "CountryTitle",
            parent=self._styles["Heading1"],
            fontName=_FONT_NAME_BOLD,
            fontSize=16,
            textColor=NAVY,
            spaceBefore=12,
            spaceAfter=8,
        ))
        self._styles.add(ParagraphStyle(
            "AIAnalysis",
            parent=self._styles["Normal"],
            fontName=_FONT_NAME,
            fontSize=9,
            textColor=colors.HexColor("#424242"),
            leading=13,
            leftIndent=8,
            spaceAfter=6,
        ))
        self._styles.add(ParagraphStyle(
            "MethodologyText",
            parent=self._styles["Normal"],
            fontName=_FONT_NAME,
            fontSize=8,
            textColor=colors.HexColor("#757575"),
            leading=11,
        ))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, context: dict, output_path: str) -> str:
        """Renderuje kontekst raportu do PDF.

        Args:
            context: dict z sekcjami raportu (z ReportGenerator._build_report_context)
            output_path: sciezka do pliku wyjsciowego PDF

        Returns:
            sciezka do wygenerowanego pliku
        """
        doc = BaseDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=2 * cm,
            title=context.get("title", "Transport Intelligence Report"),
            author="Transport Intelligence",
        )

        # Page templates
        frame_normal = Frame(
            doc.leftMargin, doc.bottomMargin,
            doc.width, doc.height,
            id="normal",
        )
        doc.addPageTemplates([
            PageTemplate(id="normal", frames=[frame_normal],
                         onPage=self._page_footer),
        ])

        # Build story
        story = []
        self._add_header(story, context)
        self._add_executive_summary(story, context)
        self._add_confirmed_section(story, context)
        self._add_signals_section(story, context)

        report_type = context.get("report_type", "biweekly")
        if report_type == "monthly":
            self._add_financial_section(story, context)

        self._add_risk_map_section(story, context)
        self._add_trends_section(story, context)

        if report_type == "monthly":
            self._add_correlations_section(story, context)
            self._add_recommendations_section(story, context)

        self._add_disclaimer(story, context)

        doc.build(story)
        logger.info("PDF rendered: %s", output_path)
        return output_path

    def render_alert(self, context: dict, output_path: str) -> str:
        """Renderuje raport alertowy do PDF."""
        doc = BaseDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=2 * cm,
            title=context.get("alert", {}).get("title", "Alert Report"),
            author="Transport Intelligence",
        )

        frame = Frame(
            doc.leftMargin, doc.bottomMargin,
            doc.width, doc.height, id="normal",
        )
        doc.addPageTemplates([
            PageTemplate(id="normal", frames=[frame], onPage=self._page_footer),
        ])

        story = []
        alert = context.get("alert", {})

        # Header
        self._add_header(story, {
            "title": f"Alert Report: {alert.get('title', '')}",
            "period": context.get("generated_at", ""),
            "countries": alert.get("country_codes", []),
            "generated_at": context.get("generated_at", ""),
        })

        # Severity banner
        severity = (alert.get("severity") or "HIGH").lower()
        sev_color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["high"])
        story.append(Spacer(1, 8))
        story.append(self._severity_badge(severity.upper(), sev_color))
        story.append(Spacer(1, 8))

        # Alert details table
        details_data = [
            ["Alert Type", alert.get("alert_type", "")],
            ["Severity", severity.upper()],
            ["Country", ", ".join(alert.get("country_codes", []))],
            ["Region", alert.get("region", "-")],
            ["Triggered", alert.get("triggered_at", "")],
        ]
        story.append(self._key_value_table(details_data))
        story.append(Spacer(1, 8))

        # Description
        if alert.get("description"):
            story.append(Paragraph(alert["description"], self._styles["BodyText9"]))
            story.append(Spacer(1, 12))

        # Related events
        related = context.get("related_events", [])
        if related:
            story.append(Paragraph("Related Events", self._styles["SectionTitle"]))
            headers = ["Date", "Country", "Type", "Severity", "Description"]
            data = [headers]
            for ev in related[:20]:
                data.append([
                    str(ev.get("date", ""))[:10],
                    ev.get("country_code", ""),
                    ev.get("event_type", ""),
                    (ev.get("severity") or "").upper(),
                    str(ev.get("description") or ev.get("title", ""))[:80],
                ])
            story.append(self._make_table(data, col_widths=[60, 40, 70, 55, None]))
            story.append(Spacer(1, 12))

        # Recommended actions
        actions = context.get("recommended_actions", [])
        if actions:
            story.append(Paragraph("Recommended Actions", self._styles["SectionTitle"]))
            for i, action in enumerate(actions, 1):
                story.append(Paragraph(
                    f"{i}. {self._safe(action)}", self._styles["BodyText9"],
                ))
            story.append(Spacer(1, 12))

        # Disclaimer
        self._add_disclaimer(story, context)

        doc.build(story)
        return output_path

    # ------------------------------------------------------------------
    # Sales Report
    # ------------------------------------------------------------------

    def render_sales(self, context: dict, output_path: str) -> str:
        """Renderuje sales intelligence report do PDF."""
        doc = BaseDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=2 * cm,
            title="European Transport Risk Report",
            author="Transport Intelligence",
        )

        frame = Frame(
            doc.leftMargin, doc.bottomMargin,
            doc.width, doc.height, id="normal",
        )
        doc.addPageTemplates([
            PageTemplate(id="title_page", frames=[frame],
                         onPage=self._title_page_background),
            PageTemplate(id="confidential", frames=[frame],
                         onPage=self._confidential_footer),
        ])

        story = []

        # 1. Title page
        self._add_title_page(story, context)
        story.append(NextPageTemplate("confidential"))
        story.append(PageBreak())

        # 2. Executive Summary
        self._add_ai_executive_summary(story, context)
        story.append(PageBreak())

        # 3. Hotspots table (top 15)
        self._add_sales_hotspots(story, context)
        story.append(PageBreak())

        # 4. Country analyses (top 5)
        self._add_country_analyses(story, context)

        # 5. Companies at risk (top 10)
        self._add_sales_companies_at_risk(story, context)
        story.append(PageBreak())

        # 6. Corridor analyses (top 10)
        self._add_sales_corridors(story, context)
        story.append(PageBreak())

        # 7. Methodology
        self._add_methodology(story, context)

        # 8. Disclaimer
        self._add_disclaimer(story, context)

        doc.build(story)
        logger.info("Sales PDF rendered: %s", output_path)
        return output_path

    def render_client(self, context: dict, output_path: str) -> str:
        """Renderuje client-specific report (filtered by client countries/corridors)."""
        doc = BaseDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=2 * cm,
            title=f"Transport Risk Report — {context.get('client_name', 'Client')}",
            author="Transport Intelligence",
        )

        frame = Frame(
            doc.leftMargin, doc.bottomMargin,
            doc.width, doc.height, id="normal",
        )
        doc.addPageTemplates([
            PageTemplate(id="title_page", frames=[frame],
                         onPage=self._title_page_background),
            PageTemplate(id="confidential", frames=[frame],
                         onPage=self._confidential_footer),
        ])

        story = []

        # Title page with client name
        self._add_title_page(story, context)
        story.append(NextPageTemplate("confidential"))
        story.append(PageBreak())

        self._add_ai_executive_summary(story, context)
        story.append(PageBreak())

        self._add_sales_hotspots(story, context)
        story.append(PageBreak())

        self._add_country_analyses(story, context)

        self._add_sales_companies_at_risk(story, context)
        story.append(PageBreak())

        self._add_sales_corridors(story, context)
        story.append(PageBreak())

        self._add_methodology(story, context)
        self._add_disclaimer(story, context)

        doc.build(story)
        logger.info("Client PDF rendered: %s", output_path)
        return output_path

    def render_insolvency(self, context: dict, output_path: str) -> str:
        """Renderuje premium insolvency analysis report do PDF."""
        doc = BaseDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=2 * cm,
            title=context.get("title", "Insolvency Analysis Report"),
            author="Transport Intelligence",
        )

        frame = Frame(
            doc.leftMargin, doc.bottomMargin,
            doc.width, doc.height, id="normal",
        )
        doc.addPageTemplates([
            PageTemplate(id="title_page", frames=[frame],
                         onPage=self._title_page_background),
            PageTemplate(id="confidential", frames=[frame],
                         onPage=self._confidential_footer),
        ])

        story = []
        analysis = context.get("analysis", {})

        # Title page
        self._add_title_page(story, context)
        story.append(NextPageTemplate("confidential"))
        story.append(PageBreak())

        # Executive Summary
        exec_summary = analysis.get("executive_summary", "")
        if exec_summary:
            story.append(Paragraph("EXECUTIVE SUMMARY", self._styles["SectionTitle"]))
            story.append(Spacer(1, 4 * mm))
            for para in str(exec_summary).split("\n\n"):
                if para.strip():
                    story.append(Paragraph(para.strip(), self._styles["AIAnalysis"]))
            story.append(Spacer(1, 4 * mm))

            # Confidence score
            confidence = analysis.get("confidence_score", 0)
            conf_pct = int(confidence * 100) if isinstance(confidence, (int, float)) else 0
            story.append(Paragraph(
                f"Confidence Score: {conf_pct}%",
                self._styles["SectionDesc"],
            ))
            story.append(PageBreak())

        # Section 1: Causes
        causes = analysis.get("causes", {})
        if causes:
            story.append(Paragraph("1. PRZYCZYNY UPADLOSCI", self._styles["SectionTitle"]))
            if causes.get("primary"):
                story.append(Paragraph(
                    f"<b>Glowna przyczyna:</b> {causes['primary']}",
                    self._styles["BodyText9"],
                ))
                story.append(Spacer(1, 3 * mm))
            secondary = causes.get("secondary", [])
            if secondary:
                story.append(Paragraph("<b>Dodatkowe przyczyny:</b>", self._styles["BodyText9"]))
                for s in secondary:
                    story.append(Paragraph(f"  - {s}", self._styles["BodyText9"]))
                story.append(Spacer(1, 3 * mm))
            if causes.get("structural"):
                story.append(Paragraph(
                    f"<b>Problemy strukturalne:</b> {causes['structural']}",
                    self._styles["BodyText9"],
                ))
            story.append(Spacer(1, 6 * mm))

        # Section 2: Payment Chain
        payment = analysis.get("payment_chain", {})
        if payment:
            story.append(Paragraph("2. LANCUCH PLATNOSCI", self._styles["SectionTitle"]))
            if payment.get("description"):
                story.append(Paragraph(payment["description"], self._styles["AIAnalysis"]))
            debtors = payment.get("debtors", [])
            if debtors:
                story.append(Paragraph("<b>Dluzniczy:</b>", self._styles["BodyText9"]))
                for d in debtors:
                    story.append(Paragraph(f"  - {d}", self._styles["BodyText9"]))
            if payment.get("estimated_unpaid_amount"):
                story.append(Spacer(1, 2 * mm))
                story.append(Paragraph(
                    f"<b>Szacunkowa kwota niezaplaconych faktur:</b> {payment['estimated_unpaid_amount']}",
                    self._styles["WarningBox"],
                ))
            story.append(Spacer(1, 6 * mm))

        # Section 3: Early Warnings
        early_warnings = context.get("early_warnings", [])
        if early_warnings:
            story.append(Paragraph("3. SYGNALY OSTRZEGAWCZE", self._styles["SectionTitle"]))
            ew_data = [["Sygnal", "Pewnosc", "Zrodlo", "Opis"]]
            for w in early_warnings[:10]:
                conf = w.get("confidence", 0)
                conf_str = f"{int(conf * 100)}%" if isinstance(conf, (int, float)) else str(conf)
                ew_data.append([
                    Paragraph(str(w.get("signal", "")), self._styles["BodyText9"]),
                    conf_str,
                    Paragraph(str(w.get("source", "")), self._styles["BodyText9"]),
                    Paragraph(str(w.get("description", ""))[:200], self._styles["BodyText9"]),
                ])
            if len(ew_data) > 1:
                col_widths = [3 * cm, 1.5 * cm, 3 * cm, 10.5 * cm]
                t = Table(ew_data, colWidths=col_widths, repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), _FONT_NAME_BOLD),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]))
                story.append(t)
            story.append(PageBreak())

        # Section 4: Market Impact
        impact = analysis.get("market_impact", {})
        if impact:
            story.append(Paragraph("4. WPLYW NA RYNEK", self._styles["SectionTitle"]))
            if impact.get("employees_affected"):
                story.append(Paragraph(
                    f"<b>Liczba pracownikow:</b> {impact['employees_affected']}",
                    self._styles["BodyText9"],
                ))
            routes = impact.get("routes_affected", [])
            if routes:
                story.append(Paragraph(
                    f"<b>Trasy:</b> {', '.join(str(r) for r in routes)}",
                    self._styles["BodyText9"],
                ))
            if impact.get("contracts_value"):
                story.append(Paragraph(
                    f"<b>Wartosc kontraktow:</b> {impact['contracts_value']}",
                    self._styles["BodyText9"],
                ))
            who = impact.get("who_benefits", [])
            if who:
                story.append(Paragraph(
                    f"<b>Beneficjenci:</b> {', '.join(str(w) for w in who)}",
                    self._styles["BodyText9"],
                ))
            story.append(Spacer(1, 6 * mm))

        # Section 5: Domino Effect
        domino = analysis.get("domino_effect", {})
        if domino:
            story.append(Paragraph("5. EFEKT DOMINA", self._styles["SectionTitle"]))
            risk_level = domino.get("risk_level", "MEDIUM")
            story.append(Paragraph(
                f"<b>Poziom ryzyka efektu domina: {risk_level}</b>",
                self._styles["WarningBox"] if risk_level in ("CRITICAL", "HIGH") else self._styles["BodyText9"],
            ))
            companies_at_risk = domino.get("companies_at_risk", [])
            if companies_at_risk:
                dr_data = [["Firma", "Relacja", "Ekspozycja", "Ocena ryzyka"]]
                for c in companies_at_risk[:10]:
                    dr_data.append([
                        Paragraph(str(c.get("name", "")), self._styles["BodyText9"]),
                        Paragraph(str(c.get("relationship", "")), self._styles["BodyText9"]),
                        str(c.get("exposure", "")),
                        Paragraph(str(c.get("risk_assessment", "")), self._styles["BodyText9"]),
                    ])
                col_widths = [4.5 * cm, 3.5 * cm, 3 * cm, 7 * cm]
                t = Table(dr_data, colWidths=col_widths, repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b71c1c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), _FONT_NAME_BOLD),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]))
                story.append(t)
            if domino.get("sector_impact"):
                story.append(Spacer(1, 3 * mm))
                story.append(Paragraph(
                    f"<b>Wplyw na sektor:</b> {domino['sector_impact']}",
                    self._styles["AIAnalysis"],
                ))
            story.append(PageBreak())

        # Section 6: Recommendations
        recs = analysis.get("recommendations", {})
        if recs:
            story.append(Paragraph("6. REKOMENDACJE", self._styles["SectionTitle"]))
            for audience, rec in recs.items():
                label = {
                    "for_leasing": "Dla firm leasingowych",
                    "for_insurance": "Dla ubezpieczycieli",
                    "for_contractors": "Dla kontrahentow",
                    "for_drivers": "Dla kierowcow",
                }.get(audience, audience)
                story.append(Paragraph(f"<b>{label}:</b>", self._styles["BodyText9"]))
                story.append(Paragraph(str(rec), self._styles["AIAnalysis"]))
                story.append(Spacer(1, 3 * mm))
            story.append(Spacer(1, 6 * mm))

        # Section 7: Lessons
        lessons = analysis.get("lessons", [])
        if lessons:
            story.append(Paragraph("7. LEKCJE I WNIOSKI", self._styles["SectionTitle"]))
            for i, lesson in enumerate(lessons, 1):
                story.append(Paragraph(f"{i}. {lesson}", self._styles["AIAnalysis"]))
            story.append(Spacer(1, 6 * mm))

        # Related companies from separate analysis
        related = context.get("related_companies", [])
        if related:
            story.append(PageBreak())
            story.append(Paragraph("FIRMY POWIAZANE", self._styles["SectionTitle"]))
            rc_data = [["Firma", "Relacja", "Kraj", "Ryzyko", "Opis"]]
            for c in related[:15]:
                rc_data.append([
                    Paragraph(str(c.get("name", "")), self._styles["BodyText9"]),
                    str(c.get("relationship", "")),
                    str(c.get("country", "")),
                    str(c.get("risk_level", "")),
                    Paragraph(str(c.get("description", ""))[:150], self._styles["BodyText9"]),
                ])
            col_widths = [3.5 * cm, 2.5 * cm, 1.5 * cm, 2 * cm, 8.5 * cm]
            t = Table(rc_data, colWidths=col_widths, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), _FONT_NAME_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(t)

        # Disclaimer
        self._add_disclaimer(story, context)

        doc.build(story)
        logger.info("Insolvency PDF rendered: %s", output_path)
        return output_path

    def render_due_diligence(self, context: dict, output_path: str) -> str:
        """Renderuje premium due diligence investigation report do PDF (10-15 pages)."""
        doc = BaseDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=2 * cm,
            title=context.get("title", "Due Diligence Investigation Report"),
            author="Transport Intelligence",
        )

        frame = Frame(
            doc.leftMargin, doc.bottomMargin,
            doc.width, doc.height, id="normal",
        )
        doc.addPageTemplates([
            PageTemplate(id="title_page", frames=[frame],
                         onPage=self._title_page_background),
            PageTemplate(id="confidential", frames=[frame],
                         onPage=self._confidential_footer),
        ])

        story = []
        inv = context.get("investigation", {})

        # ---- Page 1: Title Page ----
        self._add_title_page(story, context)
        story.append(NextPageTemplate("confidential"))
        story.append(PageBreak())

        # ---- Page 2: Executive Summary ----
        story.append(Paragraph("EXECUTIVE SUMMARY", self._styles["SectionTitle"]))
        story.append(Spacer(1, 4 * mm))

        # Risk score badge
        overall_risk = inv.get("overall_risk", {})
        risk_score = overall_risk.get("score", 0)
        risk_level = overall_risk.get("level", "UNKNOWN")
        risk_trend = overall_risk.get("trend", "unknown")

        risk_color_map = {
            "CRITICAL": SEVERITY_COLORS["critical"],
            "HIGH": SEVERITY_COLORS["high"],
            "MEDIUM": SEVERITY_COLORS["medium"],
            "LOW": SEVERITY_COLORS["low"],
        }
        risk_color = risk_color_map.get(risk_level, SEVERITY_COLORS["medium"])
        story.append(self._severity_badge(
            f"RISK: {risk_score}/100 — {risk_level}", risk_color,
        ))
        story.append(Spacer(1, 4 * mm))

        # Stats grid
        confidence = inv.get("confidence_score", 0)
        conf_pct = int(confidence * 100) if isinstance(confidence, (int, float)) else 0
        sources = inv.get("sources_consulted", [])
        ok_sources = sum(1 for s in sources if s.get("status") == "ok")
        risk_signals = inv.get("risk_signals", [])

        stats_data = [[
            self._stat_cell("Risk Score", str(risk_score)),
            self._stat_cell("Sources OK", f"{ok_sources}/{len(sources)}"),
            self._stat_cell("Risk Signals", str(len(risk_signals))),
            self._stat_cell("Confidence", f"{conf_pct}%"),
        ]]
        stats_table = Table(stats_data, colWidths=[doc_width() / 4] * 4)
        stats_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
            ("BOX", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 6 * mm))

        # AI recommendation summary
        ai_rec = inv.get("ai_recommendation", {})
        if ai_rec.get("summary"):
            for para in str(ai_rec["summary"]).split("\n\n"):
                if para.strip():
                    story.append(Paragraph(
                        self._safe(para.strip()), self._styles["AIAnalysis"],
                    ))
            story.append(Spacer(1, 4 * mm))

        # Do-business verdict
        verdict = ai_rec.get("do_business", "")
        if verdict:
            verdict_colors = {
                "YES": SEVERITY_COLORS["low"],
                "YES_WITH_CONDITIONS": SEVERITY_COLORS["medium"],
                "CAUTION": SEVERITY_COLORS["high"],
                "NO": SEVERITY_COLORS["critical"],
            }
            v_color = verdict_colors.get(verdict, SEVERITY_COLORS["medium"])
            story.append(self._severity_badge(f"VERDICT: {verdict}", v_color))

        story.append(PageBreak())

        # ---- Page 3: Basic Info ----
        basic = inv.get("basic_info", {})
        if basic:
            story.append(Paragraph("1. COMPANY INFORMATION", self._styles["SectionTitle"]))
            kv_data = []
            field_labels = [
                ("legal_name", "Legal Name"),
                ("address", "Registered Address"),
                ("registration_number", "Registration Number"),
                ("vat_number", "VAT Number"),
                ("founded", "Founded"),
                ("capital", "Share Capital"),
                ("status", "Status"),
                ("pkd_sic_code", "Activity Code (PKD/SIC)"),
                ("fleet_size", "Fleet Size"),
                ("employee_count", "Employee Count"),
            ]
            for key, label in field_labels:
                val = basic.get(key)
                if val:
                    kv_data.append([label, str(val)])
            if kv_data:
                story.append(self._key_value_table(kv_data))
            story.append(Spacer(1, 6 * mm))

        # ---- Page 4: Transport Licenses ----
        licenses = inv.get("licenses", [])
        if licenses:
            story.append(Paragraph("2. TRANSPORT LICENSES", self._styles["SectionTitle"]))
            lic_headers = ["Type", "Number", "Status", "Issued By", "Valid Until"]
            lic_data = [lic_headers]
            for lic in licenses[:15]:
                lic_data.append([
                    self._safe(str(lic.get("type", ""))),
                    self._safe(str(lic.get("number", ""))),
                    str(lic.get("status", "")),
                    self._safe(str(lic.get("issued_by", ""))),
                    str(lic.get("valid_until", "")),
                ])
            story.append(self._make_table(lic_data, col_widths=[80, 80, 70, 100, None]))
            story.append(Spacer(1, 6 * mm))

        story.append(PageBreak())

        # ---- Pages 5-6: Financial Health ----
        fin = inv.get("financial_health", {})
        if fin:
            story.append(Paragraph("3. FINANCIAL HEALTH", self._styles["SectionTitle"]))

            assessment = fin.get("assessment", "UNKNOWN")
            assessment_colors = {
                "HEALTHY": SEVERITY_COLORS["low"],
                "WARNING": SEVERITY_COLORS["medium"],
                "CRITICAL": SEVERITY_COLORS["critical"],
                "UNKNOWN": SEVERITY_COLORS["info"],
            }
            a_color = assessment_colors.get(assessment, SEVERITY_COLORS["info"])
            story.append(self._severity_badge(f"ASSESSMENT: {assessment}", a_color))
            story.append(Spacer(1, 4 * mm))

            fin_fields = [
                ("revenue_trend", "Revenue Trend"),
                ("debt_registries", "Debt Registries"),
                ("payment_behavior", "Payment Behavior"),
            ]
            for key, label in fin_fields:
                val = fin.get(key)
                if val:
                    story.append(Paragraph(
                        f"<b>{label}:</b> {self._safe(str(val))}",
                        self._styles["BodyText9"],
                    ))
                    story.append(Spacer(1, 2 * mm))

            key_events = fin.get("key_financial_events", [])
            if key_events:
                story.append(Paragraph("<b>Key Financial Events:</b>", self._styles["BodyText9"]))
                for evt in key_events[:10]:
                    story.append(Paragraph(
                        f"  - {self._safe(str(evt))}", self._styles["BodyText9"],
                    ))
            story.append(Spacer(1, 6 * mm))

        # ---- Page 7: Risk Signals ----
        if risk_signals:
            story.append(PageBreak())
            story.append(Paragraph("4. RISK SIGNALS", self._styles["SectionTitle"]))
            rs_headers = ["Type", "Severity", "Description", "Source", "Trust"]
            rs_data = [rs_headers]
            for rs in risk_signals[:20]:
                rs_data.append([
                    str(rs.get("signal_type", "")),
                    str(rs.get("severity", "")),
                    Paragraph(
                        self._safe(str(rs.get("description", ""))[:200]),
                        self._styles["BodyText9"],
                    ),
                    Paragraph(
                        self._safe(str(rs.get("source", ""))),
                        self._styles["BodyText9"],
                    ),
                    str(rs.get("trust", "")),
                ])
            story.append(self._make_table(
                rs_data, col_widths=[60, 55, None, 90, 35],
            ))
            story.append(Spacer(1, 6 * mm))

        # ---- Page 8: Board & Related Companies ----
        board = inv.get("board_members", [])
        related = inv.get("related_companies", [])
        if board or related:
            story.append(PageBreak())

        if board:
            story.append(Paragraph("5. BOARD MEMBERS", self._styles["SectionTitle"]))
            bm_headers = ["Name", "Role", "Other Directorships", "Risk Flag"]
            bm_data = [bm_headers]
            for bm in board[:15]:
                other = bm.get("other_directorships", [])
                other_str = ", ".join(str(o) for o in other[:3]) if other else "-"
                flag = "YES" if bm.get("risk_flag") else "-"
                bm_data.append([
                    Paragraph(self._safe(str(bm.get("name", ""))), self._styles["BodyText9"]),
                    str(bm.get("role", "")),
                    Paragraph(self._safe(other_str[:100]), self._styles["BodyText9"]),
                    flag,
                ])
            story.append(self._make_table(bm_data, col_widths=[100, 70, None, 50]))
            story.append(Spacer(1, 6 * mm))

        if related:
            story.append(Paragraph("6. RELATED COMPANIES", self._styles["SectionTitle"]))
            rc_headers = ["Company", "Relationship", "Status", "Risk Flag", "Note"]
            rc_data = [rc_headers]
            for rc in related[:15]:
                flag = "YES" if rc.get("risk_flag") else "-"
                rc_data.append([
                    Paragraph(self._safe(str(rc.get("name", ""))), self._styles["BodyText9"]),
                    str(rc.get("relationship", "")),
                    str(rc.get("status", "")),
                    flag,
                    Paragraph(self._safe(str(rc.get("note", ""))[:100]), self._styles["BodyText9"]),
                ])
            story.append(self._make_table(rc_data, col_widths=[90, 70, 55, 40, None]))
            story.append(Spacer(1, 6 * mm))

        # ---- Page 9: Transport Events ----
        transport = inv.get("transport_events", {})
        if transport:
            story.append(PageBreak())
            story.append(Paragraph("7. TRANSPORT EVENTS", self._styles["SectionTitle"]))

            te_kv = []
            for key, label in [
                ("total_events", "Total Events in TI Database"),
                ("events_90d", "Events (Last 90 Days)"),
                ("theft_incidents", "Theft Incidents"),
                ("payment_issues", "Payment Issues"),
            ]:
                val = transport.get(key)
                if val is not None:
                    te_kv.append([label, str(val)])
            if te_kv:
                story.append(self._key_value_table(te_kv))
                story.append(Spacer(1, 4 * mm))

            notable = transport.get("notable_events", [])
            if notable:
                story.append(Paragraph("<b>Notable Events:</b>", self._styles["BodyText9"]))
                for evt in notable[:10]:
                    story.append(Paragraph(
                        f"  - {self._safe(str(evt))}", self._styles["BodyText9"],
                    ))
            story.append(Spacer(1, 6 * mm))

        # ---- Page 10: Media & Reputation ----
        media = inv.get("media_sentiment", {})
        if media:
            story.append(PageBreak())
            story.append(Paragraph("8. MEDIA & REPUTATION", self._styles["SectionTitle"]))

            sentiment = media.get("overall", "no_data")
            sentiment_colors = {
                "positive": SEVERITY_COLORS["low"],
                "neutral": SEVERITY_COLORS["info"],
                "negative": SEVERITY_COLORS["critical"],
                "mixed": SEVERITY_COLORS["medium"],
                "no_data": SEVERITY_COLORS["info"],
            }
            s_color = sentiment_colors.get(sentiment, SEVERITY_COLORS["info"])
            story.append(self._severity_badge(
                f"SENTIMENT: {sentiment.upper()}", s_color,
            ))
            story.append(Spacer(1, 4 * mm))

            articles_count = media.get("articles_found", 0)
            story.append(Paragraph(
                f"<b>Articles Found:</b> {articles_count}",
                self._styles["BodyText9"],
            ))

            themes = media.get("key_themes", [])
            if themes:
                story.append(Paragraph(
                    f"<b>Key Themes:</b> {', '.join(str(t) for t in themes[:5])}",
                    self._styles["BodyText9"],
                ))

            notable_articles = media.get("notable_articles", [])
            if notable_articles:
                story.append(Spacer(1, 3 * mm))
                story.append(Paragraph("<b>Notable Articles:</b>", self._styles["BodyText9"]))
                for art in notable_articles[:5]:
                    story.append(Paragraph(
                        f"  - {self._safe(str(art))}", self._styles["BodyText9"],
                    ))
            story.append(Spacer(1, 6 * mm))

        # ---- Page 11: AI Recommendation ----
        if ai_rec:
            story.append(PageBreak())
            story.append(Paragraph("9. AI RECOMMENDATION", self._styles["SectionTitle"]))

            if ai_rec.get("summary"):
                for para in str(ai_rec["summary"]).split("\n\n"):
                    if para.strip():
                        story.append(Paragraph(
                            self._safe(para.strip()), self._styles["AIAnalysis"],
                        ))
                story.append(Spacer(1, 4 * mm))

            conditions = ai_rec.get("conditions", [])
            if conditions:
                story.append(Paragraph("<b>Conditions:</b>", self._styles["BodyText9"]))
                for i, cond in enumerate(conditions, 1):
                    story.append(Paragraph(
                        f"  {i}. {self._safe(str(cond))}", self._styles["BodyText9"],
                    ))
                story.append(Spacer(1, 3 * mm))

            monitoring = ai_rec.get("monitoring", [])
            if monitoring:
                story.append(Paragraph("<b>Monitoring Recommendations:</b>", self._styles["BodyText9"]))
                for i, mon in enumerate(monitoring, 1):
                    story.append(Paragraph(
                        f"  {i}. {self._safe(str(mon))}", self._styles["BodyText9"],
                    ))
            story.append(Spacer(1, 6 * mm))

        # ---- Page 12: Sources Consulted ----
        if sources:
            story.append(PageBreak())
            story.append(Paragraph("10. SOURCES CONSULTED", self._styles["SectionTitle"]))
            sc_headers = ["Source", "Tier", "Trust", "Status"]
            sc_data = [sc_headers]
            for sc in sources:
                status_mark = "OK" if sc.get("status") == "ok" else "FAILED"
                sc_data.append([
                    Paragraph(self._safe(str(sc.get("source", ""))), self._styles["BodyText9"]),
                    str(sc.get("tier", "")),
                    str(sc.get("trust", "")),
                    status_mark,
                ])
            story.append(self._make_table(sc_data, col_widths=[None, 40, 45, 50]))
            story.append(Spacer(1, 6 * mm))

        # ---- Pages 13-14: Disclaimer ----
        self._add_disclaimer(story, context)

        doc.build(story)
        logger.info("Due diligence PDF rendered: %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Sales report page callbacks
    # ------------------------------------------------------------------

    def _title_page_background(self, canvas, doc):
        """Full-page navy background for the title page."""
        canvas.saveState()
        canvas.setFillColor(DARK_NAVY)
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        # CONFIDENTIAL stamp at bottom
        canvas.setFont(_FONT_NAME_BOLD, 10)
        canvas.setFillColor(colors.HexColor("#b71c1c"))
        canvas.drawCentredString(A4[0] / 2, 1.5 * cm, "CONFIDENTIAL")
        canvas.restoreState()

    def _confidential_footer(self, canvas, doc):
        """Standard page footer with CONFIDENTIAL stamp and page number."""
        canvas.saveState()
        canvas.setFont(_FONT_NAME, 7)
        canvas.setFillColor(colors.HexColor("#9e9e9e"))
        canvas.drawString(
            doc.leftMargin, 1.2 * cm,
            "Transport Intelligence | Confidential",
        )
        canvas.drawRightString(
            A4[0] - doc.rightMargin, 1.2 * cm,
            f"Page {canvas.getPageNumber()}",
        )
        # Red CONFIDENTIAL centered
        canvas.setFont(_FONT_NAME_BOLD, 8)
        canvas.setFillColor(colors.HexColor("#b71c1c"))
        canvas.drawCentredString(A4[0] / 2, 1.2 * cm, "CONFIDENTIAL")
        canvas.restoreState()

    # ------------------------------------------------------------------
    # Sales report sections
    # ------------------------------------------------------------------

    def _add_title_page(self, story: list, context: dict):
        """Title page: logo placeholder, title, subtitle, period, confidential."""
        story.append(Spacer(1, 4 * cm))

        # Logo placeholder — navy rect with white text
        logo_data = [[Paragraph(
            "<b>TRANSPORT INTELLIGENCE</b>",
            ParagraphStyle("logo", fontName=_FONT_NAME_BOLD, fontSize=18,
                           textColor=colors.HexColor("#b0bec5"), alignment=TA_CENTER),
        )]]
        logo_table = Table(logo_data, colWidths=[doc_width() * 0.6])
        logo_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(logo_table)
        story.append(Spacer(1, 2 * cm))

        # Title
        title = context.get("title", "European Transport Risk Report")
        story.append(Paragraph(self._safe(title), self._styles["TitlePageTitle"]))
        story.append(Spacer(1, 0.5 * cm))

        # Subtitle
        subtitle = context.get("subtitle", "Biweekly Intelligence Briefing")
        story.append(Paragraph(self._safe(subtitle), self._styles["TitlePageSubtitle"]))
        story.append(Spacer(1, 0.3 * cm))

        # Client name (for client reports)
        client_name = context.get("client_name")
        if client_name:
            story.append(Paragraph(
                f"Prepared for: {self._safe(client_name)}",
                self._styles["TitlePageSubtitle"],
            ))
            story.append(Spacer(1, 0.3 * cm))

        # Period
        period = context.get("period", "")
        if period:
            story.append(Paragraph(
                f"Period: {period}",
                self._styles["TitlePageSubtitle"],
            ))
        story.append(Spacer(1, 1 * cm))

        # Confidential banner
        story.append(Paragraph(
            "CONFIDENTIAL \u2014 For authorized recipients only",
            self._styles["ConfidentialBanner"],
        ))
        story.append(Spacer(1, 0.5 * cm))

        # Generated at
        generated = context.get("generated_at", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
        story.append(Paragraph(
            f"Generated: {generated}",
            self._styles["TitlePageSubtitle"],
        ))

    def _add_ai_executive_summary(self, story: list, context: dict):
        """Executive summary with AI-generated text and stats grid."""
        story.append(Paragraph("EXECUTIVE SUMMARY", self._styles["SectionTitle"]))

        # Stats grid (reuses _stat_cell pattern)
        total = context.get("total_events", 0)
        countries_count = len(context.get("countries", []))
        hotspot_count = len(context.get("ai_hotspots", []))
        companies_count = len(context.get("ai_companies", []))

        stats_data = [[
            self._stat_cell("Total Events", str(total)),
            self._stat_cell("Countries", str(countries_count)),
            self._stat_cell("Hotspots", str(hotspot_count)),
            self._stat_cell("At-Risk Companies", str(companies_count)),
        ]]
        stats_table = Table(stats_data, colWidths=[doc_width() / 4] * 4)
        stats_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
            ("BOX", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 12))

        # AI-generated executive summary text
        ai_summary = context.get("ai_executive_summary", "")
        if ai_summary:
            for para in ai_summary.split("\n\n"):
                para = para.strip()
                if para:
                    story.append(Paragraph(
                        self._safe(para), self._styles["AIAnalysis"],
                    ))
                    story.append(Spacer(1, 4))
        story.append(Spacer(1, 8))

    def _add_sales_hotspots(self, story: list, context: dict):
        """Table of top 15 hotspots with AI descriptions."""
        story.append(Paragraph("HOTSPOT ANALYSIS", self._styles["SectionTitle"]))
        story.append(Paragraph(
            "Top risk locations based on event concentration and AI pattern analysis.",
            self._styles["SectionDesc"],
        ))

        hotspots = context.get("ai_hotspots", [])
        if not hotspots:
            story.append(Paragraph("No hotspot data available.", self._styles["BodyText9"]))
            return

        headers = ["Location", "Country", "Events", "Risk", "AI Analysis"]
        data = [headers]
        for h in hotspots[:15]:
            data.append([
                self._safe(h.get("location", "")),
                h.get("country_code", ""),
                str(h.get("event_count", 0)),
                h.get("risk_level", ""),
                self._safe(h.get("pattern", "")[:120]),
            ])
        story.append(self._make_table(data, col_widths=[90, 40, 45, 50, None]))
        story.append(Spacer(1, 12))

    def _add_country_analyses(self, story: list, context: dict):
        """Country-by-country analysis pages for top 5 countries."""
        story.append(Paragraph("COUNTRY ANALYSIS", self._styles["SectionTitle"]))

        country_analyses = context.get("ai_country_analyses", [])
        if not country_analyses:
            story.append(Paragraph("No country analysis data available.", self._styles["BodyText9"]))
            story.append(PageBreak())
            return

        for ca in country_analyses[:5]:
            country_code = ca.get("country_code", "")
            event_count = ca.get("event_count", 0)

            story.append(Paragraph(
                f"{self._safe(country_code)} \u2014 {event_count} events",
                self._styles["CountryTitle"],
            ))

            # Stats row
            severity_dist = ca.get("severity_distribution", {})
            if severity_dist:
                stats_text = " | ".join(
                    f"{sev}: {cnt}" for sev, cnt in severity_dist.items()
                )
                story.append(Paragraph(
                    f"Severity: {stats_text}",
                    self._styles["SectionDesc"],
                ))

            top_locations = ca.get("top_locations", [])
            if top_locations:
                story.append(Paragraph(
                    f"Top locations: {', '.join(top_locations[:5])}",
                    self._styles["SectionDesc"],
                ))

            # AI analysis text
            analysis_text = ca.get("analysis", "")
            if analysis_text:
                for para in analysis_text.split("\n\n"):
                    para = para.strip()
                    if para:
                        story.append(Paragraph(
                            self._safe(para), self._styles["AIAnalysis"],
                        ))
                        story.append(Spacer(1, 3))

            story.append(Spacer(1, 8))

        story.append(PageBreak())

    def _add_sales_companies_at_risk(self, story: list, context: dict):
        """Table of top 10 companies at risk with AI analysis."""
        story.append(Paragraph("COMPANIES AT RISK", self._styles["SectionTitle"]))
        story.append(Paragraph(
            "Companies with elevated risk profiles based on event history and financial data.",
            self._styles["SectionDesc"],
        ))

        companies = context.get("ai_companies", [])
        if not companies:
            story.append(Paragraph("No company risk data available.", self._styles["BodyText9"]))
            return

        headers = ["Company", "Country", "Risk Score", "Risk Factors", "Recommendation"]
        data = [headers]
        for c in companies[:10]:
            factors = c.get("risk_factors", [])
            factors_str = "; ".join(str(f) for f in factors[:3]) if factors else ""
            data.append([
                self._safe(c.get("company", "")),
                c.get("country_code", ""),
                str(c.get("risk_score", 0)),
                self._safe(factors_str[:100]),
                self._safe(c.get("recommendation", "")[:80]),
            ])
        story.append(self._make_table(data, col_widths=[90, 40, 50, None, 100]))
        story.append(Spacer(1, 12))

    def _add_sales_corridors(self, story: list, context: dict):
        """Table of top 10 corridor analyses."""
        story.append(Paragraph("CORRIDOR ANALYSIS", self._styles["SectionTitle"]))
        story.append(Paragraph(
            "Risk assessment of major cross-country transport corridors.",
            self._styles["SectionDesc"],
        ))

        corridors = context.get("ai_corridors", [])
        if not corridors:
            story.append(Paragraph("No corridor data available.", self._styles["BodyText9"]))
            return

        headers = ["Corridor", "Countries", "Events", "Trend", "Recommendation"]
        data = [headers]
        for c in corridors[:10]:
            countries = c.get("countries", [])
            recommendations = c.get("recommendations", [])
            rec_str = recommendations[0] if recommendations else ""
            data.append([
                self._safe(c.get("corridor", "")),
                ", ".join(countries),
                str(c.get("total_events", 0)),
                c.get("trend", "stable"),
                self._safe(str(rec_str)[:100]),
            ])
        story.append(self._make_table(data, col_widths=[80, 60, 45, 50, None]))
        story.append(Spacer(1, 12))

    def _add_methodology(self, story: list, context: dict):
        """Static methodology section."""
        story.append(Paragraph("METHODOLOGY", self._styles["SectionTitle"]))

        source_count = context.get("source_count", 50)
        methodology_text = [
            (
                f"This report is generated by Transport Intelligence, monitoring "
                f"{source_count}+ sources across Europe including official police "
                f"communications, court registries, business registries, news outlets, "
                f"and industry forums."
            ),
            (
                "Source types: Official police communications, court filings, "
                "public business registries (KRS, Handelsregister, Companies House), "
                "news publications, transport industry forums, financial databases."
            ),
            (
                "Data pipeline: All collected data undergoes automated NLP processing, "
                "entity extraction, severity classification, and geographic enrichment. "
                "AI-powered analysis identifies patterns, correlations, and risk assessments."
            ),
            (
                "Compliance: All personal data is removed in compliance with GDPR "
                "(EU Regulation 2016/679). Processing records are maintained as required "
                "by Article 30. Company names are included only when sourced from "
                "official public records."
            ),
        ]
        for para in methodology_text:
            story.append(Paragraph(self._safe(para), self._styles["MethodologyText"]))
            story.append(Spacer(1, 4))
        story.append(Spacer(1, 8))

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _add_header(self, story: list, context: dict):
        """Navy header block with title, period, countries."""
        title = context.get("title", "Transport Intelligence Report")
        period = context.get("period", "")
        countries = context.get("countries", [])
        generated = context.get("generated_at", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))

        # Header table with navy background
        header_data = [
            [Paragraph("<b>TRANSPORT INTELLIGENCE</b>", self._styles["ReportSubtitle"])],
            [Paragraph(self._safe(title), self._styles["ReportTitle"])],
            [Paragraph(
                f"Period: {period} | Countries: {', '.join(countries) if countries else 'All'} | "
                f"Generated: {generated}",
                self._styles["ReportSubtitle"],
            )],
        ]
        header_table = Table(header_data, colWidths=[doc_width()])
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("TOPPADDING", (0, 0), (-1, 0), 14),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 16))

    # ------------------------------------------------------------------
    # Executive Summary
    # ------------------------------------------------------------------

    def _add_executive_summary(self, story: list, context: dict):
        summary = context.get("executive_summary", {})
        if not summary:
            return

        story.append(Paragraph("EXECUTIVE SUMMARY", self._styles["SectionTitle"]))

        # Stats grid
        total = summary.get("total_events", context.get("total_events", 0))
        confirmed = context.get("confirmed")
        signals = context.get("signals")
        financial = context.get("financial")

        confirmed_count = len(confirmed.events) if confirmed else 0
        signals_count = len(signals.events) if signals else 0
        financial_count = len(financial.events) if financial else 0

        stats_data = [[
            self._stat_cell("Total Events", str(total)),
            self._stat_cell("Confirmed", str(confirmed_count)),
            self._stat_cell("Signals", str(signals_count)),
            self._stat_cell("Financial", str(financial_count)),
            self._stat_cell("Countries", str(summary.get("countries_covered", 0))),
        ]]
        stats_table = Table(stats_data, colWidths=[doc_width() / 5] * 5)
        stats_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
            ("BOX", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 8))

        # Top hotspots
        hotspots = summary.get("top_hotspots", [])
        if hotspots:
            story.append(Paragraph("Top Hotspots", self._styles["SectionDesc"]))
            data = [["Region", "Incidents"]]
            for h in hotspots[:5]:
                data.append([h.get("region", ""), str(h.get("count", 0))])
            story.append(self._make_table(data, col_widths=[None, 60]))
            story.append(Spacer(1, 8))

        # Top financial companies
        fin_companies = summary.get("top_financial_companies", [])
        if fin_companies:
            story.append(Paragraph("Companies with Financial Signals", self._styles["SectionDesc"]))
            data = [["Company", "Issues"]]
            for c in fin_companies[:5]:
                data.append([self._safe(c.get("company", "")), str(c.get("issues", 0))])
            story.append(self._make_table(data, col_widths=[None, 60]))

        story.append(Spacer(1, 12))

    # ------------------------------------------------------------------
    # Confirmed Incidents
    # ------------------------------------------------------------------

    def _add_confirmed_section(self, story: list, context: dict):
        confirmed = context.get("confirmed")
        if not confirmed:
            return

        story.append(Paragraph(
            f"1. {self._safe(confirmed.title)}", self._styles["SectionTitle"],
        ))
        story.append(Paragraph(
            self._safe(confirmed.description), self._styles["SectionDesc"],
        ))

        events = confirmed.events
        if not events:
            story.append(Paragraph("No confirmed incidents in this period.", self._styles["BodyText9"]))
            story.append(Spacer(1, 12))
            return

        headers = ["Date", "Country", "Type", "Severity", "Description", "Source"]
        data = [headers]
        for ev in events[:50]:
            sev = (ev.get("severity") or "MEDIUM").upper()
            data.append([
                str(ev.get("date", ""))[:10],
                ev.get("country_code", ""),
                ev.get("event_type", ""),
                sev,
                self._safe(str(ev.get("description") or ev.get("title", ""))[:80]),
                self._safe(ev.get("source_name", "")),
            ])
        story.append(self._make_table(data, col_widths=[55, 40, 65, 50, None, 70]))
        story.append(Spacer(1, 12))

    # ------------------------------------------------------------------
    # Market Signals
    # ------------------------------------------------------------------

    def _add_signals_section(self, story: list, context: dict):
        signals = context.get("signals")
        if not signals:
            return

        story.append(Paragraph(
            f"2. {self._safe(signals.title)}", self._styles["SectionTitle"],
        ))

        if signals.warning:
            story.append(Paragraph(self._safe(signals.warning), self._styles["WarningBox"]))

        story.append(Paragraph(self._safe(signals.description), self._styles["SectionDesc"]))

        events = signals.events
        if not events:
            story.append(Paragraph("No market signals in this period.", self._styles["BodyText9"]))
            story.append(Spacer(1, 12))
            return

        headers = ["Date", "Country", "Type", "Description", "Trust"]
        data = [headers]
        for ev in events[:50]:
            display = ev.get("company_display", "")
            desc = str(ev.get("description") or ev.get("title", ""))[:70]
            if display:
                desc = f"{display} — {desc}"
            data.append([
                str(ev.get("date", ""))[:10],
                ev.get("country_code", ""),
                ev.get("event_type", ""),
                self._safe(desc[:100]),
                f"{ev.get('trust_score', 0):.1f}",
            ])
        story.append(self._make_table(data, col_widths=[55, 40, 65, None, 40]))
        story.append(Spacer(1, 12))

    # ------------------------------------------------------------------
    # Financial Health (monthly)
    # ------------------------------------------------------------------

    def _add_financial_section(self, story: list, context: dict):
        financial = context.get("financial")
        if not financial:
            return

        story.append(Paragraph(
            f"3. {self._safe(financial.title)}", self._styles["SectionTitle"],
        ))
        story.append(Paragraph(self._safe(financial.description), self._styles["SectionDesc"]))

        if not financial.subsections:
            story.append(Paragraph("No financial events in this period.", self._styles["BodyText9"]))
            story.append(Spacer(1, 12))
            return

        for sub in financial.subsections:
            label = sub.get("label", sub.get("type", ""))
            count = sub.get("count", len(sub.get("events", [])))
            story.append(Paragraph(
                f"<b>{self._safe(label)}</b> ({count})", self._styles["BodyText9"],
            ))
            events = sub.get("events", [])
            if events:
                headers = ["Date", "Country", "Company", "Description"]
                data = [headers]
                for ev in events[:20]:
                    company = ev.get("company") or ev.get("company_display", "—")
                    data.append([
                        str(ev.get("date", ""))[:10],
                        ev.get("country_code", ""),
                        self._safe(company),
                        self._safe(str(ev.get("description", ""))[:80]),
                    ])
                story.append(self._make_table(data, col_widths=[55, 40, 100, None]))
            story.append(Spacer(1, 6))

        story.append(Spacer(1, 8))

    # ------------------------------------------------------------------
    # Risk Map
    # ------------------------------------------------------------------

    def _add_risk_map_section(self, story: list, context: dict):
        risk_map = context.get("risk_map")
        if not risk_map:
            return

        section_num = "4" if context.get("report_type") == "monthly" else "3"
        story.append(Paragraph(
            f"{section_num}. {self._safe(risk_map.title)}", self._styles["SectionTitle"],
        ))
        story.append(Paragraph(self._safe(risk_map.description), self._styles["SectionDesc"]))

        # Top hotspots from metadata
        hotspots = risk_map.metadata.get("top_hotspots", [])
        if hotspots:
            headers = ["Region", "Incidents", "Avg Severity", "Primary Type"]
            data = [headers]
            for h in hotspots[:10]:
                desc = h.get("description", "")
                # Extract primary type from description
                ptype = ""
                if "primary type:" in desc:
                    ptype = desc.split("primary type:")[1].split(",")[0].strip()
                data.append([
                    h.get("region", ""),
                    str(h.get("event_count", 0)),
                    f"{h.get('severity_avg', 0):.1f}",
                    ptype,
                ])
            story.append(self._make_table(data, col_widths=[None, 60, 70, 80]))
        elif risk_map.events:
            headers = ["Region", "Incidents", "Event Types"]
            data = [headers]
            for region in risk_map.events[:10]:
                types_str = ", ".join(
                    f"{t}: {c}" for t, c in region.get("types", {}).items()
                )
                data.append([
                    region.get("region", ""),
                    str(region.get("count", 0)),
                    types_str[:80],
                ])
            story.append(self._make_table(data, col_widths=[80, 60, None]))

        story.append(Spacer(1, 12))

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------

    def _add_trends_section(self, story: list, context: dict):
        trends = context.get("trends")
        if not trends:
            return

        section_num = "5" if context.get("report_type") == "monthly" else "4"
        story.append(Paragraph(
            f"{section_num}. {self._safe(trends.title)}", self._styles["SectionTitle"],
        ))
        story.append(Paragraph(self._safe(trends.description), self._styles["SectionDesc"]))

        # Country trends
        country_trends = trends.metadata.get("country_trends", [])
        if country_trends:
            story.append(Paragraph("<b>Country Trends</b>", self._styles["BodyText9"]))
            headers = ["Country", "Current", "Previous", "Change %", "Trend"]
            data = [headers]
            for ct in country_trends[:15]:
                arrow = TREND_ARROWS.get(ct.get("trend", ""), "")
                data.append([
                    ct.get("country", ""),
                    str(ct.get("current", 0)),
                    str(ct.get("previous", 0)),
                    f"{ct.get('change_pct', 0):+.1f}%",
                    f"{arrow} {ct.get('trend', '')}",
                ])
            story.append(self._make_table(data, col_widths=[60, 55, 55, 60, None]))
            story.append(Spacer(1, 8))

        # Type trends
        type_trends = trends.metadata.get("type_trends", [])
        if type_trends:
            story.append(Paragraph("<b>Event Type Trends</b>", self._styles["BodyText9"]))
            headers = ["Event Type", "Current", "Previous", "Change %", "Trend"]
            data = [headers]
            for tt in type_trends[:15]:
                arrow = TREND_ARROWS.get(tt.get("trend", ""), "")
                data.append([
                    tt.get("event_type", ""),
                    str(tt.get("current", 0)),
                    str(tt.get("previous", 0)),
                    f"{tt.get('change_pct', 0):+.1f}%",
                    f"{arrow} {tt.get('trend', '')}",
                ])
            story.append(self._make_table(data, col_widths=[80, 55, 55, 60, None]))

        story.append(Spacer(1, 12))

    # ------------------------------------------------------------------
    # Correlations (monthly)
    # ------------------------------------------------------------------

    def _add_correlations_section(self, story: list, context: dict):
        correlations = context.get("correlations", [])
        if not correlations:
            return

        story.append(Paragraph("6. CORRELATIONS & PATTERNS", self._styles["SectionTitle"]))
        story.append(Paragraph(
            "Patterns detected across multiple events.",
            self._styles["SectionDesc"],
        ))

        headers = ["Pattern", "Events", "Countries", "Confidence"]
        data = [headers]
        for corr in correlations[:15]:
            data.append([
                self._safe(corr.get("description") or corr.get("type", "")),
                str(corr.get("event_count", len(corr.get("event_ids", [])))),
                ", ".join(corr.get("country_codes", [])),
                f"{corr.get('confidence', 0):.2f}",
            ])
        story.append(self._make_table(data, col_widths=[None, 50, 70, 60]))
        story.append(Spacer(1, 12))

    # ------------------------------------------------------------------
    # Recommendations (monthly)
    # ------------------------------------------------------------------

    def _add_recommendations_section(self, story: list, context: dict):
        recommendations = context.get("recommendations", [])
        if not recommendations:
            return

        story.append(Paragraph("7. RECOMMENDATIONS", self._styles["SectionTitle"]))
        for i, rec in enumerate(recommendations, 1):
            story.append(Paragraph(
                f"<b>{i}.</b> {self._safe(rec)}", self._styles["BodyText9"],
            ))
        story.append(Spacer(1, 12))

    # ------------------------------------------------------------------
    # Disclaimer
    # ------------------------------------------------------------------

    def _add_disclaimer(self, story: list, context: dict):
        story.append(Spacer(1, 16))

        # Separator line
        sep_data = [["" * 100]]
        sep = Table(sep_data, colWidths=[doc_width()])
        sep.setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 1, MEDIUM_GRAY),
        ]))
        story.append(sep)
        story.append(Spacer(1, 8))

        disclaimer_text = context.get("disclaimer", "")
        if disclaimer_text:
            # Split into paragraphs
            for para in disclaimer_text.split("\n\n"):
                para = para.strip()
                if para:
                    story.append(Paragraph(
                        self._safe(para), self._styles["DisclaimerText"],
                    ))
                    story.append(Spacer(1, 4))

    # ------------------------------------------------------------------
    # Page footer callback
    # ------------------------------------------------------------------

    def _page_footer(self, canvas, doc):
        """Dodaje numer strony i branding w stopce."""
        canvas.saveState()
        canvas.setFont(_FONT_NAME, 7)
        canvas.setFillColor(colors.HexColor("#9e9e9e"))
        canvas.drawString(
            doc.leftMargin, 1.2 * cm,
            "Transport Intelligence | Confidential",
        )
        canvas.drawRightString(
            A4[0] - doc.rightMargin, 1.2 * cm,
            f"Page {canvas.getPageNumber()}",
        )
        canvas.restoreState()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _stat_cell(self, label: str, value: str) -> Paragraph:
        return Paragraph(
            f'<font size="16"><b>{value}</b></font><br/>'
            f'<font size="8" color="#757575">{label}</font>',
            ParagraphStyle("stat", fontName=_FONT_NAME, alignment=TA_CENTER),
        )

    def _severity_badge(self, text: str, color) -> Table:
        para = Paragraph(
            f'<font color="white"><b>&nbsp;{text}&nbsp;</b></font>',
            ParagraphStyle("badge", fontName=_FONT_NAME_BOLD, fontSize=11, alignment=TA_CENTER),
        )
        t = Table([[para]], colWidths=[120])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), color),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        return t

    def _key_value_table(self, data: list[list]) -> Table:
        """Two-column key-value table."""
        styled_data = []
        for row in data:
            styled_data.append([
                Paragraph(f"<b>{self._safe(str(row[0]))}</b>",
                          ParagraphStyle("kv_key", fontName=_FONT_NAME_BOLD, fontSize=9)),
                Paragraph(self._safe(str(row[1])),
                          ParagraphStyle("kv_val", fontName=_FONT_NAME, fontSize=9)),
            ])
        t = Table(styled_data, colWidths=[100, None])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
            ("BOX", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    def _make_table(self, data: list[list], col_widths: list | None = None) -> Table:
        """Standard data table with header styling and severity color coding."""
        if not data:
            return Spacer(1, 1)

        # Wrap cell content in Paragraphs for wrapping
        styled_data = []
        for i, row in enumerate(data):
            styled_row = []
            for j, cell in enumerate(row):
                cell_str = str(cell) if cell else ""
                if i == 0:
                    # Header row
                    styled_row.append(Paragraph(
                        f"<b>{self._safe(cell_str)}</b>",
                        ParagraphStyle("th", fontName=_FONT_NAME_BOLD, fontSize=8,
                                       textColor=WHITE),
                    ))
                else:
                    styled_row.append(Paragraph(
                        self._safe(cell_str),
                        ParagraphStyle("td", fontName=_FONT_NAME, fontSize=8),
                    ))
            styled_data.append(styled_row)

        # Calculate col widths — replace None with star (*) logic
        available = doc_width()
        if col_widths:
            fixed = sum(w for w in col_widths if w is not None)
            none_count = sum(1 for w in col_widths if w is None)
            remaining = max(40, available - fixed)
            each = remaining / none_count if none_count else remaining
            final_widths = [w if w is not None else each for w in col_widths]
        else:
            ncols = len(data[0]) if data else 1
            final_widths = [available / ncols] * ncols

        t = Table(styled_data, colWidths=final_widths, repeatRows=1)

        style_cmds = [
            # Header
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            # Grid
            ("BOX", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, MEDIUM_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]

        # Alternating row backgrounds
        for i in range(1, len(styled_data)):
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), LIGHT_GRAY))

        # Color-code severity column if present
        if data and len(data) > 1:
            header_row = [str(h).lower() for h in data[0]]
            sev_col = None
            for idx, h in enumerate(header_row):
                if "severity" in h:
                    sev_col = idx
                    break
            if sev_col is not None:
                for i in range(1, len(data)):
                    sev = str(data[i][sev_col]).lower() if len(data[i]) > sev_col else ""
                    bg = SEVERITY_BG.get(sev)
                    if bg:
                        style_cmds.append(("BACKGROUND", (sev_col, i), (sev_col, i), bg))

        t.setStyle(TableStyle(style_cmds))
        return t

    @staticmethod
    def _safe(text: str) -> str:
        """Escape XML special characters for Paragraph."""
        if not text:
            return ""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )


def doc_width() -> float:
    """Usable width for A4 with 1.5cm margins."""
    return A4[0] - 3 * cm
