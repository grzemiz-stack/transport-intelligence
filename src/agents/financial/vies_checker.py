"""VIESChecker — walidacja numerow VAT przez VIES REST API.

Sprawdza waznosc numerow VAT firm transportowych
za pomoca oficjalnego API Komisji Europejskiej.
"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"

RATE_LIMIT_SECONDS = 1.0  # VIES is rate-limited — max 1 req/sec


class VIESChecker:
    """Async checker walidacji numerow VAT przez VIES REST API.

    Nie jest podklasa BaseAgent — to standalone utility class.
    """

    def __init__(self):
        self._last_request_time: float = 0.0

    async def _rate_limit(self):
        """Enforce rate limiting — max 1 request per second."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            wait = RATE_LIMIT_SECONDS - elapsed
            await asyncio.sleep(wait)
        self._last_request_time = asyncio.get_event_loop().time()

    async def check_vat(self, country_code: str, vat_number: str) -> dict:
        """Sprawdza waznosc numeru VAT przez VIES REST API.

        Args:
            country_code: 2-literowy kod kraju (np. 'PL', 'DE')
            vat_number: numer VAT bez prefiksu kraju

        Returns:
            dict z polami: valid, country_code, vat_number, company_name,
            company_address, request_date
        """
        await self._rate_limit()

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    VIES_URL,
                    json={
                        "countryCode": country_code.upper(),
                        "vatNumber": vat_number.strip(),
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.warning("VIES HTTP error for %s%s: %s", country_code, vat_number, e)
                return {
                    "valid": False,
                    "country_code": country_code,
                    "vat_number": vat_number,
                    "company_name": "",
                    "company_address": "",
                    "request_date": "",
                    "error": str(e),
                }
            except Exception as e:
                logger.error("VIES request failed for %s%s: %s", country_code, vat_number, e)
                return {
                    "valid": False,
                    "country_code": country_code,
                    "vat_number": vat_number,
                    "company_name": "",
                    "company_address": "",
                    "request_date": "",
                    "error": str(e),
                }

        return {
            "valid": data.get("valid", False),
            "country_code": country_code,
            "vat_number": vat_number,
            "company_name": data.get("name", ""),
            "company_address": data.get("address", ""),
            "request_date": data.get("requestDate", ""),
        }

    async def bulk_check(self, vat_numbers: list[dict]) -> list[dict]:
        """Sprawdza wiele numerow VAT z rate limiting (1 req/sec).

        Args:
            vat_numbers: lista dict z polami 'country_code' i 'vat_number'

        Returns:
            lista wynikow check_vat() w tej samej kolejnosci
        """
        results = []
        for entry in vat_numbers:
            cc = entry.get("country_code", "")
            vn = entry.get("vat_number", "")
            if not cc or not vn:
                results.append({
                    "valid": False,
                    "country_code": cc,
                    "vat_number": vn,
                    "company_name": "",
                    "company_address": "",
                    "request_date": "",
                    "error": "Missing country_code or vat_number",
                })
                continue
            result = await self.check_vat(cc, vn)
            results.append(result)
        return results
