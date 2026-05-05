"""AustrianInsolvencyAgent — scraper edikte.justiz.gv.at.

Scrapuje ogloszenia o upadlosciach firm transportowych z oficjalnego
portalu austriackich edyktow sadowych.
"""

import asyncio
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType

logger = logging.getLogger(__name__)

EDIKTE_URL = "https://edikte.justiz.gv.at/edikte/edikthome.nsf/suche"
EDIKTE_BASE = "https://edikte.justiz.gv.at"

USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"

TRANSPORT_KEYWORDS = [
    "insolvenz", "transport", "spedition", "logistik",
    "frachtführer", "frachtfuhrer", "güterverkehr", "gueterverkehr",
    "lkw", "güterkraftverkehr", "gueterkraftverkehr",
    "spediteur", "frächter", "frachter", "transportgewerbe",
    "fuhrunternehmen", "fernverkehr", "nahverkehr",
    "lastkraftwagen", "güterbeforderung", "gueterbeforderung",
]

SEARCH_TERMS = [
    "Transport", "Spedition", "Logistik",
    "Güterverkehr",
]

RATE_LIMIT_SECONDS = 5.0


class AustrianInsolvencyAgent(BaseAgent):
    """Agent scrapujacy edikte.justiz.gv.at — austriackie edykty upadlosciowe.

    Przeszukuje portal edyktow sadowych w kategorii Insolvenzedikt
    pod katem firm transportowych i spedycyjnych.
    """

    def __init__(self, event_queue=None):
        super().__init__(
            country_code="AT",
            language="de",
            source_type=SourceType.FINANCIAL,
            source_name="Edikte Justiz AT",
            source_url=EDIKTE_URL,
            trust_score=1.0,
            is_official=True,
            scrape_interval_minutes=360,
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
            self._logger.debug("Rate limit: czekam %.1fs", wait)
            await asyncio.sleep(wait)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _fetch_url(self, url: str, method: str = "GET", data: dict | None = None) -> str:
        """Pobiera HTML z podanego URL z rate limiting."""
        await self._rate_limit()
        session = await self.get_session()
        headers = {"User-Agent": USER_AGENT}
        self._logger.info("Fetching: %s (method=%s)", url, method)
        start = asyncio.get_event_loop().time()
        if method == "POST" and data:
            response = await session.post(url, headers=headers, data=data)
        else:
            response = await session.get(url, headers=headers)
        response.raise_for_status()
        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
        self._logger.info(
            "Fetch OK: HTTP %d, %d bytes, %.0fms",
            response.status_code, len(response.text), elapsed_ms,
        )
        return response.text

    async def fetch(self) -> str:
        """Pobiera wyniki wyszukiwania z edikte.justiz.gv.at."""
        all_html_parts = []
        for term in SEARCH_TERMS:
            form_data = {
                "Ession": "Insolvenzedikt",
                "Name": term,
                "Suchbutton": "Suche+starten",
            }
            try:
                html = await self._fetch_url(EDIKTE_URL, method="POST", data=form_data)
                all_html_parts.append(html)
            except Exception as e:
                self._logger.warning("Search for '%s' failed: %s", term, e)
        return "\n<!-- SEPARATOR -->\n".join(all_html_parts)

    async def parse(self, raw_data: str) -> list[dict]:
        """Parsuje wyniki wyszukiwania edyktow upadlosciowych."""
        events = []
        seen_titles = set()

        for html_part in raw_data.split("\n<!-- SEPARATOR -->\n"):
            if not html_part.strip():
                continue
            soup = BeautifulSoup(html_part, "html.parser")

            items = (
                soup.select("tr.result")
                or soup.select("div.result")
                or soup.select("li.result")
                or soup.select("table tr")
                or soup.select("div.treffer")
            )

            if not items:
                for link in soup.find_all("a", href=True):
                    href = link.get("href", "")
                    if any(kw in href.lower() for kw in ["edikt", "detail", "insolvenz"]):
                        parent = link.find_parent(["div", "li", "tr", "section"])
                        if parent and parent not in items:
                            items.append(parent)

            for item in items:
                parsed = self._parse_item(item)
                if not parsed:
                    continue

                title = parsed.get("title", "")
                description = parsed.get("description", "")
                full_text = f"{title} {description}".lower()

                if self._is_transport_related(full_text):
                    title_key = title.strip().lower()
                    if title_key and title_key not in seen_titles:
                        seen_titles.add(title_key)
                        events.append(self._make_event(parsed))

        self._logger.info("AT Insolvency: %d transport-related events", len(events))
        return events

    def _parse_item(self, item) -> dict | None:
        """Parsuje pojedynczy element wyniku wyszukiwania."""
        result = {}

        title_el = item.find(["h2", "h3", "h4", "strong", "b"])
        if title_el:
            result["title"] = title_el.get_text(strip=True)
        else:
            link = item.find("a")
            if link:
                result["title"] = link.get_text(strip=True)
            else:
                # For table rows, concatenate cell text
                cells = item.find_all("td")
                if cells:
                    text = " | ".join(c.get_text(strip=True) for c in cells if c.get_text(strip=True))
                    if len(text) > 10:
                        result["title"] = text[:200]
                    else:
                        return None
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
                href = EDIKTE_BASE + href
            elif not href.startswith("http"):
                href = EDIKTE_BASE + "/" + href
            result["link"] = href
        else:
            result["link"] = EDIKTE_URL

        desc_el = item.find("p")
        if desc_el:
            result["description"] = desc_el.get_text(strip=True)
        else:
            full_text = item.get_text(strip=True)
            title_text = result.get("title", "")
            desc = full_text.replace(title_text, "").strip()
            result["description"] = desc[:500] if desc else ""

        result["date"] = self._extract_date(item)

        # Extract court name
        text = item.get_text()
        court_pattern = re.search(r"(Bezirksgericht|BG|Landesgericht|LG|Handelsgericht|HG)\s+[\w\-äöüÄÖÜß]+", text)
        if court_pattern:
            result["court"] = court_pattern.group(0)

        return result

    def _make_event(self, parsed: dict) -> dict:
        """Tworzy event dict z parsed data."""
        description = parsed.get("description", "")
        if parsed.get("court"):
            description = f"{description} — {parsed['court']}"

        return {
            "title": parsed.get("title", ""),
            "description": description,
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", EDIKTE_URL),
            "raw_text": f"{parsed.get('title', '')}\n{description}",
            "country_code": "AT",
            "language": "de",
            "source_name": "Edikte Justiz AT",
            "trust_score": 1.0,
            "is_official": True,
            "source_type": SourceType.FINANCIAL.value,
            "timestamp": parsed.get("date") or datetime.utcnow().isoformat(),
            "collected_at": datetime.utcnow().isoformat(),
        }

    def _extract_date(self, item) -> str:
        """Wyciaga date z elementu HTML."""
        time_el = item.find("time")
        if time_el:
            dt = time_el.get("datetime", "")
            if dt:
                return dt
            return time_el.get_text(strip=True)

        for cls_name in ["date", "datum", "data"]:
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

    def _is_transport_related(self, text: str) -> bool:
        """Sprawdza czy tekst dotyczy firm transportowych."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in TRANSPORT_KEYWORDS)
