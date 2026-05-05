"""UKCompaniesHouseAgent — scraper Companies House REST API.

Pobiera dane o firmach transportowych w likwidacji/upadlosci
z oficjalnego API Companies House (UK).
"""

import asyncio
import logging
from datetime import datetime

from src.agents.base_agent import BaseAgent, SourceType

logger = logging.getLogger(__name__)

API_BASE = "https://api.company-information.service.gov.uk"

USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"

TRANSPORT_KEYWORDS = [
    "transport", "haulage", "logistics", "freight",
    "trucking", "carrier", "shipping", "forwarding",
    "delivery", "courier", "removals", "distribution",
]

# SIC codes for transport-related industries
TRANSPORT_SIC_CODES = [
    "4941",  # Freight transport by road
    "5229",  # Other transportation support activities
    "5210",  # Warehousing and storage
]

INSOLVENCY_STATUSES = [
    "liquidation",
    "administration",
    "voluntary-arrangement",
    "insolvency-proceedings",
    "receivership",
]

RATE_LIMIT_SECONDS = 5.0


class UKCompaniesHouseAgent(BaseAgent):
    """Agent odpytujacy Companies House REST API.

    Wyszukuje firmy transportowe w stanie likwidacji/upadlosci
    za pomoca oficjalnego API z kluczem autoryzacyjnym.
    """

    def __init__(self, event_queue=None):
        super().__init__(
            country_code="GB",
            language="en",
            source_type=SourceType.FINANCIAL,
            source_name="Companies House",
            source_url=API_BASE,
            trust_score=1.0,
            is_official=True,
            scrape_interval_minutes=360,
            event_queue=event_queue,
            max_retries=3,
            base_retry_delay=10.0,
        )
        self._last_request_time: float = 0.0
        self._api_key: str = ""

    def _get_api_key(self) -> str:
        """Pobiera API key z konfiguracji."""
        if not self._api_key:
            from src.config import settings
            self._api_key = settings.companies_house_api_key
        return self._api_key

    async def _rate_limit(self):
        """Enforce rate limiting — max 1 request per RATE_LIMIT_SECONDS."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            wait = RATE_LIMIT_SECONDS - elapsed
            self._logger.debug("Rate limit: czekam %.1fs", wait)
            await asyncio.sleep(wait)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _fetch_api(self, endpoint: str, params: dict | None = None) -> dict:
        """Wykonuje zapytanie do Companies House API z autoryzacja."""
        await self._rate_limit()
        session = await self.get_session()
        api_key = self._get_api_key()

        url = f"{API_BASE}{endpoint}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        # Companies House uses HTTP Basic Auth (API key as username, empty password)
        auth = (api_key, "") if api_key else None

        self._logger.info("API call: %s %s", endpoint, params or "")
        start = asyncio.get_event_loop().time()

        if auth:
            import httpx
            async with httpx.AsyncClient(timeout=30.0, auth=auth) as client:
                response = await client.get(url, headers=headers, params=params)
        else:
            response = await session.get(url, headers=headers, params=params)

        response.raise_for_status()
        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
        self._logger.info("API OK: HTTP %d, %.0fms", response.status_code, elapsed_ms)
        return response.json()

    async def fetch(self) -> str:
        """Pobiera dane z Companies House API — szuka firm transportowych w likwidacji."""
        api_key = self._get_api_key()
        if not api_key:
            self._logger.warning("No Companies House API key configured — skipping")
            return "{}"

        all_results = []

        for sic_code in TRANSPORT_SIC_CODES:
            for status in INSOLVENCY_STATUSES:
                try:
                    data = await self._fetch_api(
                        "/advanced-search/companies",
                        params={
                            "company_status": status,
                            "sic_codes": sic_code,
                            "size": 50,
                        },
                    )
                    items = data.get("items", [])
                    if items:
                        self._logger.info(
                            "SIC %s / %s: %d results", sic_code, status, len(items),
                        )
                        for item in items:
                            item["_query_status"] = status
                            item["_query_sic"] = sic_code
                        all_results.extend(items)
                except Exception as e:
                    self._logger.warning("API call failed (SIC=%s, status=%s): %s", sic_code, status, e)

        # Serialize results as JSON string for parse()
        import json
        return json.dumps({"items": all_results})

    async def parse(self, raw_data: str) -> list[dict]:
        """Parsuje odpowiedz JSON z Companies House API."""
        import json
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            self._logger.warning("Invalid JSON from Companies House")
            return []

        items = data.get("items", [])
        events = []
        seen_companies = set()

        for item in items:
            company_name = item.get("company_name", "")
            company_number = item.get("company_number", "")

            if not company_name:
                continue

            # Dedup by company number
            if company_number in seen_companies:
                continue
            seen_companies.add(company_number)

            # Check if transport-related by name or SIC
            name_lower = company_name.lower()
            is_transport = any(kw in name_lower for kw in TRANSPORT_KEYWORDS)
            if not is_transport:
                # Already filtered by SIC code in query, so include anyway
                pass

            status = item.get("company_status", "unknown")
            date_of_cessation = item.get("date_of_cessation", "")
            date_of_creation = item.get("date_of_creation", "")
            address = item.get("registered_office_address", {})
            address_str = ", ".join(filter(None, [
                address.get("address_line_1", ""),
                address.get("locality", ""),
                address.get("postal_code", ""),
            ]))

            description = (
                f"Company {company_number} ({company_name}) — status: {status}. "
                f"Address: {address_str}."
            )
            if date_of_cessation:
                description += f" Cessation date: {date_of_cessation}."

            event_date = date_of_cessation or date_of_creation or ""

            events.append(self._make_event({
                "title": f"{company_name} — {status}",
                "description": description,
                "link": f"https://find-and-update.company-information.service.gov.uk/company/{company_number}",
                "date": event_date,
                "company_number": company_number,
                "company_status": status,
            }))

        self._logger.info("UK Companies House: %d events", len(events))
        return events

    def _make_event(self, parsed: dict) -> dict:
        """Tworzy event dict z parsed data."""
        return {
            "title": parsed.get("title", ""),
            "description": parsed.get("description", ""),
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", API_BASE),
            "raw_text": f"{parsed.get('title', '')}\n{parsed.get('description', '')}",
            "country_code": "GB",
            "language": "en",
            "source_name": "Companies House",
            "trust_score": 1.0,
            "is_official": True,
            "source_type": SourceType.FINANCIAL.value,
            "timestamp": parsed.get("date") or datetime.utcnow().isoformat(),
            "collected_at": datetime.utcnow().isoformat(),
        }
