"""PatternAnalyzer — Claude API-powered analysis of transport event patterns.

Follows the same pattern as src/pipeline/translator.py:
- httpx.AsyncClient -> POST https://api.anthropic.com/v1/messages
- Rate limiting: 5 requests/minute (analysis prompts are longer/costlier)
- In-memory cache: MD5 of JSON-serialized input data
- Fallback: statistical-only results when API unavailable
"""

import hashlib
import json
import logging
from collections import Counter

from src.config import settings
from src.utils.claude_client import ClaudeClient, COUNTRY_NAMES

logger = logging.getLogger(__name__)


class PatternAnalyzer:
    """AI-powered analysis of transport event patterns using Claude API."""

    def __init__(self):
        self._cache: dict[str, dict | str] = {}
        self._claude = ClaudeClient(
            api_key=settings.anthropic_api_key,
            max_requests_per_minute=5,
            timeout=60.0,
        )

    def _cache_key(self, data) -> str:
        """MD5 hash of JSON-serialized input data."""
        raw = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def analyze_hotspot(self, events_at_location: list[dict]) -> dict:
        """Analyze events at a single hotspot location.

        Returns dict with: location, event_count, pattern, modus_operandi,
        time_pattern, target_cargo, risk_level, recommendation.
        """
        if not events_at_location:
            return self._fallback_hotspot([])

        cache_key = self._cache_key(("hotspot", events_at_location))
        if cache_key in self._cache:
            return self._cache[cache_key]

        location = events_at_location[0].get("region", "Unknown")
        country = events_at_location[0].get("country_code", "")

        events_text = "\n".join(
            f"- [{e.get('date', '')}] {e.get('event_type', '')} "
            f"({e.get('severity', '')}) — {e.get('description', e.get('title', ''))[:150]}"
            for e in events_at_location[:30]
        )

        system_prompt = (
            "Jestes analitykiem bezpieczenstwa transportu. Odpowiadaj w formacie JSON. "
            "Nie dodawaj zadnego tekstu poza JSON."
        )
        user_prompt = (
            f"Przeanalizuj ponizsze zdarzenia z jednej lokalizacji ({location}, {country}).\n\n"
            f"Zdarzenia:\n{events_text}\n\n"
            f"Zwroc JSON:\n"
            f'{{"pattern": "opis wzorca (1-2 zdania)", '
            f'"modus_operandi": "opis sposobu dzialania", '
            f'"time_pattern": "opis wzorca czasowego (np. nocne, weekendowe)", '
            f'"target_cargo": "najczesciej kradzione towary lub cel ataku", '
            f'"risk_level": "CRITICAL/HIGH/MEDIUM/LOW", '
            f'"recommendation": "rekomendacja bezpieczenstwa (1-2 zdania)"}}'
        )

        result_text = await self._claude.call(user_prompt, system_prompt)
        if result_text:
            try:
                parsed = json.loads(ClaudeClient.extract_json(result_text))
                result = {
                    "location": location,
                    "country_code": country,
                    "event_count": len(events_at_location),
                    **parsed,
                }
                self._cache[cache_key] = result
                return result
            except (json.JSONDecodeError, ValueError, TypeError):
                logger.warning("Failed to parse hotspot analysis JSON, using fallback")

        result = self._fallback_hotspot(events_at_location)
        self._cache[cache_key] = result
        return result

    async def analyze_corridor(self, events_on_route: list[dict]) -> dict:
        """Analyze events along a transport corridor.

        Returns dict with: corridor, total_events, hotspots, trend, recommendations.
        """
        if not events_on_route:
            return self._fallback_corridor([])

        cache_key = self._cache_key(("corridor", events_on_route))
        if cache_key in self._cache:
            return self._cache[cache_key]

        countries = sorted(set(e.get("country_code", "") for e in events_on_route))
        corridor_name = " - ".join(countries) if countries else "Unknown"

        events_text = "\n".join(
            f"- [{e.get('date', '')}] {e.get('country_code', '')} / "
            f"{e.get('region', '')} — {e.get('event_type', '')} "
            f"({e.get('severity', '')}): {e.get('title', '')[:100]}"
            for e in events_on_route[:30]
        )

        system_prompt = (
            "Jestes analitykiem bezpieczenstwa transportu. Odpowiadaj w formacie JSON. "
            "Nie dodawaj zadnego tekstu poza JSON."
        )
        user_prompt = (
            f"Przeanalizuj zdarzenia na korytarzu transportowym {corridor_name}.\n\n"
            f"Zdarzenia:\n{events_text}\n\n"
            f"Zwroc JSON:\n"
            f'{{"hotspots": ["lista najgroniejszych lokalizacji na trasie"], '
            f'"trend": "rising/stable/declining", '
            f'"recommendations": ["lista rekomendacji bezpieczenstwa"]}}'
        )

        result_text = await self._claude.call(user_prompt, system_prompt)
        if result_text:
            try:
                parsed = json.loads(ClaudeClient.extract_json(result_text))
                result = {
                    "corridor": corridor_name,
                    "total_events": len(events_on_route),
                    "countries": countries,
                    **parsed,
                }
                self._cache[cache_key] = result
                return result
            except (json.JSONDecodeError, ValueError, TypeError):
                logger.warning("Failed to parse corridor analysis JSON, using fallback")

        result = self._fallback_corridor(events_on_route)
        self._cache[cache_key] = result
        return result

    async def analyze_company(
        self, company_events: list[dict], company_financials: dict
    ) -> dict:
        """Analyze company risk based on events and financial data.

        Returns dict with: company, risk_score (0-100), risk_factors, recommendation.
        """
        if not company_events and not company_financials:
            return self._fallback_company([], {})

        cache_key = self._cache_key(("company", company_events, company_financials))
        if cache_key in self._cache:
            return self._cache[cache_key]

        company_name = (
            company_events[0].get("company_name", "Unknown")
            if company_events
            else company_financials.get("name", "Unknown")
        )

        events_text = "\n".join(
            f"- [{e.get('date', '')}] {e.get('event_type', '')} "
            f"({e.get('severity', '')}): {e.get('title', '')[:100]}"
            for e in company_events[:20]
        )

        financials_text = (
            f"Status finansowy: {company_financials.get('financial_status', 'unknown')}\n"
            f"Risk score: {company_financials.get('risk_score', 0)}\n"
            f"Kraj: {company_financials.get('country_code', '')}\n"
            f"Typ: {company_financials.get('company_type', '')}"
        )

        system_prompt = (
            "Jestes analitykiem bezpieczenstwa transportu. Odpowiadaj w formacie JSON. "
            "Nie dodawaj zadnego tekstu poza JSON."
        )
        user_prompt = (
            f"Przeanalizuj sytuacje firmy transportowej '{company_name}'.\n\n"
            f"Zdarzenia:\n{events_text}\n\n"
            f"Dane finansowe:\n{financials_text}\n\n"
            f"Zwroc JSON:\n"
            f'{{"risk_score": 0, '
            f'"risk_factors": ["lista czynnikow ryzyka"], '
            f'"recommendation": "rekomendacja dot. wspolpracy z ta firma"}}'
            f"\nrisk_score: 0-100, gdzie 100 = najwyzsze ryzyko"
        )

        result_text = await self._claude.call(user_prompt, system_prompt)
        if result_text:
            try:
                parsed = json.loads(ClaudeClient.extract_json(result_text))
                result = {
                    "company": company_name,
                    "country_code": company_financials.get("country_code", ""),
                    **parsed,
                }
                self._cache[cache_key] = result
                return result
            except (json.JSONDecodeError, ValueError, TypeError):
                logger.warning("Failed to parse company analysis JSON, using fallback")

        result = self._fallback_company(company_events, company_financials)
        self._cache[cache_key] = result
        return result

    async def generate_executive_summary(
        self, all_events: list[dict], period_days: int
    ) -> str:
        """Generate AI executive summary for all events in a period.

        Returns 3-5 paragraph text.
        """
        if not all_events:
            return self._fallback_executive_summary([], period_days)

        cache_key = self._cache_key(("exec_summary", len(all_events), period_days))
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Build statistics for the prompt
        type_counts = Counter(e.get("event_type", "other") for e in all_events)
        country_counts = Counter(e.get("country_code", "") for e in all_events)
        severity_counts = Counter(
            (e.get("severity") or "MEDIUM").upper() for e in all_events
        )

        stats_text = (
            f"Okres: ostatnie {period_days} dni\n"
            f"Laczna liczba zdarzen: {len(all_events)}\n"
            f"Wg typu: {dict(type_counts.most_common(10))}\n"
            f"Wg kraju: {dict(country_counts.most_common(10))}\n"
            f"Wg severity: {dict(severity_counts)}\n"
        )

        # Sample recent critical/high events
        critical_events = [
            e for e in all_events
            if (e.get("severity") or "").upper() in ("CRITICAL", "HIGH")
        ][:10]
        events_text = "\n".join(
            f"- [{e.get('date', '')}] {e.get('country_code', '')} — "
            f"{e.get('event_type', '')} ({e.get('severity', '')}): "
            f"{e.get('title', '')[:100]}"
            for e in critical_events
        )

        system_prompt = (
            "Jestes glownym analitykiem Transport Intelligence. "
            "Pisz po polsku, profesjonalnie, zwiezle. "
            "Nie uzywaj markdowna ani formatowania — tylko tekst ciagle akapitami."
        )
        user_prompt = (
            f"Napisz executive summary (3-5 akapitow) dla raportu bezpieczenstwa transportu.\n\n"
            f"Statystyki:\n{stats_text}\n\n"
            f"Najwazniejsze zdarzenia:\n{events_text}\n\n"
            f"Executive summary powinno:\n"
            f"1. Zaczac od kluczowych liczb i trendow\n"
            f"2. Wskazac najgroniejsze regiony i typy zdarzen\n"
            f"3. Opisac zidentyfikowane wzorce\n"
            f"4. Zakonczyc rekomendacjami"
        )

        result_text = await self._claude.call(user_prompt, system_prompt)
        if result_text:
            self._cache[cache_key] = result_text
            return result_text

        result = self._fallback_executive_summary(all_events, period_days)
        self._cache[cache_key] = result
        return result

    async def generate_country_analysis(
        self, country_events: list[dict], country_code: str
    ) -> str:
        """Generate AI analysis for a specific country.

        Returns 2-4 paragraph text.
        """
        if not country_events:
            return self._fallback_country_analysis([], country_code)

        cache_key = self._cache_key(
            ("country", country_code, len(country_events))
        )
        if cache_key in self._cache:
            return self._cache[cache_key]

        type_counts = Counter(e.get("event_type", "other") for e in country_events)
        severity_counts = Counter(
            (e.get("severity") or "MEDIUM").upper() for e in country_events
        )
        regions = Counter(e.get("region", "") for e in country_events if e.get("region"))

        stats_text = (
            f"Kraj: {country_code}\n"
            f"Laczna liczba zdarzen: {len(country_events)}\n"
            f"Wg typu: {dict(type_counts.most_common(10))}\n"
            f"Wg severity: {dict(severity_counts)}\n"
            f"Najaktywniejsze regiony: {dict(regions.most_common(5))}\n"
        )

        recent = sorted(
            country_events,
            key=lambda e: e.get("date", ""),
            reverse=True,
        )[:10]
        events_text = "\n".join(
            f"- [{e.get('date', '')}] {e.get('region', '')} — "
            f"{e.get('event_type', '')} ({e.get('severity', '')}): "
            f"{e.get('title', '')[:100]}"
            for e in recent
        )

        country_name = COUNTRY_NAMES.get(country_code, country_code)

        system_prompt = (
            "Jestes analitykiem Transport Intelligence. "
            "Pisz po polsku, profesjonalnie, zwiezle. "
            "Nie uzywaj markdowna ani formatowania — tylko tekst ciagle akapitami."
        )
        user_prompt = (
            f"Napisz analize bezpieczenstwa transportu dla kraju: {country_name} ({country_code}).\n\n"
            f"Statystyki:\n{stats_text}\n\n"
            f"Ostatnie zdarzenia:\n{events_text}\n\n"
            f"Analiza (2-4 akapity) powinna:\n"
            f"1. Opisac ogolna sytuacje w kraju\n"
            f"2. Wskazac najgroniejsze regiony i trasy\n"
            f"3. Opisac dominujace typy zdarzen\n"
            f"4. Dac rekomendacje dla przewoznikow operujacych w tym kraju"
        )

        result_text = await self._claude.call(user_prompt, system_prompt)
        if result_text:
            self._cache[cache_key] = result_text
            return result_text

        result = self._fallback_country_analysis(country_events, country_code)
        self._cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    # Fallback methods (statistical-only, no AI)
    # ------------------------------------------------------------------

    def _fallback_hotspot(self, events: list[dict]) -> dict:
        if not events:
            return {
                "location": "Unknown",
                "country_code": "",
                "event_count": 0,
                "pattern": "Brak danych",
                "modus_operandi": "N/A",
                "time_pattern": "N/A",
                "target_cargo": "N/A",
                "risk_level": "LOW",
                "recommendation": "Monitorowac sytuacje.",
            }

        location = events[0].get("region", "Unknown")
        country = events[0].get("country_code", "")
        type_counts = Counter(e.get("event_type", "other") for e in events)
        severity_counts = Counter(
            (e.get("severity") or "MEDIUM").upper() for e in events
        )
        top_type = type_counts.most_common(1)[0][0] if type_counts else "other"

        # Determine risk level from severity distribution
        crit_high = severity_counts.get("CRITICAL", 0) + severity_counts.get("HIGH", 0)
        if crit_high >= 3 or severity_counts.get("CRITICAL", 0) >= 1:
            risk_level = "CRITICAL"
        elif crit_high >= 1 or len(events) >= 5:
            risk_level = "HIGH"
        elif len(events) >= 3:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            "location": location,
            "country_code": country,
            "event_count": len(events),
            "pattern": f"Dominujacy typ zdarzen: {top_type} ({type_counts[top_type]} zdarzen)",
            "modus_operandi": f"Zidentyfikowano {len(type_counts)} typow zdarzen",
            "time_pattern": "Wymaga analizy AI",
            "target_cargo": "Wymaga analizy AI",
            "risk_level": risk_level,
            "recommendation": f"Region o podwyzszonym ryzyku — {len(events)} zdarzen. Zalecany monitoring.",
        }

    def _fallback_corridor(self, events: list[dict]) -> dict:
        if not events:
            return {
                "corridor": "Unknown",
                "total_events": 0,
                "countries": [],
                "hotspots": [],
                "trend": "stable",
                "recommendations": [],
            }

        countries = sorted(set(e.get("country_code", "") for e in events))
        corridor_name = " - ".join(countries) if countries else "Unknown"
        region_counts = Counter(
            f"{e.get('country_code', '')}/{e.get('region', '')}" for e in events
        )
        hotspots = [loc for loc, _ in region_counts.most_common(5)]

        return {
            "corridor": corridor_name,
            "total_events": len(events),
            "countries": countries,
            "hotspots": hotspots,
            "trend": "stable",
            "recommendations": [
                f"Monitorowac korytarz {corridor_name} — {len(events)} zdarzen.",
                f"Najgroniejsze lokalizacje: {', '.join(hotspots[:3])}.",
            ],
        }

    def _fallback_company(
        self, events: list[dict], financials: dict
    ) -> dict:
        company_name = (
            events[0].get("company_name", "Unknown")
            if events
            else financials.get("name", "Unknown")
        )
        financial_status = financials.get("financial_status", "unknown")

        risk_factors = []
        risk_score = 0

        if events:
            risk_score += min(len(events) * 10, 50)
            risk_factors.append(f"{len(events)} zdarzen w okresie")

        status_scores = {
            "bankrupt": 40, "critical": 35, "restructuring": 30,
            "warning": 20, "unknown": 10, "healthy": 0,
        }
        risk_score += status_scores.get(financial_status, 10)
        if financial_status in ("bankrupt", "critical", "restructuring"):
            risk_factors.append(f"Status finansowy: {financial_status}")

        risk_score = min(risk_score, 100)

        return {
            "company": company_name,
            "country_code": financials.get("country_code", ""),
            "risk_score": risk_score,
            "risk_factors": risk_factors or ["Brak zidentyfikowanych czynnikow ryzyka"],
            "recommendation": (
                "Firma wymaga szczegolowej weryfikacji."
                if risk_score >= 50
                else "Standardowy monitoring."
            ),
        }

    def _fallback_executive_summary(
        self, events: list[dict], period_days: int
    ) -> str:
        if not events:
            return (
                f"W analizowanym okresie {period_days} dni nie odnotowano zdarzen "
                f"wymagajacych szczegolowej analizy."
            )

        type_counts = Counter(e.get("event_type", "other") for e in events)
        country_counts = Counter(e.get("country_code", "") for e in events)
        severity_counts = Counter(
            (e.get("severity") or "MEDIUM").upper() for e in events
        )
        top_type = type_counts.most_common(1)[0][0] if type_counts else "other"
        top_country = country_counts.most_common(1)[0][0] if country_counts else ""

        return (
            f"W analizowanym okresie {period_days} dni zarejestrowano "
            f"{len(events)} zdarzen transportowych w {len(country_counts)} krajach. "
            f"Najczesciej wystepujacym typem zdarzen bylo {top_type} "
            f"({type_counts[top_type]} przypadkow).\n\n"
            f"Kraj z najwieksza liczba zdarzen to {top_country} "
            f"({country_counts[top_country]} zdarzen). "
            f"Zdarzenia krytyczne i wysokiego ryzyka stanowily "
            f"{severity_counts.get('CRITICAL', 0) + severity_counts.get('HIGH', 0)} "
            f"z {len(events)} wszystkich zdarzen.\n\n"
            f"Zalecany jest wzmozony monitoring regionow o najwyzszej koncentracji zdarzen "
            f"oraz weryfikacja firm transportowych z podwyzszonym profilem ryzyka."
        )

    def _fallback_country_analysis(
        self, events: list[dict], country_code: str
    ) -> str:
        if not events:
            return (
                f"W analizowanym okresie nie odnotowano zdarzen "
                f"w kraju {country_code}."
            )

        type_counts = Counter(e.get("event_type", "other") for e in events)
        regions = Counter(e.get("region", "") for e in events if e.get("region"))
        top_type = type_counts.most_common(1)[0][0] if type_counts else "other"
        top_region = regions.most_common(1)[0][0] if regions else "nieznany"

        return (
            f"W kraju {country_code} zarejestrowano {len(events)} zdarzen. "
            f"Dominujacym typem zdarzen bylo {top_type} "
            f"({type_counts[top_type]} przypadkow).\n\n"
            f"Regionem o najwyzszej aktywnosci jest {top_region} "
            f"({regions[top_region] if regions else 0} zdarzen). "
            f"Zalecany jest monitoring kluczowych tras tranzytowych w tym kraju."
        )
