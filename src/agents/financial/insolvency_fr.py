"""FrenchInsolvencyAgent — scraper BODACC (bodacc.fr).

Scrapuje ogloszenia o likwidacjach firm transportowych z oficjalnego
Bulletin officiel des annonces civiles et commerciales.
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType

logger = logging.getLogger(__name__)

BODACC_URL = "https://www.bodacc.fr/"
BODACC_RSS_URL = "https://www.bodacc.fr/annonce/liste?rubrique=liquidation&format=rss"

USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"

TRANSPORT_KEYWORDS = [
    "transport", "logistique", "fret", "routier",
    "camionnage", "messagerie", "expédition", "expedition",
    "affrètement", "affretement", "transitaire",
    "livraison", "déménagement", "demenagement",
    "entreposage", "stockage", "chauffeur", "poids lourd",
    "marchandises", "colis",
]

RATE_LIMIT_SECONDS = 5.0


class FrenchInsolvencyAgent(BaseAgent):
    """Agent scrapujacy BODACC — francuskie ogloszenia o likwidacjach.

    Przeszukuje Bulletin officiel des annonces civiles et commerciales
    pod katem firm transportowych i logistycznych.
    """

    def __init__(self, event_queue=None):
        super().__init__(
            country_code="FR",
            language="fr",
            source_type=SourceType.FINANCIAL,
            source_name="BODACC",
            source_url=BODACC_URL,
            trust_score=0.95,
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
        """Pobiera HTML/XML z podanego URL z rate limiting."""
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
        """Pobiera dane z BODACC RSS + HTML fallback."""
        parts = []

        # 1. RSS feed — liquidation announcements
        try:
            rss_xml = await self._fetch_url(BODACC_RSS_URL)
            parts.append(f"<!-- BODACC_RSS -->\n{rss_xml}")
        except Exception as e:
            self._logger.warning("BODACC RSS fetch failed: %s", e)

        # 2. HTML fallback — main site
        try:
            html = await self._fetch_url(BODACC_URL)
            parts.append(f"<!-- BODACC_HTML -->\n{html}")
        except Exception as e:
            self._logger.warning("BODACC HTML fetch failed: %s", e)

        return "\n<!-- SEPARATOR -->\n".join(parts)

    async def parse(self, raw_data: str) -> list[dict]:
        """Parsuje dane z BODACC (RSS + HTML)."""
        events = []
        seen_titles = set()

        for part in raw_data.split("\n<!-- SEPARATOR -->\n"):
            if not part.strip():
                continue

            if "<!-- BODACC_RSS -->" in part:
                xml_content = part.replace("<!-- BODACC_RSS -->", "").strip()
                events.extend(self._parse_rss(xml_content, seen_titles))
            elif "<!-- BODACC_HTML -->" in part:
                html_content = part.replace("<!-- BODACC_HTML -->", "").strip()
                events.extend(self._parse_html(html_content, seen_titles))

        self._logger.info("FR Insolvency (BODACC): %d transport-related events", len(events))
        return events

    def _parse_rss(self, xml_content: str, seen_titles: set) -> list[dict]:
        """Parsuje RSS XML z BODACC."""
        events = []
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            self._logger.warning("BODACC RSS parse error: %s", e)
            return events

        for item in root.iter("item"):
            title_el = item.find("title")
            desc_el = item.find("description")
            link_el = item.find("link")
            pubdate_el = item.find("pubDate")

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            description = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else BODACC_URL
            pubdate = pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else ""

            full_text = f"{title} {description}".lower()
            if not self._is_transport_related(full_text):
                continue

            title_key = title.strip().lower()
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                events.append(self._make_event({
                    "title": title,
                    "description": description,
                    "link": link,
                    "date": pubdate,
                }))

        return events

    def _parse_html(self, html: str, seen_titles: set) -> list[dict]:
        """Parsuje HTML z BODACC."""
        soup = BeautifulSoup(html, "html.parser")
        events = []

        items = (
            soup.select("div.annonce")
            or soup.select("div.result")
            or soup.select("article")
            or soup.select("div.list-item")
            or soup.select("tr")
        )

        if not items:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if any(kw in href.lower() for kw in ["annonce", "liquidation", "jugement"]):
                    parent = link.find_parent(["div", "li", "article", "tr", "section"])
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

        return events

    def _parse_item(self, item) -> dict | None:
        """Parsuje pojedynczy element HTML."""
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
                href = "https://www.bodacc.fr" + href
            elif not href.startswith("http"):
                href = "https://www.bodacc.fr/" + href
            result["link"] = href
        else:
            result["link"] = BODACC_URL

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

    def _make_event(self, parsed: dict) -> dict:
        """Tworzy event dict z parsed data."""
        return {
            "title": parsed.get("title", ""),
            "description": parsed.get("description", ""),
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", BODACC_URL),
            "raw_text": f"{parsed.get('title', '')}\n{parsed.get('description', '')}",
            "country_code": "FR",
            "language": "fr",
            "source_name": "BODACC",
            "trust_score": 0.95,
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
        # French date format: DD/MM/YYYY
        m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", text)
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
