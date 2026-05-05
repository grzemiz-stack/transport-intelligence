"""Rejestr wszystkich krajow Europy i ich metadanych.

Centralny slownik 46 krajow obslugiwanych przez system z informacjami
o kodzie ISO, jezykach, strefie czasowej, regionie i sciezce do konfiguracji.
"""

from dataclasses import dataclass
from pathlib import Path

COUNTRIES_DIR = Path(__file__).parent


@dataclass
class CountryMeta:
    """Metadane kraju."""

    name: str
    code: str
    languages: list[str]
    timezone: str
    region: str
    directory: str
    active: bool = True


COUNTRY_REGISTRY: dict[str, CountryMeta] = {
    "DE": CountryMeta("Germany", "DE", ["de"], "Europe/Berlin", "Western Europe", "germany"),
    "PL": CountryMeta("Poland", "PL", ["pl"], "Europe/Warsaw", "Eastern Europe", "poland"),
    "FR": CountryMeta("France", "FR", ["fr"], "Europe/Paris", "Western Europe", "france"),
    "NL": CountryMeta("Netherlands", "NL", ["nl"], "Europe/Amsterdam", "Western Europe", "netherlands"),
    "BE": CountryMeta("Belgium", "BE", ["nl", "fr", "de"], "Europe/Brussels", "Western Europe", "belgium"),
    "CZ": CountryMeta("Czech Republic", "CZ", ["cs"], "Europe/Prague", "Eastern Europe", "czech_republic"),
    "SK": CountryMeta("Slovakia", "SK", ["sk"], "Europe/Bratislava", "Eastern Europe", "slovakia"),
    "AT": CountryMeta("Austria", "AT", ["de"], "Europe/Vienna", "Western Europe", "austria"),
    "CH": CountryMeta("Switzerland", "CH", ["de", "fr", "it"], "Europe/Zurich", "Western Europe", "switzerland"),
    "IT": CountryMeta("Italy", "IT", ["it"], "Europe/Rome", "Southern Europe", "italy"),
    "ES": CountryMeta("Spain", "ES", ["es"], "Europe/Madrid", "Southern Europe", "spain"),
    "PT": CountryMeta("Portugal", "PT", ["pt"], "Europe/Lisbon", "Southern Europe", "portugal"),
    "GB": CountryMeta("United Kingdom", "GB", ["en"], "Europe/London", "Northern Europe", "united_kingdom"),
    "IE": CountryMeta("Ireland", "IE", ["en", "ga"], "Europe/Dublin", "Northern Europe", "ireland"),
    "SE": CountryMeta("Sweden", "SE", ["sv"], "Europe/Stockholm", "Northern Europe", "sweden"),
    "NO": CountryMeta("Norway", "NO", ["no"], "Europe/Oslo", "Northern Europe", "norway"),
    "FI": CountryMeta("Finland", "FI", ["fi", "sv"], "Europe/Helsinki", "Northern Europe", "finland"),
    "DK": CountryMeta("Denmark", "DK", ["da"], "Europe/Copenhagen", "Northern Europe", "denmark"),
    "HU": CountryMeta("Hungary", "HU", ["hu"], "Europe/Budapest", "Eastern Europe", "hungary"),
    "RO": CountryMeta("Romania", "RO", ["ro"], "Europe/Bucharest", "Eastern Europe", "romania"),
    "BG": CountryMeta("Bulgaria", "BG", ["bg"], "Europe/Sofia", "Southeastern Europe", "bulgaria"),
    "HR": CountryMeta("Croatia", "HR", ["hr"], "Europe/Zagreb", "Southeastern Europe", "croatia"),
    "SI": CountryMeta("Slovenia", "SI", ["sl"], "Europe/Ljubljana", "Southeastern Europe", "slovenia"),
    "RS": CountryMeta("Serbia", "RS", ["sr"], "Europe/Belgrade", "Southeastern Europe", "serbia"),
    "BA": CountryMeta("Bosnia and Herzegovina", "BA", ["bs", "hr", "sr"], "Europe/Sarajevo", "Southeastern Europe", "bosnia"),
    "ME": CountryMeta("Montenegro", "ME", ["sr"], "Europe/Podgorica", "Southeastern Europe", "montenegro"),
    "MK": CountryMeta("North Macedonia", "MK", ["mk"], "Europe/Skopje", "Southeastern Europe", "north_macedonia"),
    "AL": CountryMeta("Albania", "AL", ["sq"], "Europe/Tirane", "Southeastern Europe", "albania"),
    "XK": CountryMeta("Kosovo", "XK", ["sq", "sr"], "Europe/Pristina", "Southeastern Europe", "kosovo"),
    "GR": CountryMeta("Greece", "GR", ["el"], "Europe/Athens", "Southern Europe", "greece"),
    "TR": CountryMeta("Turkey", "TR", ["tr"], "Europe/Istanbul", "Southeastern Europe", "turkey"),
    "UA": CountryMeta("Ukraine", "UA", ["uk"], "Europe/Kyiv", "Eastern Europe", "ukraine"),
    "BY": CountryMeta("Belarus", "BY", ["be", "ru"], "Europe/Minsk", "Eastern Europe", "belarus"),
    "MD": CountryMeta("Moldova", "MD", ["ro"], "Europe/Chisinau", "Eastern Europe", "moldova"),
    "LT": CountryMeta("Lithuania", "LT", ["lt"], "Europe/Vilnius", "Northern Europe", "lithuania"),
    "LV": CountryMeta("Latvia", "LV", ["lv"], "Europe/Riga", "Northern Europe", "latvia"),
    "EE": CountryMeta("Estonia", "EE", ["et"], "Europe/Tallinn", "Northern Europe", "estonia"),
    "LU": CountryMeta("Luxembourg", "LU", ["lb", "fr", "de"], "Europe/Luxembourg", "Western Europe", "luxembourg"),
    "IS": CountryMeta("Iceland", "IS", ["is"], "Atlantic/Reykjavik", "Northern Europe", "iceland"),
    "MT": CountryMeta("Malta", "MT", ["mt", "en"], "Europe/Malta", "Southern Europe", "malta"),
    "CY": CountryMeta("Cyprus", "CY", ["el", "tr"], "Asia/Nicosia", "Southern Europe", "cyprus"),
    "LI": CountryMeta("Liechtenstein", "LI", ["de"], "Europe/Vaduz", "Western Europe", "liechtenstein"),
    "MC": CountryMeta("Monaco", "MC", ["fr"], "Europe/Monaco", "Western Europe", "monaco"),
    "AD": CountryMeta("Andorra", "AD", ["ca"], "Europe/Andorra", "Southern Europe", "andorra"),
    "SM": CountryMeta("San Marino", "SM", ["it"], "Europe/San_Marino", "Southern Europe", "san_marino"),
    "GE": CountryMeta("Georgia", "GE", ["ka"], "Asia/Tbilisi", "Eastern Europe", "georgia"),
}


def get_all_countries() -> dict[str, CountryMeta]:
    """Zwraca slownik wszystkich zarejestrowanych krajow."""
    return COUNTRY_REGISTRY.copy()


def get_country(code: str) -> CountryMeta | None:
    """Zwraca metadane kraju po kodzie ISO."""
    return COUNTRY_REGISTRY.get(code.upper())


def get_active_countries() -> dict[str, CountryMeta]:
    """Zwraca tylko aktywne kraje."""
    return {k: v for k, v in COUNTRY_REGISTRY.items() if v.active}


def get_countries_by_region(region: str) -> dict[str, CountryMeta]:
    """Zwraca kraje z danego regionu (np. 'Western Europe')."""
    return {k: v for k, v in COUNTRY_REGISTRY.items() if v.region == region}


def get_config_path(code: str) -> Path | None:
    """Zwraca sciezke do config.yaml danego kraju."""
    meta = get_country(code)
    if meta:
        return COUNTRIES_DIR / meta.directory / "config.yaml"
    return None
