"""Generowanie mapy kradziezi i incydentow transportowych.

Tworzy hotspoty, heatmapy, analizy korytarzy transportowych i eksport GeoJSON
do wyswietlenia na mapie interaktywnej (Leaflet, Mapbox).
"""

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.analysis.geo_extractor import GeoExtractor, _haversine
from src.analysis.risk_scorer import RiskScorer

# ---------------------------------------------------------------------------
# Hotspot dataclass
# ---------------------------------------------------------------------------


@dataclass
class Hotspot:
    center_lat: float = 0.0
    center_lon: float = 0.0
    radius_km: float = 30.0
    event_count: int = 0
    severity_avg: float = 0.0
    dominant_type: str = "other"
    country_code: str = ""
    region: str = ""
    peak_hours: str | None = None
    common_targets: list[str] = field(default_factory=list)
    trend: str = "STABLE"
    first_event: datetime | None = None
    last_event: datetime | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_VALUES = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}


def _parse_dt(val) -> datetime | None:
    if isinstance(val, datetime):
        return val
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00").replace("+00:00", ""))
    except (ValueError, TypeError):
        return None


def _get_coords(ev: dict) -> tuple[float, float] | None:
    loc = ev.get("location", {})
    if isinstance(loc, dict):
        lat = loc.get("latitude")
        lon = loc.get("longitude")
        if lat is not None and lon is not None:
            try:
                return float(lat), float(lon)
            except (ValueError, TypeError):
                pass
    return None


# Country name lookup (subset)
_COUNTRY_NAMES = {
    "PL": "Poland", "DE": "Germany", "FR": "France", "CZ": "Czech Republic",
    "SK": "Slovakia", "HU": "Hungary", "RO": "Romania", "BG": "Bulgaria",
    "HR": "Croatia", "SI": "Slovenia", "AT": "Austria", "NL": "Netherlands",
    "BE": "Belgium", "IT": "Italy", "ES": "Spain", "PT": "Portugal",
    "SE": "Sweden", "NO": "Norway", "DK": "Denmark", "FI": "Finland",
    "GB": "United Kingdom", "IE": "Ireland", "CH": "Switzerland",
    "GR": "Greece", "TR": "Turkey", "RS": "Serbia", "BA": "Bosnia",
    "LT": "Lithuania", "LV": "Latvia", "EE": "Estonia", "UA": "Ukraine",
}


# ---------------------------------------------------------------------------
# CrimeMap
# ---------------------------------------------------------------------------


class CrimeMap:
    """Generator map kradziezi i incydentow."""

    def __init__(self):
        self.geo_extractor = GeoExtractor()
        self.risk_scorer = RiskScorer()

    # ------------------------------------------------------------------
    # Hotspot generation (DBSCAN-like)
    # ------------------------------------------------------------------

    def generate_hotspots(
        self,
        events: list[dict],
        min_events: int = 3,
        radius_km: float = 30.0,
        time_window_days: int = 30,
    ) -> list[Hotspot]:
        """Grupuje eventy w promieniu radius_km (DBSCAN-like clustering).

        Minimum min_events w oknie czasowym -> hotspot.
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(days=time_window_days)

        # Filter events with coords and within time window
        geo_events: list[tuple[dict, float, float, datetime]] = []
        for ev in events:
            coords = _get_coords(ev)
            dt = _parse_dt(ev.get("date") or ev.get("date_parsed"))
            if coords and dt and dt >= cutoff:
                geo_events.append((ev, coords[0], coords[1], dt))

        if len(geo_events) < min_events:
            return []

        used: set[int] = set()
        hotspots: list[Hotspot] = []

        for i, (ev_i, lat_i, lon_i, dt_i) in enumerate(geo_events):
            if i in used:
                continue

            cluster = [i]
            for j, (ev_j, lat_j, lon_j, dt_j) in enumerate(geo_events):
                if j <= i or j in used:
                    continue
                if _haversine(lat_i, lon_i, lat_j, lon_j) <= radius_km:
                    cluster.append(j)

            if len(cluster) < min_events:
                continue

            for idx in cluster:
                used.add(idx)

            # Centroid
            lats = [geo_events[idx][1] for idx in cluster]
            lons = [geo_events[idx][2] for idx in cluster]
            center_lat = sum(lats) / len(lats)
            center_lon = sum(lons) / len(lons)

            cluster_events = [geo_events[idx][0] for idx in cluster]
            cluster_dts = [geo_events[idx][3] for idx in cluster]

            # Stats
            sev_values = [_SEVERITY_VALUES.get(ev.get("severity", "LOW"), 1) for ev in cluster_events]
            sev_avg = round(sum(sev_values) / len(sev_values), 2)

            type_counts = Counter(ev.get("event_type", "other") for ev in cluster_events)
            dominant_type = type_counts.most_common(1)[0][0]

            countries = Counter(ev.get("country_code", "??") for ev in cluster_events)
            country_code = countries.most_common(1)[0][0]

            # Region
            region = ""
            for ev in cluster_events:
                loc = ev.get("location", {})
                if isinstance(loc, dict) and loc.get("region"):
                    region = loc["region"]
                    break

            # Peak hours
            hours = [dt.hour for dt in cluster_dts]
            hour_counts = Counter(hours)
            peak_hour = hour_counts.most_common(1)[0][0] if hour_counts else 12
            if peak_hour >= 22 or peak_hour < 5:
                peak_hours = "22:00-05:00 (night)"
            elif peak_hour < 10:
                peak_hours = "06:00-10:00 (morning)"
            elif peak_hour < 16:
                peak_hours = "10:00-16:00 (daytime)"
            else:
                peak_hours = "16:00-22:00 (evening)"

            # Common targets (cargo types)
            targets: list[str] = []
            for ev in cluster_events:
                for tag in ev.get("tags", []):
                    targets.append(tag)
            common_targets = [t for t, _ in Counter(targets).most_common(3)]

            hotspot = Hotspot(
                center_lat=round(center_lat, 4),
                center_lon=round(center_lon, 4),
                radius_km=radius_km,
                event_count=len(cluster),
                severity_avg=sev_avg,
                dominant_type=dominant_type,
                country_code=country_code,
                region=region,
                peak_hours=peak_hours,
                common_targets=common_targets,
                trend="STABLE",  # calculated later in detect_emerging
                first_event=min(cluster_dts),
                last_event=max(cluster_dts),
            )
            hotspots.append(hotspot)

        # Sort by event count desc
        hotspots.sort(key=lambda h: h.event_count, reverse=True)
        return hotspots

    # ------------------------------------------------------------------
    # Heatmap data
    # ------------------------------------------------------------------

    def generate_heatmap_data(
        self,
        events: list[dict],
        resolution: float = 0.5,
    ) -> list[dict]:
        """Grid Europy (lat 35-72, lon -12-45). Intensity per cell."""
        grid: dict[tuple[float, float], dict] = {}

        for ev in events:
            coords = _get_coords(ev)
            if not coords:
                continue
            lat, lon = coords

            # Snap to grid
            grid_lat = round(math.floor(lat / resolution) * resolution + resolution / 2, 2)
            grid_lon = round(math.floor(lon / resolution) * resolution + resolution / 2, 2)

            key = (grid_lat, grid_lon)
            if key not in grid:
                grid[key] = {"lat": grid_lat, "lon": grid_lon, "event_count": 0, "severity_sum": 0}
            grid[key]["event_count"] += 1
            grid[key]["severity_sum"] += _SEVERITY_VALUES.get(ev.get("severity", "LOW"), 1)

        # Calculate intensity
        result: list[dict] = []
        max_count = max((c["event_count"] for c in grid.values()), default=1)
        for cell in grid.values():
            intensity = round(cell["event_count"] / max(max_count, 1), 3)
            result.append({
                "lat": cell["lat"],
                "lon": cell["lon"],
                "intensity": intensity,
                "event_count": cell["event_count"],
            })

        result.sort(key=lambda x: x["intensity"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # Corridor risk
    # ------------------------------------------------------------------

    def generate_corridor_risk(self, events: list[dict]) -> list[dict]:
        """Ryzyko per korytarz transportowy."""
        corridor_events: dict[str, list[dict]] = defaultdict(list)

        for ev in events:
            cc = ev.get("country_code", "").upper()
            loc = ev.get("location", {})
            road = loc.get("road", "") if isinstance(loc, dict) else ""

            for corridor_name, info in self.geo_extractor.transport_corridors.items():
                if cc in info["countries"]:
                    if road and road in info.get("highways", []):
                        corridor_events[corridor_name].append(ev)
                    elif not road:
                        # Country match without highway — weaker signal
                        corridor_events[corridor_name].append(ev)

        results: list[dict] = []
        for name, evts in corridor_events.items():
            if not evts:
                continue
            info = self.geo_extractor.transport_corridors[name]
            type_counts = Counter(ev.get("event_type", "other") for ev in evts)
            sev_values = [_SEVERITY_VALUES.get(ev.get("severity", "LOW"), 1) for ev in evts]
            risk_score = min(100.0, round(sum(sev_values) * 3.0, 1))

            # Top incidents
            top_incidents = sorted(evts, key=lambda e: _SEVERITY_VALUES.get(e.get("severity", "LOW"), 0), reverse=True)[:3]
            top_desc = [
                {"type": e.get("event_type"), "severity": e.get("severity"), "country": e.get("country_code")}
                for e in top_incidents
            ]

            results.append({
                "corridor_name": name,
                "countries": info["countries"],
                "event_count": len(evts),
                "risk_score": risk_score,
                "dominant_type": type_counts.most_common(1)[0][0] if type_counts else "other",
                "trend": "STABLE",
                "top_incidents": top_desc,
            })

        results.sort(key=lambda r: r["risk_score"], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Country summary
    # ------------------------------------------------------------------

    def generate_country_summary(self, events: list[dict]) -> list[dict]:
        """Per country summary: event_count, top_type, risk_score, trend, hotspots."""
        country_events: dict[str, list[dict]] = defaultdict(list)
        for ev in events:
            cc = ev.get("country_code", "??").upper()
            country_events[cc].append(ev)

        hotspots = self.generate_hotspots(events, min_events=2, radius_km=50, time_window_days=90)
        hotspot_by_country: dict[str, int] = Counter(h.country_code for h in hotspots)

        results: list[dict] = []
        for cc, evts in country_events.items():
            type_counts = Counter(ev.get("event_type", "other") for ev in evts)
            sev_values = [_SEVERITY_VALUES.get(ev.get("severity", "LOW"), 1) for ev in evts]
            risk_score = min(100.0, round(sum(sev_values) * 2.5, 1))

            results.append({
                "country_code": cc,
                "country_name": _COUNTRY_NAMES.get(cc, cc),
                "event_count": len(evts),
                "top_type": type_counts.most_common(1)[0][0] if type_counts else "other",
                "risk_score": risk_score,
                "trend": "STABLE",
                "hotspot_count": hotspot_by_country.get(cc, 0),
            })

        results.sort(key=lambda r: r["risk_score"], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Emerging hotspot detection
    # ------------------------------------------------------------------

    def detect_emerging_hotspots(
        self,
        current_events: list[dict],
        previous_events: list[dict],
    ) -> list[dict]:
        """Porownuje hotspoty current vs previous. EMERGING/GROWING/FADING/RESOLVED."""
        current_hs = self.generate_hotspots(current_events, min_events=2, radius_km=30, time_window_days=90)
        previous_hs = self.generate_hotspots(previous_events, min_events=2, radius_km=30, time_window_days=90)

        results: list[dict] = []

        # Match hotspots by proximity
        matched_prev: set[int] = set()

        for hs in current_hs:
            best_match = None
            best_dist = float("inf")

            for pidx, phs in enumerate(previous_hs):
                if pidx in matched_prev:
                    continue
                dist = _haversine(hs.center_lat, hs.center_lon, phs.center_lat, phs.center_lon)
                if dist < 50 and dist < best_dist:
                    best_match = pidx
                    best_dist = dist

            if best_match is not None:
                matched_prev.add(best_match)
                phs = previous_hs[best_match]
                if hs.event_count > phs.event_count * 1.3:
                    status = "GROWING"
                elif hs.event_count < phs.event_count * 0.7:
                    status = "FADING"
                else:
                    status = "STABLE"
            else:
                status = "EMERGING"

            results.append({
                "status": status,
                "center_lat": hs.center_lat,
                "center_lon": hs.center_lon,
                "event_count": hs.event_count,
                "country_code": hs.country_code,
                "region": hs.region,
                "dominant_type": hs.dominant_type,
            })

        # Previous hotspots not matched -> RESOLVED
        for pidx, phs in enumerate(previous_hs):
            if pidx not in matched_prev:
                results.append({
                    "status": "RESOLVED",
                    "center_lat": phs.center_lat,
                    "center_lon": phs.center_lon,
                    "event_count": 0,
                    "prev_event_count": phs.event_count,
                    "country_code": phs.country_code,
                    "region": phs.region,
                    "dominant_type": phs.dominant_type,
                })

        return results

    # ------------------------------------------------------------------
    # GeoJSON export
    # ------------------------------------------------------------------

    def export_geojson(self, hotspots: list[Hotspot]) -> dict:
        """Eksportuje hotspoty do formatu GeoJSON (FeatureCollection)."""
        features: list[dict] = []

        for hs in hotspots:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [hs.center_lon, hs.center_lat],  # GeoJSON: [lon, lat]
                },
                "properties": {
                    "event_count": hs.event_count,
                    "severity_avg": hs.severity_avg,
                    "dominant_type": hs.dominant_type,
                    "country_code": hs.country_code,
                    "region": hs.region,
                    "radius_km": hs.radius_km,
                    "peak_hours": hs.peak_hours,
                    "common_targets": hs.common_targets,
                    "trend": hs.trend,
                    "first_event": hs.first_event.isoformat() if hs.first_event else None,
                    "last_event": hs.last_event.isoformat() if hs.last_event else None,
                },
            }
            features.append(feature)

        return {
            "type": "FeatureCollection",
            "features": features,
        }
