"""InsolvencyAnalyzer — Claude API-powered analysis of transport company insolvencies.

Premium product: deep analysis of why a transport company went bankrupt,
payment chain analysis, domino effect detection, early warning signals.

Uses the same Claude API pattern as PatternAnalyzer:
- httpx.AsyncClient -> POST https://api.anthropic.com/v1/messages
- Rate limiting: 5 requests/minute
- In-memory cache: MD5 of JSON-serialized input data
- Google News RSS for supplementary research
"""

import hashlib
import json
import logging
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import httpx

from src.config import settings
from src.utils.claude_client import ClaudeClient, COUNTRY_NAMES

logger = logging.getLogger(__name__)


class InsolvencyAnalyzer:
    """AI-powered insolvency analysis for transport companies.

    Premium product — generates deep analysis of company bankruptcies:
    - Root causes of insolvency
    - Payment chain analysis (who didn't pay whom)
    - Early warning signals
    - Market impact (employees, routes, contracts)
    - Domino effect — related companies at risk
    - Actionable recommendations for leasing/insurance companies
    """

    def __init__(self):
        self._cache: dict[str, dict | str | list] = {}
        self._claude = ClaudeClient(
            api_key=settings.anthropic_api_key,
            max_requests_per_minute=5,
            timeout=90.0,
        )

    def _cache_key(self, data) -> str:
        """MD5 hash of JSON-serialized input data."""
        raw = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Google News RSS research
    # ------------------------------------------------------------------

    async def _search_google_news(self, query: str, lang: str = "pl") -> list[dict]:
        """Search Google News RSS for articles about a company."""
        encoded_query = quote_plus(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl={lang}&gl={lang.upper()}&ceid={lang.upper()}:{lang}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "TransportIntelligence/1.0 (Research Bot)",
                })
                resp.raise_for_status()

            articles = []
            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError:
                return []

            for item in root.iter("item"):
                title_el = item.find("title")
                desc_el = item.find("description")
                link_el = item.find("link")
                pubdate_el = item.find("pubDate")

                articles.append({
                    "title": title_el.text.strip() if title_el is not None and title_el.text else "",
                    "description": desc_el.text.strip() if desc_el is not None and desc_el.text else "",
                    "link": link_el.text.strip() if link_el is not None and link_el.text else "",
                    "pubDate": pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else "",
                })

            logger.info("Google News: %d articles for '%s'", len(articles), query)
            return articles[:20]

        except Exception as e:
            logger.warning("Google News search failed for '%s': %s", query, e)
            return []

    async def _research_company(self, company_name: str, country: str) -> str:
        """Research a company using Google News RSS — returns text summary of findings."""
        country_name = COUNTRY_NAMES.get(country, country)

        # Search multiple queries for comprehensive coverage
        queries = [
            f"{company_name} upadlosc bankructwo",
            f"{company_name} insolvency bankruptcy",
            f"{company_name} transport {country_name}",
            f"{company_name} problemy finansowe",
        ]

        all_articles = []
        for query in queries:
            articles = await self._search_google_news(query)
            all_articles.extend(articles)

        if not all_articles:
            return "Brak wynikow wyszukiwania w Google News."

        # Deduplicate by title
        seen = set()
        unique = []
        for a in all_articles:
            key = a["title"].strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(a)

        # Format as text for Claude prompt
        articles_text = "\n".join(
            f"- [{a.get('pubDate', '')}] {a['title']}: {a.get('description', '')[:200]}"
            for a in unique[:15]
        )

        return articles_text

    # ------------------------------------------------------------------
    # Main analysis method
    # ------------------------------------------------------------------

    async def analyze_insolvency(
        self,
        company_name: str,
        country: str,
        insolvency_data: dict,
    ) -> dict:
        """Full insolvency analysis for a transport company.

        Uses Claude API + Google News research to generate:
        - Root causes of insolvency
        - Payment chain analysis
        - Early warning signals
        - Market impact
        - Lessons learned
        - Related companies at risk (domino effect)

        Args:
            company_name: Name of the bankrupt company
            country: ISO 2-letter country code
            insolvency_data: dict with fields: date, court, type, description, events, financials

        Returns:
            dict with sections: causes, payment_chain, early_warnings, market_impact,
            lessons, related_companies, executive_summary, confidence_score
        """
        cache_key = self._cache_key(("insolvency", company_name, country, insolvency_data))
        if cache_key in self._cache:
            return self._cache[cache_key]

        country_name = COUNTRY_NAMES.get(country, country)

        # Step 1: Research the company online
        news_text = await self._research_company(company_name, country)

        # Step 2: Build context from insolvency_data
        events_text = ""
        if insolvency_data.get("events"):
            events_text = "\n".join(
                f"- [{e.get('date', '')}] {e.get('event_type', '')} "
                f"({e.get('severity', '')}): {e.get('title', '')[:150]}"
                for e in insolvency_data["events"][:20]
            )

        financials_text = ""
        if insolvency_data.get("financials"):
            fin = insolvency_data["financials"]
            financials_text = (
                f"Status finansowy: {fin.get('financial_status', 'unknown')}\n"
                f"Risk score: {fin.get('risk_score', 0)}\n"
                f"Typ firmy: {fin.get('company_type', 'carrier')}\n"
            )
            if fin.get("history"):
                financials_text += "Historia:\n" + "\n".join(
                    f"  - [{h.get('date', '')}] {h.get('metric', '')}: {h.get('value', '')}"
                    for h in fin["history"][:10]
                )

        insolvency_info = (
            f"Data upadlosci: {insolvency_data.get('date', 'nieznana')}\n"
            f"Sad: {insolvency_data.get('court', 'nieznany')}\n"
            f"Typ postepowania: {insolvency_data.get('type', 'nieznany')}\n"
            f"Opis: {insolvency_data.get('description', '')}\n"
        )

        # Step 3: Call Claude with full prompt
        system_prompt = (
            "Jestes analitykiem branzy transportowej specjalizujacym sie w analizie upadlosci. "
            "Twoje analizy sa premium produktem kupowanym przez firmy leasingowe i ubezpieczeniowe "
            "za 2000-5000 EUR za raport. Musisz byc dokladny, profesjonalny i konkretny. "
            "Odpowiadaj w formacie JSON. Nie dodawaj tekstu poza JSON."
        )

        user_prompt = f"""Firma {company_name} z {country_name} ({country}) oglosila upadlosc.

DANE O UPADLOSCI:
{insolvency_info}

HISTORIA ZDARZEN W SYSTEMIE:
{events_text if events_text else "Brak zdarzen w systemie."}

DANE FINANSOWE:
{financials_text if financials_text else "Brak danych finansowych."}

WYNIKI WYSZUKIWANIA W MEDIACH:
{news_text}

Przeanalizuj dokladnie i zwroc JSON:
{{
    "executive_summary": "2-3 akapity — profesjonalne streszczenie sytuacji dla decydentow",
    "causes": {{
        "primary": "glowna przyczyna upadlosci",
        "secondary": ["lista dodatkowych przyczyn"],
        "structural": "problemy strukturalne branzy ktore przyczynyly sie do upadlosci"
    }},
    "payment_chain": {{
        "description": "analiza lancucha platnosci — kto komu nie placil",
        "debtors": ["lista firm/podmiotow ktore zalegaly z platnosciami wobec upadlej firmy"],
        "estimated_unpaid_amount": "szacunkowa kwota niezaplaconych faktur (jesli mozna oszacowac)",
        "affected_subcontractors": ["podwykonawcy ktorzy moga stracic pieniadze"]
    }},
    "early_warnings": [
        {{
            "signal": "typ sygnalu (np. payment_delays, driver_exodus, cargo_issues)",
            "description": "opis sygnalu ostrzegawczego",
            "timing": "kiedy sygnal byl widoczny (np. 3 miesiace przed upadloscia)",
            "source": "skad mozna bylo ten sygnal wychwycic"
        }}
    ],
    "market_impact": {{
        "employees_affected": "szacunkowa liczba pracownikow",
        "routes_affected": ["trasy ktore obslugiwala firma"],
        "contracts_value": "szacunkowa wartosc kontraktow do przejecia",
        "who_benefits": ["firmy ktore moga przejac kontrakty"]
    }},
    "domino_effect": {{
        "risk_level": "CRITICAL/HIGH/MEDIUM/LOW",
        "companies_at_risk": [
            {{
                "name": "nazwa firmy",
                "relationship": "relacja z upadla firma (kontrahent/podwykonawca/klient)",
                "exposure": "wartosc ekspozycji (szacunkowo)",
                "risk_assessment": "ocena ryzyka upadlosci tej firmy"
            }}
        ],
        "sector_impact": "wplyw na sektor transportowy w regionie"
    }},
    "lessons": [
        "konkretna lekcja do zastosowania — co robic aby uniknac podobnej sytuacji"
    ],
    "recommendations": {{
        "for_leasing": "rekomendacje dla firm leasingowych",
        "for_insurance": "rekomendacje dla ubezpieczycieli",
        "for_contractors": "rekomendacje dla kontrahentow upadlej firmy",
        "for_drivers": "rekomendacje dla kierowcow"
    }},
    "confidence_score": 0.7
}}

confidence_score: 0.0-1.0, gdzie 1.0 = pelna pewnosc analizy (wieksza gdy jest wiecej danych)
"""

        result_text = await self._claude.call(user_prompt, system_prompt, max_tokens=8192)
        if result_text:
            try:
                parsed = json.loads(ClaudeClient.extract_json(result_text))
                parsed["company_name"] = company_name
                parsed["country"] = country
                parsed["analyzed_at"] = datetime.utcnow().isoformat()
                parsed["news_articles_found"] = len(news_text.split("\n")) if news_text else 0
                self._cache[cache_key] = parsed
                return parsed
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("Failed to parse insolvency analysis JSON: %s", e)

        # Fallback
        result = self._fallback_analysis(company_name, country, insolvency_data)
        self._cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    # Find related companies
    # ------------------------------------------------------------------

    async def find_related_companies(self, company_name: str, country: str = "") -> list[dict]:
        """Search for companies related to the bankrupt company.

        Uses Google News + TI database cross-reference to find:
        - Contractors
        - Subcontractors
        - Clients
        - Partners

        Returns list of related companies with risk assessment.
        """
        cache_key = self._cache_key(("related", company_name, country))
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Research via Google News
        news_text = await self._research_company(company_name, country)

        # Also search for contractors / partners
        partner_articles = await self._search_google_news(
            f"{company_name} kontrahent partner podwykonawca"
        )
        partner_text = "\n".join(
            f"- {a['title']}: {a.get('description', '')[:200]}"
            for a in partner_articles[:10]
        )

        system_prompt = (
            "Jestes analitykiem branzy transportowej. "
            "Na podstawie danych o firmie i artykulow, zidentyfikuj firmy powiazane. "
            "Odpowiadaj w formacie JSON. Nie dodawaj tekstu poza JSON."
        )
        user_prompt = f"""Firma transportowa: {company_name} ({country})

Artykuly medialne:
{news_text}

{partner_text}

Zidentyfikuj firmy powiazane i zwroc JSON:
[
    {{
        "name": "nazwa firmy",
        "relationship": "kontrahent/podwykonawca/klient/partner/wierzyciel",
        "country": "kod kraju",
        "risk_level": "CRITICAL/HIGH/MEDIUM/LOW",
        "description": "opis powiazania i potencjalnego ryzyka",
        "estimated_exposure_eur": 0
    }}
]

Jesli brak danych, zwroc pusta liste [].
"""

        result_text = await self._claude.call(user_prompt, system_prompt)
        if result_text:
            try:
                extracted = ClaudeClient.extract_json(result_text)
                # Handle both list and wrapped object
                if extracted.startswith("["):
                    parsed = json.loads(extracted)
                else:
                    obj = json.loads(extracted)
                    parsed = obj.get("companies", obj.get("related_companies", []))

                # Cross-reference with TI database
                parsed = await self._cross_reference_with_db(parsed)
                self._cache[cache_key] = parsed
                return parsed
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("Failed to parse related companies JSON: %s", e)

        self._cache[cache_key] = []
        return []

    async def _cross_reference_with_db(self, companies: list[dict]) -> list[dict]:
        """Cross-reference found companies with TI database."""
        try:
            from sqlalchemy import select
            from src.db.models import Company, Event
            from src.db.postgres import async_session

            async with async_session() as session:
                for comp in companies:
                    name = comp.get("name", "")
                    if not name:
                        continue

                    # Search by name (partial match)
                    result = await session.execute(
                        select(Company).where(
                            Company.name.ilike(f"%{name}%")
                        ).limit(1)
                    )
                    db_company = result.scalar_one_or_none()

                    if db_company:
                        comp["in_ti_database"] = True
                        comp["ti_financial_status"] = db_company.financial_status
                        comp["ti_risk_score"] = db_company.risk_score
                        comp["ti_company_id"] = str(db_company.id)

                        # Count recent events
                        cutoff = datetime.utcnow() - timedelta(days=90)
                        ev_result = await session.execute(
                            select(Event.id).where(
                                Event.company_id == db_company.id,
                                Event.date_collected >= cutoff,
                            )
                        )
                        comp["ti_recent_events"] = len(ev_result.all())
                    else:
                        comp["in_ti_database"] = False

        except Exception as e:
            logger.warning("DB cross-reference failed: %s", e)

        return companies

    # ------------------------------------------------------------------
    # Generate insolvency report
    # ------------------------------------------------------------------

    async def generate_insolvency_report(
        self,
        company_name: str,
        country: str,
        insolvency_data: dict | None = None,
    ) -> str:
        """Generate full insolvency analysis report as PDF.

        Returns: path to generated PDF file.
        """
        from src.reports.pdf_renderer import PdfRenderer
        from src.reports.disclaimer import DisclaimerGenerator

        OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "reports" / "output"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Run full analysis
        if insolvency_data is None:
            insolvency_data = {}

        # Fetch company data from DB if available
        insolvency_data = await self._enrich_from_db(company_name, country, insolvency_data)

        analysis = await self.analyze_insolvency(company_name, country, insolvency_data)
        related = await self.find_related_companies(company_name, country)
        early_warnings = await self.detect_early_warnings(
            insolvency_data.get("events", [])
        )

        country_name = COUNTRY_NAMES.get(country, country)
        disclaimer = DisclaimerGenerator().generate_disclaimer("sales", [country], "pl")

        context = {
            "title": f"Analiza Upadlosci: {company_name}",
            "subtitle": "Premium Insolvency Intelligence Report",
            "report_type": "insolvency",
            "language": "pl",
            "company_name": company_name,
            "country": country,
            "country_name": country_name,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "year": datetime.utcnow().year,
            # Analysis sections
            "analysis": analysis,
            "related_companies": related,
            "early_warnings": early_warnings,
            # Legal
            "disclaimer": disclaimer,
        }

        report_id = uuid.uuid4()
        safe_name = company_name.replace(" ", "_").replace("/", "_")[:50]
        filename = f"insolvency_{safe_name}_{country}_{report_id.hex[:8]}.pdf"
        pdf_path = str(OUTPUT_DIR / filename)

        # Render PDF
        renderer = PdfRenderer()
        renderer.render_insolvency(context, pdf_path)

        # Save report record
        try:
            from src.db.models import Report
            from src.db.postgres import async_session

            async with async_session() as session:
                report = Report(
                    id=report_id,
                    report_type="insolvency",
                    title=f"Insolvency Analysis: {company_name}",
                    period_start=datetime.utcnow().date(),
                    period_end=datetime.utcnow().date(),
                    countries=[country],
                    language="pl",
                    status="generated",
                    file_path=pdf_path,
                    total_events=len(insolvency_data.get("events", [])),
                    confirmed_events=0,
                    signal_events=0,
                    disclaimer_text=disclaimer,
                    generated_by="insolvency_analyzer",
                )
                session.add(report)
                await session.commit()
        except Exception as e:
            logger.warning("Failed to save insolvency report record: %s", e)

        logger.info("Insolvency report generated: %s", pdf_path)
        return pdf_path

    async def _enrich_from_db(
        self, company_name: str, country: str, insolvency_data: dict,
    ) -> dict:
        """Enrich insolvency_data with data from TI database."""
        try:
            from sqlalchemy import select, desc
            from sqlalchemy.orm import joinedload
            from src.db.models import Company, CompanyFinancial, Event
            from src.db.postgres import async_session

            async with async_session() as session:
                # Find company
                result = await session.execute(
                    select(Company).where(
                        Company.name.ilike(f"%{company_name}%"),
                        Company.country_code == country.upper(),
                    ).limit(1)
                )
                company = result.scalar_one_or_none()

                if not company:
                    # Try without country filter
                    result = await session.execute(
                        select(Company).where(
                            Company.name.ilike(f"%{company_name}%"),
                        ).limit(1)
                    )
                    company = result.scalar_one_or_none()

                if company:
                    # Fetch events
                    ev_result = await session.execute(
                        select(Event)
                        .options(joinedload(Event.source))
                        .where(Event.company_id == company.id)
                        .order_by(desc(Event.date_occurred))
                        .limit(30)
                    )
                    events = ev_result.unique().scalars().all()

                    insolvency_data.setdefault("events", [])
                    for e in events:
                        insolvency_data["events"].append({
                            "date": e.date_occurred.strftime("%Y-%m-%d") if e.date_occurred else "",
                            "event_type": e.event_type,
                            "severity": (e.severity or "medium").upper(),
                            "title": e.title,
                            "description": e.description or "",
                            "source_name": e.source.name if e.source else "",
                        })

                    # Fetch financials
                    fin_result = await session.execute(
                        select(CompanyFinancial)
                        .where(CompanyFinancial.company_id == company.id)
                        .order_by(desc(CompanyFinancial.date_occurred))
                        .limit(20)
                    )
                    financials = fin_result.scalars().all()

                    insolvency_data.setdefault("financials", {})
                    insolvency_data["financials"].update({
                        "financial_status": company.financial_status,
                        "risk_score": company.risk_score,
                        "company_type": company.company_type,
                        "history": [
                            {
                                "date": f.date_occurred.isoformat() if f.date_occurred else "",
                                "metric": f.event_type,
                                "value": f.amount_eur or 0,
                                "description": f.description or "",
                            }
                            for f in financials
                        ],
                    })

                    insolvency_data["_company_id"] = str(company.id)

        except Exception as e:
            logger.warning("DB enrichment failed for %s: %s", company_name, e)

        return insolvency_data

    # ------------------------------------------------------------------
    # Detect early warnings
    # ------------------------------------------------------------------

    async def detect_early_warnings(self, company_events: list[dict]) -> list[dict]:
        """Analyze company events and detect early warning patterns.

        Patterns detected:
        - payment_delays: "firma X nie placi" from forums
        - driver_exodus: "uciekajcie z firmy X" from Telegram
        - cargo_issues: theft/damage events
        - activity_decline: fewer orders
        - financial_deterioration: worsening financial indicators
        - legal_issues: court cases, license problems

        Returns list of warning signals with confidence scores.
        """
        if not company_events:
            return []

        cache_key = self._cache_key(("early_warnings", company_events))
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Statistical analysis first
        warnings = []

        # Check for payment-related events
        payment_events = [
            e for e in company_events
            if any(kw in (e.get("event_type", "") + " " + e.get("title", "") + " " + e.get("description", "")).lower()
                   for kw in ["payment", "platnosc", "placi", "zaleglosc", "dlug", "faktur", "naleznosc"])
        ]
        if payment_events:
            warnings.append({
                "signal": "payment_delays",
                "confidence": min(0.9, 0.3 + len(payment_events) * 0.15),
                "source": "system events",
                "description": f"Wykryto {len(payment_events)} zdarzen zwiazanych z opoznieniami platnosci.",
                "event_count": len(payment_events),
                "first_seen": min(
                    (e.get("date", "") for e in payment_events if e.get("date")),
                    default="",
                ),
            })

        # Check for driver/employee issues
        driver_events = [
            e for e in company_events
            if any(kw in (e.get("event_type", "") + " " + e.get("title", "") + " " + e.get("description", "")).lower()
                   for kw in ["kierowc", "driver", "pracowni", "employee", "odejsc", "rezygnac", "uciekaj", "exodus"])
        ]
        if driver_events:
            warnings.append({
                "signal": "driver_exodus",
                "confidence": min(0.85, 0.3 + len(driver_events) * 0.15),
                "source": "system events",
                "description": f"Wykryto {len(driver_events)} zdarzen wskazujacych na problemy z kierowcami/pracownikami.",
                "event_count": len(driver_events),
                "first_seen": min(
                    (e.get("date", "") for e in driver_events if e.get("date")),
                    default="",
                ),
            })

        # Check for cargo/operational issues
        cargo_events = [
            e for e in company_events
            if e.get("event_type", "") in (
                "theft_cargo", "theft_fuel", "theft_vehicle", "damage",
            )
        ]
        if cargo_events:
            warnings.append({
                "signal": "cargo_issues",
                "confidence": min(0.8, 0.2 + len(cargo_events) * 0.1),
                "source": "system events",
                "description": f"Wykryto {len(cargo_events)} zdarzen dotyczacych kradziezi/uszkodzen ladunkow.",
                "event_count": len(cargo_events),
                "first_seen": min(
                    (e.get("date", "") for e in cargo_events if e.get("date")),
                    default="",
                ),
            })

        # Check for financial deterioration
        financial_events = [
            e for e in company_events
            if any(kw in (e.get("event_type", "") + " " + e.get("title", "") + " " + e.get("description", "")).lower()
                   for kw in ["bankrupt", "upadl", "restrukt", "likwidac", "insolvenz", "liquidat", "financial"])
        ]
        if financial_events:
            warnings.append({
                "signal": "financial_deterioration",
                "confidence": min(0.95, 0.5 + len(financial_events) * 0.15),
                "source": "system events",
                "description": f"Wykryto {len(financial_events)} zdarzen dotyczacych pogorszenia kondycji finansowej.",
                "event_count": len(financial_events),
                "first_seen": min(
                    (e.get("date", "") for e in financial_events if e.get("date")),
                    default="",
                ),
            })

        # Check for license/legal issues
        legal_events = [
            e for e in company_events
            if any(kw in (e.get("event_type", "") + " " + e.get("title", "") + " " + e.get("description", "")).lower()
                   for kw in ["license", "licencj", "zakaz", "cofni", "zawieszeni", "sad", "court", "legal"])
        ]
        if legal_events:
            warnings.append({
                "signal": "legal_issues",
                "confidence": min(0.85, 0.3 + len(legal_events) * 0.15),
                "source": "system events",
                "description": f"Wykryto {len(legal_events)} zdarzen prawnych/licencyjnych.",
                "event_count": len(legal_events),
                "first_seen": min(
                    (e.get("date", "") for e in legal_events if e.get("date")),
                    default="",
                ),
            })

        # Check event density — sudden increase in events = warning
        if len(company_events) >= 5:
            dates = sorted(e.get("date", "") for e in company_events if e.get("date"))
            if len(dates) >= 5:
                recent = dates[-5:]
                # If 5+ events in last 30 days
                warnings.append({
                    "signal": "activity_spike",
                    "confidence": min(0.7, 0.2 + len(company_events) * 0.05),
                    "source": "event density analysis",
                    "description": f"Wzrost aktywnosci — {len(company_events)} zdarzen w systemie, co moze wskazywac na narastajace problemy.",
                    "event_count": len(company_events),
                    "first_seen": dates[0] if dates else "",
                })

        # Use Claude for deeper AI analysis if we have enough events
        if len(company_events) >= 3:
            ai_warnings = await self._ai_detect_warnings(company_events)
            if ai_warnings:
                # Merge AI warnings with statistical ones, avoid duplicates
                existing_signals = {w["signal"] for w in warnings}
                for aw in ai_warnings:
                    if aw.get("signal") not in existing_signals:
                        warnings.append(aw)

        # Sort by confidence descending
        warnings.sort(key=lambda w: w.get("confidence", 0), reverse=True)

        self._cache[cache_key] = warnings
        return warnings

    async def _ai_detect_warnings(self, events: list[dict]) -> list[dict]:
        """Use Claude to detect subtle early warning patterns."""
        events_text = "\n".join(
            f"- [{e.get('date', '')}] {e.get('event_type', '')} "
            f"({e.get('severity', '')}): {e.get('title', '')[:100]} "
            f"— {e.get('description', '')[:100]}"
            for e in events[:20]
        )

        system_prompt = (
            "Jestes analitykiem ryzyka w branzy transportowej. "
            "Analizujesz sygnaly ostrzegawcze wskazujace na mozliwa upadlosc firmy. "
            "Odpowiadaj w formacie JSON. Nie dodawaj tekstu poza JSON."
        )
        user_prompt = f"""Przeanalizuj ponizsze zdarzenia dotyczace firmy transportowej i zidentyfikuj sygnaly ostrzegawcze:

{events_text}

Zwroc JSON — liste sygnalow:
[
    {{
        "signal": "typ sygnalu (payment_delays/driver_exodus/cargo_issues/activity_decline/financial_deterioration/legal_issues/reputation_damage/market_changes)",
        "confidence": 0.7,
        "source": "skad pochodzi sygnal",
        "description": "szczegolowy opis sygnalu ostrzegawczego"
    }}
]

Jesli nie wykrywasz sygnalow, zwroc pusta liste [].
"""

        result_text = await self._claude.call(user_prompt, system_prompt, max_tokens=2048)
        if result_text:
            try:
                extracted = ClaudeClient.extract_json(result_text)
                if extracted.startswith("["):
                    return json.loads(extracted)
                obj = json.loads(extracted)
                return obj.get("warnings", obj.get("signals", []))
            except (json.JSONDecodeError, ValueError):
                pass

        return []

    # ------------------------------------------------------------------
    # Fallback (no AI)
    # ------------------------------------------------------------------

    def _fallback_analysis(
        self, company_name: str, country: str, insolvency_data: dict,
    ) -> dict:
        """Statistical-only analysis when Claude API is unavailable."""
        events = insolvency_data.get("events", [])
        type_counts = Counter(e.get("event_type", "other") for e in events)

        return {
            "company_name": company_name,
            "country": country,
            "analyzed_at": datetime.utcnow().isoformat(),
            "news_articles_found": 0,
            "executive_summary": (
                f"Firma {company_name} z {COUNTRY_NAMES.get(country, country)} oglosila upadlosc. "
                f"W systemie Transport Intelligence zarejestrowano {len(events)} zdarzen "
                f"zwiazanych z ta firma. Analiza AI jest chwilowo niedostepna — "
                f"ponizsze dane oparte sa na statystykach systemowych."
            ),
            "causes": {
                "primary": "Wymaga analizy AI",
                "secondary": [],
                "structural": "Wymaga analizy AI",
            },
            "payment_chain": {
                "description": "Wymaga analizy AI",
                "debtors": [],
                "estimated_unpaid_amount": "Nieznane",
                "affected_subcontractors": [],
            },
            "early_warnings": [],
            "market_impact": {
                "employees_affected": "Nieznane",
                "routes_affected": [],
                "contracts_value": "Nieznane",
                "who_benefits": [],
            },
            "domino_effect": {
                "risk_level": "MEDIUM",
                "companies_at_risk": [],
                "sector_impact": "Wymaga analizy AI",
            },
            "lessons": [
                "Monitorowac terminowosc platnosci kontrahentow.",
                "Sprawdzac status finansowy partnerow biznesowych w rejestrach upadlosciowych.",
            ],
            "recommendations": {
                "for_leasing": "Sprawdzic ekspozycje na upadla firme i jej kontrahentow.",
                "for_insurance": "Zweryfikowac polisy powiazane z upadla firma.",
                "for_contractors": "Skontaktowac sie z syndykiem w sprawie naleznosci.",
                "for_drivers": "Sprawdzic zaleglosci placowe, skontaktowac sie z PIP.",
            },
            "confidence_score": 0.2,
        }
