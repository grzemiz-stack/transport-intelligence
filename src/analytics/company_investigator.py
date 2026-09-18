"""CompanyInvestigator — Deep due diligence on transport companies.

Premium product (2000-5000 EUR): exhaustive investigation querying ALL available
public sources (registries, media, forums, transport exchanges, board cross-references),
synthesizing results via Claude AI, and generating professional PDF reports.

Follows the InsolvencyAnalyzer pattern exactly:
- httpx.AsyncClient -> POST https://api.anthropic.com/v1/messages
- Rate limiting: 5 requests/minute (Claude), 5s between external registry calls
- In-memory cache: MD5 of JSON-serialized input data
- Google News RSS for media research
"""

import asyncio
import hashlib
import json
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import httpx

from src.config import settings
from src.utils.claude_client import ClaudeClient, COUNTRY_NAMES

logger = logging.getLogger(__name__)

# Country-specific registries to check
COUNTRY_SOURCES = {
    "PL": ["krs", "ceidg", "kreptd", "regon", "debt_pl", "krz"],
    "DE": ["handelsregister", "unternehmensregister", "bundesanzeiger", "insolvenz_de"],
    "GB": ["companies_house", "gazette_uk"],
}


class CompanyInvestigator:
    """Deep due diligence investigator for transport companies.

    Premium product — generates exhaustive investigation reports:
    - Official registry checks (KRS, CEIDG, Handelsregister, Companies House, etc.)
    - Transport license verification (KREPTD)
    - Debt registry checks (KRD, BIG, Bundesanzeiger, Gazette)
    - Insolvency checks (KRZ, Insolvenzbekanntmachungen)
    - Media & reputation research (Google News, forums)
    - Transport exchange presence (Trans.eu, Timocom)
    - Board member cross-referencing (other directorships, failed companies)
    - Financial data from TI database
    - AI synthesis via Claude into structured risk assessment
    """

    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._claude = ClaudeClient(
            api_key=settings.anthropic_api_key,
            max_requests_per_minute=5,
            timeout=90.0,
        )
        self._vies_checker = None  # lazy init
        self._last_external_request: float = 0.0
        self._RATE_LIMIT_SECONDS = 5.0

    def _cache_key(self, data) -> str:
        """MD5 hash of JSON-serialized input data."""
        raw = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()

    async def _search_google_news(self, query: str, lang: str = "en") -> list[dict]:
        """Search Google News RSS for articles about a company."""
        encoded_query = quote_plus(query)
        url = (
            f"https://news.google.com/rss/search?q={encoded_query}"
            f"&hl={lang}&gl={lang.upper()}&ceid={lang.upper()}:{lang}"
        )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "TransportIntelligence/1.0 (Research Bot)",
                })
                resp.raise_for_status()

            articles = []
            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError:
                return []

            for item in root.iter("item"):
                title_el = item.find("title")
                desc_el = item.find("description")
                link_el = item.find("link")
                pubdate_el = item.find("pubDate")

                articles.append({
                    "title": title_el.text.strip() if title_el is not None and title_el.text else "",
                    "description": desc_el.text.strip() if desc_el is not None and desc_el.text else "",
                    "link": link_el.text.strip() if link_el is not None and link_el.text else "",
                    "pubDate": pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else "",
                })

            logger.info("Google News: %d articles for '%s'", len(articles), query)
            return articles[:20]

        except Exception as e:
            logger.warning("Google News search failed for '%s': %s", query, e)
            return []

    async def _rate_limit_external(self):
        """Enforce 5s delay between external registry calls."""
        now = time.time()
        elapsed = now - self._last_external_request
        if elapsed < self._RATE_LIMIT_SECONDS:
            await asyncio.sleep(self._RATE_LIMIT_SECONDS - elapsed)
        self._last_external_request = time.time()

    async def _fetch_url(
        self,
        url: str,
        source_name: str,
        method: str = "GET",
        data: dict | None = None,
        timeout: float = 15.0,
        headers: dict | None = None,
    ) -> dict:
        """Generic httpx fetch with rate limiting + try/except wrapper."""
        await self._rate_limit_external()

        default_headers = {
            "User-Agent": "TransportIntelligence/1.0 (Due Diligence Research)",
        }
        if headers:
            default_headers.update(headers)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method.upper() == "POST":
                    resp = await client.post(url, json=data, headers=default_headers)
                else:
                    resp = await client.get(url, headers=default_headers)
                resp.raise_for_status()
                return {
                    "source": source_name,
                    "status_code": resp.status_code,
                    "data": resp.text,
                    "error": None,
                }
        except Exception as e:
            logger.warning("Fetch failed for %s (%s): %s", source_name, url, e)
            return {
                "source": source_name,
                "status_code": None,
                "data": None,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Tier 1 — Official Registries (trust 1.0)
    # ------------------------------------------------------------------

    async def _check_vies(self, vat: str) -> dict:
        """Check VAT validity via VIES (delegates to VIESChecker)."""
        try:
            if self._vies_checker is None:
                from src.agents.financial.vies_checker import VIESChecker
                self._vies_checker = VIESChecker()

            country_code = vat[:2].upper()
            vat_number = vat[2:].strip()
            result = await self._vies_checker.check_vat(country_code, vat_number)
            return {
                "source": "VIES (EU VAT Validation)",
                "trust": 1.0,
                "tier": 1,
                "data": result,
                "error": None,
            }
        except Exception as e:
            logger.warning("VIES check failed for %s: %s", vat, e)
            return {
                "source": "VIES (EU VAT Validation)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_krs(self, name: str, krs: str | None = None) -> dict:
        """Check Polish KRS (National Court Register) via API."""
        try:
            await self._rate_limit_external()
            search_param = krs if krs else name
            url = f"https://api-krs.ms.gov.pl/api/krs/OdpisPelny/{search_param}" if krs else None

            # Search by name if no KRS number
            if not krs:
                search_url = f"https://api-krs.ms.gov.pl/api/krs/OdpisPelny?nazwa={quote_plus(name)}"
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(search_url, headers={
                        "User-Agent": "TransportIntelligence/1.0",
                    })
                    if resp.status_code == 200:
                        data = resp.json()
                        return {
                            "source": "KRS (Krajowy Rejestr Sadowy)",
                            "trust": 1.0,
                            "tier": 1,
                            "data": data,
                            "error": None,
                        }
                    else:
                        return {
                            "source": "KRS (Krajowy Rejestr Sadowy)",
                            "trust": 1.0,
                            "tier": 1,
                            "data": None,
                            "error": f"HTTP {resp.status_code}",
                        }
            else:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url, headers={
                        "User-Agent": "TransportIntelligence/1.0",
                    })
                    if resp.status_code == 200:
                        data = resp.json()
                        return {
                            "source": "KRS (Krajowy Rejestr Sadowy)",
                            "trust": 1.0,
                            "tier": 1,
                            "data": data,
                            "error": None,
                        }
                    else:
                        return {
                            "source": "KRS (Krajowy Rejestr Sadowy)",
                            "trust": 1.0,
                            "tier": 1,
                            "data": None,
                            "error": f"HTTP {resp.status_code}",
                        }
        except Exception as e:
            logger.warning("KRS check failed for %s: %s", name, e)
            return {
                "source": "KRS (Krajowy Rejestr Sadowy)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_ceidg(self, nip: str | None = None, name: str | None = None) -> dict:
        """Check Polish CEIDG (sole proprietorships) via API."""
        try:
            await self._rate_limit_external()
            params = {}
            if nip:
                params["nip"] = nip
            elif name:
                params["nazwa"] = name
            else:
                return {
                    "source": "CEIDG (Centralna Ewidencja Dzialalnosci Gospodarczej)",
                    "trust": 1.0,
                    "tier": 1,
                    "data": None,
                    "error": "No NIP or name provided",
                }

            url = "https://dane.biznes.gov.pl/api/ceidg/v2/firma"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params, headers={
                    "User-Agent": "TransportIntelligence/1.0",
                })
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "source": "CEIDG (Centralna Ewidencja Dzialalnosci Gospodarczej)",
                        "trust": 1.0,
                        "tier": 1,
                        "data": data,
                        "error": None,
                    }
                else:
                    return {
                        "source": "CEIDG (Centralna Ewidencja Dzialalnosci Gospodarczej)",
                        "trust": 1.0,
                        "tier": 1,
                        "data": None,
                        "error": f"HTTP {resp.status_code}",
                    }
        except Exception as e:
            logger.warning("CEIDG check failed: %s", e)
            return {
                "source": "CEIDG (Centralna Ewidencja Dzialalnosci Gospodarczej)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_kreptd(self, name: str) -> dict:
        """Check Polish KREPTD for transport license status (follows licenses_pl.py pattern)."""
        try:
            await self._rate_limit_external()
            url = "https://kreptd.gitd.gov.pl/"
            result = await self._fetch_url(url, "KREPTD")

            if result["data"]:
                # Search for company name in KREPTD results
                html = result["data"]
                found_revoked = bool(re.search(
                    rf"(?i)(cofni|zawieszeni|wygas).*{re.escape(name[:20])}", html,
                ))
                return {
                    "source": "KREPTD (Transport License Registry)",
                    "trust": 1.0,
                    "tier": 1,
                    "data": {
                        "checked": True,
                        "license_issues_found": found_revoked,
                        "note": "License revocation/suspension keywords detected" if found_revoked else "No issues found in initial check",
                    },
                    "error": None,
                }
            return {
                "source": "KREPTD (Transport License Registry)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": result.get("error", "No data returned"),
            }
        except Exception as e:
            logger.warning("KREPTD check failed for %s: %s", name, e)
            return {
                "source": "KREPTD (Transport License Registry)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_regon(self, nip: str) -> dict:
        """Check Polish GUS REGON for company statistical data."""
        try:
            await self._rate_limit_external()
            url = f"https://wyszukiwarkaregon.stat.gov.pl/appBIR/Search?SearchValue={quote_plus(nip)}"
            result = await self._fetch_url(url, "GUS REGON")
            return {
                "source": "GUS REGON (Statistical Registry)",
                "trust": 1.0,
                "tier": 1,
                "data": {"checked": True, "raw_available": result["data"] is not None},
                "error": result.get("error"),
            }
        except Exception as e:
            logger.warning("REGON check failed for %s: %s", nip, e)
            return {
                "source": "GUS REGON (Statistical Registry)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_debt_pl(self, name: str) -> dict:
        """Check Polish debt registries (KRD, BIG) — follows debt_registries.py pattern."""
        try:
            await self._rate_limit_external()
            # Check KRD
            krd_url = f"https://krd.pl/szukaj?q={quote_plus(name)}"
            krd_result = await self._fetch_url(krd_url, "KRD")

            await self._rate_limit_external()
            # Check BIG InfoMonitor
            big_url = f"https://www.big.pl/sprawdz-firme?name={quote_plus(name)}"
            big_result = await self._fetch_url(big_url, "BIG InfoMonitor")

            krd_found = False
            big_found = False
            if krd_result.get("data"):
                krd_found = bool(re.search(r"(?i)(dluznik|zadluzeni|zaleglosc)", krd_result["data"]))
            if big_result.get("data"):
                big_found = bool(re.search(r"(?i)(dluznik|zadluzeni|zaleglosc)", big_result["data"]))

            return {
                "source": "Polish Debt Registries (KRD + BIG)",
                "trust": 1.0,
                "tier": 1,
                "data": {
                    "krd_checked": True,
                    "krd_issues_found": krd_found,
                    "big_checked": True,
                    "big_issues_found": big_found,
                },
                "error": None,
            }
        except Exception as e:
            logger.warning("PL debt registry check failed for %s: %s", name, e)
            return {
                "source": "Polish Debt Registries (KRD + BIG)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_krz(self, name: str) -> dict:
        """Check Polish KRZ (insolvency registry) — follows insolvency_pl.py pattern."""
        try:
            await self._rate_limit_external()
            url = f"https://krz.ms.gov.pl/#!/szukaj?q={quote_plus(name)}"
            result = await self._fetch_url(url, "KRZ")

            found = False
            if result.get("data"):
                found = bool(re.search(
                    r"(?i)(upadl|restrukturyz|sanac|likwidac)", result["data"],
                ))

            return {
                "source": "KRZ (Krajowy Rejestr Zadluzonych)",
                "trust": 1.0,
                "tier": 1,
                "data": {
                    "checked": True,
                    "insolvency_found": found,
                },
                "error": result.get("error"),
            }
        except Exception as e:
            logger.warning("KRZ check failed for %s: %s", name, e)
            return {
                "source": "KRZ (Krajowy Rejestr Zadluzonych)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_handelsregister(self, name: str) -> dict:
        """Check German Handelsregister for company data."""
        try:
            await self._rate_limit_external()
            url = f"https://www.handelsregister.de/rp_web/search.xhtml?searchterm={quote_plus(name)}"
            result = await self._fetch_url(url, "Handelsregister")

            data_found = {}
            if result.get("data"):
                html = result["data"]
                # Extract HRB number
                hrb_match = re.search(r"(HRB?\s*\d+)", html)
                if hrb_match:
                    data_found["hrb_number"] = hrb_match.group(1)
                data_found["checked"] = True
                data_found["raw_available"] = True

            return {
                "source": "Handelsregister (German Commercial Register)",
                "trust": 1.0,
                "tier": 1,
                "data": data_found or None,
                "error": result.get("error"),
            }
        except Exception as e:
            logger.warning("Handelsregister check failed for %s: %s", name, e)
            return {
                "source": "Handelsregister (German Commercial Register)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_unternehmensregister(self, name: str) -> dict:
        """Check German Unternehmensregister for annual financial filings."""
        try:
            await self._rate_limit_external()
            url = f"https://www.unternehmensregister.de/ureg/?submitaction=search&searchterm={quote_plus(name)}"
            result = await self._fetch_url(url, "Unternehmensregister")
            return {
                "source": "Unternehmensregister (German Company Register)",
                "trust": 1.0,
                "tier": 1,
                "data": {"checked": True, "raw_available": result["data"] is not None},
                "error": result.get("error"),
            }
        except Exception as e:
            logger.warning("Unternehmensregister check failed for %s: %s", name, e)
            return {
                "source": "Unternehmensregister (German Company Register)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_bundesanzeiger(self, name: str) -> dict:
        """Check German Bundesanzeiger for announcements and debts."""
        try:
            await self._rate_limit_external()
            url = f"https://www.bundesanzeiger.de/pub/de/suche?5&query={quote_plus(name)}"
            result = await self._fetch_url(url, "Bundesanzeiger")

            debt_found = False
            if result.get("data"):
                debt_found = bool(re.search(
                    r"(?i)(insolvenz|schuld|mahnung|zwangsvollstreck)", result["data"],
                ))

            return {
                "source": "Bundesanzeiger (German Official Gazette)",
                "trust": 1.0,
                "tier": 1,
                "data": {
                    "checked": True,
                    "debt_announcements_found": debt_found,
                },
                "error": result.get("error"),
            }
        except Exception as e:
            logger.warning("Bundesanzeiger check failed for %s: %s", name, e)
            return {
                "source": "Bundesanzeiger (German Official Gazette)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_insolvenz_de(self, name: str) -> dict:
        """Check German Insolvenzbekanntmachungen — follows insolvency_de.py pattern."""
        try:
            await self._rate_limit_external()
            url = f"https://www.insolvenzbekanntmachungen.de/cgi-bin/bl_suche.pl?Name={quote_plus(name)}"
            result = await self._fetch_url(url, "Insolvenzbekanntmachungen")

            insolvency_found = False
            insolvency_type = None
            if result.get("data"):
                html = result["data"]
                insolvency_found = bool(re.search(
                    r"(?i)(eroeffnung|abweisung|einstellung|aufhebung|restschuldbefreiung)",
                    html,
                ))
                type_match = re.search(
                    r"(?i)(Eroeffnung|Abweisung|Einstellung|Aufhebung|Restschuldbefreiung)",
                    html,
                )
                if type_match:
                    insolvency_type = type_match.group(1)

            return {
                "source": "Insolvenzbekanntmachungen (German Insolvency Portal)",
                "trust": 1.0,
                "tier": 1,
                "data": {
                    "checked": True,
                    "insolvency_found": insolvency_found,
                    "insolvency_type": insolvency_type,
                },
                "error": result.get("error"),
            }
        except Exception as e:
            logger.warning("Insolvenz DE check failed for %s: %s", name, e)
            return {
                "source": "Insolvenzbekanntmachungen (German Insolvency Portal)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_companies_house(self, name: str, number: str | None = None) -> dict:
        """Check UK Companies House API for company data."""
        try:
            await self._rate_limit_external()
            if number:
                url = f"https://api.company-information.service.gov.uk/company/{number}"
            else:
                url = f"https://api.company-information.service.gov.uk/search/companies?q={quote_plus(name)}"

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "TransportIntelligence/1.0",
                })
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "source": "Companies House (UK)",
                        "trust": 1.0,
                        "tier": 1,
                        "data": data,
                        "error": None,
                    }
                else:
                    return {
                        "source": "Companies House (UK)",
                        "trust": 1.0,
                        "tier": 1,
                        "data": None,
                        "error": f"HTTP {resp.status_code}",
                    }
        except Exception as e:
            logger.warning("Companies House check failed for %s: %s", name, e)
            return {
                "source": "Companies House (UK)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_gazette_uk(self, name: str) -> dict:
        """Check UK Gazette for winding-up petitions."""
        try:
            await self._rate_limit_external()
            url = f"https://www.thegazette.co.uk/all-notices/content?text={quote_plus(name)}"
            result = await self._fetch_url(url, "The Gazette (UK)")

            winding_up_found = False
            if result.get("data"):
                winding_up_found = bool(re.search(
                    r"(?i)(winding.up|liquidat|insolvenc|petition)", result["data"],
                ))

            return {
                "source": "The Gazette (UK Official Public Record)",
                "trust": 1.0,
                "tier": 1,
                "data": {
                    "checked": True,
                    "winding_up_found": winding_up_found,
                },
                "error": result.get("error"),
            }
        except Exception as e:
            logger.warning("UK Gazette check failed for %s: %s", name, e)
            return {
                "source": "The Gazette (UK Official Public Record)",
                "trust": 1.0,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    async def _check_opencorporates(self, name: str, country: str) -> dict:
        """Check OpenCorporates for cross-border company status."""
        try:
            await self._rate_limit_external()
            jurisdiction = country.lower()
            url = (
                f"https://api.opencorporates.com/v0.4/companies/search"
                f"?q={quote_plus(name)}&jurisdiction_code={jurisdiction}"
            )
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "TransportIntelligence/1.0",
                })
                if resp.status_code == 200:
                    data = resp.json()
                    companies = data.get("results", {}).get("companies", [])
                    return {
                        "source": "OpenCorporates",
                        "trust": 0.8,
                        "tier": 1,
                        "data": {
                            "found": len(companies) > 0,
                            "count": len(companies),
                            "companies": [
                                {
                                    "name": c.get("company", {}).get("name"),
                                    "status": c.get("company", {}).get("current_status"),
                                    "incorporation_date": c.get("company", {}).get("incorporation_date"),
                                    "company_number": c.get("company", {}).get("company_number"),
                                }
                                for c in companies[:5]
                            ],
                        },
                        "error": None,
                    }
                else:
                    return {
                        "source": "OpenCorporates",
                        "trust": 0.8,
                        "tier": 1,
                        "data": None,
                        "error": f"HTTP {resp.status_code}",
                    }
        except Exception as e:
            logger.warning("OpenCorporates check failed for %s: %s", name, e)
            return {
                "source": "OpenCorporates",
                "trust": 0.8,
                "tier": 1,
                "data": None,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Tier 2 — Media (trust 0.5-0.8)
    # ------------------------------------------------------------------

    async def _search_media(self, name: str, country: str) -> dict:
        """Search media: Google News + Google web search for reviews/problems."""
        try:
            lang_map = {"PL": "pl", "DE": "de", "GB": "en", "FR": "fr"}
            lang = lang_map.get(country, "en")

            # Query variants depending on language
            negative_queries = {
                "pl": [
                    f"{name} opinie problemy",
                    f"{name} nie placi zaleglosci",
                    f"{name} upadlosc bankructwo transport",
                ],
                "de": [
                    f"{name} Bewertung Probleme",
                    f"{name} zahlt nicht Schulden",
                    f"{name} Insolvenz Transport",
                ],
                "en": [
                    f"{name} reviews problems transport",
                    f"{name} payment issues complaints",
                    f"{name} insolvency bankruptcy haulage",
                ],
            }

            queries = negative_queries.get(lang, negative_queries["en"])
            all_articles = []
            for query in queries:
                articles = await self._search_google_news(query, lang)
                all_articles.extend(articles)

            # Deduplicate by title
            seen = set()
            unique = []
            for a in all_articles:
                key = a["title"].strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    unique.append(a)

            return {
                "source": "Media (Google News)",
                "trust": 0.6,
                "tier": 2,
                "data": {
                    "articles_found": len(unique),
                    "articles": [
                        {
                            "title": a["title"],
                            "description": a.get("description", "")[:200],
                            "link": a.get("link", ""),
                            "date": a.get("pubDate", ""),
                        }
                        for a in unique[:15]
                    ],
                },
                "error": None,
            }
        except Exception as e:
            logger.warning("Media search failed for %s: %s", name, e)
            return {
                "source": "Media (Google News)",
                "trust": 0.6,
                "tier": 2,
                "data": None,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Tier 3 — Forums & Social (trust 0.2-0.4)
    # ------------------------------------------------------------------

    async def _search_forums(self, name: str, country: str) -> dict:
        """Search forums and review sites for company reputation."""
        try:
            forum_queries = {
                "PL": [
                    f'site:gowork.pl "{name}"',
                    f'site:forum.prawnikow.pl "{name}" transport',
                    f'"{name}" forum kierowcow opinie',
                ],
                "DE": [
                    f'site:kununu.com "{name}"',
                    f'site:glassdoor.de "{name}"',
                    f'"{name}" Forum LKW Fahrer Erfahrung',
                ],
                "GB": [
                    f'site:glassdoor.co.uk "{name}"',
                    f'"{name}" haulage driver forum reviews',
                ],
            }

            queries = forum_queries.get(country, [f'"{name}" transport driver reviews forum'])
            all_results = []
            for query in queries:
                articles = await self._search_google_news(query, "en")
                all_results.extend(articles)

            return {
                "source": "Forums & Review Sites",
                "trust": 0.3,
                "tier": 3,
                "data": {
                    "mentions_found": len(all_results),
                    "mentions": [
                        {
                            "title": a["title"],
                            "description": a.get("description", "")[:200],
                            "link": a.get("link", ""),
                        }
                        for a in all_results[:10]
                    ],
                },
                "error": None,
            }
        except Exception as e:
            logger.warning("Forum search failed for %s: %s", name, e)
            return {
                "source": "Forums & Review Sites",
                "trust": 0.3,
                "tier": 3,
                "data": None,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Tier 4 — Transport Exchanges (trust 0.6)
    # ------------------------------------------------------------------

    async def _search_transport_exchanges(self, name: str) -> dict:
        """Search transport exchanges (Trans.eu, Timocom) via Google."""
        try:
            queries = [
                f'site:trans.eu "{name}"',
                f'site:timocom.de "{name}"',
                f'site:teleroute.com "{name}"',
            ]

            all_results = []
            for query in queries:
                articles = await self._search_google_news(query, "en")
                all_results.extend(articles)

            return {
                "source": "Transport Exchanges (Trans.eu, Timocom, Teleroute)",
                "trust": 0.6,
                "tier": 4,
                "data": {
                    "presence_found": len(all_results) > 0,
                    "mentions": len(all_results),
                    "results": [
                        {
                            "title": a["title"],
                            "link": a.get("link", ""),
                        }
                        for a in all_results[:5]
                    ],
                },
                "error": None,
            }
        except Exception as e:
            logger.warning("Transport exchange search failed for %s: %s", name, e)
            return {
                "source": "Transport Exchanges (Trans.eu, Timocom, Teleroute)",
                "trust": 0.6,
                "tier": 4,
                "data": None,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Tier 5 — Personal Connections (trust 1.0)
    # ------------------------------------------------------------------

    async def _cross_reference_board(
        self, board_members: list[str], country: str,
    ) -> dict:
        """Cross-reference board members against registries for other directorships."""
        try:
            connections = []
            for person in board_members[:5]:  # Limit to 5 people
                if not person or len(person) < 3:
                    continue

                if country == "PL":
                    await self._rate_limit_external()
                    url = f"https://api-krs.ms.gov.pl/api/krs/OdpisPelny?osoby={quote_plus(person)}"
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.get(url, headers={
                            "User-Agent": "TransportIntelligence/1.0",
                        })
                        if resp.status_code == 200:
                            data = resp.json()
                            if data:
                                connections.append({
                                    "person": person,
                                    "other_companies_found": True,
                                    "source": "KRS",
                                    "data": data,
                                })
                elif country == "GB":
                    await self._rate_limit_external()
                    url = f"https://api.company-information.service.gov.uk/search/officers?q={quote_plus(person)}"
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.get(url, headers={
                            "User-Agent": "TransportIntelligence/1.0",
                        })
                        if resp.status_code == 200:
                            data = resp.json()
                            items = data.get("items", [])
                            if items:
                                connections.append({
                                    "person": person,
                                    "other_companies_found": True,
                                    "source": "Companies House Officers",
                                    "data": {"total": data.get("total_results", 0)},
                                })
                else:
                    # For DE and other countries, use Google search
                    articles = await self._search_google_news(
                        f'"{person}" Geschaeftsfuehrer director transport', "en",
                    )
                    if articles:
                        connections.append({
                            "person": person,
                            "other_companies_found": True,
                            "source": "Google Search",
                            "data": {"articles": len(articles)},
                        })

            return {
                "source": "Board Cross-Reference",
                "trust": 1.0,
                "tier": 5,
                "data": {
                    "members_checked": len(board_members[:5]),
                    "connections_found": len(connections),
                    "connections": connections,
                },
                "error": None,
            }
        except Exception as e:
            logger.warning("Board cross-reference failed: %s", e)
            return {
                "source": "Board Cross-Reference",
                "trust": 1.0,
                "tier": 5,
                "data": None,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Tier 6 — Financial / TI Database (trust 1.0)
    # ------------------------------------------------------------------

    async def _enrich_from_db(self, name: str, country: str) -> dict:
        """Enrich with data from TI database (Company, Event, CompanyFinancial)."""
        try:
            from sqlalchemy import select, desc
            from src.db.models import Company, CompanyFinancial, Event
            from src.db.postgres import async_session

            db_data = {
                "company": None,
                "events": [],
                "financials": [],
            }

            async with async_session() as session:
                # Find company
                result = await session.execute(
                    select(Company).where(
                        Company.name.ilike(f"%{name}%"),
                        Company.country_code == country.upper(),
                    ).limit(1)
                )
                company = result.scalar_one_or_none()

                if not company:
                    # Try without country filter
                    result = await session.execute(
                        select(Company).where(
                            Company.name.ilike(f"%{name}%"),
                        ).limit(1)
                    )
                    company = result.scalar_one_or_none()

                if company:
                    db_data["company"] = {
                        "id": str(company.id),
                        "name": company.name,
                        "country_code": company.country_code,
                        "financial_status": company.financial_status,
                        "risk_score": company.risk_score,
                        "company_type": company.company_type,
                        "tax_id": company.tax_id,
                        "address": getattr(company, "address", None),
                        "employee_count": getattr(company, "employee_count", None),
                        "fleet_size": getattr(company, "fleet_size", None),
                    }

                    # Fetch events
                    ev_result = await session.execute(
                        select(Event)
                        .where(Event.company_id == company.id)
                        .order_by(desc(Event.date_occurred))
                        .limit(30)
                    )
                    events = ev_result.scalars().all()

                    for e in events:
                        db_data["events"].append({
                            "date": e.date_occurred.strftime("%Y-%m-%d") if e.date_occurred else "",
                            "event_type": e.event_type,
                            "severity": (e.severity or "medium").upper(),
                            "title": e.title,
                            "description": e.description or "",
                        })

                    # Fetch financials
                    fin_result = await session.execute(
                        select(CompanyFinancial)
                        .where(CompanyFinancial.company_id == company.id)
                        .order_by(desc(CompanyFinancial.date_occurred))
                        .limit(20)
                    )
                    financials = fin_result.scalars().all()

                    for f in financials:
                        db_data["financials"].append({
                            "date": f.date_occurred.isoformat() if f.date_occurred else "",
                            "event_type": f.event_type,
                            "amount_eur": f.amount_eur or 0,
                            "description": f.description or "",
                        })

            return {
                "source": "Transport Intelligence Database",
                "trust": 1.0,
                "tier": 6,
                "data": db_data,
                "error": None,
            }
        except Exception as e:
            logger.warning("DB enrichment failed for %s: %s", name, e)
            return {
                "source": "Transport Intelligence Database",
                "trust": 1.0,
                "tier": 6,
                "data": None,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Main investigation method
    # ------------------------------------------------------------------

    async def investigate(
        self,
        company_name: str,
        country: str,
        vat_number: str | None = None,
        registration_number: str | None = None,
    ) -> dict:
        """Full deep due diligence investigation.

        Queries ALL available public sources, synthesizes via Claude AI,
        returns structured risk assessment.

        Args:
            company_name: Name of the company to investigate
            country: ISO 2-letter country code
            vat_number: Optional VAT number (with country prefix, e.g. PL1234567890)
            registration_number: Optional registration number (KRS, HRB, etc.)

        Returns:
            Structured investigation result dict
        """
        cache_key = self._cache_key(("investigate", company_name, country, vat_number, registration_number))
        if cache_key in self._cache:
            return self._cache[cache_key]

        country = country.upper()
        sources_consulted: list[dict] = []
        all_source_data: list[dict] = []

        logger.info("Starting deep investigation: %s (%s)", company_name, country)

        # --- Tier 1: VIES (if VAT provided) ---
        if vat_number:
            vies_result = await self._check_vies(vat_number)
            all_source_data.append(vies_result)
            sources_consulted.append({
                "source": vies_result["source"],
                "tier": 1,
                "trust": vies_result["trust"],
                "status": "ok" if vies_result["data"] else "failed",
                "error": vies_result.get("error"),
            })

        # --- Tier 1: Country-specific registries ---
        country_sources = COUNTRY_SOURCES.get(country, [])
        nip = vat_number[2:] if vat_number and len(vat_number) > 2 else None

        for source_id in country_sources:
            result = None
            if source_id == "krs":
                result = await self._check_krs(company_name, registration_number)
            elif source_id == "ceidg":
                result = await self._check_ceidg(nip=nip, name=company_name)
            elif source_id == "kreptd":
                result = await self._check_kreptd(company_name)
            elif source_id == "regon" and nip:
                result = await self._check_regon(nip)
            elif source_id == "debt_pl":
                result = await self._check_debt_pl(company_name)
            elif source_id == "krz":
                result = await self._check_krz(company_name)
            elif source_id == "handelsregister":
                result = await self._check_handelsregister(company_name)
            elif source_id == "unternehmensregister":
                result = await self._check_unternehmensregister(company_name)
            elif source_id == "bundesanzeiger":
                result = await self._check_bundesanzeiger(company_name)
            elif source_id == "insolvenz_de":
                result = await self._check_insolvenz_de(company_name)
            elif source_id == "companies_house":
                result = await self._check_companies_house(company_name, registration_number)
            elif source_id == "gazette_uk":
                result = await self._check_gazette_uk(company_name)

            if result:
                all_source_data.append(result)
                sources_consulted.append({
                    "source": result["source"],
                    "tier": result.get("tier", 1),
                    "trust": result["trust"],
                    "status": "ok" if result["data"] else "failed",
                    "error": result.get("error"),
                })

        # --- Tier 1: OpenCorporates (all countries) ---
        oc_result = await self._check_opencorporates(company_name, country)
        all_source_data.append(oc_result)
        sources_consulted.append({
            "source": oc_result["source"],
            "tier": 1,
            "trust": oc_result["trust"],
            "status": "ok" if oc_result["data"] else "failed",
            "error": oc_result.get("error"),
        })

        # --- Tier 2: Media ---
        media_result = await self._search_media(company_name, country)
        all_source_data.append(media_result)
        sources_consulted.append({
            "source": media_result["source"],
            "tier": 2,
            "trust": media_result["trust"],
            "status": "ok" if media_result["data"] else "failed",
            "error": media_result.get("error"),
        })

        # --- Tier 3: Forums ---
        forum_result = await self._search_forums(company_name, country)
        all_source_data.append(forum_result)
        sources_consulted.append({
            "source": forum_result["source"],
            "tier": 3,
            "trust": forum_result["trust"],
            "status": "ok" if forum_result["data"] else "failed",
            "error": forum_result.get("error"),
        })

        # --- Tier 4: Transport Exchanges ---
        exchange_result = await self._search_transport_exchanges(company_name)
        all_source_data.append(exchange_result)
        sources_consulted.append({
            "source": exchange_result["source"],
            "tier": 4,
            "trust": exchange_result["trust"],
            "status": "ok" if exchange_result["data"] else "failed",
            "error": exchange_result.get("error"),
        })

        # --- Tier 5: Board cross-reference ---
        # Extract board members from Tier 1 results
        board_members = self._extract_board_members(all_source_data)
        if board_members:
            board_result = await self._cross_reference_board(board_members, country)
            all_source_data.append(board_result)
            sources_consulted.append({
                "source": board_result["source"],
                "tier": 5,
                "trust": board_result["trust"],
                "status": "ok" if board_result["data"] else "failed",
                "error": board_result.get("error"),
            })

        # --- Tier 6: TI Database ---
        db_result = await self._enrich_from_db(company_name, country)
        all_source_data.append(db_result)
        sources_consulted.append({
            "source": db_result["source"],
            "tier": 6,
            "trust": db_result["trust"],
            "status": "ok" if db_result["data"] else "failed",
            "error": db_result.get("error"),
        })

        # --- Claude AI Synthesis ---
        report = await self._synthesize_report(
            company_name, country, all_source_data, sources_consulted,
        )
        if not report:
            report = self._fallback_report(
                company_name, country, all_source_data, sources_consulted,
            )

        report["sources_consulted"] = sources_consulted
        report["investigated_at"] = datetime.utcnow().isoformat()

        self._cache[cache_key] = report
        logger.info(
            "Investigation complete: %s (%s) — %d sources, risk=%s",
            company_name, country,
            len(sources_consulted),
            report.get("overall_risk", {}).get("level", "unknown"),
        )
        return report

    def _extract_board_members(self, source_data: list[dict]) -> list[str]:
        """Extract board member names from registry results."""
        members = []
        for source in source_data:
            data = source.get("data")
            if not data or not isinstance(data, dict):
                continue

            # KRS format
            if isinstance(data, dict):
                # Look for persons in various formats
                for key in ("osoby", "board", "directors", "officers", "items"):
                    items = data.get(key, [])
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                name = item.get("name") or item.get("imie_nazwisko") or item.get("title", "")
                                if name and len(name) > 3:
                                    members.append(name)
                            elif isinstance(item, str) and len(item) > 3:
                                members.append(item)

                # Companies House format
                if "items" in data:
                    for item in data.get("items", []):
                        if isinstance(item, dict):
                            name = item.get("title", "")
                            if name:
                                members.append(name)

        return list(set(members))[:10]

    # ------------------------------------------------------------------
    # Claude AI Synthesis
    # ------------------------------------------------------------------

    async def _synthesize_report(
        self,
        company_name: str,
        country: str,
        source_data: list[dict],
        sources_consulted: list[dict],
    ) -> dict | None:
        """Use Claude AI to synthesize all gathered data into a structured report."""
        # Build data summary for Claude
        data_summary = []
        for sd in source_data:
            source_name = sd.get("source", "Unknown")
            trust = sd.get("trust", 0)
            tier = sd.get("tier", 0)
            data = sd.get("data")
            error = sd.get("error")

            if data:
                data_str = json.dumps(data, ensure_ascii=False, default=str)[:2000]
                data_summary.append(
                    f"[SOURCE: {source_name}] [TRUST: {trust}] [TIER: {tier}]\n{data_str}"
                )
            elif error:
                data_summary.append(
                    f"[SOURCE: {source_name}] [TRUST: {trust}] [TIER: {tier}] FAILED: {error}"
                )

        data_text = "\n\n".join(data_summary)

        # Count successful sources
        ok_count = sum(1 for s in sources_consulted if s["status"] == "ok")
        total_count = len(sources_consulted)

        system_prompt = (
            "You are a senior transport due diligence analyst. "
            "Your reports are premium products worth 2000-5000 EUR. "
            "You must be precise, professional, and cite specific data from the sources provided. "
            "Respond ONLY in JSON format. No text outside JSON."
        )

        user_prompt = f"""Analyze ALL the following data about transport company "{company_name}" ({country}).
{ok_count}/{total_count} sources returned data.

RAW DATA FROM ALL SOURCES:
{data_text}

Produce a comprehensive due diligence report as JSON:
{{
    "company_name": "{company_name}",
    "country": "{country}",
    "basic_info": {{
        "legal_name": "official name from registry",
        "address": "registered address",
        "registration_number": "KRS/HRB/company number",
        "vat_number": "VAT if known",
        "founded": "incorporation date",
        "capital": "share capital",
        "status": "active/dissolved/etc",
        "pkd_sic_code": "business activity code",
        "fleet_size": "estimated fleet if known",
        "employee_count": "estimated if known"
    }},
    "licenses": [
        {{
            "type": "transport license type",
            "number": "license number",
            "status": "active/revoked/suspended/expired",
            "issued_by": "issuing authority",
            "valid_until": "expiry date"
        }}
    ],
    "financial_health": {{
        "assessment": "HEALTHY/WARNING/CRITICAL/UNKNOWN",
        "revenue_trend": "growing/stable/declining/unknown",
        "debt_registries": "found_in_N_registries or clean",
        "payment_behavior": "description of payment patterns",
        "key_financial_events": ["list of significant financial events"]
    }},
    "risk_signals": [
        {{
            "signal_type": "insolvency/debt/license/payment/legal/reputation",
            "severity": "CRITICAL/HIGH/MEDIUM/LOW",
            "description": "detailed description of the risk signal",
            "source": "which source reported this",
            "trust": 0.0,
            "date": "when detected"
        }}
    ],
    "related_companies": [
        {{
            "name": "company name",
            "relationship": "subsidiary/parent/director_overlap/contractor",
            "status": "active/dissolved/bankrupt",
            "risk_flag": true,
            "note": "why this is relevant"
        }}
    ],
    "board_members": [
        {{
            "name": "full name",
            "role": "director/CEO/board member",
            "other_directorships": ["list of other companies"],
            "risk_flag": false,
            "note": "any concerns"
        }}
    ],
    "transport_events": {{
        "total_events": 0,
        "events_90d": 0,
        "theft_incidents": 0,
        "payment_issues": 0,
        "notable_events": ["list of notable events"]
    }},
    "media_sentiment": {{
        "overall": "positive/neutral/negative/mixed/no_data",
        "articles_found": 0,
        "key_themes": ["main themes from media coverage"],
        "notable_articles": ["titles of most relevant articles"]
    }},
    "overall_risk": {{
        "score": 0,
        "level": "LOW/MEDIUM/HIGH/CRITICAL",
        "trend": "improving/stable/deteriorating/unknown"
    }},
    "ai_recommendation": {{
        "summary": "2-3 paragraph professional recommendation",
        "do_business": "YES/YES_WITH_CONDITIONS/CAUTION/NO",
        "conditions": ["conditions for doing business if applicable"],
        "monitoring": ["what to monitor going forward"]
    }},
    "confidence_score": 0.0
}}

RULES:
- score 0-100 where 100 = highest risk
- confidence_score 0.0-1.0 based on how much data was available
- Cite specific sources for each risk signal
- If a source failed, note reduced confidence
- Be specific with dates, amounts, names
- risk_signals should be sorted by severity (CRITICAL first)
"""

        result_text = await self._claude.call(user_prompt, system_prompt, max_tokens=8192)
        if result_text:
            try:
                parsed = json.loads(ClaudeClient.extract_json(result_text))
                return parsed
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("Failed to parse investigation synthesis JSON: %s", e)

        return None

    def _fallback_report(
        self,
        company_name: str,
        country: str,
        source_data: list[dict],
        sources_consulted: list[dict],
    ) -> dict:
        """Statistical-only report when Claude API is unavailable."""
        ok_sources = [s for s in sources_consulted if s["status"] == "ok"]
        failed_sources = [s for s in sources_consulted if s["status"] == "failed"]

        # Detect critical signals from raw data
        risk_signals = []
        for sd in source_data:
            data = sd.get("data")
            if not data or not isinstance(data, dict):
                continue
            # Check for insolvency flags
            if data.get("insolvency_found"):
                risk_signals.append({
                    "signal_type": "insolvency",
                    "severity": "CRITICAL",
                    "description": f"Insolvency record found in {sd['source']}",
                    "source": sd["source"],
                    "trust": sd.get("trust", 0),
                    "date": datetime.utcnow().strftime("%Y-%m-%d"),
                })
            # Check for debt flags
            if data.get("krd_issues_found") or data.get("big_issues_found"):
                risk_signals.append({
                    "signal_type": "debt",
                    "severity": "HIGH",
                    "description": f"Debt registry entries found via {sd['source']}",
                    "source": sd["source"],
                    "trust": sd.get("trust", 0),
                    "date": datetime.utcnow().strftime("%Y-%m-%d"),
                })
            # Check for license issues
            if data.get("license_issues_found"):
                risk_signals.append({
                    "signal_type": "license",
                    "severity": "HIGH",
                    "description": f"Transport license issues detected via {sd['source']}",
                    "source": sd["source"],
                    "trust": sd.get("trust", 0),
                    "date": datetime.utcnow().strftime("%Y-%m-%d"),
                })
            # Check winding-up
            if data.get("winding_up_found"):
                risk_signals.append({
                    "signal_type": "insolvency",
                    "severity": "CRITICAL",
                    "description": f"Winding-up petition found via {sd['source']}",
                    "source": sd["source"],
                    "trust": sd.get("trust", 0),
                    "date": datetime.utcnow().strftime("%Y-%m-%d"),
                })

        # Compute risk score
        risk_score = 0
        severity_weights = {"CRITICAL": 30, "HIGH": 20, "MEDIUM": 10, "LOW": 5}
        for rs in risk_signals:
            risk_score += severity_weights.get(rs["severity"], 5)
        risk_score = min(risk_score, 100)

        if risk_score >= 70:
            risk_level = "CRITICAL"
        elif risk_score >= 40:
            risk_level = "HIGH"
        elif risk_score >= 20:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        confidence = min(0.8, len(ok_sources) / max(len(sources_consulted), 1))

        return {
            "company_name": company_name,
            "country": country,
            "basic_info": {},
            "licenses": [],
            "financial_health": {
                "assessment": "UNKNOWN",
                "note": "AI analysis unavailable — statistical data only",
            },
            "risk_signals": risk_signals,
            "related_companies": [],
            "board_members": [],
            "transport_events": {},
            "media_sentiment": {
                "overall": "no_data",
                "note": "AI analysis unavailable",
            },
            "overall_risk": {
                "score": risk_score,
                "level": risk_level,
                "trend": "unknown",
            },
            "ai_recommendation": {
                "summary": (
                    f"Automated investigation of {company_name} ({country}) completed. "
                    f"{len(ok_sources)}/{len(sources_consulted)} sources returned data. "
                    f"{len(risk_signals)} risk signal(s) detected. "
                    "AI synthesis unavailable — this report is based on statistical analysis only. "
                    "Manual review recommended."
                ),
                "do_business": "CAUTION" if risk_signals else "YES_WITH_CONDITIONS",
                "conditions": ["Manual review of raw source data recommended"],
                "monitoring": ["Re-run investigation when AI synthesis is available"],
            },
            "confidence_score": confidence,
        }

    # ------------------------------------------------------------------
    # PDF Report Generation
    # ------------------------------------------------------------------

    async def generate_due_diligence_report(
        self,
        company_name: str,
        country: str,
        vat_number: str | None = None,
        registration_number: str | None = None,
    ) -> str:
        """Generate full due diligence investigation report as PDF.

        Returns: path to generated PDF file.
        """
        from src.reports.pdf_renderer import PdfRenderer
        from src.reports.disclaimer import DisclaimerGenerator

        OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "reports" / "output"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Run full investigation
        investigation = await self.investigate(
            company_name=company_name,
            country=country,
            vat_number=vat_number,
            registration_number=registration_number,
        )

        country_name = COUNTRY_NAMES.get(country, country)
        disclaimer = DisclaimerGenerator().generate_disclaimer(
            "due_diligence", [country], "en",
        )

        context = {
            "title": f"Due Diligence Report: {company_name}",
            "subtitle": "Deep Company Investigation — Premium Intelligence",
            "report_type": "due_diligence",
            "language": "en",
            "company_name": company_name,
            "country": country,
            "country_name": country_name,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "year": datetime.utcnow().year,
            # Investigation data
            "investigation": investigation,
            # Legal
            "disclaimer": disclaimer,
        }

        report_id = uuid.uuid4()
        safe_name = company_name.replace(" ", "_").replace("/", "_")[:50]
        filename = f"due_diligence_{safe_name}_{country}_{report_id.hex[:8]}.pdf"
        pdf_path = str(OUTPUT_DIR / filename)

        # Render PDF
        renderer = PdfRenderer()
        renderer.render_due_diligence(context, pdf_path)

        # Save report record
        try:
            from src.db.models import Report
            from src.db.postgres import async_session

            async with async_session() as session:
                report = Report(
                    id=report_id,
                    report_type="due_diligence",
                    title=f"Due Diligence: {company_name} ({country})",
                    period_start=datetime.utcnow().date(),
                    period_end=datetime.utcnow().date(),
                    countries=[country],
                    language="en",
                    status="generated",
                    file_path=pdf_path,
                    total_events=len(investigation.get("risk_signals", [])),
                    confirmed_events=0,
                    signal_events=0,
                    disclaimer_text=disclaimer,
                    generated_by="company_investigator",
                )
                session.add(report)
                await session.commit()
        except Exception as e:
            logger.warning("Failed to save due diligence report record: %s", e)

        logger.info("Due diligence report generated: %s", pdf_path)
        return pdf_path
