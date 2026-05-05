"""CroatianPoliceAgent — live scraper dla strony MUP Hrvatska.

Scrapuje: https://mup.gov.hr/vijesti-8/8
Keywords HR: krađa, prijevoz, kamion, autocesta
"""

import asyncio, logging, re
from datetime import datetime
from bs4 import BeautifulSoup
from src.agents.base_agent import BaseAgent, SourceType
from src.agents.transport_keywords import is_transport_related

logger = logging.getLogger(__name__)
POLICE_URL = "https://mup.gov.hr/vijesti-8/8"
USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"
RATE_LIMIT_SECONDS = 5.0

class CroatianPoliceAgent(BaseAgent):
    def __init__(self, event_queue=None):
        super().__init__(
            country_code="HR", language="hr", source_type=SourceType.POLICE,
            source_name="MUP Hrvatska", source_url=POLICE_URL,
            trust_score=1.0, is_official=True, scrape_interval_minutes=60,
            event_queue=event_queue, max_retries=3, base_retry_delay=10.0)
        self._last_request_time: float = 0.0

    async def _rate_limit(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            await asyncio.sleep(RATE_LIMIT_SECONDS - elapsed)
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

    async def fetch(self):
        return await self._fetch_url(POLICE_URL)

    async def parse(self, raw_data):
        soup = BeautifulSoup(raw_data, "html.parser")
        events, seen = [], set()
        items = soup.select("article") or soup.select("div.news-item") or soup.select("div.list-item") or soup.select("li.list-item")
        if not items:
            for link in soup.find_all("a", href=True):
                if "/vijesti" in link["href"]:
                    p = link.find_parent(["div","li","article","section"])
                    if p and p not in items: items.append(p)
        self._logger.info("MUP.hr: znaleziono %d elementow", len(items))
        for item in items:
            parsed = self._parse_item(item)
            if not parsed: continue
            full = f"{parsed['title']} {parsed.get('description','')}".lower()
            if is_transport_related(full, "hr"):
                key = parsed["title"].strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    events.append({"title":parsed["title"],"description":parsed.get("description",""),"date":parsed.get("date",""),"source_url":parsed["link"],"raw_text":f"{parsed['title']}\n{parsed.get('description','')}","country_code":"HR","language":"hr","source_name":"MUP Hrvatska","trust_score":1.0,"is_official":True,"source_type":SourceType.POLICE.value,"timestamp":parsed.get("date") or datetime.utcnow().isoformat(),"collected_at":datetime.utcnow().isoformat()})
        self._logger.info("MUP.hr: %d transport-related events", len(events))
        return events

    def _parse_item(self, item):
        title_el = item.find(["h2","h3","h4"]) or item.find("a")
        if not title_el: return None
        title = title_el.get_text(strip=True)
        if not title or len(title)<5: return None
        link_el = item.find("a", href=True)
        href = POLICE_URL
        if link_el:
            h = link_el["href"]
            href = ("https://mup.gov.hr"+h) if h.startswith("/") else (h if h.startswith("http") else "https://mup.gov.hr/"+h)
        desc_el = item.find("p")
        time_el = item.find("time")
        date = ""
        if time_el: date = time_el.get("datetime","") or time_el.get_text(strip=True)
        if not date:
            for cls in ["date","datum"]:
                el = item.find(class_=re.compile(cls, re.IGNORECASE))
                if el: date = el.get_text(strip=True); break
        if not date:
            for pat in [r"(\d{1,2}\.\d{1,2}\.\d{4})", r"(\d{4}-\d{2}-\d{2})"]:
                m = re.search(pat, item.get_text())
                if m: date = m.group(1); break
        return {"title":title,"link":href,"description":desc_el.get_text(strip=True) if desc_el else "","date":date}
