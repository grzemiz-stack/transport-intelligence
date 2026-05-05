"""IntelligenceFilter — klasyfikacja zdarzen do 4 tier-ow waznosci.

Multilingual keyword matching (PL, DE, EN, FR, NL, CZ, RO, ES, IT, HU, UA)
na podstawie tytulu, opisu i event_type.

TIER 1 CRITICAL: cargo theft, fuel theft, curtain slashing, robbery/hijack,
                  organized crime, smuggling, arson, vehicle hijacking
TIER 2 HIGH:     insolvency, fraud/scam, dangerous parking, non-payment,
                  vandalism, theft from vehicle
TIER 3 MEDIUM:   fatal truck accidents, police checkpoints, protests/road blocks,
                  extreme weather
TIER 4 LOW:      minor accidents, general transport news, no-event articles, duplicates
"""

import re
from dataclasses import dataclass


@dataclass
class TierResult:
    tier: int  # 1-4
    category: str  # e.g. "cargo_theft", "fraud", "accident"
    confidence: float  # 0.0 - 1.0
    matched_keywords: list[str]


# ─── Keyword dictionaries per tier ────────────────────────────────────

TIER_1_KEYWORDS: dict[str, list[str]] = {
    "cargo_theft": [
        # EN
        "cargo theft", "cargo stolen", "load theft", "load stolen",
        "freight theft", "trailer theft", "container theft",
        "stolen goods", "stolen cargo", "stolen trailer",
        # PL
        "kradzież ładunku", "kradzież towaru", "kradzież naczepy",
        "kradzież kontenera", "skradziono ładunek", "skradziono towar",
        "okradziono ciężarówkę", "okradzione", "kradzież transportu",
        # DE
        "ladungsdiebstahl", "frachtdiebstahl", "ladung gestohlen",
        "lkw-diebstahl", "containerdiebstahl", "trailer gestohlen",
        "diebesgut", "gestohlene ladung", "gestohlene ware",
        # FR
        "vol de cargaison", "vol de marchandises", "vol de fret",
        "cargaison volée", "vol de remorque",
        # NL
        "ladingdiefstal", "vracht gestolen", "lading gestolen",
        # CZ
        "krádež nákladu", "ukradený náklad",
        # RO
        "furt de marfă", "marfă furată",
        # ES
        "robo de carga", "carga robada",
        # IT
        "furto di carico", "carico rubato", "furto merci",
        # HU
        "rakománylopás", "ellopott rakomány",
    ],
    "fuel_theft": [
        "fuel theft", "diesel theft", "fuel stolen", "diesel stolen",
        "siphoned fuel", "fuel siphoning",
        "kradzież paliwa", "kradzież diesla", "skradziono paliwo",
        "wyssano paliwo", "spuszczono paliwo",
        "kraftstoffdiebstahl", "dieseldiebstahl", "diesel gestohlen",
        "tankdiebstahl",
        "vol de carburant", "vol de diesel",
        "brandstof gestolen", "dieseldiefstal",
        "krádež paliva", "krádež nafty",
        "furt de combustibil",
        "robo de combustible",
        "furto di carburante",
    ],
    "curtain_slashing": [
        "curtain slashing", "tarpaulin cut", "curtain cut",
        "curtainside slashed", "slashed tarpaulin",
        "przecięta plandeka", "rozcieta plandeka", "pocięta plandeka",
        "naciecie plandeki", "rozcięcie plandeki",
        "plane aufgeschlitzt", "planendiebstahl", "plane aufgeschnitten",
        "planenschlitzer",
        "bâche découpée", "bâche lacérée",
        "zeil opengesneden", "zeildoek",
    ],
    "robbery_hijack": [
        "robbery", "hijack", "hijacking", "armed robbery",
        "truck hijack", "driver robbed", "carjacking",
        "napad", "rozbój", "napad na kierowcę", "napad rabunkowy",
        "porwanie ciężarówki", "napad z bronią",
        "überfall", "raubüberfall", "lkw-überfall", "fahrer überfallen",
        "bewaffneter überfall",
        "braquage", "vol à main armée", "car-jacking",
        "overval", "beroving",
        "loupežné přepadení", "přepadení",
        "jaf armat", "tâlhărie",
    ],
    "organized_crime": [
        "organized crime", "organised crime", "crime ring",
        "gang", "criminal network", "mafia",
        "zorganizowana przestępczość", "grupa przestępcza",
        "gang złodziei", "szajka", "mafia",
        "organisierte kriminalität", "bande",
        "verbrecherbande", "diebesbande",
        "crime organisé", "réseau criminel",
    ],
    "smuggling": [
        "smuggling", "contraband", "illegal goods",
        "przemyt", "kontrabanda", "nielegalne towary",
        "schmuggel", "schmuggelware",
        "contrebande", "trafic",
        "smokkel",
        "pašování",
        "contrabandă",
    ],
    "arson": [
        "arson", "set on fire", "truck fire deliberate",
        "podpalenie", "celowe podpalenie", "podpalony",
        "brandstiftung", "in brand gesetzt",
        "incendie criminel", "incendie volontaire",
        "brandstichting",
    ],
    "vehicle_hijacking": [
        "vehicle hijacking", "truck stolen", "vehicle stolen",
        "stolen truck", "stolen lorry", "stolen hgv",
        "kradzież pojazdu", "kradzież ciężarówki",
        "skradziony pojazd", "skradziony tir",
        "fahrzeugdiebstahl", "lkw gestohlen",
        "vol de véhicule", "vol de camion",
        "voertuigdiefstal", "vrachtwagen gestolen",
        "krádež vozidla",
        "furt de vehicul",
    ],
}

TIER_2_KEYWORDS: dict[str, list[str]] = {
    "insolvency": [
        "insolvency", "insolvent", "bankruptcy", "bankrupt",
        "liquidation", "administration", "winding up",
        "upadłość", "niewypłacalność", "likwidacja",
        "postępowanie upadłościowe", "ogłoszenie upadłości",
        "insolvenz", "insolvenzverfahren", "zahlungsunfähig",
        "konkurs", "liquidation",
        "insolvabilité", "faillite", "liquidation judiciaire",
        "faillissement", "failliet",
        "úpadek", "insolvence",
        "insolvență", "faliment",
        "insolvencia", "quiebra",
        "fallimento", "insolvenza",
        "csőd", "fizetésképtelenség",
    ],
    "fraud": [
        "fraud", "scam", "fake company", "fake carrier",
        "double brokering", "identity theft",
        "oszustwo", "wyłudzenie", "firma-krzak",
        "fałszywy przewoźnik", "podwójne pośrednictwo",
        "betrug", "betrugsversuch", "scheinunternehmen",
        "scheinfirma", "betrüger",
        "fraude", "escroquerie", "arnaque",
        "fraude", "oplichterij", "zwendel",
        "podvod",
        "fraudă", "escrocherie",
    ],
    "dangerous_parking": [
        "dangerous parking", "unsafe parking",
        "parking lot attack", "rest area crime",
        "niebezpieczny parking", "kradzież na parkingu",
        "niestrzeżony parking", "atak na parkingu",
        "unsicherer parkplatz", "rastplatz kriminalität",
        "parking dangereux", "aire de repos criminalité",
        "onveilige parkeerplaats",
    ],
    "non_payment": [
        "non-payment", "nonpayment", "unpaid freight",
        "payment default", "payment refused", "debt collection",
        "brak zapłaty", "niezapłacone", "nieuregulowane",
        "zaległa płatność", "windykacja", "niepłacenie",
        "nichtzahlung", "zahlungsverzug", "zahlungsausfall",
        "unbezahlte fracht",
        "non-paiement", "impayé", "défaut de paiement",
        "wanbetaling", "onbetaald",
        "neplacení", "nezaplaceno",
        "neplată", "neplătit",
    ],
    "vandalism": [
        "vandalism", "vandalized", "deliberate damage",
        "graffiti truck", "slashed tires",
        "wandalizm", "celowe uszkodzenie", "zniszczenie",
        "pocięte opony", "dewastacja",
        "vandalismus", "sachbeschädigung", "mutwillige beschädigung",
        "vandalisme", "dégradation volontaire",
        "vandalisme", "vernieling",
        "vandalismus", "vandalizmus",
    ],
    "theft_from_vehicle": [
        "theft from vehicle", "break-in", "broken into",
        "cab theft", "tools stolen",
        "kradzież z pojazdu", "włamanie do kabiny",
        "kradzież z kabiny", "skradziono z ciężarówki",
        "diebstahl aus fahrzeug", "einbruch in lkw",
        "aufbruch", "fahrerhaus aufgebrochen",
        "vol dans véhicule", "effraction",
        "inbraak in voertuig",
    ],
}

TIER_3_KEYWORDS: dict[str, list[str]] = {
    "fatal_accident": [
        "fatal accident", "fatal truck accident", "fatal crash",
        "deadly crash", "deadly accident", "truck driver killed",
        "fatal collision", "death toll", "fatalities",
        "killed in crash", "killed in accident", "driver dead",
        "śmiertelny wypadek", "zginął kierowca", "ofiara śmiertelna",
        "wypadek ze skutkiem śmiertelnym", "wypadek śmiertelny",
        "tödlicher unfall", "tödlicher lkw-unfall",
        "lkw-fahrer getötet", "lkw-fahrer verstorben",
        "tödlicher zusammenstoß", "todesopfer",
        "accident mortel", "collision mortelle",
        "dodelijk ongeval", "dodelijke aanrijding",
        "smrtelná nehoda",
        "accident mortal",
    ],
    "police_checkpoint": [
        "police checkpoint", "roadside inspection",
        "police control", "weight check", "enforcement",
        "kontrola policyjna", "kontrola drogowa",
        "inspekcja", "ważenie pojazdów",
        "polizeikontrolle", "verkehrskontrolle",
        "lkw-kontrolle", "bak-kontrolle",
        "contrôle routier", "contrôle de police",
        "politiecontrole", "verkeerscontrole",
        "policejní kontrola", "silniční kontrola",
    ],
    "protest_roadblock": [
        "protest", "road block", "roadblock", "blockade",
        "farmers protest", "border blockade", "strike action",
        "protest", "blokada drogi", "blokada granicy",
        "protest rolników", "strajk", "blokada",
        "straßenblockade", "protest", "blockade",
        "grenzblockade", "streik", "bauernprotest",
        "manifestation", "blocage routier", "grève",
        "wegblokkade", "boerenprotest",
        "blokáda", "stávka",
    ],
    "extreme_weather": [
        "extreme weather", "flooding", "heavy snow",
        "black ice", "storm damage", "hurricane",
        "tornado", "heatwave",
        "ekstremalna pogoda", "powódź", "obfite opady śniegu",
        "gołoledź", "huragan", "burza", "upał",
        "extremwetter", "überschwemmung", "schneesturm",
        "glatteis", "sturmschäden", "hitzewelle",
        "intempéries", "inondation", "verglas", "tempête",
        "extreem weer", "overstroming", "gladheid",
    ],
}

TIER_4_KEYWORDS: dict[str, list[str]] = {
    "minor_accident": [
        "minor accident", "fender bender", "minor collision",
        "slight damage", "no injuries",
        "drobna kolizja", "stłuczka", "niewielkie uszkodzenie",
        "bez ofiar", "bez rannych",
        "kleiner unfall", "auffahrunfall", "sachschaden",
        "leichter unfall", "keine verletzten",
        "accident mineur", "accrochage", "sans blessé",
        "klein ongeluk", "blikschade",
    ],
    "general_news": [
        "transport news", "logistics update", "industry report",
        "market analysis", "fleet update", "new regulation",
        "wiadomości transportowe", "rynek transportowy",
        "aktualizacja logistyczna", "analiza rynku",
        "transportnachrichten", "logistik update",
        "marktanalyse",
        "actualités transport", "marché logistique",
    ],
    "no_event": [
        "press release", "announcement", "conference",
        "webinar", "trade fair", "exhibition",
        "komunikat prasowy", "ogłoszenie", "konferencja",
        "targi", "wystawa", "webinar",
        "pressemitteilung", "ankündigung", "messe",
        "communiqué de presse", "salon professionnel",
    ],
}

# Event types that directly map to tiers
EVENT_TYPE_TIER_MAP: dict[str, tuple[int, str]] = {
    "theft_cargo": (1, "cargo_theft"),
    "theft_fuel": (1, "fuel_theft"),
    "theft_vehicle": (1, "vehicle_hijacking"),
    "bankruptcy": (2, "insolvency"),
    "restructuring": (2, "insolvency"),
    "payment_issue": (2, "non_payment"),
    "license_revoked": (2, "fraud"),
    "strike": (3, "protest_roadblock"),
    "route_closure": (3, "protest_roadblock"),
    "damage": (3, "fatal_accident"),
    "delay": (4, "general_news"),
    "other": (4, "general_news"),
}


class IntelligenceFilter:
    """Classifies events into intelligence tiers 1-4 based on keyword matching."""

    def __init__(self):
        self._compiled: dict[int, dict[str, list[re.Pattern]]] = {}
        self._compile_patterns()

    def _compile_patterns(self):
        for tier_num, keywords_dict in [
            (1, TIER_1_KEYWORDS),
            (2, TIER_2_KEYWORDS),
            (3, TIER_3_KEYWORDS),
            (4, TIER_4_KEYWORDS),
        ]:
            self._compiled[tier_num] = {}
            for category, kw_list in keywords_dict.items():
                self._compiled[tier_num][category] = [
                    re.compile(re.escape(kw), re.IGNORECASE)
                    for kw in kw_list
                ]

    def classify(
        self,
        title: str,
        description: str | None = None,
        event_type: str | None = None,
        tags: list[str] | None = None,
    ) -> TierResult:
        """Classify text into a tier. Returns TierResult with tier, category, confidence."""
        text = f"{title or ''} {description or ''} {' '.join(tags or '')}".strip()

        # 1. Try event_type direct mapping first (high confidence if matched)
        if event_type and event_type in EVENT_TYPE_TIER_MAP:
            tier, category = EVENT_TYPE_TIER_MAP[event_type]
            # Still do keyword scan to boost confidence
            kw_matches = self._scan_keywords(text, tier)
            confidence = 0.7 if kw_matches else 0.5
            return TierResult(
                tier=tier,
                category=category,
                confidence=min(1.0, confidence + len(kw_matches) * 0.05),
                matched_keywords=kw_matches[:10],
            )

        # 2. Full keyword scan across all tiers
        best_tier = 4
        best_category = "general_news"
        best_confidence = 0.1
        best_keywords: list[str] = []

        for tier_num in (1, 2, 3, 4):
            for category, patterns in self._compiled[tier_num].items():
                matches = []
                for pattern in patterns:
                    if pattern.search(text):
                        matches.append(pattern.pattern)

                if matches:
                    # More matches = higher confidence
                    confidence = min(1.0, 0.4 + len(matches) * 0.1)

                    # Higher tier (lower number) wins, or more matches wins at same tier
                    if tier_num < best_tier or (
                        tier_num == best_tier and confidence > best_confidence
                    ):
                        best_tier = tier_num
                        best_category = category
                        best_confidence = confidence
                        best_keywords = matches

        # 3. If no keywords matched at all, default to tier 4
        if not best_keywords:
            best_confidence = 0.2

        return TierResult(
            tier=best_tier,
            category=best_category,
            confidence=round(best_confidence, 2),
            matched_keywords=best_keywords[:10],
        )

    def _scan_keywords(self, text: str, tier_num: int) -> list[str]:
        """Scan text for keywords of a specific tier."""
        matches = []
        for patterns in self._compiled.get(tier_num, {}).values():
            for pattern in patterns:
                if pattern.search(text):
                    matches.append(pattern.pattern)
        return matches
