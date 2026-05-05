"""Multilingual road alerts keyword matching — for CargoControl stream.

Classifies messages as road alerts (checkpoints, roadworks, jams, closures,
weather warnings, strikes, toll changes, accidents, border delays).

Usage:
    from src.agents.road_alerts_keywords import is_road_alert, classify_alert_type
    if is_road_alert(text, "pl"):
        alert_type = classify_alert_type(text, "pl")
"""

ROAD_ALERT_KEYWORDS: dict[str, list[str]] = {
    "pl": [
        "kontrola", "itd", "policja", "waga", "tachograf", "mandat", "remont",
        "objazd", "korek", "wypadek", "zamknięta droga", "zakaz ruchu", "wiatr",
        "oblodzenie", "mgła", "blokada", "strajk",
    ],
    "de": [
        "kontrolle", "bag", "polizei", "waage", "tachograph", "bußgeld", "baustelle",
        "umleitung", "stau", "sperrung", "fahrverbot", "wind", "glatteis", "streik",
        "maut", "unfall",
    ],
    "en": [
        "checkpoint", "inspection", "police", "weigh station", "tachograph", "fine",
        "roadwork", "diversion", "traffic jam", "road closed", "ban", "wind", "ice",
        "strike", "toll", "accident",
    ],
    "ru": [
        "контроль", "полиция", "весы", "тахограф", "штраф", "ремонт", "объезд",
        "пробка", "перекрытие", "запрет", "ветер", "гололёд", "забастовка",
    ],
    "uk": [
        "контроль", "поліція", "ваги", "тахограф", "штраф", "ремонт", "об'їзд",
        "затор", "перекриття", "заборона",
    ],
    "fr": [
        "contrôle", "gendarmerie", "péage", "tachygraphe", "amende", "travaux",
        "déviation", "bouchon", "route barrée", "grève", "accident",
    ],
    "tr": [
        "kontrol", "polis", "tartı", "takoğraf", "ceza", "yol çalışması",
        "trafik sıkışıklığı", "grev", "kaza",
    ],
    "ro": [
        "control", "poliție", "cântar", "tahograf", "amendă", "lucrări", "deviere",
        "blocat", "accident",
    ],
    "hu": [
        "ellenőrzés", "rendőrség", "mérleg", "tachográf", "bírság", "útépítés",
        "kerülő", "dugó", "baleset",
    ],
    "cs": [
        "kontrola", "policie", "váha", "tachograf", "pokuta", "oprava", "objížďka",
        "zácpa", "nehoda",
    ],
    "es": [
        "control", "policía", "báscula", "tacógrafo", "multa", "obras", "desvío",
        "atasco", "accidente",
    ],
    "it": [
        "controllo", "polizia", "bilancia", "tachigrafo", "multa", "lavori",
        "deviazione", "coda", "incidente",
    ],
}

ALERT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "police_checkpoint": [
        "kontrola", "checkpoint", "inspection", "kontrolle", "contrôle", "control",
        "kontrol", "ellenőrzés", "itd", "bag", "police", "policja", "polizei",
        "polizia", "policía", "poliție", "policie", "polis", "rendőrség",
        "gendarmerie", "поліція", "полиция",
    ],
    "roadwork": [
        "remont", "roadwork", "baustelle", "travaux", "obras", "lavori", "lucrări",
        "oprava", "útépítés", "yol çalışması", "ремонт",
    ],
    "traffic_jam": [
        "korek", "traffic jam", "stau", "bouchon", "atasco", "coda", "dugó",
        "zácpa", "trafik sıkışıklığı", "затор", "пробка",
    ],
    "road_closed": [
        "zamknięta droga", "road closed", "sperrung", "route barrée", "zakaz ruchu",
        "fahrverbot", "blocat", "blokada", "перекриття", "перекрытие", "заборона",
        "запрет", "ban",
    ],
    "weather_warning": [
        "wiatr", "oblodzenie", "mgła", "wind", "ice", "glatteis", "ветер",
        "гололёд",
    ],
    "strike": [
        "strajk", "strike", "streik", "grève", "grev", "забастовка",
    ],
    "toll_change": [
        "maut", "toll", "péage",
    ],
    "accident": [
        "wypadek", "accident", "unfall", "incidente", "accidente", "baleset",
        "nehoda", "kaza",
    ],
    "border_delay": [
        "granica", "border", "grenze", "frontière", "frontera", "confine",
        "границa", "кордон", "grænse", "raja",
    ],
}


def is_road_alert(text: str, language: str) -> bool:
    """Return True if text matches any road alert keyword for the given language."""
    text_lower = text.lower()
    keywords = ROAD_ALERT_KEYWORDS.get(language, ROAD_ALERT_KEYWORDS.get("en", []))
    return any(kw in text_lower for kw in keywords)


def classify_alert_type(text: str, language: str) -> str:
    """Return best-matching alert type from ALERT_TYPE_KEYWORDS.

    Checks all alert type keyword lists and returns the type with the most
    keyword matches. Falls back to "other" if no match.
    """
    text_lower = text.lower()
    best_type = "other"
    best_count = 0

    for alert_type, keywords in ALERT_TYPE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > best_count:
            best_count = count
            best_type = alert_type

    return best_type
