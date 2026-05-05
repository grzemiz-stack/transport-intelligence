"""GreekPoliceAgent — live scraper dla strony Ελληνική Αστυνομία.

Scrapuje: https://www.astynomia.gr/deltia-typou/
Keywords EL: κλοπή, μεταφορά, φορτηγό, αυτοκινητόδρομος
"""

import asyncio, logging, re
from datetime import datetime
from bs4 import BeautifulSoup
from src.agents.base_agent import BaseAgent, SourceType
from src.agents.transport_keywords import is_transport_related

logger = logging.getLogger(__name__)
POLICE_URL = "https://www.astynomia.gr/deltia-typou/"
USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"
RATE_LIMIT_SECONDS = 5.0

class GreekPoliceAgent(BaseAgent):
    def __init__(self, event_queue=None):
        super().__init__(
            country_code="GR", language="el", source_type=SourceType.POLICE,
            source_name="Ελληνική Αστυνομία", source_url=POLICE_URL,
            trust_score=1.0, is_official=True, scrape_interval_minutes=60,
            event_queue=event_queue, max_retries=3, base_retry_delay=10.0)
        self._last_request_time: float = 0.0

    async def _rate_limit(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS: await asyncio.sleep(RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _fetch_url(self, url):
        await self._rate_limit()
        session = await self.get_session()
        self._logger.info("Fetching: %s", url)
        start = asyncio.get_event_loop().time()
        r = await session.get(url, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        self._logger.info("Fetch OK: HTTP %d, %d bytes, %.0fms", r.status_code, len(r.text), (asyncio.get_event_loop().time()-start)*1000)
        return r.text

    async def fetch(self): return await self._fetch_url(POLICE_URL)

    async def parse(self, raw_data):
        soup = BeautifulSoup(raw_data, "html.parser")
        events, seen = [], set()
        items = soup.select("article") or soup.select("div.news-item") or soup.select("div.list-item") or soup.select("li.list-item")
        if not items:
            for link in soup.find_all("a", href=True):
                if "/deltia-typou/" in link["href"] and link["href"] != "/deltia-typou/":
                    p = link.find_parent(["div","li","article","section"])
                    if p and p not in items: items.append(p)
        self._logger.info("Astynomia.gr: znaleziono %d elementow", len(items))
        for item in items:
            title_el = item.find(["h2","h3","h4"]) or item.find("a")
            if not title_el: continue
            title = title_el.get_text(strip=True)
            if not title or len(title)<5: continue
            link_el = item.find("a", href=True)
            href = POLICE_URL
            if link_el:
                h = link_el["href"]
                href = ("https://www.astynomia.gr"+h) if h.startswith("/") else (h if h.startswith("http") else "https://www.astynomia.gr/"+h)
            desc_el = item.find("p")
            desc = desc_el.get_text(strip=True) if desc_el else ""
            full = f"{title} {desc}".lower()
            if is_transport_related(full, "el"):
                key = title.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    time_el = item.find("time")
                    date = (time_el.get("datetime","") or time_el.get_text(strip=True)) if time_el else ""
                    if not date:
                        for pat in [r"(\d{1,2}/\d{1,2}/\d{4})", r"(\d{1,2}\.\d{1,2}\.\d{4})", r"(\d{4}-\d{2}-\d{2})"]:
                            m = re.search(pat, item.get_text())
                            if m: date = m.group(1); break
                    events.append({"title":title,"description":desc,"date":date,"source_url":href,"raw_text":f"{title}\n{desc}","country_code":"GR","language":"el","source_name":"Ελληνική Αστυνομία","trust_score":1.0,"is_official":True,"source_type":SourceType.POLICE.value,"timestamp":date or datetime.utcnow().isoformat(),"collected_at":datetime.utcnow().isoformat()})
        self._logger.info("Astynomia.gr: %d transport-related events", len(events))
        return events
