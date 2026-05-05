"""Scoring ryzyka dla firm, tras, regionow i typow ladunku.

Oblicza wskaznik ryzyka na podstawie historycznych zdarzen,
czestotliwosci incydentow, ich wagi i time decay.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CompanyRisk:
    overall_score: float = 0.0
    financial_score: float = 0.0
    operational_score: float = 0.0
    trend: str = "STABLE"  # RISING / STABLE / DECLINING
    risk_level: str = "MINIMAL"  # CRITICAL / HIGH / MEDIUM / LOW / MINIMAL
    factors: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class RouteRisk:
    overall_score: float = 0.0
    segments: list[dict] = field(default_factory=list)
    hotspots_on_route: list[dict] = field(default_factory=list)
    high_risk_hours: list[str] = field(default_factory=list)
    high_risk_areas: list[str] = field(default_factory=list)
    recommended_stops: list[str] = field(default_factory=list)
    risk_level: str = "MINIMAL"
    recommendations: list[str] = field(default_factory=list)


@dataclass
class RegionRisk:
    overall_score: float = 0.0
    event_count: int = 0
    dominant_type: str = "other"
    trend: str = "STABLE"
    peak_hours: str | None = None
    risk_level: str = "MINIMAL"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EVENT_WEIGHTS: dict[str, float] = {
    "theft_cargo": 15.0,
    "theft_fuel": 8.0,
    "theft_vehicle": 12.0,
    "damage": 5.0,
    "delay": 3.0,
    "strike": 6.0,
    "payment_issue": 20.0,
    "bankruptcy": 40.0,
    "restructuring": 25.0,
    "license_revoked": 50.0,
    "route_closure": 4.0,
    "other": 2.0,
}

_FINANCIAL_TYPES = {"bankruptcy", "restructuring", "payment_issue", "license_revoked"}
_OPERATIONAL_TYPES = {"theft_cargo", "theft_fuel", "theft_vehicle", "damage", "delay", "strike", "route_closure"}

_CARGO_BASE_RISK: dict[str, float] = {
    "electronics": 0.80,
    "fuel": 0.70,
    "pharmaceuticals": 0.75,
    "alcohol": 0.70,
    "tobacco": 0.70,
    "food": 0.30,
    "building_materials": 0.20,
    "textiles": 0.40,
    "metals": 0.45,
    "chemicals": 0.50,
    "automotive_parts": 0.55,
    "machinery": 0.35,
}


def _risk_level(score: float) -> str:
    if score >= 80:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    if score >= 20:
        return "LOW"
    return "MINIMAL"


def _parse_dt(val) -> datetime | None:
    if isinstance(val, datetime):
        return val
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00").replace("+00:00", ""))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# RiskScorer
# ---------------------------------------------------------------------------


class RiskScorer:
    """Kalkulator ryzyka dla firm, tras i regionow transportowych."""

    def __init__(self):
        self.weights = dict(_EVENT_WEIGHTS)
        self.decay_factor = 0.5  # events >90d get 50% weight
        self.thresholds = {"CRITICAL": 80, "HIGH": 60, "MEDIUM": 40, "LOW": 20}

    # ------------------------------------------------------------------
    # Time decay helper
    # ------------------------------------------------------------------

    def _time_decay(self, event_date, now: datetime | None = None) -> float:
        """Starsze zdarzenia maja mniejsza wage. Returns multiplier 0.25..1.0."""
        now = now or datetime.utcnow()
        dt = _parse_dt(event_date)
        if not dt:
            return 0.5  # unknown date -> half weight

        days = (now - dt).days
        if days < 0:
            return 1.0
        if days <= 30:
            return 1.0
        if days <= 90:
            return 0.75
        if days <= 180:
            return self.decay_factor  # 0.5
        return 0.25

    # ------------------------------------------------------------------
    # Company risk
    # ------------------------------------------------------------------

    def calculate_company_risk(
        self,
        company_events: list[dict],
        financial_data: list[dict] | None = None,
    ) -> CompanyRisk:
        """Oblicza ryzyko firmy na podstawie zdarzen i danych finansowych."""
        result = CompanyRisk()
        if not company_events:
            return result

        now = datetime.utcnow()
        financial_raw = 0.0
        operational_raw = 0.0
        factors: list[str] = []

        for ev in company_events:
            etype = ev.get("event_type", "other")
            weight = self.weights.get(etype, 2.0)
            decay = self._time_decay(ev.get("date") or ev.get("date_parsed"), now)
            score = weight * decay

            if etype in _FINANCIAL_TYPES:
                financial_raw += score
            elif etype in _OPERATIONAL_TYPES:
                operational_raw += score

        # Frequency bonus: 3+ events in 30 days -> 1.5x multiplier
        recent_count = sum(
            1 for ev in company_events
            if self._time_decay(ev.get("date") or ev.get("date_parsed"), now) == 1.0
        )
        frequency_multiplier = 1.0
        if recent_count >= 5:
            frequency_multiplier = 2.0
            factors.append(f"{recent_count} events in last 30 days (high frequency)")
        elif recent_count >= 3:
            frequency_multiplier = 1.5
            factors.append(f"{recent_count} events in last 30 days (elevated frequency)")

        financial_raw *= frequency_multiplier
        operational_raw *= frequency_multiplier

        result.financial_score = min(100.0, round(financial_raw, 1))
        result.operational_score = min(100.0, round(operational_raw, 1))
        result.overall_score = min(100.0, round(financial_raw + operational_raw, 1))

        # Factor descriptions
        type_counts = Counter(ev.get("event_type", "other") for ev in company_events)
        for etype, count in type_counts.most_common(5):
            if count >= 1:
                factors.append(f"{count}x {etype} (weight: {self.weights.get(etype, 2.0)})")

        # Financial data bonus
        if financial_data:
            for fd in financial_data:
                if fd.get("metric") == "payment_delays" and fd.get("value", 0) > 60:
                    result.financial_score = min(100.0, result.financial_score + 15)
                    result.overall_score = min(100.0, result.overall_score + 15)
                    factors.append(f"Payment delays: {fd['value']} days")

        result.factors = factors
        result.risk_level = _risk_level(result.overall_score)

        # Trend: compare last 30d vs 30-60d
        recent_30d = sum(1 for ev in company_events if self._time_decay(ev.get("date"), now) == 1.0)
        older_30_60 = sum(
            1 for ev in company_events
            if 0.5 < self._time_decay(ev.get("date"), now) < 1.0
        )
        if recent_30d > older_30_60 * 1.5:
            result.trend = "RISING"
        elif recent_30d < older_30_60 * 0.5:
            result.trend = "DECLINING"
        else:
            result.trend = "STABLE"

        # Recommendations (neutral language)
        result.recommendations = self._company_recommendations(result, type_counts)
        return result

    def _company_recommendations(self, risk: CompanyRisk, type_counts: Counter) -> list[str]:
        recs: list[str] = []
        if risk.risk_level in ("CRITICAL", "HIGH"):
            recs.append("Exercise enhanced due diligence in business dealings with this company.")
        if risk.financial_score >= 40:
            recs.append("Review outstanding contracts and receivables. Consider credit insurance.")
        if type_counts.get("bankruptcy", 0) > 0:
            recs.append("Verify current legal status and ability to operate.")
        if type_counts.get("license_revoked", 0) > 0:
            recs.append("Confirm license status before any new business engagement.")
        if risk.operational_score >= 40:
            recs.append("Monitor operational performance and incident reports closely.")
        if risk.trend == "RISING":
            recs.append("Risk trend is rising. Consider contingency planning for alternative partners.")
        if not recs:
            recs.append("No specific concerns identified. Continue standard monitoring.")
        return recs

    # ------------------------------------------------------------------
    # Route risk
    # ------------------------------------------------------------------

    def calculate_route_risk(
        self,
        origin: dict,
        destination: dict,
        events_on_route: list[dict],
        hotspots: list[dict] | None = None,
    ) -> RouteRisk:
        """Oblicza ryzyko trasy na podstawie zdarzen, hotspotow i warunkow."""
        result = RouteRisk()
        now = datetime.utcnow()

        if not events_on_route:
            result.risk_level = "MINIMAL"
            result.recommendations.append("No recent incidents on this route. Standard precautions apply.")
            return result

        # Score based on events
        total_score = 0.0
        areas_seen: set[str] = set()
        night_count = 0

        for ev in events_on_route:
            etype = ev.get("event_type", "other")
            weight = self.weights.get(etype, 2.0)
            decay = self._time_decay(ev.get("date"), now)
            total_score += weight * decay

            # Track high-risk areas
            loc = ev.get("location", {})
            if isinstance(loc, dict):
                area = loc.get("city") or loc.get("region") or ""
                road = loc.get("road", "")
                if area:
                    label = f"{area} ({road})" if road else area
                    areas_seen.add(label)

            # Night events
            dt = _parse_dt(ev.get("date"))
            if dt and (dt.hour >= 22 or dt.hour < 5):
                night_count += 1

        # Hotspot bonus
        if hotspots:
            result.hotspots_on_route = hotspots[:5]
            total_score += len(hotspots) * 5

        # Night risk
        if night_count > 0:
            result.high_risk_hours = ["22:00-05:00"]
            total_score += night_count * 3

        result.overall_score = min(100.0, round(total_score, 1))
        result.risk_level = _risk_level(result.overall_score)
        result.high_risk_areas = list(areas_seen)[:5]

        # Segments (simplified: origin, midpoints from events, destination)
        result.segments = [
            {"name": f"Start: {origin.get('city', origin.get('name', 'Origin'))}", "risk": 0},
        ]
        if areas_seen:
            for area in list(areas_seen)[:3]:
                result.segments.append({"name": area, "risk": round(total_score / len(areas_seen), 1)})
        result.segments.append(
            {"name": f"End: {destination.get('city', destination.get('name', 'Destination'))}", "risk": 0},
        )

        # Recommended stops (safe parking areas far from hotspots — simplified)
        result.recommended_stops = ["Autohof Lehrte (A2)", "MOP Kamionki (A1)", "Truck Stop Gyor (M1)"]

        # Recommendations
        recs: list[str] = []
        if result.risk_level in ("CRITICAL", "HIGH"):
            recs.append("Consider alternative route or enhanced security measures for this corridor.")
        if night_count > 0:
            recs.append(f"Night incidents detected ({night_count}). Avoid overnight stops in high-risk areas.")
        if result.hotspots_on_route:
            recs.append(f"{len(result.hotspots_on_route)} hotspot(s) on route. Plan stops at secure parking facilities.")
        if not recs:
            recs.append("Standard precautions recommended. Monitor for updates.")
        result.recommendations = recs

        return result

    # ------------------------------------------------------------------
    # Region risk
    # ------------------------------------------------------------------

    def calculate_region_risk(
        self,
        country_code: str,
        region: str,
        events: list[dict],
    ) -> RegionRisk:
        """Oblicza ryzyko regionu na podstawie zdarzen."""
        result = RegionRisk()
        now = datetime.utcnow()

        # Filter events for this region
        region_events = []
        for ev in events:
            cc = ev.get("country_code", "")
            if cc.upper() != country_code.upper():
                continue
            loc = ev.get("location", {})
            ev_region = loc.get("region", "") if isinstance(loc, dict) else ""
            if region.lower() in ev_region.lower() or ev_region.lower() in region.lower():
                region_events.append(ev)

        result.event_count = len(region_events)
        if not region_events:
            return result

        # Scoring: weighted sum with time decay
        total_score = 0.0
        for ev in region_events:
            etype = ev.get("event_type", "other")
            weight = self.weights.get(etype, 2.0)
            decay = self._time_decay(ev.get("date"), now)
            total_score += weight * decay

        # Density normalization (simplified — cap at 100)
        result.overall_score = min(100.0, round(total_score, 1))
        result.risk_level = _risk_level(result.overall_score)

        # Dominant type
        type_counts = Counter(ev.get("event_type", "other") for ev in region_events)
        result.dominant_type = type_counts.most_common(1)[0][0] if type_counts else "other"

        # Peak hours
        hours = []
        for ev in region_events:
            dt = _parse_dt(ev.get("date"))
            if dt:
                hours.append(dt.hour)
        if hours:
            hour_counts = Counter(hours)
            peak_hour = hour_counts.most_common(1)[0][0]
            if peak_hour >= 22 or peak_hour < 5:
                result.peak_hours = "22:00-05:00 (night)"
            elif peak_hour < 10:
                result.peak_hours = "06:00-10:00 (morning)"
            elif peak_hour < 16:
                result.peak_hours = "10:00-16:00 (daytime)"
            else:
                result.peak_hours = "16:00-22:00 (evening)"

        # Trend
        recent = sum(1 for ev in region_events if self._time_decay(ev.get("date"), now) >= 0.75)
        older = sum(1 for ev in region_events if self._time_decay(ev.get("date"), now) < 0.75)
        if recent > older * 1.5:
            result.trend = "RISING"
        elif recent < older * 0.5 and older > 0:
            result.trend = "DECLINING"
        else:
            result.trend = "STABLE"

        return result

    # ------------------------------------------------------------------
    # Cargo risk
    # ------------------------------------------------------------------

    def calculate_cargo_risk(
        self,
        cargo_type: str,
        route_risk: RouteRisk | None = None,
    ) -> float:
        """Oblicza ryzyko per typ ladunku (0-1). Modyfikatory: route risk."""
        base = _CARGO_BASE_RISK.get(cargo_type.lower(), 0.3)

        if route_risk:
            route_modifier = route_risk.overall_score / 200.0  # max +0.5
            base = min(1.0, base + route_modifier)

            # Night bonus for high-value cargo
            if route_risk.high_risk_hours and cargo_type.lower() in ("electronics", "pharmaceuticals"):
                base = min(1.0, base + 0.1)

        return round(base, 2)

    # ------------------------------------------------------------------
    # Risk report
    # ------------------------------------------------------------------

    def generate_risk_report(
        self,
        company_risk: CompanyRisk | None = None,
        route_risk: RouteRisk | None = None,
        region_risk: RegionRisk | None = None,
    ) -> dict:
        """Laczy wszystkie ryzyka i generuje podsumowanie tekstowe. Neutralny jezyk."""
        sections: list[str] = []
        overall_level = "MINIMAL"
        all_recs: list[str] = []

        levels = []

        if company_risk:
            sections.append(
                f"Company Risk: {company_risk.risk_level} (score: {company_risk.overall_score}/100). "
                f"Financial: {company_risk.financial_score}/100, Operational: {company_risk.operational_score}/100. "
                f"Trend: {company_risk.trend}."
            )
            all_recs.extend(company_risk.recommendations)
            levels.append(company_risk.overall_score)

        if route_risk:
            sections.append(
                f"Route Risk: {route_risk.risk_level} (score: {route_risk.overall_score}/100). "
                f"{len(route_risk.high_risk_areas)} high-risk area(s) identified."
            )
            all_recs.extend(route_risk.recommendations)
            levels.append(route_risk.overall_score)

        if region_risk:
            sections.append(
                f"Region Risk: {region_risk.risk_level} (score: {region_risk.overall_score}/100). "
                f"{region_risk.event_count} events, dominant type: {region_risk.dominant_type}. "
                f"Trend: {region_risk.trend}."
            )
            levels.append(region_risk.overall_score)

        # Overall
        max_score = max(levels) if levels else 0
        overall_level = _risk_level(max_score)

        summary = " | ".join(sections) if sections else "No risk data available."

        # Deduplicate recommendations
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in all_recs:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        return {
            "overall_risk_level": overall_level,
            "overall_score": max_score,
            "summary": summary,
            "recommendations": unique_recs,
            "company_risk": {
                "score": company_risk.overall_score if company_risk else None,
                "level": company_risk.risk_level if company_risk else None,
                "trend": company_risk.trend if company_risk else None,
            } if company_risk else None,
            "route_risk": {
                "score": route_risk.overall_score if route_risk else None,
                "level": route_risk.risk_level if route_risk else None,
            } if route_risk else None,
            "region_risk": {
                "score": region_risk.overall_score if region_risk else None,
                "level": region_risk.risk_level if region_risk else None,
                "trend": region_risk.trend if region_risk else None,
            } if region_risk else None,
        }
