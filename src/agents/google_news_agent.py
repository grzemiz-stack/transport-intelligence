"""Google News RSS Agent — monitoruje lokalne media w kluczowych miastach Europy.

Google News agreguje lokalne gazety automatycznie — jeden feed per miasto/region
daje dostep do dziesiatek lokalnych zrodel. Format: Atom/RSS.

URL pattern:
    https://news.google.com/rss/search?q={query}&hl={lang}&gl={country}&ceid={country}:{lang}
"""

import logging
import re
from datetime import datetime
from html import unescape
from urllib.parse import quote_plus

import feedparser
import httpx

from src.agents.base_agent import BaseAgent, SourceType
from src.agents.transport_keywords import is_transport_related

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Browser-like User-Agent (Google blocks bot UAs)
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    if not text:
        return ""
    text = _HTML_TAG_RE.sub(" ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def build_google_news_url(query: str, lang: str, country: str) -> str:
    """Build Google News RSS search URL."""
    encoded_query = quote_plus(query)
    return (
        f"https://news.google.com/rss/search?"
        f"q={encoded_query}&hl={lang}&gl={country}&ceid={country}:{lang}"
    )


class GoogleNewsAgent(BaseAgent):
    """Agent monitorujacy Google News RSS dla danego regionu/zapytania."""

    def __init__(
        self,
        country_code: str,
        language: str,
        region_name: str,
        query: str,
        trust_score: float = 0.4,
        is_official: bool = False,
    ):
        self.query = query
        self.region_name = region_name
        self.feed_url = build_google_news_url(query, language, country_code)

        super().__init__(
            country_code=country_code,
            language=language,
            source_type=SourceType.NEWS,
            source_name=f"Google News/{region_name}",
            source_url=self.feed_url,
            trust_score=trust_score,
            is_official=is_official,
        )
        self._seen_urls: set[str] = set()

    async def fetch(self) -> str:
        """Fetch Google News RSS feed."""
        session = await self.get_session()
        headers = {
            "User-Agent": BROWSER_UA,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": f"{self.language},en;q=0.5",
        }
        response = await session.get(self.feed_url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def _extract_real_source(self, entry: dict) -> str:
        """Extract the real news source name from Google News entry."""
        # Google News includes source in <source> tag
        source = entry.get("source", {})
        if isinstance(source, dict):
            return source.get("title", "") or source.get("value", "")
        # Fallback: source name often appears at end of title after " - "
        title = entry.get("title", "")
        if " - " in title:
            return title.rsplit(" - ", 1)[-1].strip()
        return ""

    async def parse(self, raw_data: str) -> list[dict]:
        """Parse Google News Atom feed and filter by transport keywords."""
        feed = feedparser.parse(raw_data)

        if feed.bozo and not feed.entries:
            logger.warning(
                "[%s] Google News feed parse error: %s",
                self.region_name, feed.bozo_exception,
            )
            return []

        events = []
        for entry in feed.entries:
            link = entry.get("link", "")

            # Dedup by URL
            if link in self._seen_urls:
                continue
            self._seen_urls.add(link)

            title = strip_html(entry.get("title", ""))
            description = strip_html(
                entry.get("summary", "")
                or entry.get("description", "")
            )
            real_source = self._extract_real_source(entry)

            # Parse date
            date_parsed = None
            for date_field in ("published_parsed", "updated_parsed"):
                tp = entry.get(date_field)
                if tp:
                    try:
                        date_parsed = datetime(*tp[:6])
                    except (TypeError, ValueError):
                        pass
                    break

            # Dual-list keyword filtering: vehicle + event
            combined = f"{title} {description}"
            if not is_transport_related(combined, self.language):
                continue

            date_iso = date_parsed.isoformat() if date_parsed else datetime.utcnow().isoformat()

            event = {
                "title": title,
                "description": description[:3000] if description else None,
                "source_url": link,
                "raw_text": f"{title}\n{description[:3000]}" if description else title,
                "date": date_iso,
                "timestamp": date_iso,
                "date_parsed": date_parsed,
                "collected_at": datetime.utcnow().isoformat(),
                "source_name": f"Google News/{self.region_name}",
                "original_source": real_source,
                "source_type": "news",
                "country_code": self.country_code,
                "language": self.language,
                "trust_score": self.trust_score,
                "is_official": False,
                "region": self.region_name,
                "query": self.query,
            }
            events.append(event)

        return events

    async def fetch_article_details(self, article_url: str, language: str) -> dict:
        """Fetch full article text and extract structured details."""
        from src.pipeline.article_extractor import fetch_article_text, ArticleExtractor

        full_text = await fetch_article_text(article_url, language)
        if not full_text:
            return {}
        extractor = ArticleExtractor()
        details = extractor.extract_details(full_text, language)
        details["full_text"] = full_text
        return details
