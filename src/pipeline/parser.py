"""Parsowanie surowych danych z agentow do wspolnego formatu wewnetrznego.

Obsluguje rozne formaty wejsciowe (HTML, JSON, plain text) i wyodrebnia
kluczowe pola: tytul, tresc, date, lokalizacja, zrodlo, kwoty finansowe.
Parsuje daty z wielu formatow europejskich, wyciaga lokalizacje z tekstu
(miasta, regiony, autostrady), wykrywa kwoty w roznych walutach.
"""

import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Date patterns
# ---------------------------------------------------------------------------

# ISO 8601
_ISO_PATTERN = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?"
)
# dd.mm.yyyy lub dd.mm.yy
_DOT_PATTERN = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})")
# dd/mm/yyyy
_SLASH_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")
# dd-mm-yyyy (europejski)
_DASH_EU_PATTERN = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{4})")

# Tekstowe miesiace per jezyk (numer -> lista nazw)
_MONTH_NAMES: dict[int, list[str]] = {
    1: ["january", "januar", "janvier", "enero", "gennaio", "januari", "leden",
        "styczen", "stycznia", "styczeń", "ianuarie", "січень", "ocak", "january"],
    2: ["february", "februar", "février", "febrero", "febbraio", "februari",
        "únor", "luty", "lutego", "februarie", "лютий", "şubat"],
    3: ["march", "märz", "mars", "marzo", "maart", "březen",
        "marzec", "marca", "martie", "березень", "mart"],
    4: ["april", "avril", "abril", "aprile", "duben",
        "kwiecien", "kwietnia", "kwiecień", "aprilie", "квітень", "nisan"],
    5: ["may", "mai", "mayo", "maggio", "mei", "květen",
        "maj", "maja", "mai", "травень", "mayıs"],
    6: ["june", "juni", "juin", "junio", "giugno", "červen",
        "czerwiec", "czerwca", "iunie", "червень", "haziran"],
    7: ["july", "juli", "juillet", "julio", "luglio", "červenec",
        "lipiec", "lipca", "iulie", "липень", "temmuz"],
    8: ["august", "août", "agosto", "augustus", "srpen",
        "sierpien", "sierpnia", "sierpień", "august", "серпень", "ağustos"],
    9: ["september", "septembre", "septiembre", "settembre", "září",
        "wrzesien", "września", "wrzesień", "septembrie", "вересень", "eylül"],
    10: ["october", "oktober", "octobre", "octubre", "ottobre", "říjen",
         "pazdziernik", "października", "październik", "octombrie", "жовтень", "ekim"],
    11: ["november", "novembre", "noviembre", "listopad",
         "listopad", "listopada", "noiembrie", "листопад", "kasım"],
    12: ["december", "dezember", "décembre", "diciembre", "dicembre",
         "prosinec", "grudzien", "grudnia", "grudzień", "decembrie", "грудень", "aralık"],
}

# Odwrocony lookup: nazwa -> numer
_MONTH_LOOKUP: dict[str, int] = {}
for _num, _names in _MONTH_NAMES.items():
    for _name in _names:
        _MONTH_LOOKUP[_name.lower()] = _num

# Pattern: "dd month_name yyyy" lub "month_name dd, yyyy"
_TEXT_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+([a-zA-ZàâäéèêëïîôùûüÿçæœßÀ-ž]+)\s+(\d{4})"
    r"|"
    r"([a-zA-ZàâäéèêëïîôùûüÿçæœßÀ-ž]+)\s+(\d{1,2}),?\s+(\d{4})",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Location patterns
# ---------------------------------------------------------------------------

# Autostrady europejskie
_ROAD_PATTERN = re.compile(
    r"\b([AaBbEe][\s-]?\d{1,4})\b"
    r"|\b(autostrada|autoroute|autobahn|motorway|snelweg|autopista)\s+([A-Za-z]?\d{1,4})\b",
    re.IGNORECASE,
)

# Duze europejskie miasta (transport hubs) — top ~150
_MAJOR_CITIES: dict[str, dict] = {
    # DE
    "berlin": {"country": "DE", "region": "Brandenburg"},
    "hamburg": {"country": "DE", "region": "Hamburg"},
    "münchen": {"country": "DE", "region": "Bayern"},
    "munich": {"country": "DE", "region": "Bayern"},
    "köln": {"country": "DE", "region": "Nordrhein-Westfalen"},
    "cologne": {"country": "DE", "region": "Nordrhein-Westfalen"},
    "frankfurt": {"country": "DE", "region": "Hessen"},
    "düsseldorf": {"country": "DE", "region": "Nordrhein-Westfalen"},
    "dortmund": {"country": "DE", "region": "Nordrhein-Westfalen"},
    "stuttgart": {"country": "DE", "region": "Baden-Württemberg"},
    "bremen": {"country": "DE", "region": "Bremen"},
    "hannover": {"country": "DE", "region": "Niedersachsen"},
    "duisburg": {"country": "DE", "region": "Nordrhein-Westfalen"},
    "nürnberg": {"country": "DE", "region": "Bayern"},
    "nuremberg": {"country": "DE", "region": "Bayern"},
    "dresden": {"country": "DE", "region": "Sachsen"},
    "leipzig": {"country": "DE", "region": "Sachsen"},
    # PL
    "warszawa": {"country": "PL", "region": "Mazowieckie"},
    "warsaw": {"country": "PL", "region": "Mazowieckie"},
    "kraków": {"country": "PL", "region": "Małopolskie"},
    "krakow": {"country": "PL", "region": "Małopolskie"},
    "wrocław": {"country": "PL", "region": "Dolnośląskie"},
    "wroclaw": {"country": "PL", "region": "Dolnośląskie"},
    "łódź": {"country": "PL", "region": "Łódzkie"},
    "lodz": {"country": "PL", "region": "Łódzkie"},
    "poznań": {"country": "PL", "region": "Wielkopolskie"},
    "poznan": {"country": "PL", "region": "Wielkopolskie"},
    "gdańsk": {"country": "PL", "region": "Pomorskie"},
    "gdansk": {"country": "PL", "region": "Pomorskie"},
    "szczecin": {"country": "PL", "region": "Zachodniopomorskie"},
    "katowice": {"country": "PL", "region": "Śląskie"},
    "lublin": {"country": "PL", "region": "Lubelskie"},
    "białystok": {"country": "PL", "region": "Podlaskie"},
    "bialystok": {"country": "PL", "region": "Podlaskie"},
    # FR
    "paris": {"country": "FR", "region": "Île-de-France"},
    "lyon": {"country": "FR", "region": "Auvergne-Rhône-Alpes"},
    "marseille": {"country": "FR", "region": "Provence-Alpes-Côte d'Azur"},
    "lille": {"country": "FR", "region": "Hauts-de-France"},
    "toulouse": {"country": "FR", "region": "Occitanie"},
    "bordeaux": {"country": "FR", "region": "Nouvelle-Aquitaine"},
    "strasbourg": {"country": "FR", "region": "Grand Est"},
    "calais": {"country": "FR", "region": "Hauts-de-France"},
    # NL
    "amsterdam": {"country": "NL", "region": "Noord-Holland"},
    "rotterdam": {"country": "NL", "region": "Zuid-Holland"},
    "utrecht": {"country": "NL", "region": "Utrecht"},
    "den haag": {"country": "NL", "region": "Zuid-Holland"},
    "eindhoven": {"country": "NL", "region": "Noord-Brabant"},
    # BE
    "brussels": {"country": "BE", "region": "Brussels"},
    "bruxelles": {"country": "BE", "region": "Brussels"},
    "antwerp": {"country": "BE", "region": "Flanders"},
    "antwerpen": {"country": "BE", "region": "Flanders"},
    "gent": {"country": "BE", "region": "Flanders"},
    "liège": {"country": "BE", "region": "Wallonia"},
    # AT
    "wien": {"country": "AT", "region": "Wien"},
    "vienna": {"country": "AT", "region": "Wien"},
    "graz": {"country": "AT", "region": "Steiermark"},
    "linz": {"country": "AT", "region": "Oberösterreich"},
    "salzburg": {"country": "AT", "region": "Salzburg"},
    "innsbruck": {"country": "AT", "region": "Tirol"},
    # CZ
    "praha": {"country": "CZ", "region": "Praha"},
    "prague": {"country": "CZ", "region": "Praha"},
    "brno": {"country": "CZ", "region": "Jihomoravský"},
    "ostrava": {"country": "CZ", "region": "Moravskoslezský"},
    # IT
    "roma": {"country": "IT", "region": "Lazio"},
    "rome": {"country": "IT", "region": "Lazio"},
    "milano": {"country": "IT", "region": "Lombardia"},
    "milan": {"country": "IT", "region": "Lombardia"},
    "napoli": {"country": "IT", "region": "Campania"},
    "naples": {"country": "IT", "region": "Campania"},
    "torino": {"country": "IT", "region": "Piemonte"},
    "turin": {"country": "IT", "region": "Piemonte"},
    "genova": {"country": "IT", "region": "Liguria"},
    "genoa": {"country": "IT", "region": "Liguria"},
    "bologna": {"country": "IT", "region": "Emilia-Romagna"},
    "verona": {"country": "IT", "region": "Veneto"},
    # ES
    "madrid": {"country": "ES", "region": "Comunidad de Madrid"},
    "barcelona": {"country": "ES", "region": "Cataluña"},
    "valencia": {"country": "ES", "region": "Comunitat Valenciana"},
    "sevilla": {"country": "ES", "region": "Andalucía"},
    "bilbao": {"country": "ES", "region": "País Vasco"},
    # GB
    "london": {"country": "GB", "region": "Greater London"},
    "birmingham": {"country": "GB", "region": "West Midlands"},
    "manchester": {"country": "GB", "region": "Greater Manchester"},
    "liverpool": {"country": "GB", "region": "Merseyside"},
    "leeds": {"country": "GB", "region": "West Yorkshire"},
    "dover": {"country": "GB", "region": "Kent"},
    # Nordics
    "stockholm": {"country": "SE", "region": "Stockholm"},
    "göteborg": {"country": "SE", "region": "Västra Götaland"},
    "gothenburg": {"country": "SE", "region": "Västra Götaland"},
    "malmö": {"country": "SE", "region": "Skåne"},
    "oslo": {"country": "NO", "region": "Oslo"},
    "helsinki": {"country": "FI", "region": "Uusimaa"},
    "copenhagen": {"country": "DK", "region": "Hovedstaden"},
    "københavn": {"country": "DK", "region": "Hovedstaden"},
    # Eastern Europe
    "budapest": {"country": "HU", "region": "Budapest"},
    "bucuresti": {"country": "RO", "region": "Ilfov"},
    "bucharest": {"country": "RO", "region": "Ilfov"},
    "sofia": {"country": "BG", "region": "Sofia"},
    "zagreb": {"country": "HR", "region": "Zagreb"},
    "ljubljana": {"country": "SI", "region": "Osrednjeslovenska"},
    "bratislava": {"country": "SK", "region": "Bratislavský"},
    "beograd": {"country": "RS", "region": "Beograd"},
    "belgrade": {"country": "RS", "region": "Beograd"},
    "sarajevo": {"country": "BA", "region": "Sarajevo"},
    "kyiv": {"country": "UA", "region": "Kyiv"},
    "kiev": {"country": "UA", "region": "Kyiv"},
    "lviv": {"country": "UA", "region": "Lviv"},
    "odessa": {"country": "UA", "region": "Odessa"},
    # TR
    "istanbul": {"country": "TR", "region": "Istanbul"},
    "ankara": {"country": "TR", "region": "Ankara"},
    "izmir": {"country": "TR", "region": "Izmir"},
    # CH
    "zürich": {"country": "CH", "region": "Zürich"},
    "zurich": {"country": "CH", "region": "Zürich"},
    "genève": {"country": "CH", "region": "Genève"},
    "geneva": {"country": "CH", "region": "Genève"},
    "basel": {"country": "CH", "region": "Basel-Stadt"},
    "bern": {"country": "CH", "region": "Bern"},
    # Baltics
    "vilnius": {"country": "LT", "region": "Vilnius"},
    "kaunas": {"country": "LT", "region": "Kaunas"},
    "riga": {"country": "LV", "region": "Riga"},
    "tallinn": {"country": "EE", "region": "Harju"},
    # Other
    "thessaloniki": {"country": "GR", "region": "Central Macedonia"},
    "athens": {"country": "GR", "region": "Attica"},
    "porto": {"country": "PT", "region": "Norte"},
    "lisboa": {"country": "PT", "region": "Lisboa"},
    "lisbon": {"country": "PT", "region": "Lisboa"},
    "dublin": {"country": "IE", "region": "Leinster"},
    "luxembourg": {"country": "LU", "region": "Luxembourg"},
    "minsk": {"country": "BY", "region": "Minsk"},
    "chisinau": {"country": "MD", "region": "Chisinau"},
    "tirana": {"country": "AL", "region": "Tirana"},
    "skopje": {"country": "MK", "region": "Skopje"},
    "podgorica": {"country": "ME", "region": "Podgorica"},
}

# ---------------------------------------------------------------------------
# Currency patterns
# ---------------------------------------------------------------------------

_NUM = r"(\d[\d\s.,]*\d|\d+)"  # wymaga min 1 cyfry, opcjonalnie wiecej

_CURRENCY_PATTERN = re.compile(
    rf"(?:€|EUR|eur)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:€|EUR|eur)"
    rf"|"
    rf"(?:PLN|pln|zł|zl)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:PLN|pln|zł|zl)"
    rf"|"
    rf"(?:£|GBP|gbp)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:£|GBP|gbp)"
    rf"|"
    rf"(?:CHF|chf)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:CHF|chf)"
    rf"|"
    rf"(?:CZK|czk|Kč|kč)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:CZK|czk|Kč|kč)"
    rf"|"
    rf"(?:SEK|sek|kr)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:SEK|sek|kr)"
    rf"|"
    rf"(?:NOK|nok)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:NOK|nok)"
    rf"|"
    rf"(?:DKK|dkk)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:DKK|dkk)"
    rf"|"
    rf"(?:HUF|huf|Ft|ft)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:HUF|huf|Ft|ft)"
    rf"|"
    rf"(?:RON|ron|lei)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:RON|ron|lei)"
    rf"|"
    rf"(?:TRY|try|₺|TL)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:TRY|try|₺|TL)"
    rf"|"
    rf"(?:BGN|bgn|лв)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:BGN|bgn|лв)"
    rf"|"
    rf"(?:UAH|uah|₴|грн)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:UAH|uah|₴|грн)"
    rf"|"
    rf"(?:\$|USD|usd)\s?{_NUM}"
    rf"|"
    rf"{_NUM}\s?(?:\$|USD|usd)",
    re.IGNORECASE,
)

# Kolejnosc grup w regex odpowiada walutom (para: prefix, suffix)
_CURRENCY_GROUP_MAP: list[str] = [
    "EUR", "EUR",
    "PLN", "PLN",
    "GBP", "GBP",
    "CHF", "CHF",
    "CZK", "CZK",
    "SEK", "SEK",
    "NOK", "NOK",
    "DKK", "DKK",
    "HUF", "HUF",
    "RON", "RON",
    "TRY", "TRY",
    "BGN", "BGN",
    "UAH", "UAH",
    "USD", "USD",
]

# Przyblizone kursy do EUR (statyczne — w produkcji pobieroby sie z API)
_EXCHANGE_RATES_TO_EUR: dict[str, float] = {
    "EUR": 1.0,
    "PLN": 0.23,
    "GBP": 1.16,
    "CHF": 1.05,
    "CZK": 0.041,
    "SEK": 0.088,
    "NOK": 0.087,
    "DKK": 0.134,
    "HUF": 0.0026,
    "RON": 0.20,
    "TRY": 0.029,
    "BGN": 0.51,
    "UAH": 0.025,
    "USD": 0.92,
    "HRK": 0.133,
    "RSD": 0.0085,
}


def _parse_number(s: str) -> float | None:
    """Parsuje string liczbowy z roznych formatow europejskich."""
    s = s.strip().replace(" ", "").replace("\u00a0", "")
    if not s:
        return None
    # Europejski: 1.234.567,89 lub 1 234 567,89
    if "," in s and "." in s:
        if s.rindex(",") > s.rindex("."):
            # 1.234,56 -> comma is decimal
            s = s.replace(".", "").replace(",", ".")
        else:
            # 1,234.56 -> dot is decimal
            s = s.replace(",", "")
    elif "," in s:
        # Moze byc 1234,56 (decimal) lub 1,234 (thousands)
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# EventParser
# ---------------------------------------------------------------------------


class EventParser:
    """Parser surowych danych do ustandaryzowanego formatu zdarzen."""

    def parse_raw_event(self, raw_event: dict) -> dict:
        """Wyciaga i normalizuje pola: title, description, date, location, source.

        Zwraca ustrukturyzowany dict gotowy do zapisu.
        """
        title = (raw_event.get("title") or "").strip()
        description = (raw_event.get("description") or raw_event.get("text") or "").strip()
        raw_text = (raw_event.get("raw_text") or "").strip()
        source_url = raw_event.get("source_url", "")
        source_name = raw_event.get("source_name", "")
        country_code = (raw_event.get("country_code") or "").upper()

        # Wyciagnij date
        date_str = raw_event.get("date") or raw_event.get("timestamp") or ""
        parsed_date = self.extract_date(date_str)
        if parsed_date is None:
            # Sprobuj z tytulu lub opisu
            for text_field in (title, description, raw_text):
                parsed_date = self.extract_date(text_field)
                if parsed_date:
                    break

        # Wyciagnij lokalizacje
        full_text = f"{title} {description} {raw_text}"
        location = self.extract_location(full_text, country_code)

        # Wyciagnij impact finansowy
        financial_impact = self.extract_financial_impact(full_text)

        result = {
            "title": title,
            "description": description,
            "raw_text": raw_text[:5000],
            "date": parsed_date.isoformat() if parsed_date else None,
            "date_parsed": parsed_date,
            "source_url": source_url,
            "source_name": source_name,
            "country_code": country_code,
            "location": location,
            "financial_impact_eur": financial_impact,
        }

        # Przepisz oryginalne metadane
        for key in ("trust_score", "is_official", "source_type", "language",
                     "collected_at", "agent_name"):
            if key in raw_event:
                result[key] = raw_event[key]

        return result

    def extract_date(self, text: str) -> datetime | None:
        """Parsuje daty z wielu formatow europejskich. Zwraca datetime lub None."""
        if not text:
            return None

        # 1. ISO 8601: 2024-01-15T10:30:00
        m = _ISO_PATTERN.search(text)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                h = int(m.group(4) or 0)
                mi = int(m.group(5) or 0)
                s = int(m.group(6) or 0)
                return datetime(y, mo, d, h, mi, s)
            except (ValueError, TypeError):
                pass

        # 2. dd.mm.yyyy
        m = _DOT_PATTERN.search(text)
        if m:
            try:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 100:
                    y += 2000
                return datetime(y, mo, d)
            except (ValueError, TypeError):
                pass

        # 3. dd/mm/yyyy
        m = _SLASH_PATTERN.search(text)
        if m:
            try:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 100:
                    y += 2000
                return datetime(y, mo, d)
            except (ValueError, TypeError):
                pass

        # 4. dd-mm-yyyy (europejski)
        m = _DASH_EU_PATTERN.search(text)
        if m:
            try:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return datetime(y, mo, d)
            except (ValueError, TypeError):
                pass

        # 5. Tekstowe: "15 stycznia 2024" lub "January 15, 2024"
        m = _TEXT_DATE_PATTERN.search(text)
        if m:
            try:
                if m.group(1):
                    # dd month_name yyyy
                    d = int(m.group(1))
                    month_name = m.group(2).lower()
                    y = int(m.group(3))
                    mo = _MONTH_LOOKUP.get(month_name)
                    if mo:
                        return datetime(y, mo, d)
                elif m.group(4):
                    # month_name dd, yyyy
                    month_name = m.group(4).lower()
                    d = int(m.group(5))
                    y = int(m.group(6))
                    mo = _MONTH_LOOKUP.get(month_name)
                    if mo:
                        return datetime(y, mo, d)
            except (ValueError, TypeError):
                pass

        return None

    def extract_location(self, text: str, country_code: str = "") -> dict:
        """Szuka nazw miast, regionow, autostrad (A1, A2, E40 itd.).

        Zwraca: {country, region, city, road, latitude, longitude}
        (lat/lon nullable na razie).
        """
        result: dict = {
            "country": country_code or None,
            "region": None,
            "city": None,
            "road": None,
            "latitude": None,
            "longitude": None,
        }

        if not text:
            return result

        text_lower = text.lower()

        # Szukaj autostrad
        roads = []
        for m in _ROAD_PATTERN.finditer(text):
            road = m.group(1) or f"{m.group(3)}"
            road = road.upper().replace(" ", "").replace("-", "")
            if road not in roads:
                roads.append(road)
        if roads:
            result["road"] = roads[0]  # glowna droga

        # Szukaj miast
        for city_name, city_info in _MAJOR_CITIES.items():
            # Szukaj calego slowa
            pattern = r"\b" + re.escape(city_name) + r"\b"
            if re.search(pattern, text_lower):
                result["city"] = city_name.title()
                result["region"] = city_info["region"]
                if not result["country"]:
                    result["country"] = city_info["country"]
                break

        return result

    def extract_financial_impact(self, text: str) -> float | None:
        """Szuka kwot w tekscie i konwertuje na EUR.

        Obsluguje: €, EUR, PLN, zł, £, GBP, CHF, CZK, SEK, NOK, DKK,
        HUF, RON, TRY, BGN, UAH, USD.
        """
        if not text:
            return None

        best_eur = None

        for m in _CURRENCY_PATTERN.finditer(text):
            groups = m.groups()
            # Znajdz ktora grupa matchuje
            for i, val in enumerate(groups):
                if val is not None:
                    currency = _CURRENCY_GROUP_MAP[i]
                    amount = _parse_number(val)
                    if amount is not None and amount > 0:
                        rate = _EXCHANGE_RATES_TO_EUR.get(currency, 1.0)
                        eur_amount = round(amount * rate, 2)
                        if best_eur is None or eur_amount > best_eur:
                            best_eur = eur_amount
                    break

        return best_eur
