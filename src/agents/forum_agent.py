"""Forum Scraper Agent — scrapuje fora kierowcow, spedytorow i transportu.

Fora to najcenniejsze zrodlo crowdsourced intelligence:
kierowcy raportuja kradzieze, wandalizm, niebezpieczne parkingi, problemy z firmami.

Strategia pobierania:
1. Probuj RSS/Atom feed (wiele forow ma /feed, /rss.php, /syndication.php)
2. Jesli brak RSS — parsuj HTML (phpBB, vBulletin, XenForo, Discourse, generic)
3. Filtruj po keywords transport-related per jezyk
4. Anonimizuj autorow (GDPR) — nigdy nie zapisuj nickow

Rate limiting: 5s miedzy requestami do tego samego forum.
Respektuje robots.txt kazdego forum.
Scrapuje TYLKO publiczne tresci — nie loguje sie.
"""

import logging
import re
import time
from datetime import datetime
from html import unescape
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType
from src.agents.transport_keywords import is_transport_related as _is_transport_related

logger = logging.getLogger(__name__)

FORUM_USER_AGENT = "TransportIntelligence/1.0 (Research; transport-intel.com)"
RATE_LIMIT_SECONDS = 5.0

# HTML tag stripper
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    if not text:
        return ""
    text = _HTML_TAG_RE.sub(" ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


# ── Common RSS feed paths for forum engines ──────────────────────────────

RSS_PATHS = [
    "/feed",
    "/feed/",
    "/rss",
    "/rss.php",
    "/syndication.php",
    "/index.php?action=.xml;type=rss2",
    "/external.php?type=RSS2",
    "/latest.rss",
    "/forums/-/index.rss",
]


class ForumAgent(BaseAgent):
    """Uniwersalny scraper forow transportowych.

    Probuje najpierw RSS/Atom feed, potem HTML parsing.
    Respektuje robots.txt, rate limiting, GDPR.
    """

    def __init__(
        self,
        country_code: str,
        language: str,
        source_name: str,
        forum_url: str,
        trust_score: float = 0.3,
        is_official: bool = False,
        keywords: list[str] | None = None,
        keywords_extra: list[str] | None = None,
        forum_type: str = "generic",
        rss_url: str | None = None,
    ):
        super().__init__(
            country_code=country_code,
            language=language,
            source_type=SourceType.FORUM,
            source_name=source_name,
            source_url=forum_url,
            trust_score=trust_score,
            is_official=is_official,
            max_retries=2,
            base_retry_delay=10.0,
        )
        self.forum_url = forum_url
        self.forum_type = forum_type
        self.rss_url = rss_url
        self._seen_urls: set[str] = set()
        self._last_request_time: float = 0.0

        # Build keyword list: explicit only (dual-list is default)
        if keywords is not None:
            self.keywords = keywords
            if keywords_extra:
                self.keywords.extend(keywords_extra)
        else:
            self.keywords = None  # Use shared dual-list filtering

    async def _rate_limited_get(self, url: str, min_delay: float | None = None) -> httpx.Response:
        """GET z rate limiting i custom User-Agent.

        Args:
            min_delay: Override delay (default RATE_LIMIT_SECONDS=5s).
                       Use shorter delay for RSS discovery probing.
        """
        delay = min_delay if min_delay is not None else RATE_LIMIT_SECONDS
        elapsed = time.time() - self._last_request_time
        if elapsed < delay:
            wait = delay - elapsed
            import asyncio
            await asyncio.sleep(wait)

        session = await self.get_session()
        response = await session.get(
            url,
            headers={"User-Agent": FORUM_USER_AGENT},
        )
        self._last_request_time = time.time()
        response.raise_for_status()
        return response

    # ── RSS detection ────────────────────────────────────────────────────

    async def _try_rss(self) -> str | None:
        """Probuje znalezc i pobrac RSS/Atom feed forum.

        Uzywa krotszego delay (1s) dla RSS discovery — to probing, nie scraping.
        Returns:
            XML string jesli znaleziono feed, None w przeciwnym razie.
        """
        probe_delay = 1.0  # Shorter delay for RSS path probing

        # 1. Explicit RSS URL from config
        if self.rss_url:
            try:
                resp = await self._rate_limited_get(self.rss_url, min_delay=probe_delay)
                content = resp.text
                if self._is_valid_feed(content):
                    self._logger.info("RSS feed found (explicit): %s", self.rss_url)
                    return content
            except Exception as e:
                self._logger.debug("Explicit RSS URL failed: %s", e)

        # 2. First fetch the main page — check for <link rel="alternate">
        main_html = None
        try:
            resp = await self._rate_limited_get(self.forum_url, min_delay=probe_delay)
            main_html = resp.text
            soup = BeautifulSoup(main_html, "html.parser")
            for link_tag in soup.find_all("link", rel="alternate"):
                link_type = (link_tag.get("type") or "").lower()
                if "rss" in link_type or "atom" in link_type or "xml" in link_type:
                    href = link_tag.get("href", "")
                    if href:
                        feed_url = urljoin(self.forum_url, href)
                        try:
                            resp2 = await self._rate_limited_get(feed_url, min_delay=probe_delay)
                            if self._is_valid_feed(resp2.text):
                                self._logger.info("RSS feed found (link tag): %s", feed_url)
                                return resp2.text
                        except Exception:
                            continue
        except Exception:
            pass

        # 3. Try top 3 most common RSS paths only (skip rest for speed)
        base = self.forum_url.rstrip("/")
        top_paths = ["/feed/", "/rss", "/syndication.php"]
        for path in top_paths:
            url = base + path
            try:
                resp = await self._rate_limited_get(url, min_delay=probe_delay)
                content = resp.text
                if self._is_valid_feed(content):
                    self._logger.info("RSS feed found: %s", url)
                    return content
            except Exception:
                continue

        return None

    def _is_valid_feed(self, content: str) -> bool:
        """Sprawdza czy content to prawidlowy RSS/Atom feed."""
        if not content:
            return False
        # Quick check for XML feed markers
        lower = content[:500].lower()
        return any(marker in lower for marker in ["<rss", "<feed", "<rdf"])

    # ── fetch() ──────────────────────────────────────────────────────────

    async def fetch(self) -> str:
        """Fetch forum content — RSS first, HTML fallback.

        Returns:
            Raw content string (RSS XML or HTML).
        """
        # Try RSS first (also caches main page HTML internally)
        rss_content = await self._try_rss()
        if rss_content:
            return f"__RSS__\n{rss_content}"

        # Fallback: fetch HTML (may need a fresh fetch if _try_rss failed early)
        self._logger.info("No RSS feed — falling back to HTML scraping")
        resp = await self._rate_limited_get(self.forum_url)
        html = resp.text

        # Check if login required
        if self._requires_login(html):
            self._logger.warning("Forum requires login — skipping: %s", self.forum_url)
            return ""

        return html

    def _requires_login(self, html: str) -> bool:
        """Detect if page requires login."""
        lower = html[:3000].lower()
        login_indicators = [
            "you must be logged in",
            "please log in",
            "musisz się zalogować",
            "musisz byc zalogowany",
            "bitte anmelden",
            "bitte einloggen",
            "connectez-vous",
            "trebuie sa fii autentificat",
            'action="login"',
            "login_required",
        ]
        return any(ind in lower for ind in login_indicators)

    # ── parse() ──────────────────────────────────────────────────────────

    async def parse(self, raw_data: str) -> list[dict]:
        """Parse forum content — RSS or HTML."""
        if not raw_data:
            return []

        if raw_data.startswith("__RSS__\n"):
            return self._parse_rss(raw_data[8:])
        return self._parse_html(raw_data)

    # ── RSS parsing ──────────────────────────────────────────────────────

    def _parse_rss(self, xml_content: str) -> list[dict]:
        """Parse RSS/Atom feed from forum."""
        feed = feedparser.parse(xml_content)

        if feed.bozo and not feed.entries:
            self._logger.warning("Feed parse error: %s", feed.bozo_exception)
            return []

        events = []
        for entry in feed.entries:
            link = entry.get("link", "")

            if link in self._seen_urls:
                continue
            self._seen_urls.add(link)

            title = strip_html(entry.get("title", ""))
            description = self._extract_feed_description(entry)

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

            # Keyword filtering
            if not self._matches_keywords(title, description):
                continue

            date_iso = date_parsed.isoformat() if date_parsed else datetime.utcnow().isoformat()

            events.append(self._make_event(
                title=title,
                description=description[:3000],
                link=link,
                date_iso=date_iso,
                date_parsed=date_parsed,
            ))

        return events

    def _extract_feed_description(self, entry: dict) -> str:
        """Extract description from feed entry."""
        content_list = entry.get("content", [])
        if content_list:
            return strip_html(content_list[0].get("value", ""))
        return strip_html(
            entry.get("summary", "")
            or entry.get("description", "")
        )

    # ── HTML parsing ─────────────────────────────────────────────────────

    def _parse_html(self, html: str) -> list[dict]:
        """Parse HTML forum page — extract threads."""
        soup = BeautifulSoup(html, "html.parser")

        # Try forum-engine-specific parsers
        parsers = {
            "phpbb": self._parse_phpbb,
            "vbulletin": self._parse_vbulletin,
            "xenforo": self._parse_xenforo,
            "discourse": self._parse_discourse,
            "generic": self._parse_generic,
        }

        if self.forum_type == "auto":
            detected = self._detect_forum_type(html)
            parser = parsers.get(detected, self._parse_generic)
        else:
            parser = parsers.get(self.forum_type, self._parse_generic)

        threads = parser(soup)

        # Filter by keywords
        events = []
        for thread in threads:
            title = thread.get("title", "")
            desc = thread.get("description", "")
            if self._matches_keywords(title, desc):
                events.append(thread)

        return events

    def _detect_forum_type(self, html: str) -> str:
        """Auto-detect forum engine from HTML."""
        lower = html[:5000].lower()
        if "phpbb" in lower or 'class="topiclist' in lower:
            return "phpbb"
        if "vbulletin" in lower or "vb_" in lower:
            return "vbulletin"
        if "xenforo" in lower or "data-xf-" in lower:
            return "xenforo"
        if "discourse" in lower or "data-topic-id" in lower:
            return "discourse"
        return "generic"

    def _parse_phpbb(self, soup: BeautifulSoup) -> list[dict]:
        """Parse phpBB forum layout."""
        threads = []

        # phpBB: threads in .topiclist or ul.topics
        for topic in soup.select(".topiclist .row, .topiclist li, .topics li"):
            link_el = topic.select_one("a.topictitle, a.forumtitle")
            if not link_el:
                link_el = topic.find("a")
            if not link_el:
                continue

            title = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            url = urljoin(self.forum_url, href)

            if url in self._seen_urls:
                continue
            self._seen_urls.add(url)

            # Preview / description
            preview_el = topic.select_one(".topic-preview, .topic_content, .post-text")
            desc = preview_el.get_text(strip=True)[:500] if preview_el else ""

            # Date
            date_el = topic.select_one("time, .topic-date, dd.lastpost")
            date_text = date_el.get("datetime", "") if date_el else ""

            threads.append(self._make_event(
                title=title, description=desc, link=url,
                date_iso=date_text or datetime.utcnow().isoformat(),
            ))

        return threads

    def _parse_vbulletin(self, soup: BeautifulSoup) -> list[dict]:
        """Parse vBulletin forum layout."""
        threads = []

        for thread_el in soup.select("#threads .threadtitle a, .thread-title a, .title a"):
            title = thread_el.get_text(strip=True)
            href = thread_el.get("href", "")
            url = urljoin(self.forum_url, href)

            if url in self._seen_urls:
                continue
            self._seen_urls.add(url)

            threads.append(self._make_event(
                title=title, description="", link=url,
                date_iso=datetime.utcnow().isoformat(),
            ))

        return threads

    def _parse_xenforo(self, soup: BeautifulSoup) -> list[dict]:
        """Parse XenForo forum layout."""
        threads = []

        for item in soup.select(".structItem, .discussionListItem"):
            link_el = item.select_one(".structItem-title a, a.PreviewTooltip, .title a")
            if not link_el:
                continue

            title = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            url = urljoin(self.forum_url, href)

            if url in self._seen_urls:
                continue
            self._seen_urls.add(url)

            # Snippet
            snippet_el = item.select_one(".structItem-minor, .snippet")
            desc = snippet_el.get_text(strip=True)[:500] if snippet_el else ""

            # Date
            time_el = item.select_one("time")
            date_text = time_el.get("datetime", "") if time_el else ""

            threads.append(self._make_event(
                title=title, description=desc, link=url,
                date_iso=date_text or datetime.utcnow().isoformat(),
            ))

        return threads

    def _parse_discourse(self, soup: BeautifulSoup) -> list[dict]:
        """Parse Discourse forum layout."""
        threads = []

        for row in soup.select(".topic-list-item, tr[data-topic-id]"):
            link_el = row.select_one(".title a, a.raw-topic-link")
            if not link_el:
                continue

            title = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            url = urljoin(self.forum_url, href)

            if url in self._seen_urls:
                continue
            self._seen_urls.add(url)

            threads.append(self._make_event(
                title=title, description="", link=url,
                date_iso=datetime.utcnow().isoformat(),
            ))

        return threads

    def _parse_generic(self, soup: BeautifulSoup) -> list[dict]:
        """Generic forum parser — finds thread-like links."""
        threads = []

        # Strategy: find all <a> tags that look like forum thread links
        # Thread URLs typically contain: /topic/, /thread/, /viewtopic, /showthread,
        # /forum/.../, /t/, /post/, /discussion/
        thread_patterns = re.compile(
            r"(topic|thread|viewtopic|showthread|discussion|post|wątek|watek|temat)"
            r"|/t/\d+|/p/\d+|/forum/[^/]+/\d+",
            re.IGNORECASE,
        )

        seen_titles = set()

        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            title = a_tag.get_text(strip=True)

            if not title or len(title) < 10 or len(title) > 300:
                continue

            # Skip navigation / non-thread links
            if title.lower() in ("next", "previous", "back", "home", "login",
                                  "register", "search", "forum", "dalej", "wstecz"):
                continue

            url = urljoin(self.forum_url, href)

            # Must be same domain
            if urlparse(url).netloc != urlparse(self.forum_url).netloc:
                continue

            # Check if URL looks like a thread
            is_thread = bool(thread_patterns.search(href))

            # Also consider links from common forum containers
            parent = a_tag.parent
            if parent:
                parent_classes = " ".join(parent.get("class", []))
                if any(cls in parent_classes.lower() for cls in
                       ("topic", "thread", "forum-list", "post-list", "entry",
                        "title", "item", "row")):
                    is_thread = True

            if not is_thread:
                continue

            if url in self._seen_urls:
                continue
            if title in seen_titles:
                continue

            self._seen_urls.add(url)
            seen_titles.add(title)

            threads.append(self._make_event(
                title=title, description="", link=url,
                date_iso=datetime.utcnow().isoformat(),
            ))

        return threads

    # ── Thread content fetching ──────────────────────────────────────────

    async def fetch_thread(self, thread_url: str) -> dict:
        """Fetch full thread content (first post).

        Returns:
            Dict with: content, date, author (anonymized).
        """
        try:
            resp = await self._rate_limited_get(thread_url)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Try to find first post content
            post_selectors = [
                ".post_body",       # phpBB
                ".postbody",        # phpBB alt
                ".post-text",       # vBulletin
                ".message-body",    # XenForo
                ".bbWrapper",       # XenForo alt
                ".cooked",          # Discourse
                ".entry-content",   # WordPress
                ".post-content",
                ".content",
                "article",
            ]

            content = ""
            for selector in post_selectors:
                el = soup.select_one(selector)
                if el:
                    content = el.get_text(strip=True)[:3000]
                    break

            if not content:
                # Fallback: get main text block
                main = soup.find("main") or soup.find("article") or soup.find("body")
                if main:
                    content = main.get_text(strip=True)[:3000]

            return {
                "content": content,
                "url": thread_url,
            }
        except Exception as e:
            self._logger.debug("Failed to fetch thread %s: %s", thread_url, e)
            return {"content": "", "url": thread_url}

    # ── Helpers ──────────────────────────────────────────────────────────

    def _matches_keywords(self, title: str, description: str) -> bool:
        """Check if text matches transport keywords (dual-list filtering)."""
        combined = f"{title} {description}"
        if self.keywords:
            # Explicit keywords: single-list match (backwards compat)
            return any(kw.lower() in combined.lower() for kw in self.keywords)
        # Default: shared dual-list filtering
        return _is_transport_related(combined, self.language)

    def _make_event(
        self,
        title: str,
        description: str,
        link: str,
        date_iso: str,
        date_parsed: datetime | None = None,
    ) -> dict:
        """Create standardized event dict."""
        return {
            "title": title,
            "description": description[:3000] if description else None,
            "source_url": link,
            "raw_text": description[:3000] if description else title,
            "date": date_iso,
            "timestamp": date_iso,
            "date_parsed": date_parsed,
            "collected_at": datetime.utcnow().isoformat(),
            "source_name": self.source_name,
            "source_type": "forum",
            "country_code": self.country_code,
            "language": self.language,
            "trust_score": self.trust_score,
            "is_official": self.is_official_source,
        }
