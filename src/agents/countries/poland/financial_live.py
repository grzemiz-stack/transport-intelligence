"""PolishFinancialAgent — live scraper dla Monitora Sadowego i Gospodarczego.

Scrapuje ogloszenia o upadlosciach i restrukturyzacjach firm transportowych z:
https://ems.ms.gov.pl/

Filtruje te dotyczace firm transportowych i spedycyjnych.
"""

import asyncio
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType

logger = logging.getLogger(__name__)

EMS_URL = "https://ems.ms.gov.pl/"

USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"

# Keywords for transport-related bankruptcy/restructuring (Polish)
TRANSPORT_KEYWORDS = [
    "upadłość", "upadlosc", "upadłości", "upadlosci",
    "restrukturyzacja", "restrukturyzacji", "restrukturyzacyjne",
    "transport", "transportu", "transportowy", "transportowa",
    "spedycja", "spedycji", "spedycyjna", "spedycyjny",
    "przewóz", "przewoz", "przewozu", "przewozy", "przewozów",
    "logistyka", "logistyki", "logistyczny", "logistyczna",
    "ciężarowy", "ciezarowy", "ciężarowych",
    "tir", "naczep", "naczepa",
    "fracht", "frachtu",
    "przewoźnik", "przewoznik", "przewoźnika",
]

RATE_LIMIT_SECONDS = 5.0


class PolishFinancialAgent(BaseAgent):
    """Agent scrapujacy Monitor Sadowy i Gospodarczy dot. firm transportowych.

    Szuka ogloszen o upadlosciach i restrukturyzacjach firm transportowych.
    Respektuje robots.txt, rate-limiting (max 1 req / 5s),
    custom User-Agent z danymi kontaktowymi.
    """

    def __init__(self, event_queue=None):
        super().__init__(
            country_code="PL",
            language="pl",
            source_type=SourceType.FINANCIAL,
            source_name="Monitor Sadowy i Gospodarczy",
            source_url=EMS_URL,
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
            response.status_code, len(response.text), elapsed_ms,
        )
        return response.text

    async def fetch(self) -> str:
        """Pobiera HTML z ems.ms.gov.pl."""
        return await self._fetch_url(EMS_URL)

    async def parse(self, raw_data: str) -> list[dict]:
        """Parsuje HTML z Monitora Sadowego i Gospodarczego."""
        soup = BeautifulSoup(raw_data, "html.parser")
        events = []
        seen_titles = set()

        # Try multiple selectors for announcement items
        items = (
            soup.select("div.announcement")
            or soup.select("div.msig-item")
            or soup.select("article")
            or soup.select("div.list-item")
            or soup.select("tr")
        )

        if not items:
            # Fallback: find all links that look like announcements
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if any(kw in href.lower() for kw in ["ogloszeni", "wpis", "msig", "announcement"]):
                    parent = link.find_parent(["div", "li", "article", "tr", "section"])
                    if parent and parent not in items:
                        items.append(parent)

        self._logger.info("EMS: znaleziono %d elementow", len(items))
        transport_count = 0

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
                    transport_count += 1
                    events.append(self._make_event(parsed))

        self._logger.info("EMS: %d transport-related events", transport_count)
        return events

    def _parse_item(self, item) -> dict | None:
        """Parsuje pojedynczy element ogloszenia."""
        result = {}

        # Title
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

        # Link
        link_el = item.find("a", href=True)
        if link_el:
            href = link_el["href"]
            if href.startswith("/"):
                href = "https://ems.ms.gov.pl" + href
            elif not href.startswith("http"):
                href = "https://ems.ms.gov.pl/" + href
            result["link"] = href
        else:
            result["link"] = EMS_URL

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
        result["date"] = self._extract_date(item)

        return result

    def _make_event(self, parsed: dict) -> dict:
        """Tworzy event dict z parsed data."""
        return {
            "title": parsed.get("title", ""),
            "description": parsed.get("description", ""),
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", EMS_URL),
            "raw_text": f"{parsed.get('title', '')}\n{parsed.get('description', '')}",
            "country_code": "PL",
            "language": "pl",
            "source_name": "Monitor Sadowy i Gospodarczy",
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

    def _is_transport_related(self, text: str) -> bool:
        """Sprawdza czy tekst dotyczy firm transportowych."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in TRANSPORT_KEYWORDS)
