"""Budowanie sekcji raportow z podzialem na stopien wiarygodnosci.

Sekcje:
- POTWIERDZONE ZDARZENIA: trust_score >= 0.8, zrodla oficjalne, pelne zrodlo i data.
- SYGNALY RYNKOWE: trust_score 0.2-0.79, zrodla nieoficjalne, firmy zanonimizowane,
  oznaczone jako 'niezweryfikowane'.
- KONDYCJA FINANSOWA: dane z rejestrow publicznych, moga zawierac nazwy firm.
- MAPA RYZYKA: agregacja bez nazw firm, tylko regiony i statystyki.
- TRENDY: porownanie z poprzednim okresem, wzrosty/spadki per region.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class ReportSection:
    """Pojedyncza sekcja raportu."""

    title: str
    events: list[dict]
    description: str = ""
    warning: str = ""
    subsections: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Section titles per language
# ---------------------------------------------------------------------------

_TITLES = {
    "confirmed": {
        "en": "CONFIRMED INCIDENTS",
        "de": "BESTAETIGTE VORFAELLE",
        "pl": "POTWIERDZONE ZDARZENIA",
        "fr": "INCIDENTS CONFIRMES",
    },
    "signals": {
        "en": "MARKET SIGNALS",
        "de": "MARKTSIGNALE",
        "pl": "SYGNALY RYNKOWE",
        "fr": "SIGNAUX DU MARCHE",
    },
    "financial": {
        "en": "FINANCIAL HEALTH",
        "de": "FINANZIELLE LAGE",
        "pl": "KONDYCJA FINANSOWA",
        "fr": "SANTE FINANCIERE",
    },
    "risk_map": {
        "en": "RISK MAP",
        "de": "RISIKOKARTE",
        "pl": "MAPA RYZYKA",
        "fr": "CARTE DES RISQUES",
    },
    "trends": {
        "en": "TRENDS",
        "de": "TRENDS",
        "pl": "TRENDY",
        "fr": "TENDANCES",
    },
}


def _title(section_key: str, language: str = "en") -> str:
    return _TITLES.get(section_key, {}).get(language, _TITLES.get(section_key, {}).get("en", section_key.upper()))


class ReportSectionBuilder:
    """Buduje sekcje raportu z podzialem na stopien wiarygodnosci zdarzen."""

    # ------------------------------------------------------------------
    # 1. Confirmed Incidents
    # ------------------------------------------------------------------

    def build_confirmed_section(self, events: list[dict], language: str = "en") -> ReportSection:
        """Sekcja POTWIERDZONE ZDARZENIA.

        Filtruje: trust_score >= 0.8 AND is_official == True.
        Grupuje per country, per event_type.
        """
        confirmed = [
            e for e in events
            if e.get("trust_score", 0) >= 0.8
            and e.get("is_official")
        ]

        # Group by country then by event_type
        by_country: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        for ev in confirmed:
            cc = ev.get("country_code", "??")
            etype = ev.get("event_type", "other")
            by_country[cc][etype].append(self._format_event(ev, include_company=True))

        subsections = []
        for cc in sorted(by_country):
            for etype in sorted(by_country[cc]):
                subsections.append({
                    "country": cc,
                    "event_type": etype,
                    "events": by_country[cc][etype],
                })

        descriptions = {
            "en": (
                "Incidents confirmed by official sources (police, court registries, "
                "official government communications). Each incident includes a source link."
            ),
            "de": (
                "Durch offizielle Quellen bestaetigte Vorfaelle (Polizei, Handelsregister, "
                "amtliche Bekanntmachungen). Jeder Vorfall enthaelt einen Quellenlink."
            ),
            "pl": (
                "Zdarzenia potwierdzone przez oficjalne zrodla (policja, rejestry sadowe, "
                "komunikaty urzedowe). Kazde zdarzenie posiada link do zrodla."
            ),
            "fr": (
                "Incidents confirmes par des sources officielles (police, registres judiciaires, "
                "communications gouvernementales). Chaque incident contient un lien vers la source."
            ),
        }

        return ReportSection(
            title=_title("confirmed", language),
            events=confirmed,
            description=descriptions.get(language, descriptions["en"]),
            subsections=subsections,
        )

    # ------------------------------------------------------------------
    # 2. Market Signals
    # ------------------------------------------------------------------

    def build_signals_section(self, events: list[dict], language: str = "en") -> ReportSection:
        """Sekcja SYGNALY RYNKOWE.

        Filtruje: trust_score 0.2-0.79 OR is_official == False.
        Firmy ZAWSZE zanonimizowane: 'Transport company in [region]'.
        """
        signals = [
            e for e in events
            if (0.2 <= e.get("trust_score", 0) <= 0.79)
            or (not e.get("is_official") and e.get("trust_score", 0) > 0)
        ]

        # Anonymize company names
        anonymized = []
        for ev in signals:
            fmt = self._format_event(ev, include_company=False)
            # Replace company with anonymized description
            cc = ev.get("country_code", "??")
            loc = ev.get("location", {})
            region = loc.get("region", cc) if isinstance(loc, dict) else cc
            fmt["company_display"] = f"Transport company in {region}"
            anonymized.append(fmt)

        # Group by country
        by_country: dict[str, list[dict]] = defaultdict(list)
        for ev in anonymized:
            by_country[ev.get("country_code", "??")].append(ev)

        subsections = [
            {"country": cc, "events": evts}
            for cc, evts in sorted(by_country.items())
        ]

        warnings = {
            "en": (
                "UNVERIFIED \u2014 based on unofficial sources. The information below has not "
                "been independently verified. It does not constitute an accusation against any entity."
            ),
            "de": (
                "UNBESTAETIGT \u2014 basierend auf inoffiziellen Quellen. Die folgenden Informationen "
                "wurden nicht unabhaengig verifiziert. Sie stellen keine Anschuldigung dar."
            ),
            "pl": (
                "NIEZWERYFIKOWANE \u2014 na podstawie nieoficjalnych zrodel. Ponizsze informacje "
                "nie zostaly niezaleznie zweryfikowane. Nie stanowia oskarzenia wobec zadnego podmiotu."
            ),
            "fr": (
                "NON VERIFIE \u2014 base sur des sources non officielles. Les informations ci-dessous "
                "n'ont pas ete verifiees independamment. Elles ne constituent pas une accusation."
            ),
        }

        descriptions = {
            "en": "Information from unofficial sources (forums, social media). Company names anonymized.",
            "de": "Informationen aus inoffiziellen Quellen (Foren, soziale Medien). Firmennamen anonymisiert.",
            "pl": "Informacje z nieoficjalnych zrodel (fora, media spolecznosciowe). Nazwy firm zanonimizowane.",
            "fr": "Informations provenant de sources non officielles (forums, reseaux sociaux). Noms anonymises.",
        }

        return ReportSection(
            title=_title("signals", language),
            events=anonymized,
            description=descriptions.get(language, descriptions["en"]),
            warning=warnings.get(language, warnings["en"]),
            subsections=subsections,
        )

    # ------------------------------------------------------------------
    # 3. Financial Health
    # ------------------------------------------------------------------

    def build_financial_section(self, events: list[dict], language: str = "en") -> ReportSection:
        """Sekcja KONDYCJA FINANSOWA.

        Filtruje event_type in (bankruptcy, restructuring, payment_issue, license_revoked).
        Dane z oficjalnych rejestrow -> moga zawierac nazwy firm.
        Dane z forow -> zanonimizowane.
        """
        financial_types = {"bankruptcy", "restructuring", "payment_issue", "license_revoked"}
        financial = [e for e in events if e.get("event_type") in financial_types]

        # Build subsections per type
        type_labels = {
            "bankruptcy": {"en": "Bankruptcies", "de": "Insolvenzen", "pl": "Upadlosci", "fr": "Faillites"},
            "restructuring": {"en": "Restructurings", "de": "Restrukturierungen", "pl": "Restrukturyzacje", "fr": "Restructurations"},
            "payment_issue": {"en": "Payment Issues", "de": "Zahlungsprobleme", "pl": "Problemy platnicze", "fr": "Problemes de paiement"},
            "license_revoked": {"en": "License Revocations", "de": "Lizenzentzuege", "pl": "Cofniecia licencji", "fr": "Revocations de licence"},
        }

        subsections = []
        for ftype in ("bankruptcy", "restructuring", "payment_issue", "license_revoked"):
            type_events = [e for e in financial if e.get("event_type") == ftype]
            if not type_events:
                continue

            formatted = []
            for ev in type_events:
                # Official sources may name companies; unofficial must be anonymized
                include_company = bool(ev.get("is_official"))
                formatted.append(self._format_event(ev, include_company=include_company))

            label = type_labels.get(ftype, {}).get(language, ftype)
            subsections.append({
                "type": ftype,
                "label": label,
                "events": formatted,
                "count": len(formatted),
            })

        descriptions = {
            "en": (
                "Data from public commercial and insolvency registries. Company names are public "
                "by law when sourced from official records. Unofficial sources are anonymized."
            ),
            "de": (
                "Daten aus oeffentlichen Handels- und Insolvenzregistern. Firmennamen sind gesetzlich "
                "oeffentlich, wenn sie aus offiziellen Quellen stammen. Inoffizielle Quellen anonymisiert."
            ),
            "pl": (
                "Dane z publicznych rejestrow handlowych i upadlosciowych. Nazwy firm sa publiczne "
                "na mocy prawa. Dane z nieoficjalnych zrodel sa zanonimizowane."
            ),
            "fr": (
                "Donnees des registres commerciaux et d'insolvabilite publics. Les noms d'entreprises "
                "sont publics par la loi. Les sources non officielles sont anonymisees."
            ),
        }

        return ReportSection(
            title=_title("financial", language),
            events=financial,
            description=descriptions.get(language, descriptions["en"]),
            subsections=subsections,
        )

    # ------------------------------------------------------------------
    # 4. Risk Map
    # ------------------------------------------------------------------

    def build_risk_map_section(self, events: list[dict], language: str = "en") -> ReportSection:
        """Sekcja MAPA RYZYKA.

        Agregacja per region (nie per firma).
        Heatmap data: lat, lon, event_count, severity_avg.
        Top 10 hotspotow z opisem. BEZ nazw firm.
        """
        risk_data = self._aggregate_by_region(events)

        # Build heatmap data points from events with coordinates
        heatmap_points: list[dict] = []
        region_groups: dict[str, list[dict]] = defaultdict(list)
        for ev in events:
            loc = ev.get("location", {})
            if not isinstance(loc, dict):
                continue
            cc = ev.get("country_code", "??")
            region = loc.get("region", cc)
            key = f"{cc}/{region}" if region else cc
            region_groups[key].append(ev)

        severity_values = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}

        for key, group in region_groups.items():
            # Compute centroid from events with lat/lon
            lats, lons = [], []
            for ev in group:
                loc = ev.get("location", {})
                if isinstance(loc, dict):
                    lat = loc.get("latitude")
                    lon = loc.get("longitude")
                    if lat is not None and lon is not None:
                        try:
                            lats.append(float(lat))
                            lons.append(float(lon))
                        except (ValueError, TypeError):
                            pass

            severities = [severity_values.get(ev.get("severity", "LOW"), 1) for ev in group]
            avg_severity = round(sum(severities) / len(severities), 2) if severities else 0

            point = {
                "region": key,
                "event_count": len(group),
                "severity_avg": avg_severity,
            }
            if lats and lons:
                point["latitude"] = round(sum(lats) / len(lats), 4)
                point["longitude"] = round(sum(lons) / len(lons), 4)
            heatmap_points.append(point)

        # Sort by event_count desc, take top 10
        heatmap_points.sort(key=lambda p: p["event_count"], reverse=True)
        top_hotspots = heatmap_points[:10]

        # Build descriptions for hotspots
        for spot in top_hotspots:
            region_key = spot["region"]
            group = region_groups.get(region_key, [])
            types = Counter(ev.get("event_type", "other") for ev in group)
            top_type = types.most_common(1)[0][0] if types else "other"
            spot["description"] = (
                f"{spot['event_count']} incidents in {region_key} "
                f"(primary type: {top_type}, avg severity: {spot['severity_avg']})"
            )

        descriptions = {
            "en": "Aggregated risk data by region. Does not contain company names or personal data.",
            "de": "Aggregierte Risikodaten nach Region. Enthaelt keine Firmennamen oder personenbezogene Daten.",
            "pl": "Zagregowane dane ryzyka per region. Nie zawiera nazw firm ani danych osobowych.",
            "fr": "Donnees de risque agregees par region. Ne contient ni noms d'entreprises ni donnees personnelles.",
        }

        return ReportSection(
            title=_title("risk_map", language),
            events=risk_data,
            description=descriptions.get(language, descriptions["en"]),
            metadata={
                "heatmap_data": heatmap_points,
                "top_hotspots": top_hotspots,
            },
        )

    # ------------------------------------------------------------------
    # 5. Trends
    # ------------------------------------------------------------------

    def build_trends_section(
        self,
        current_events: list[dict],
        previous_events: list[dict] | None = None,
        language: str = "en",
    ) -> ReportSection:
        """Sekcja TRENDY.

        Porownanie current vs previous period.
        Zmiany procentowe per country, per event_type.
        'rising' / 'stable' / 'declining' per kategoria.
        Nowe hotspoty vs znikajace hotspoty.
        """
        current_by_country = Counter(ev.get("country_code", "??") for ev in current_events)
        current_by_type = Counter(ev.get("event_type", "other") for ev in current_events)

        if previous_events:
            prev_by_country = Counter(ev.get("country_code", "??") for ev in previous_events)
            prev_by_type = Counter(ev.get("event_type", "other") for ev in previous_events)
        else:
            prev_by_country = Counter()
            prev_by_type = Counter()

        def _trend_label(current_val: int, prev_val: int) -> str:
            if prev_val == 0:
                return "new" if current_val > 0 else "stable"
            pct = ((current_val - prev_val) / prev_val) * 100
            if pct > 15:
                return "rising"
            elif pct < -15:
                return "declining"
            return "stable"

        def _pct_change(current_val: int, prev_val: int) -> float:
            if prev_val == 0:
                return 100.0 if current_val > 0 else 0.0
            return round(((current_val - prev_val) / prev_val) * 100, 1)

        # Country trends
        all_countries = set(current_by_country) | set(prev_by_country)
        country_trends = []
        for cc in sorted(all_countries):
            cur = current_by_country.get(cc, 0)
            prev = prev_by_country.get(cc, 0)
            country_trends.append({
                "country": cc,
                "current": cur,
                "previous": prev,
                "change_pct": _pct_change(cur, prev),
                "trend": _trend_label(cur, prev),
            })

        # Type trends
        all_types = set(current_by_type) | set(prev_by_type)
        type_trends = []
        for etype in sorted(all_types):
            cur = current_by_type.get(etype, 0)
            prev = prev_by_type.get(etype, 0)
            type_trends.append({
                "event_type": etype,
                "current": cur,
                "previous": prev,
                "change_pct": _pct_change(cur, prev),
                "trend": _trend_label(cur, prev),
            })

        # Hotspot comparison
        current_hotspots = set(cc for cc, cnt in current_by_country.items() if cnt >= 3)
        prev_hotspots = set(cc for cc, cnt in prev_by_country.items() if cnt >= 3)
        new_hotspots = list(current_hotspots - prev_hotspots)
        fading_hotspots = list(prev_hotspots - current_hotspots)

        trend_arrow = {"rising": "\u2191", "declining": "\u2193", "stable": "\u2192", "new": "\u2605"}

        subsections = [
            {
                "label": "Country Trends",
                "items": country_trends,
            },
            {
                "label": "Event Type Trends",
                "items": type_trends,
            },
        ]

        descriptions = {
            "en": "Comparison with previous reporting period. Changes in incident frequency by country and type.",
            "de": "Vergleich mit dem vorherigen Berichtszeitraum. Veraenderungen der Vorfallhaeufigkeit.",
            "pl": "Porownanie z poprzednim okresem raportowania. Zmiany czestotliwosci zdarzen.",
            "fr": "Comparaison avec la periode de rapport precedente. Evolution de la frequence des incidents.",
        }

        return ReportSection(
            title=_title("trends", language),
            events=[],
            description=descriptions.get(language, descriptions["en"]),
            subsections=subsections,
            metadata={
                "country_trends": country_trends,
                "type_trends": type_trends,
                "new_hotspots": new_hotspots,
                "fading_hotspots": fading_hotspots,
                "trend_arrows": trend_arrow,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_event(self, event: dict, include_company: bool = True) -> dict:
        """Formatuje event do wyswietlenia w raporcie."""
        loc = event.get("location", {})
        if isinstance(loc, dict):
            location_str = ", ".join(
                filter(None, [loc.get("city"), loc.get("region"), loc.get("country")])
            )
        else:
            location_str = str(loc) if loc else ""

        formatted = {
            "date": event.get("date") or event.get("date_parsed", ""),
            "country_code": event.get("country_code", "??"),
            "region": loc.get("region", "") if isinstance(loc, dict) else "",
            "location": location_str,
            "event_type": event.get("event_type", "other"),
            "severity": event.get("severity", "MEDIUM"),
            "description": event.get("processed_text") or event.get("description") or event.get("title", ""),
            "source_name": event.get("source_name", ""),
            "source_url": event.get("source_url", ""),
            "trust_score": event.get("trust_score", 0),
            "is_official": event.get("is_official", False),
        }

        if include_company:
            formatted["company"] = event.get("company_name") or event.get("company", "")
        else:
            formatted["company"] = ""
            formatted["company_display"] = ""

        return formatted

    def _aggregate_by_region(self, events: list[dict]) -> list[dict]:
        """Agreguje zdarzenia per region (bez nazw firm)."""
        regions: dict[str, dict] = {}
        for event in events:
            region = event.get("country_code", "unknown")
            if region not in regions:
                regions[region] = {"region": region, "count": 0, "types": {}, "severities": {}}
            regions[region]["count"] += 1
            etype = event.get("event_type", "other")
            regions[region]["types"][etype] = regions[region]["types"].get(etype, 0) + 1
            sev = event.get("severity", "MEDIUM")
            regions[region]["severities"][sev] = regions[region]["severities"].get(sev, 0) + 1

        result = sorted(regions.values(), key=lambda r: r["count"], reverse=True)
        return result
