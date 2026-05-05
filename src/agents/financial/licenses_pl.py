"""PolishLicenseAgent — scraper KREPTD (kreptd.gitd.gov.pl).

Scrapuje informacje o cofnietych/zawieszonych licencjach transportowych
z Krajowego Rejestru Elektronicznego Przedsiebiorcow Transportu Drogowego.
"""

import asyncio
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType

logger = logging.getLogger(__name__)

KREPTD_URL = "https://kreptd.gitd.gov.pl/"

USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"

LICENSE_KEYWORDS = [
    "cofnięcie", "cofniecie", "cofnięta", "cofnieta",
    "zawieszenie", "zawieszona", "zawieszony",
    "wygaśnięcie", "wygasniecie", "wygasła", "wygasla",
    "zakaz", "zakazu",
    "decyzja", "decyzji",
    "utrata", "odebranie",
]

TRANSPORT_KEYWORDS = [
    "transport", "transportu", "transportowy",
    "spedycja", "spedycji",
    "przewóz", "przewoz", "przewozu", "przewozy",
    "licencja", "licencji",
    "zezwolenie", "zezwolenia",
    "międzynarodowy", "miedzynarodowy",
    "krajowy", "drogowy",
]

RATE_LIMIT_SECONDS = 5.0


class PolishLicenseAgent(BaseAgent):
    """Agent scrapujacy KREPTD — polski rejestr licencji transportowych.

    Wyszukuje informacje o cofnietych, zawieszonych i wygaslych
    licencjach transportowych.
    """

    def __init__(self, event_queue=None):
        super().__init__(
            country_code="PL",
            language="pl",
            source_type=SourceType.FINANCIAL,
            source_name="KREPTD",
            source_url=KREPTD_URL,
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
        """Pobiera dane z KREPTD."""
        return await self._fetch_url(KREPTD_URL)

    async def parse(self, raw_data: str) -> list[dict]:
        """Parsuje HTML z KREPTD — szuka cofnietych/zawieszonych licencji."""
        soup = BeautifulSoup(raw_data, "html.parser")
        events = []
        seen_titles = set()

        items = (
            soup.select("div.result")
            or soup.select("table tr")
            or soup.select("div.list-item")
            or soup.select("article")
            or soup.select("tr")
        )

        if not items:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if any(kw in href.lower() for kw in ["licencja", "zezwolenie", "rejestr", "wpis"]):
                    parent = link.find_parent(["div", "li", "article", "tr", "section"])
                    if parent and parent not in items:
                        items.append(parent)

        self._logger.info("KREPTD: znaleziono %d elementow", len(items))
        license_count = 0

        for item in items:
            parsed = self._parse_item(item)
            if not parsed:
                continue

            title = parsed.get("title", "")
            description = parsed.get("description", "")
            full_text = f"{title} {description}".lower()

            if self._is_license_event(full_text):
                title_key = title.strip().lower()
                if title_key and title_key not in seen_titles:
                    seen_titles.add(title_key)
                    license_count += 1
                    events.append(self._make_event(parsed))

        self._logger.info("KREPTD: %d license events", license_count)
        return events

    def _parse_item(self, item) -> dict | None:
        """Parsuje pojedynczy element z KREPTD."""
        result = {}

        title_el = item.find(["h2", "h3", "h4", "strong"])
        if title_el:
            result["title"] = title_el.get_text(strip=True)
        else:
            link = item.find("a")
            if link:
                result["title"] = link.get_text(strip=True)
            else:
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
                href = "https://kreptd.gitd.gov.pl" + href
            elif not href.startswith("http"):
                href = "https://kreptd.gitd.gov.pl/" + href
            result["link"] = href
        else:
            result["link"] = KREPTD_URL

        desc_el = item.find("p")
        if desc_el:
            result["description"] = desc_el.get_text(strip=True)
        else:
            full_text = item.get_text(strip=True)
            title_text = result.get("title", "")
            desc = full_text.replace(title_text, "").strip()
            result["description"] = desc[:500] if desc else ""

        result["date"] = self._extract_date(item)

        # Determine decision type
        full_text = f"{result.get('title', '')} {result.get('description', '')}".lower()
        if any(kw in full_text for kw in ["cofnięcie", "cofniecie", "cofnięta", "cofnieta"]):
            result["decision_type"] = "license_revocation"
        elif any(kw in full_text for kw in ["zawieszenie", "zawieszona", "zawieszony"]):
            result["decision_type"] = "license_suspension"
        elif any(kw in full_text for kw in ["wygaśnięcie", "wygasniecie", "wygasła", "wygasla"]):
            result["decision_type"] = "license_expiry"
        else:
            result["decision_type"] = "license_change"

        # Try to extract license number
        text = item.get_text()
        license_match = re.search(r"(?:licencja|zezwolenie)\s*(?:nr\.?|numer)?\s*([A-Z0-9/\-]+)", text, re.IGNORECASE)
        if license_match:
            result["license_number"] = license_match.group(1)

        return result

    def _make_event(self, parsed: dict) -> dict:
        """Tworzy event dict z parsed data."""
        decision_type = parsed.get("decision_type", "license_change")
        description = parsed.get("description", "")
        if parsed.get("license_number"):
            description = f"Licencja: {parsed['license_number']}. {description}"

        return {
            "title": parsed.get("title", ""),
            "description": f"[{decision_type}] {description}",
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", KREPTD_URL),
            "raw_text": f"{parsed.get('title', '')}\n{description}",
            "country_code": "PL",
            "language": "pl",
            "source_name": "KREPTD",
            "trust_score": 1.0,
            "is_official": True,
            "source_type": SourceType.FINANCIAL.value,
            "event_type": decision_type,
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

    def _is_license_event(self, text: str) -> bool:
        """Sprawdza czy tekst dotyczy zmian w licencjach transportowych."""
        text_lower = text.lower()
        has_license_keyword = any(kw in text_lower for kw in LICENSE_KEYWORDS)
        has_transport_keyword = any(kw in text_lower for kw in TRANSPORT_KEYWORDS)
        return has_license_keyword or has_transport_keyword
