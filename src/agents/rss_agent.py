"""Uniwersalny agent RSS — pobiera i parsuje dowolny feed RSS/Atom.

Uzywa feedparser do obslugi RSS 2.0, Atom i wariantow.
Obsluguje rowniez Reddit RSS (format Atom).
Filtruje artykuly po slowach kluczowych transportowych per jezyk.
Deduplikuje po URL artykulu.
"""

import logging
import re
from datetime import datetime
from html import unescape

import feedparser

from src.agents.base_agent import BaseAgent, SourceType
from src.agents.transport_keywords import is_transport_related as _is_transport_related

logger = logging.getLogger(__name__)

# HTML tag stripper
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    if not text:
        return ""
    text = _HTML_TAG_RE.sub(" ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class RSSAgent(BaseAgent):
    """Uniwersalny agent RSS/Atom — dziala z dowolnym feedem."""

    def __init__(
        self,
        country_code: str,
        language: str,
        source_name: str,
        feed_url: str,
        trust_score: float = 0.5,
        is_official: bool = False,
        keywords: list[str] | None = None,
        source_type_str: str = "news",
    ):
        source_type_map = {
            "police": SourceType.POLICE,
            "news": SourceType.NEWS,
            "forum": SourceType.FORUM,
            "alerts": SourceType.ALERTS,
            "financial": SourceType.FINANCIAL,
        }
        st = source_type_map.get(source_type_str, SourceType.NEWS)

        super().__init__(
            country_code=country_code,
            language=language,
            source_type=st,
            source_name=source_name,
            source_url=feed_url,
            trust_score=trust_score,
            is_official=is_official,
        )
        self.feed_url = feed_url
        self.keywords = keywords
        self.source_type_str = source_type_str
        self.is_reddit = "reddit.com" in feed_url
        self._seen_urls: set[str] = set()

    async def fetch(self) -> str:
        """Fetch RSS/Atom XML content via httpx."""
        headers = {}
        if self.is_reddit:
            headers["User-Agent"] = "TransportIntelligence/1.0 (by /u/WarNeon169)"
        session = await self.get_session()
        response = await session.get(self.feed_url, headers=headers)
        response.raise_for_status()
        return response.text

    def _extract_description(self, entry: dict) -> str:
        """Extract description from feed entry, handling Reddit Atom content."""
        if self.is_reddit:
            # Reddit Atom: content is in <content> tag as HTML
            content_list = entry.get("content", [])
            if content_list:
                raw_html = content_list[0].get("value", "")
                return strip_html(raw_html)
            # Fallback to summary
            return strip_html(entry.get("summary", ""))

        # Standard RSS/Atom
        return strip_html(
            entry.get("summary", "")
            or entry.get("description", "")
            or (entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "")
        )

    async def parse(self, raw_data: str) -> list[dict]:
        """Parse RSS/Atom feed and filter by transport keywords."""
        feed = feedparser.parse(raw_data)

        if feed.bozo and not feed.entries:
            logger.warning("[%s] Feed parse error: %s", self.source_name, feed.bozo_exception)
            return []

        # Reddit: truncate to 500 chars; standard feeds: 5000
        desc_limit = 500 if self.is_reddit else 5000

        events = []
        for entry in feed.entries:
            link = entry.get("link", "")

            # Dedup by URL
            if link in self._seen_urls:
                continue
            self._seen_urls.add(link)

            title = strip_html(entry.get("title", ""))
            description = self._extract_description(entry)

            # Reddit: extract author
            author = None
            if self.is_reddit:
                author_detail = entry.get("author_detail", {})
                author = author_detail.get("name") or entry.get("author")

            # Parse date
            date_parsed = None
            for date_field in ("published_parsed", "updated_parsed", "created_parsed"):
                tp = entry.get(date_field)
                if tp:
                    try:
                        date_parsed = datetime(*tp[:6])
                    except (TypeError, ValueError):
                        pass
                    break

            # Keyword filtering — dual-list: vehicle + event
            if self.keywords:
                # Explicit keywords override: single-list match (backwards compat)
                combined = f"{title} {description}".lower()
                if not any(kw.lower() in combined for kw in self.keywords):
                    continue
            else:
                # Default: use shared dual-list filtering
                combined = f"{title} {description}"
                if not _is_transport_related(combined, self.language):
                    continue

            date_iso = date_parsed.isoformat() if date_parsed else datetime.utcnow().isoformat()

            event = {
                "title": title,
                "description": description[:desc_limit] if description else None,
                "source_url": link,
                "raw_text": description[:desc_limit] if description else title,
                "date": date_iso,
                "timestamp": date_iso,
                "date_parsed": date_parsed,
                "collected_at": datetime.utcnow().isoformat(),
                "source_name": self.source_name,
                "source_type": self.source_type_str,
                "country_code": self.country_code,
                "language": self.language,
                "trust_score": self.trust_score,
                "is_official": self.is_official_source,
            }

            if author:
                event["author"] = author

            events.append(event)

        return events
