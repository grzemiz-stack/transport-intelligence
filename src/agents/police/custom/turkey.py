"""TurkishPoliceAgent — dual-source scraper (EGM + Anadolu Ajansi).

Key difference from DE/AT: trust_score and is_official vary per source.
EGM (official police) gets trust=1.0, AA (news agency) gets trust=0.85.
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import SourceType
from src.agents.police.base import BasePoliceAgent, PoliceSourceConfig
from src.agents.transport_keywords import is_transport_related

EGM_URL = "https://www.egm.gov.tr/haberler"
AA_URL = "https://www.aa.com.tr/tr/gundem"

_CONFIG = PoliceSourceConfig(
    country_code="TR",
    language="tr",
    source_name="EGM T\u00fcrkiye",
    source_url=EGM_URL,
    url_domain="https://www.egm.gov.tr",
    selectors=(),  # not used — parse() is overridden
    fallback_href_markers=(),
)

_SELECTORS = ("article", "div.news-item", "div.list-item", "li.list-item")
_HREF_MARKERS = ("/basin", "/gundem/", "/haber")


class TurkishPoliceAgent(BasePoliceAgent):
    """Dual-source Turkish police scraper.

    Sources:
      1. egm.gov.tr (official EGM) — trust 1.0
      2. aa.com.tr (Anadolu Agency) — trust 0.85
    """

    def __init__(self, event_queue=None):
        super().__init__(_CONFIG, event_queue)

    async def fetch(self) -> str:
        parts: list[str] = []
        for label, url in [("egm", EGM_URL), ("aa", AA_URL)]:
            try:
                html = await self._fetch_url(url)
                parts.append(f"<!-- SOURCE:{label} -->\n{html}")
            except Exception as e:
                self._logger.warning("%s fetch failed: %s", label, e)
        if not parts:
            raise RuntimeError("Oba zrodla tureckie niedostepne")
        return "\n<!-- SEPARATOR -->\n".join(parts)

    async def parse(self, raw_data: str) -> list[dict]:
        events: list[dict] = []
        seen: set[str] = set()

        for block in raw_data.split("<!-- SEPARATOR -->"):
            is_egm = "SOURCE:egm" in block
            base_url = "https://www.egm.gov.tr" if is_egm else "https://www.aa.com.tr"
            trust = 1.0 if is_egm else 0.85
            source_name = "EGM T\u00fcrkiye" if is_egm else "Anadolu Ajans\u0131"

            soup = BeautifulSoup(block, "html.parser")
            items: list = []
            for sel in _SELECTORS:
                items = soup.select(sel)
                if items:
                    break
            if not items:
                for link in soup.find_all("a", href=True):
                    h = link["href"]
                    if any(kw in h for kw in _HREF_MARKERS):
                        p = link.find_parent(["div", "li", "article", "section"])
                        if p and p not in items:
                            items.append(p)

            self._logger.info("%s: znaleziono %d elementow", source_name, len(items))

            for item in items:
                title_el = item.find(["h2", "h3", "h4"]) or item.find("a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                link_el = item.find("a", href=True)
                href = base_url
                if link_el:
                    h = link_el["href"]
                    if h.startswith("/"):
                        href = base_url + h
                    elif h.startswith("http"):
                        href = h
                    else:
                        href = base_url + "/" + h

                desc_el = item.find("p")
                desc = desc_el.get_text(strip=True) if desc_el else ""
                full = f"{title} {desc}".lower()

                if is_transport_related(full, "tr"):
                    key = title.strip().lower()
                    if key and key not in seen:
                        seen.add(key)
                        date = self._extract_tr_date(item)
                        events.append({
                            "title": title,
                            "description": desc,
                            "date": date,
                            "source_url": href,
                            "raw_text": f"{title}\n{desc}",
                            "country_code": "TR",
                            "language": "tr",
                            "source_name": source_name,
                            "trust_score": trust,
                            "is_official": is_egm,
                            "source_type": SourceType.POLICE.value,
                            "timestamp": date or datetime.utcnow().isoformat(),
                            "collected_at": datetime.utcnow().isoformat(),
                        })

        self._logger.info("TR total: %d transport-related events", len(events))
        return events

    @staticmethod
    def _extract_tr_date(item) -> str:
        time_el = item.find("time")
        if time_el:
            return time_el.get("datetime", "") or time_el.get_text(strip=True)
        text = item.get_text()
        for pat in (r"(\d{1,2}\.\d{1,2}\.\d{4})", r"(\d{4}-\d{2}-\d{2})"):
            m = re.search(pat, text)
            if m:
                return m.group(1)
        return ""
