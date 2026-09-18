"""Korelacja zdarzen i wykrywanie wzorcow (powiazane kradzieze, serie wypadkow).

Laczy zdarzenia z roznych zrodel dotyczace tego samego incydentu
oraz identyfikuje powtarzajace sie wzorce przestepcze:
- klastry geograficzne (SAME_LOCATION)
- wzorce per firma (SAME_COMPANY, FINANCIAL_OPERATIONAL)
- wzorce czasowe (SAME_TIME_PATTERN)
- trasy miedzynarodowe (CROSS_COUNTRY_ROUTE)
"""

import logging
import math
import re
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stale
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0

# Glowne europejskie korytarze transportowe (autostrady miedzynarodowe)
# Mapowanie: nazwa korytarza -> lista segmentow (country_code, road_id)
TRANSPORT_CORRIDORS: dict[str, list[tuple[str, str]]] = {
    "North Sea-Baltic": [
        ("NL", "A1"), ("DE", "A1"), ("DE", "A2"), ("PL", "A2"), ("LT", "A5"),
    ],
    "Rhine-Alpine": [
        ("NL", "A15"), ("DE", "A3"), ("DE", "A5"), ("CH", "A2"), ("IT", "A9"),
    ],
    "Scandinavian-Mediterranean": [
        ("FI", "E18"), ("SE", "E4"), ("DK", "E45"), ("DE", "A7"), ("AT", "A13"), ("IT", "A22"),
    ],
    "Orient-East-Med": [
        ("DE", "A17"), ("CZ", "D8"), ("AT", "A4"), ("HU", "M1"), ("RO", "A1"),
        ("BG", "A1"), ("GR", "A1"), ("TR", "E80"),
    ],
    "Baltic-Adriatic": [
        ("PL", "A1"), ("CZ", "D1"), ("AT", "A2"), ("SI", "A1"), ("IT", "A4"),
    ],
    "Mediterranean": [
        ("ES", "AP7"), ("FR", "A9"), ("IT", "A10"), ("SI", "A1"), ("HR", "A1"),
    ],
    "Rhine-Danube": [
        ("FR", "A35"), ("DE", "A5"), ("DE", "A6"), ("AT", "A1"), ("SK", "D1"),
        ("HU", "M1"), ("RO", "A1"),
    ],
    "Atlantic": [
        ("PT", "A1"), ("ES", "A1"), ("FR", "A63"), ("FR", "A10"),
    ],
    "E40 corridor": [
        ("BE", "E40"), ("DE", "A4"), ("DE", "E40"), ("PL", "A4"), ("PL", "E40"),
        ("UA", "E40"),
    ],
    "E30 corridor": [
        ("NL", "E30"), ("DE", "A3"), ("DE", "E30"), ("PL", "A2"), ("PL", "E30"),
    ],
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Oblicza odleglosc miedzy dwoma punktami w km (formula haversine)."""
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def _parse_date(val) -> datetime | None:
    """Parsuje date z roznych formatow."""
    if isinstance(val, datetime):
        return val
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00").replace("+00:00", ""))
    except (ValueError, TypeError):
        return None


def _get_road(event: dict) -> str | None:
    """Wyciaga identyfikator drogi z eventu."""
    loc = event.get("location", {})
    if isinstance(loc, dict):
        road = loc.get("road")
        if road:
            return road.upper().replace(" ", "").replace("-", "")
    # Fallback: szukaj w tekscie
    text = f"{event.get('title', '')} {event.get('description', '')}"
    m = re.search(r"\b([AaBbEe]\d{1,4})\b", text)
    if m:
        return m.group(1).upper()
    return None


def _get_company(event: dict) -> str | None:
    """Wyciaga nazwe firmy z eventu."""
    return event.get("company_name") or event.get("company") or None


def _get_coords(event: dict) -> tuple[float, float] | None:
    """Wyciaga wspolrzedne z eventu."""
    loc = event.get("location", {})
    if isinstance(loc, dict):
        lat = loc.get("latitude")
        lon = loc.get("longitude")
        if lat is not None and lon is not None:
            try:
                return float(lat), float(lon)
            except (ValueError, TypeError):
                pass
    return None


def _get_hour(event: dict) -> int | None:
    """Wyciaga godzine z daty eventu."""
    dt = _parse_date(event.get("date") or event.get("date_parsed"))
    if dt:
        return dt.hour
    return None


def _get_weekday(event: dict) -> int | None:
    """Wyciaga dzien tygodnia (0=pon, 6=nie)."""
    dt = _parse_date(event.get("date") or event.get("date_parsed"))
    if dt:
        return dt.weekday()
    return None


class EventCorrelator:
    """Koreluje zdarzenia z roznych zrodel i wykrywa wzorce."""

    def correlate(self, events: list[dict]) -> list[dict]:
        """Analizuje liste eventow i szuka wzorcow.

        Uruchamia wszystkie metody korelacji i zwraca polaczona liste.
        """
        correlations = []
        correlations.extend(self.find_location_clusters(events))
        correlations.extend(self.find_company_patterns(events))
        correlations.extend(self.find_time_patterns(events))
        correlations.extend(self.find_cross_country_routes(events))
        return correlations

    def find_location_clusters(
        self,
        events: list[dict],
        radius_km: float = 30.0,
        min_events: int = 3,
        time_window_days: int = 14,
    ) -> list[dict]:
        """Grupuje eventy blisko siebie geograficznie w oknie czasowym.

        Jesli >= min_events w promieniu radius_km w ciagu time_window_days
        -> tworzy korelacje SAME_LOCATION z centroidem klastra.
        """
        # Filtruj eventy z koordynatami
        geo_events = []
        for ev in events:
            coords = _get_coords(ev)
            dt = _parse_date(ev.get("date") or ev.get("date_parsed"))
            if coords and dt:
                geo_events.append((ev, coords, dt))

        if len(geo_events) < min_events:
            return []

        clusters = []
        used = set()

        for i, (ev_i, coords_i, dt_i) in enumerate(geo_events):
            if i in used:
                continue
            cluster_indices = [i]
            for j, (ev_j, coords_j, dt_j) in enumerate(geo_events):
                if j <= i or j in used:
                    continue
                dist = _haversine_km(coords_i[0], coords_i[1], coords_j[0], coords_j[1])
                time_diff = abs((dt_i - dt_j).days)
                if dist <= radius_km and time_diff <= time_window_days:
                    cluster_indices.append(j)

            if len(cluster_indices) >= min_events:
                for idx in cluster_indices:
                    used.add(idx)
                # Centroid
                lats = [geo_events[idx][1][0] for idx in cluster_indices]
                lons = [geo_events[idx][1][1] for idx in cluster_indices]
                centroid_lat = sum(lats) / len(lats)
                centroid_lon = sum(lons) / len(lons)

                cluster_events = [geo_events[idx][0] for idx in cluster_indices]
                correlation = {
                    "type": "SAME_LOCATION",
                    "events": cluster_events,
                    "event_count": len(cluster_events),
                    "centroid": {"latitude": centroid_lat, "longitude": centroid_lon},
                    "radius_km": radius_km,
                    "time_window_days": time_window_days,
                    "countries": list({ev.get("country_code") for ev in cluster_events if ev.get("country_code")}),
                }
                correlation["confidence"] = self.calculate_confidence(correlation)
                clusters.append(correlation)

        return clusters

    def find_company_patterns(self, events: list[dict]) -> list[dict]:
        """Grupuje eventy per firma i szuka wzorcow.

        - >= 3 zdarzenia w 30 dni -> SAME_COMPANY
        - problemy finansowe + zdarzenia operacyjne -> FINANCIAL_OPERATIONAL
        """
        company_events: dict[str, list[dict]] = defaultdict(list)
        for ev in events:
            company = _get_company(ev)
            if company:
                company_events[company.lower()].append(ev)

        correlations = []

        for company_name, comp_events in company_events.items():
            if len(comp_events) < 2:
                continue

            # Sortuj po dacie
            dated = []
            for ev in comp_events:
                dt = _parse_date(ev.get("date") or ev.get("date_parsed"))
                dated.append((ev, dt))
            dated.sort(key=lambda x: x[1] or datetime.min)

            # Szukaj 3+ zdarzen w oknie 30 dni
            for i in range(len(dated)):
                window_events = [dated[i][0]]
                for j in range(i + 1, len(dated)):
                    if dated[j][1] and dated[i][1]:
                        if (dated[j][1] - dated[i][1]).days <= 30:
                            window_events.append(dated[j][0])
                        else:
                            break

                if len(window_events) >= 3:
                    correlation = {
                        "type": "SAME_COMPANY",
                        "company": company_name,
                        "events": window_events,
                        "event_count": len(window_events),
                        "time_window_days": 30,
                        "countries": list({ev.get("country_code") for ev in window_events if ev.get("country_code")}),
                    }
                    correlation["confidence"] = self.calculate_confidence(correlation)
                    correlations.append(correlation)
                    break  # jedno dopasowanie per firma

            # FINANCIAL_OPERATIONAL: polaczenie finansowych i operacyjnych
            financial_types = {"bankruptcy", "restructuring", "payment_issue"}
            operational_types = {"theft_cargo", "theft_fuel", "theft_vehicle", "damage", "delay"}

            has_financial = any(ev.get("event_type") in financial_types for ev in comp_events)
            has_operational = any(ev.get("event_type") in operational_types for ev in comp_events)

            if has_financial and has_operational:
                correlation = {
                    "type": "FINANCIAL_OPERATIONAL",
                    "company": company_name,
                    "events": comp_events,
                    "event_count": len(comp_events),
                    "financial_events": [ev for ev in comp_events if ev.get("event_type") in financial_types],
                    "operational_events": [ev for ev in comp_events if ev.get("event_type") in operational_types],
                    "countries": list({ev.get("country_code") for ev in comp_events if ev.get("country_code")}),
                }
                correlation["confidence"] = self.calculate_confidence(correlation)
                correlations.append(correlation)

        return correlations

    def find_time_patterns(self, events: list[dict]) -> list[dict]:
        """Szuka powtarzajacych sie godzin/dni tygodnia.

        Np. kradzieze w piatek 22:00-04:00 -> SAME_TIME_PATTERN.
        """
        # Grupuj zdarzenia typu theft per (dzien_tygodnia, okno_godzinowe)
        theft_types = {"theft_cargo", "theft_fuel", "theft_vehicle"}
        theft_events = [ev for ev in events if ev.get("event_type") in theft_types]

        if len(theft_events) < 3:
            return []

        # Okna godzinowe: nocne (22-04), poranne (06-10), dzienne (10-16), wieczorne (16-22)
        time_windows = {
            "night_22_04": (22, 4),
            "morning_06_10": (6, 10),
            "day_10_16": (10, 16),
            "evening_16_22": (16, 22),
        }

        # Grupuj per (dzien, okno)
        pattern_groups: dict[tuple[int, str], list[dict]] = defaultdict(list)

        for ev in theft_events:
            weekday = _get_weekday(ev)
            hour = _get_hour(ev)
            if weekday is None or hour is None:
                continue
            for window_name, (start_h, end_h) in time_windows.items():
                if start_h > end_h:
                    # Nocne okno: 22-04 = 22..23 + 0..3
                    if hour >= start_h or hour < end_h:
                        pattern_groups[(weekday, window_name)].append(ev)
                        break
                else:
                    if start_h <= hour < end_h:
                        pattern_groups[(weekday, window_name)].append(ev)
                        break

        correlations = []
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        for (weekday, window_name), group_events in pattern_groups.items():
            if len(group_events) >= 3:
                correlation = {
                    "type": "SAME_TIME_PATTERN",
                    "day_of_week": day_names[weekday],
                    "time_window": window_name,
                    "events": group_events,
                    "event_count": len(group_events),
                    "countries": list({ev.get("country_code") for ev in group_events if ev.get("country_code")}),
                }
                correlation["confidence"] = self.calculate_confidence(correlation)
                correlations.append(correlation)

        return correlations

    def find_cross_country_routes(self, events: list[dict]) -> list[dict]:
        """Szuka zdarzen na tej samej trasie miedzynarodowej.

        Identyfikuje wspolne autostrady/korytarze transportowe.
        Korelacja CROSS_COUNTRY_ROUTE.
        """
        # Mapuj eventy do korytarzy
        corridor_events: dict[str, list[dict]] = defaultdict(list)

        for ev in events:
            country = ev.get("country_code", "").upper()
            road = _get_road(ev)
            if not country or not road:
                continue

            for corridor_name, segments in TRANSPORT_CORRIDORS.items():
                for seg_country, seg_road in segments:
                    if seg_country == country and seg_road == road:
                        corridor_events[corridor_name].append(ev)
                        break

        correlations = []

        for corridor_name, corr_events in corridor_events.items():
            # Potrzebujemy zdarzen z min. 2 roznych krajow
            countries = {ev.get("country_code") for ev in corr_events if ev.get("country_code")}
            if len(countries) < 2:
                continue
            if len(corr_events) < 2:
                continue

            correlation = {
                "type": "CROSS_COUNTRY_ROUTE",
                "corridor": corridor_name,
                "events": corr_events,
                "event_count": len(corr_events),
                "countries": list(countries),
                "roads": list({_get_road(ev) for ev in corr_events if _get_road(ev)}),
            }
            correlation["confidence"] = self.calculate_confidence(correlation)
            correlations.append(correlation)

        return correlations

    def calculate_confidence(self, correlation: dict) -> float:
        """Oblicza confidence korelacji.

        Im wiecej eventow, im blizej siebie, im krotsze okno czasowe -> wyzszy confidence.
        Skala: 0.0 - 1.0.
        """
        base = 0.3
        event_count = correlation.get("event_count", 0)
        corr_type = correlation.get("type", "")

        # Bonus za liczbe eventow (wiecej = pewniejszy wzorzec)
        if event_count >= 10:
            count_bonus = 0.35
        elif event_count >= 5:
            count_bonus = 0.25
        elif event_count >= 3:
            count_bonus = 0.15
        else:
            count_bonus = 0.05

        # Bonus per typ
        type_bonus = 0.0
        if corr_type == "SAME_LOCATION":
            type_bonus = 0.15
        elif corr_type == "SAME_COMPANY":
            type_bonus = 0.10
        elif corr_type == "FINANCIAL_OPERATIONAL":
            type_bonus = 0.20
        elif corr_type == "SAME_TIME_PATTERN":
            type_bonus = 0.10
        elif corr_type == "CROSS_COUNTRY_ROUTE":
            # Bonus za ilosc krajow
            num_countries = len(correlation.get("countries", []))
            type_bonus = 0.10 + min(0.15, num_countries * 0.05)

        confidence = base + count_bonus + type_bonus
        return min(1.0, round(confidence, 2))
