"""DebtRegistryAgent — monitors European debtor registries for transport companies.

Scrapuje rejestry dluznikow w Europie:
- PL: KRD (krd.pl), BIG InfoMonitor (big.pl)
- DE: Bundesanzeiger (bundesanzeiger.de) — insolvency/debt announcements
- FR: BODACC (bodacc.fr) — creditor announcements
- GB: The Gazette (thegazette.co.uk) — winding-up petitions
- EU: OpenCorporates API — company status checks
"""

import asyncio
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType

logger = logging.getLogger(__name__)

USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"

RATE_LIMIT_SECONDS = 5.0

# ---------------------------------------------------------------------------
# Registry sources
# ---------------------------------------------------------------------------

REGISTRIES = [
    {
        "name": "KRD",
        "country": "PL",
        "language": "pl",
        "url": "https://krd.pl/",
        "method": "html",
        "description": "Krajowy Rejestr Dlugów — Polish debt registry",
    },
    {
        "name": "BIG InfoMonitor",
        "country": "PL",
        "language": "pl",
        "url": "https://www.big.pl/",
        "method": "html",
        "description": "BIG InfoMonitor — Polish debtor registry",
    },
    {
        "name": "Bundesanzeiger",
        "country": "DE",
        "language": "de",
        "url": "https://www.bundesanzeiger.de/",
        "method": "html",
        "description": "Bundesanzeiger — German insolvency/debt announcements",
    },
    {
        "name": "BODACC",
        "country": "FR",
        "language": "fr",
        "url": "https://www.bodacc.fr/",
        "method": "html",
        "description": "BODACC — French creditor announcements",
    },
    {
        "name": "The Gazette",
        "country": "GB",
        "language": "en",
        "url": "https://www.thegazette.co.uk/",
        "method": "html",
        "description": "The Gazette — UK winding-up petitions",
    },
    {
        "name": "OpenCorporates",
        "country": "EU",
        "language": "en",
        "url": "https://api.opencorporates.com/",
        "method": "api",
        "description": "OpenCorporates — company status checks (REST API)",
    },
]

# ---------------------------------------------------------------------------
# Transport keywords per language
# ---------------------------------------------------------------------------

TRANSPORT_KEYWORDS = {
    "pl": [
        "transport", "spedycja", "przewóz", "przewoz", "logistyka", "fracht",
        "tir", "ciężarowy", "ciezarowy", "naczep", "przewoźnik", "przewoznik",
        "transportowy", "spedycyjna", "logistyczny",
    ],
    "de": [
        "transport", "spedition", "logistik", "fracht", "lkw", "güterverkehr",
        "gueterverkehr", "speditions", "transportfirma", "transportunternehmen",
    ],
    "fr": [
        "transport", "logistique", "fret", "routier", "camionnage",
        "transporteur", "logistiques",
    ],
    "en": [
        "transport", "logistics", "haulage", "freight", "carrier", "trucking",
        "haulier", "road freight",
    ],
}

# Event type mapping for debt types
DEBT_TYPE_MAP = {
    "debt": "payment_issue",
    "late_filing": "payment_issue",
    "winding_up": "bankruptcy",
    "insolvency": "bankruptcy",
    "liquidation": "bankruptcy",
    "creditor_claim": "payment_issue",
}


class DebtRegistryAgent(BaseAgent):
    """Agent monitoring European debtor registries for transport companies.

    Checks KRD, BIG, Bundesanzeiger, BODACC, The Gazette, and OpenCorporates
    for debt entries related to transport/logistics companies.
    """

    def __init__(self, event_queue=None):
        super().__init__(
            country_code="EU",
            language="en",
            source_type=SourceType.FINANCIAL,
            source_name="EU Debt Registries",
            source_url="https://krd.pl/",
            trust_score=1.0,
            is_official=True,
            scrape_interval_minutes=720,
            event_queue=event_queue,
            max_retries=3,
            base_retry_delay=10.0,
        )
        self._last_request_time: float = 0.0

    async def _rate_limit(self):
        """Enforce rate limiting — max 1 request per RATE_LIMIT_SECONDS."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            wait = RATE_LIMIT_SECONDS - elapsed
            self._logger.debug("Rate limit: waiting %.1fs", wait)
            await asyncio.sleep(wait)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _fetch_url(self, url: str) -> str:
        """Fetch HTML/JSON from URL with rate limiting."""
        await self._rate_limit()
        session = await self.get_session()
        headers = {"User-Agent": USER_AGENT}
        self._logger.info("Fetching: %s", url)
        start = asyncio.get_event_loop().time()
        response = await session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
        self._logger.info(
            "Fetch OK: HTTP %d, %d bytes, %.0fms",
            response.status_code, len(response.text), elapsed_ms,
        )
        return response.text

    async def fetch(self) -> str:
        """Fetch data from all debt registries with rate limiting between requests."""
        parts = []

        for reg in REGISTRIES:
            try:
                content = await self._fetch_url(reg["url"])
                marker = reg["name"].upper().replace(" ", "_")
                parts.append(
                    f"<!-- {marker} country={reg['country']} lang={reg['language']} -->\n{content}"
                )
            except Exception as e:
                self._logger.warning("%s fetch failed: %s", reg["name"], e)

        return "\n<!-- SEPARATOR -->\n".join(parts)

    async def parse(self, raw_data: str) -> list[dict]:
        """Parse fetched data — split by separator, route to per-registry parser."""
        events = []
        seen_titles = set()

        for part in raw_data.split("\n<!-- SEPARATOR -->\n"):
            if not part.strip():
                continue

            # Extract metadata from marker comment
            meta = self._extract_marker_meta(part)
            registry_name = meta.get("name", "unknown")
            country = meta.get("country", "EU")
            lang = meta.get("lang", "en")

            # Remove marker line
            content = re.sub(r"^<!--.*?-->\n?", "", part, count=1).strip()
            if not content:
                continue

            if registry_name == "OPENCORPORATES":
                parsed = self._parse_opencorporates(content, country, lang, seen_titles)
            else:
                parsed = self._parse_html_registry(
                    content, registry_name, country, lang, seen_titles,
                )

            events.extend(parsed)

        self._logger.info("EU Debt Registries: %d transport-related events", len(events))
        return events

    def _extract_marker_meta(self, part: str) -> dict:
        """Extract registry metadata from the marker comment."""
        meta = {}
        m = re.match(r"<!-- (\S+)\s+country=(\S+)\s+lang=(\S+)\s*-->", part)
        if m:
            meta["name"] = m.group(1)
            meta["country"] = m.group(2)
            meta["lang"] = m.group(3)
        return meta

    def _parse_html_registry(
        self, html: str, registry_name: str, country: str, lang: str,
        seen_titles: set,
    ) -> list[dict]:
        """Parse HTML from any debt registry — generic parser."""
        soup = BeautifulSoup(html, "html.parser")
        events = []

        # Try common HTML structures
        items = (
            soup.select("div.result, div.entry, div.announcement, div.notice")
            or soup.select("article")
            or soup.select("div.list-item, li.search-result")
            or soup.select("tr")
        )

        # Fallback: look for links with debt-related keywords
        if not items:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "").lower()
                text = link.get_text(strip=True).lower()
                debt_hints = ["debt", "dlug", "schuld", "créance", "creance",
                              "insolvency", "winding", "petition", "upadl"]
                if any(kw in href or kw in text for kw in debt_hints):
                    parent = link.find_parent(["div", "li", "article", "tr", "section"])
                    if parent and parent not in items:
                        items.append(parent)

        keywords = TRANSPORT_KEYWORDS.get(lang, TRANSPORT_KEYWORDS["en"])
        registry_url = next(
            (r["url"] for r in REGISTRIES if r["name"].upper().replace(" ", "_") == registry_name),
            "",
        )

        for item in items:
            parsed = self._parse_item(item, base_url=registry_url)
            if not parsed:
                continue

            title = parsed.get("title", "")
            description = parsed.get("description", "")
            full_text = f"{title} {description}".lower()

            if self._is_transport_related(full_text, keywords):
                title_key = title.strip().lower()
                if title_key and title_key not in seen_titles:
                    seen_titles.add(title_key)
                    debt_type = self._classify_debt_type(full_text, lang)
                    amount = self._extract_amount(full_text)
                    events.append(self._make_event(
                        parsed,
                        registry_name=registry_name,
                        country=country,
                        lang=lang,
                        debt_type=debt_type,
                        amount_eur=amount,
                    ))

        return events

    def _parse_opencorporates(
        self, content: str, country: str, lang: str, seen_titles: set,
    ) -> list[dict]:
        """Parse OpenCorporates API response (JSON)."""
        import json

        events = []
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            # Might be HTML error page
            self._logger.warning("OpenCorporates response is not JSON")
            return events

        companies = []
        if isinstance(data, dict):
            results = data.get("results", data)
            if isinstance(results, dict):
                companies = results.get("companies", [])
            elif isinstance(results, list):
                companies = results

        keywords = TRANSPORT_KEYWORDS.get("en", [])

        for entry in companies:
            company = entry.get("company", entry) if isinstance(entry, dict) else {}
            name = company.get("name", "")
            status = company.get("current_status", "")
            jurisdiction = company.get("jurisdiction_code", "")

            full_text = f"{name} {status}".lower()
            if not self._is_transport_related(full_text, keywords):
                continue

            inactive_statuses = [
                "dissolved", "liquidation", "struck off", "inactive",
                "in administration", "winding up",
            ]
            if not any(s in status.lower() for s in inactive_statuses):
                continue

            title_key = name.strip().lower()
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                debt_type = "liquidation" if "liquidat" in status.lower() else "insolvency"
                events.append(self._make_event(
                    {
                        "title": name,
                        "description": f"Company status: {status} (jurisdiction: {jurisdiction})",
                        "link": company.get("opencorporates_url", "https://api.opencorporates.com/"),
                        "date": company.get("updated_at", ""),
                    },
                    registry_name="OpenCorporates",
                    country=jurisdiction[:2].upper() if jurisdiction else "EU",
                    lang="en",
                    debt_type=debt_type,
                    amount_eur=None,
                ))

        return events

    def _parse_item(self, item, base_url: str = "") -> dict | None:
        """Parse a single HTML element into a dict."""
        result = {}

        title_el = item.find(["h2", "h3", "h4", "strong"])
        if title_el:
            result["title"] = title_el.get_text(strip=True)
        else:
            link = item.find("a")
            if link:
                result["title"] = link.get_text(strip=True)
            else:
                text = item.get_text(strip=True)
                if len(text) > 10:
                    result["title"] = text[:200]
                else:
                    return None

        if not result.get("title") or len(result["title"]) < 5:
            return None

        link_el = item.find("a", href=True)
        if link_el:
            href = link_el["href"]
            if href.startswith("/"):
                href = base_url.rstrip("/") + href
            elif not href.startswith("http"):
                href = base_url.rstrip("/") + "/" + href
            result["link"] = href
        else:
            result["link"] = base_url

        desc_el = item.find("p")
        if desc_el:
            result["description"] = desc_el.get_text(strip=True)
        else:
            full_text = item.get_text(strip=True)
            title_text = result.get("title", "")
            desc = full_text.replace(title_text, "").strip()
            result["description"] = desc[:500] if desc else ""

        result["date"] = self._extract_date(item)
        return result

    def _make_event(
        self,
        parsed: dict,
        registry_name: str = "unknown",
        country: str = "EU",
        lang: str = "en",
        debt_type: str = "debt",
        amount_eur: float | None = None,
    ) -> dict:
        """Create event dict from parsed data."""
        company_name = parsed.get("title", "Unknown")
        event_type = DEBT_TYPE_MAP.get(debt_type, "payment_issue")

        return {
            "title": f"[DEBT] {company_name} — {debt_type}",
            "description": f"Debt registry entry: {parsed.get('description', '')[:500]}",
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", ""),
            "raw_text": f"{parsed.get('title', '')}\n{parsed.get('description', '')}",
            "event_type": event_type,
            "severity": "high",
            "country_code": country,
            "language": lang,
            "source_name": registry_name,
            "trust_score": 1.0,
            "is_official": True,
            "source_type": SourceType.FINANCIAL.value,
            "intelligence_tier": 2,
            "tags": ["debt_registry", debt_type, registry_name],
            "financial_impact_eur": amount_eur,
            "timestamp": parsed.get("date") or datetime.utcnow().isoformat(),
            "collected_at": datetime.utcnow().isoformat(),
        }

    def _extract_date(self, item) -> str:
        """Extract date from HTML element."""
        time_el = item.find("time")
        if time_el:
            dt = time_el.get("datetime", "")
            if dt:
                return dt
            return time_el.get_text(strip=True)

        for cls_name in ["date", "data", "datum"]:
            date_el = item.find(class_=re.compile(cls_name, re.IGNORECASE))
            if date_el:
                return date_el.get_text(strip=True)

        text = item.get_text()
        m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", text)
        if m:
            return m.group(1)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)

        return ""

    def _is_transport_related(self, text: str, keywords: list[str]) -> bool:
        """Check if text relates to transport companies."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)

    def _classify_debt_type(self, text: str, lang: str) -> str:
        """Classify the type of debt entry from text content."""
        text_lower = text.lower()

        winding_up_terms = [
            "winding up", "winding-up", "liquidat", "likwidac",
            "auflösung", "auflosung", "dissolution",
        ]
        if any(t in text_lower for t in winding_up_terms):
            return "winding_up"

        insolvency_terms = [
            "insolvency", "insolven", "upadłość", "upadlosc",
            "bankrupt", "bankrott", "faillite",
        ]
        if any(t in text_lower for t in insolvency_terms):
            return "insolvency"

        late_filing_terms = [
            "late filing", "overdue", "zaległ", "zalegl",
            "verspätet", "verspaetet", "retard",
        ]
        if any(t in text_lower for t in late_filing_terms):
            return "late_filing"

        creditor_terms = [
            "creditor", "wierzyciel", "gläubiger", "glaeubiger",
            "créancier", "creancier",
        ]
        if any(t in text_lower for t in creditor_terms):
            return "creditor_claim"

        return "debt"

    def _extract_amount(self, text: str) -> float | None:
        """Try to extract a monetary amount in EUR from text."""
        # Match patterns like: 123,456.78 EUR, EUR 123456, 123.456,78 €
        patterns = [
            r"([\d.,]+)\s*(?:EUR|eur|€)",
            r"(?:EUR|eur|€)\s*([\d.,]+)",
            r"([\d.,]+)\s*(?:PLN|pln|zł|zl)",
            r"([\d.,]+)\s*(?:GBP|gbp|£)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                amount_str = m.group(1)
                try:
                    # Handle European number format (1.234.567,89)
                    if "," in amount_str and "." in amount_str:
                        if amount_str.rindex(",") > amount_str.rindex("."):
                            amount_str = amount_str.replace(".", "").replace(",", ".")
                        else:
                            amount_str = amount_str.replace(",", "")
                    elif "," in amount_str:
                        amount_str = amount_str.replace(",", ".")
                    amount = float(amount_str)
                    # Rough conversion for non-EUR currencies
                    if "PLN" in text or "pln" in text or "zł" in text or "zl" in text:
                        amount *= 0.23
                    elif "GBP" in text or "gbp" in text or "£" in text:
                        amount *= 1.16
                    return round(amount, 2)
                except (ValueError, TypeError):
                    pass
        return None
