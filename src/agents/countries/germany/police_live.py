"""BundespolizeiAgent — live scraper dla strony Bundespolizei.

Scrapuje komunikaty policyjne z dwoch zrodel:
1. https://www.bundespolizei.de/aktuelles/meldungen — oficjalne komunikaty
2. https://www.presseportal.de/blaulicht/d/bundespolizei — komunikaty prasowe Bundespolizei

Filtruje te dotyczace transportu (kradzieze, wypadki, przemyt na autostradach).
"""

import asyncio
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType
from src.agents.transport_keywords import is_transport_related

logger = logging.getLogger(__name__)

BUNDESPOLIZEI_URL = "https://www.bundespolizei.de/aktuelles/meldungen"
PRESSEPORTAL_URL = "https://www.presseportal.de/blaulicht/d/bundespolizei"

USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"

# Rate limiting: min seconds between requests
RATE_LIMIT_SECONDS = 5.0


class BundespolizeiAgent(BaseAgent):
    """Agent scrapujacy komunikaty Bundespolizei dot. transportu.

    Scrapuje z dwoch zrodel:
    - bundespolizei.de/aktuelles/meldungen (oficjalne komunikaty)
    - presseportal.de/blaulicht/d/bundespolizei (komunikaty prasowe)

    Respektuje robots.txt, uzywa rate-limiting (max 1 req / 5s),
    custom User-Agent z danymi kontaktowymi.
    """

    def __init__(self, event_queue=None):
        super().__init__(
            country_code="DE",
            language="de",
            source_type=SourceType.POLICE,
            source_name="Bundespolizei",
            source_url=BUNDESPOLIZEI_URL,
            trust_score=1.0,
            is_official=True,
            scrape_interval_minutes=60,
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

    async def _fetch_url(self, url: str) -> str:
        """Pobiera HTML z podanego URL z rate limiting."""
        await self._rate_limit()

        session = await self.get_session()
        headers = {"User-Agent": USER_AGENT}

        self._logger.info("Fetching: %s", url)
        start = asyncio.get_event_loop().time()

        response = await session.get(url, headers=headers)
        response.raise_for_status()

        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
        self._logger.info(
            "Fetch OK: HTTP %d, %d bytes, %.0fms",
            response.status_code,
            len(response.text),
            elapsed_ms,
        )
        return response.text

    async def fetch(self) -> str:
        """Pobiera HTML z obu zrodel i laczy je.

        Zwraca HTML z separatorem miedzy zrodlami.
        Jesli jedno zrodlo nie odpowiada, kontynuuje z drugim.
        """
        parts = []

        # Source 1: Presseportal (primary — more transport-related content)
        try:
            html = await self._fetch_url(PRESSEPORTAL_URL)
            parts.append(f"<!-- SOURCE:presseportal -->\n{html}")
        except Exception as e:
            self._logger.warning("Presseportal fetch failed: %s", e)

        # Source 2: Bundespolizei official
        try:
            html = await self._fetch_url(BUNDESPOLIZEI_URL)
            parts.append(f"<!-- SOURCE:bundespolizei -->\n{html}")
        except Exception as e:
            self._logger.warning("Bundespolizei.de fetch failed: %s", e)

        if not parts:
            raise RuntimeError("Oba zrodla niedostepne")

        return "\n<!-- SEPARATOR -->\n".join(parts)

    async def parse(self, raw_data: str) -> list[dict]:
        """Parsuje HTML z obu zrodel komunikatow Bundespolizei.

        Dla kazdego komunikatu:
        1. Wyciaga tytul, date, link, opis
        2. Sprawdza keyword matching (transport-related)
        3. Jesli dotyczy transportu -> tworzy event dict
        """
        events = []
        seen_titles = set()

        # Split by source separator
        source_blocks = raw_data.split("<!-- SEPARATOR -->")

        for block in source_blocks:
            if "SOURCE:presseportal" in block:
                block_events = self._parse_presseportal(block)
            elif "SOURCE:bundespolizei" in block:
                block_events = self._parse_bundespolizei(block)
            else:
                block_events = self._parse_bundespolizei(block)

            for ev in block_events:
                # Dedup by title
                title_key = ev.get("title", "").strip().lower()
                if title_key and title_key not in seen_titles:
                    seen_titles.add(title_key)
                    events.append(ev)

        self._logger.info("Parse total: %d transport-related events", len(events))
        return events

    # -- Presseportal parser ------------------------------------------------

    def _parse_presseportal(self, html: str) -> list[dict]:
        """Parsuje komunikaty prasowe z presseportal.de."""
        soup = BeautifulSoup(html, "html.parser")
        events = []

        # Presseportal structure: article elements or list-items
        items = soup.select("article") or soup.select("div.news-item")
        if not items:
            # Fallback: find all links to /blaulicht/pm/
            items = []
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if "/blaulicht/pm/" in href:
                    parent = link.find_parent(["div", "li", "article", "section"])
                    if parent and parent not in items:
                        items.append(parent)

        self._logger.info("Presseportal: znaleziono %d elementow", len(items))
        transport_count = 0

        for item in items:
            parsed = self._parse_presseportal_item(item)
            if not parsed:
                continue

            title = parsed.get("title", "")
            description = parsed.get("description", "")
            full_text = f"{title} {description}".lower()

            if self._is_transport_related(full_text):
                transport_count += 1
                events.append(self._make_event(parsed, "Presseportal/Bundespolizei"))

        self._logger.info("Presseportal: %d transport-related", transport_count)
        return events

    def _parse_presseportal_item(self, item) -> dict | None:
        """Parsuje pojedynczy element z presseportal.de."""
        result = {}

        # Title
        title_el = item.find(["h3", "h2", "h4"])
        if title_el:
            result["title"] = title_el.get_text(strip=True)
        else:
            link = item.find("a")
            if link:
                result["title"] = link.get_text(strip=True)
            else:
                return None

        if not result.get("title") or len(result["title"]) < 5:
            return None

        # Link
        link_el = item.find("a", href=True)
        if link_el:
            href = link_el["href"]
            if href.startswith("/"):
                href = "https://www.presseportal.de" + href
            result["link"] = href
        else:
            result["link"] = PRESSEPORTAL_URL

        # Description
        desc_el = item.find("p")
        if desc_el:
            result["description"] = desc_el.get_text(strip=True)
        else:
            result["description"] = ""

        # Date
        date_el = item.find(class_=re.compile(r"date|datum|time", re.IGNORECASE))
        if date_el:
            result["date"] = date_el.get_text(strip=True)
        else:
            result["date"] = self._extract_date_from_element(item)

        return result

    # -- Bundespolizei.de parser -------------------------------------------

    def _parse_bundespolizei(self, html: str) -> list[dict]:
        """Parsuje komunikaty z bundespolizei.de/aktuelles/meldungen."""
        soup = BeautifulSoup(html, "html.parser")
        events = []

        # Try multiple selectors
        items = self._find_news_items(soup)
        self._logger.info("Bundespolizei.de: znaleziono %d elementow", len(items))
        transport_count = 0

        for item in items:
            parsed = self._parse_single_item(item)
            if not parsed:
                continue

            title = parsed.get("title", "")
            description = parsed.get("description", "")
            full_text = f"{title} {description}".lower()

            if self._is_transport_related(full_text):
                transport_count += 1
                events.append(self._make_event(parsed, "Bundespolizei"))

        self._logger.info("Bundespolizei.de: %d transport-related", transport_count)
        return events

    def _find_news_items(self, soup: BeautifulSoup) -> list:
        """Szuka elementow wiadomosci na stronie Bundespolizei."""
        selectors = [
            "article",
            "div.teaser",
            "div.list-item",
            "li.list-item",
            "div.c-teaser",
            "div.meldung",
            "div.news-item",
            "div.result-item",
            "ul.list-unstyled > li",
            "div.c-content-stage",
        ]

        for selector in selectors:
            items = soup.select(selector)
            if items:
                self._logger.debug("Selector '%s' -> %d items", selector, len(items))
                return items

        # Fallback: find all links that look like news article links
        self._logger.debug("Brak match na selektory — fallback na linki")
        items = []
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if "/meldungen/" in href.lower():
                parent = link.find_parent(["div", "li", "article"])
                if parent and parent not in items:
                    items.append(parent)
        return items

    def _parse_single_item(self, item) -> dict | None:
        """Parsuje pojedynczy element wiadomosci z bundespolizei.de."""
        result = {}

        # Title
        title_el = item.find(["h2", "h3", "h4"])
        if title_el:
            result["title"] = title_el.get_text(strip=True)
        else:
            link = item.find("a")
            if link:
                result["title"] = link.get_text(strip=True)
            else:
                return None

        if not result.get("title") or len(result["title"]) < 5:
            return None

        # Link
        link_el = item.find("a", href=True)
        if link_el:
            href = link_el["href"]
            if href.startswith("/"):
                href = "https://www.bundespolizei.de" + href
            elif not href.startswith("http"):
                href = "https://www.bundespolizei.de/" + href
            result["link"] = href
        else:
            result["link"] = BUNDESPOLIZEI_URL

        # Description
        desc_el = item.find("p")
        if desc_el:
            result["description"] = desc_el.get_text(strip=True)
        else:
            full_text = item.get_text(strip=True)
            title_text = result.get("title", "")
            desc = full_text.replace(title_text, "").strip()
            result["description"] = desc[:500] if desc else ""

        # Date
        result["date"] = self._extract_date_from_element(item)

        return result

    # -- Helpers -----------------------------------------------------------

    def _make_event(self, parsed: dict, source_label: str) -> dict:
        """Tworzy event dict z parsed data."""
        return {
            "title": parsed.get("title", ""),
            "description": parsed.get("description", ""),
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", BUNDESPOLIZEI_URL),
            "raw_text": f"{parsed.get('title', '')}\n{parsed.get('description', '')}",
            "country_code": "DE",
            "language": "de",
            "source_name": source_label,
            "trust_score": 1.0,
            "is_official": True,
            "source_type": SourceType.POLICE.value,
            "timestamp": parsed.get("date") or datetime.utcnow().isoformat(),
            "collected_at": datetime.utcnow().isoformat(),
        }

    def _extract_date_from_element(self, item) -> str:
        """Wyciaga date z elementu HTML."""
        # <time> element
        time_el = item.find("time")
        if time_el:
            dt = time_el.get("datetime", "")
            if dt:
                return dt
            return time_el.get_text(strip=True)

        # <span> with date class
        for cls_name in ["date", "datum", "teaser-date", "c-date"]:
            date_el = item.find(class_=re.compile(cls_name, re.IGNORECASE))
            if date_el:
                return date_el.get_text(strip=True)

        # Regex in text
        text = item.get_text()
        m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", text)
        if m:
            return m.group(1)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)

        return ""

    def _is_transport_related(self, text: str) -> bool:
        """Sprawdza czy tekst dotyczy transportu (keyword matching DE)."""
        return is_transport_related(text, "de")
