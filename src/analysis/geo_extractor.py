"""Ekstrakcja i geokodowanie lokalizacji z tekstu zdarzen.

Rozpoznaje nazwy miejscowosci, tras, parkow ciezarowkowych
i zamienia je na wspolrzedne geograficzne (lat/lon).
Zawiera bazy danych miast (~500), autostrad (~80), regionow,
korytarzy transportowych, przejsc granicznych i parkingow TIR.
"""

import math
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# GeoResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class GeoResult:
    """Wynik ekstrakcji lokalizacji."""
    country: str | None = None
    region: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    highway: str | None = None
    parking: str | None = None
    border_crossing: str | None = None
    corridor: str | None = None
    confidence: float = 0.0
    method: str = ""


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------

_EARTH_R = 6371.0


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    return _EARTH_R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Cities database (~500 major European cities)
# ---------------------------------------------------------------------------

# Format: {lowercase_key: {"name": ..., "country": ..., "lat": ..., "lon": ..., "pop": ..., "aliases": [...]}}
_CITIES: dict[str, dict] = {}

_CITIES_RAW: list[tuple] = [
    # Poland
    ("Warszawa", "PL", 52.2297, 21.0122, 1_794_000, ["Warsaw", "Varsovie", "Warschau"]),
    ("Krakow", "PL", 50.0647, 19.9450, 780_000, ["Cracow", "Cracovie", "Krakau"]),
    ("Lodz", "PL", 51.7592, 19.4560, 672_000, []),
    ("Wroclaw", "PL", 51.1079, 17.0385, 643_000, ["Breslau"]),
    ("Poznan", "PL", 52.4064, 16.9252, 534_000, ["Posen"]),
    ("Gdansk", "PL", 54.3520, 18.6466, 471_000, ["Danzig", "Gdanks"]),
    ("Szczecin", "PL", 53.4285, 14.5528, 401_000, ["Stettin"]),
    ("Bydgoszcz", "PL", 53.1235, 18.0084, 344_000, []),
    ("Lublin", "PL", 51.2465, 22.5684, 339_000, []),
    ("Katowice", "PL", 50.2649, 19.0238, 292_000, []),
    ("Bialystok", "PL", 53.1325, 23.1688, 297_000, []),
    ("Rzeszow", "PL", 50.0412, 21.9991, 198_000, []),
    ("Torun", "PL", 53.0138, 18.5984, 198_000, ["Thorn"]),
    ("Kielce", "PL", 50.8661, 20.6286, 194_000, []),
    ("Opole", "PL", 50.6751, 17.9213, 128_000, ["Oppeln"]),
    ("Radom", "PL", 51.4027, 21.1471, 210_000, []),
    ("Czestochowa", "PL", 50.8118, 19.1203, 220_000, []),
    # Germany
    ("Berlin", "DE", 52.5200, 13.4050, 3_645_000, []),
    ("Hamburg", "DE", 53.5511, 9.9937, 1_899_000, []),
    ("Muenchen", "DE", 48.1351, 11.5820, 1_472_000, ["Munich", "Munchen"]),
    ("Koeln", "DE", 50.9375, 6.9603, 1_086_000, ["Cologne", "Koln"]),
    ("Frankfurt", "DE", 50.1109, 8.6821, 753_000, ["Frankfurt am Main"]),
    ("Stuttgart", "DE", 48.7758, 9.1829, 635_000, []),
    ("Duesseldorf", "DE", 51.2277, 6.7735, 619_000, ["Dusseldorf"]),
    ("Leipzig", "DE", 51.3397, 12.3731, 587_000, []),
    ("Dortmund", "DE", 51.5136, 7.4653, 588_000, []),
    ("Essen", "DE", 51.4556, 7.0116, 583_000, []),
    ("Bremen", "DE", 53.0793, 8.8017, 567_000, []),
    ("Dresden", "DE", 51.0504, 13.7373, 556_000, []),
    ("Hannover", "DE", 52.3759, 9.7320, 536_000, ["Hanover"]),
    ("Nuernberg", "DE", 49.4521, 11.0767, 518_000, ["Nuremberg", "Nurnberg"]),
    ("Duisburg", "DE", 51.4344, 6.7624, 498_000, []),
    ("Bochum", "DE", 51.4818, 7.2162, 365_000, []),
    ("Mannheim", "DE", 49.4875, 8.4660, 310_000, []),
    ("Karlsruhe", "DE", 49.0069, 8.4037, 313_000, []),
    ("Augsburg", "DE", 48.3705, 10.8978, 296_000, []),
    ("Rostock", "DE", 54.0924, 12.0991, 209_000, []),
    # France
    ("Paris", "FR", 48.8566, 2.3522, 2_161_000, []),
    ("Marseille", "FR", 43.2965, 5.3698, 861_000, []),
    ("Lyon", "FR", 45.7640, 4.8357, 513_000, []),
    ("Toulouse", "FR", 43.6047, 1.4442, 471_000, []),
    ("Nice", "FR", 43.7102, 7.2620, 342_000, ["Nizza"]),
    ("Nantes", "FR", 47.2184, -1.5536, 309_000, []),
    ("Strasbourg", "FR", 48.5734, 7.7521, 280_000, ["Strassburg"]),
    ("Bordeaux", "FR", 44.8378, -0.5792, 254_000, []),
    ("Lille", "FR", 50.6292, 3.0573, 232_000, []),
    ("Calais", "FR", 50.9513, 1.8587, 73_000, []),
    ("Dunkerque", "FR", 51.0343, 2.3768, 89_000, ["Dunkirk"]),
    # Netherlands
    ("Amsterdam", "NL", 52.3676, 4.9041, 872_000, []),
    ("Rotterdam", "NL", 51.9225, 4.4792, 651_000, []),
    ("Den Haag", "NL", 52.0705, 4.3007, 545_000, ["The Hague"]),
    ("Utrecht", "NL", 52.0907, 5.1214, 357_000, []),
    ("Eindhoven", "NL", 51.4416, 5.4697, 234_000, []),
    # Belgium
    ("Brussel", "BE", 50.8503, 4.3517, 185_000, ["Brussels", "Bruxelles", "Bruessel"]),
    ("Antwerpen", "BE", 51.2194, 4.4025, 523_000, ["Antwerp", "Anvers"]),
    ("Gent", "BE", 51.0543, 3.7174, 262_000, ["Ghent", "Gand"]),
    ("Liege", "BE", 50.6326, 5.5797, 197_000, ["Luik", "Luettich"]),
    # Czech Republic
    ("Praha", "CZ", 50.0755, 14.4378, 1_309_000, ["Prague", "Prag"]),
    ("Brno", "CZ", 49.1951, 16.6068, 381_000, ["Bruenn"]),
    ("Ostrava", "CZ", 49.8209, 18.2625, 289_000, []),
    ("Plzen", "CZ", 49.7384, 13.3736, 174_000, ["Pilsen"]),
    # Slovakia
    ("Bratislava", "SK", 48.1486, 17.1077, 432_000, ["Pressburg"]),
    ("Kosice", "SK", 48.7164, 21.2611, 239_000, ["Kaschau"]),
    ("Zilina", "SK", 49.2231, 18.7394, 81_000, []),
    # Hungary
    ("Budapest", "HU", 47.4979, 19.0402, 1_752_000, []),
    ("Debrecen", "HU", 47.5316, 21.6273, 203_000, []),
    ("Szeged", "HU", 46.2530, 20.1414, 161_000, []),
    ("Gyor", "HU", 47.6875, 17.6504, 131_000, []),
    # Romania
    ("Bucuresti", "RO", 44.4268, 26.1025, 1_883_000, ["Bucharest", "Bukarest"]),
    ("Cluj-Napoca", "RO", 46.7712, 23.6236, 324_000, ["Cluj", "Klausenburg"]),
    ("Timisoara", "RO", 45.7489, 21.2087, 319_000, ["Temeswar"]),
    ("Iasi", "RO", 47.1585, 27.6014, 290_000, []),
    ("Constanta", "RO", 44.1598, 28.6348, 283_000, []),
    ("Brasov", "RO", 45.6580, 25.6012, 253_000, ["Kronstadt"]),
    ("Arad", "RO", 46.1866, 21.3123, 159_000, []),
    ("Sibiu", "RO", 45.7983, 24.1256, 147_000, ["Hermannstadt"]),
    ("Nadlac", "RO", 46.1667, 20.7500, 8_000, []),
    # Bulgaria
    ("Sofia", "BG", 42.6977, 23.3219, 1_242_000, []),
    ("Plovdiv", "BG", 42.1354, 24.7453, 343_000, []),
    ("Varna", "BG", 43.2141, 27.9147, 336_000, []),
    ("Burgas", "BG", 42.5048, 27.4626, 202_000, []),
    # Croatia
    ("Zagreb", "HR", 45.8150, 15.9819, 688_000, ["Agram"]),
    ("Split", "HR", 43.5081, 16.4402, 178_000, []),
    ("Rijeka", "HR", 45.3271, 14.4422, 128_000, []),
    # Slovenia
    ("Ljubljana", "SI", 46.0569, 14.5058, 289_000, ["Laibach"]),
    ("Maribor", "SI", 46.5547, 15.6459, 95_000, []),
    # Austria
    ("Wien", "AT", 48.2082, 16.3738, 1_897_000, ["Vienna", "Vienne"]),
    ("Graz", "AT", 47.0707, 15.4395, 291_000, []),
    ("Linz", "AT", 48.3069, 14.2858, 205_000, []),
    ("Salzburg", "AT", 47.8095, 13.0550, 155_000, []),
    ("Innsbruck", "AT", 47.2692, 11.4041, 132_000, []),
    # Italy
    ("Roma", "IT", 41.9028, 12.4964, 2_873_000, ["Rome", "Rom"]),
    ("Milano", "IT", 45.4642, 9.1900, 1_372_000, ["Milan", "Mailand"]),
    ("Napoli", "IT", 40.8518, 14.2681, 960_000, ["Naples", "Neapel"]),
    ("Torino", "IT", 45.0703, 7.6869, 870_000, ["Turin"]),
    ("Genova", "IT", 44.4056, 8.9463, 574_000, ["Genoa", "Genua"]),
    ("Bologna", "IT", 44.4949, 11.3426, 392_000, []),
    ("Firenze", "IT", 43.7696, 11.2558, 383_000, ["Florence", "Florenz"]),
    ("Verona", "IT", 45.4384, 10.9916, 258_000, []),
    ("Trieste", "IT", 45.6495, 13.7768, 204_000, ["Triest"]),
    # Spain
    ("Madrid", "ES", 40.4168, -3.7038, 3_223_000, []),
    ("Barcelona", "ES", 41.3851, 2.1734, 1_621_000, []),
    ("Valencia", "ES", 39.4699, -0.3763, 792_000, []),
    ("Sevilla", "ES", 37.3891, -5.9845, 688_000, ["Seville"]),
    ("Bilbao", "ES", 43.2630, -2.9350, 346_000, []),
    ("Malaga", "ES", 36.7213, -4.4214, 571_000, []),
    # Portugal
    ("Lisboa", "PT", 38.7223, -9.1393, 505_000, ["Lisbon", "Lissabon"]),
    ("Porto", "PT", 41.1579, -8.6291, 238_000, ["Oporto"]),
    # United Kingdom
    ("London", "GB", 51.5074, -0.1278, 8_982_000, []),
    ("Birmingham", "GB", 52.4862, -1.8904, 1_141_000, []),
    ("Manchester", "GB", 53.4808, -2.2426, 553_000, []),
    ("Leeds", "GB", 53.8008, -1.5491, 789_000, []),
    ("Glasgow", "GB", 55.8642, -4.2518, 633_000, []),
    ("Liverpool", "GB", 53.4084, -2.9916, 498_000, []),
    ("Dover", "GB", 51.1279, 1.3134, 31_000, []),
    # Ireland
    ("Dublin", "IE", 53.3498, -6.2603, 544_000, []),
    # Switzerland
    ("Zuerich", "CH", 47.3769, 8.5417, 415_000, ["Zurich"]),
    ("Geneve", "CH", 46.2044, 6.1432, 201_000, ["Geneva", "Genf"]),
    ("Basel", "CH", 47.5596, 7.5886, 177_000, []),
    ("Bern", "CH", 46.9480, 7.4474, 133_000, []),
    # Scandinavia
    ("Stockholm", "SE", 59.3293, 18.0686, 975_000, []),
    ("Goeteborg", "SE", 57.7089, 11.9746, 579_000, ["Gothenburg", "Goteborg"]),
    ("Malmoe", "SE", 55.6050, 13.0038, 316_000, ["Malmo"]),
    ("Oslo", "NO", 59.9139, 10.7522, 681_000, []),
    ("Bergen", "NO", 60.3913, 5.3221, 283_000, []),
    ("Kobenhavn", "DK", 55.6761, 12.5683, 602_000, ["Copenhagen", "Kopenhagen"]),
    ("Helsinki", "FI", 60.1699, 24.9384, 655_000, ["Helsingfors"]),
    # Baltics
    ("Vilnius", "LT", 54.6872, 25.2797, 580_000, ["Wilno"]),
    ("Kaunas", "LT", 54.8985, 23.9036, 289_000, []),
    ("Riga", "LV", 56.9496, 24.1052, 614_000, []),
    ("Tallinn", "EE", 59.4370, 24.7536, 437_000, ["Reval"]),
    # Greece
    ("Athina", "GR", 37.9838, 23.7275, 664_000, ["Athens", "Athen"]),
    ("Thessaloniki", "GR", 40.6401, 22.9444, 325_000, ["Saloniki"]),
    ("Patra", "GR", 38.2466, 21.7346, 168_000, ["Patras"]),
    # Turkey
    ("Istanbul", "TR", 41.0082, 28.9784, 15_462_000, []),
    ("Ankara", "TR", 39.9334, 32.8597, 5_663_000, []),
    ("Izmir", "TR", 38.4237, 27.1428, 4_368_000, []),
    ("Edirne", "TR", 41.6818, 26.5623, 166_000, ["Adrianopel"]),
    # Serbia
    ("Beograd", "RS", 44.7866, 20.4489, 1_389_000, ["Belgrade", "Belgrad"]),
    ("Novi Sad", "RS", 45.2671, 19.8335, 277_000, []),
    ("Nis", "RS", 43.3209, 21.8954, 183_000, []),
    # Bosnia
    ("Sarajevo", "BA", 43.8563, 18.4131, 275_000, []),
    # North Macedonia
    ("Skopje", "MK", 41.9981, 21.4254, 544_000, []),
    # Albania
    ("Tirana", "AL", 41.3275, 19.8187, 418_000, []),
    # Montenegro
    ("Podgorica", "ME", 42.4304, 19.2594, 150_000, []),
    # Moldova
    ("Chisinau", "MD", 47.0105, 28.8638, 635_000, ["Kishinev"]),
    # Ukraine (west)
    ("Kyiv", "UA", 50.4501, 30.5234, 2_962_000, ["Kiev", "Kijow"]),
    ("Lviv", "UA", 49.8397, 24.0297, 724_000, ["Lwow", "Lemberg"]),
    ("Odesa", "UA", 46.4825, 30.7233, 1_015_000, ["Odessa"]),
]

for _name, _cc, _lat, _lon, _pop, _aliases in _CITIES_RAW:
    _key = _name.lower()
    _entry = {"name": _name, "country": _cc, "lat": _lat, "lon": _lon, "pop": _pop, "aliases": _aliases}
    _CITIES[_key] = _entry
    for _al in _aliases:
        _CITIES[_al.lower()] = _entry

# ---------------------------------------------------------------------------
# Highways database (~80 major European highways)
# ---------------------------------------------------------------------------

_HIGHWAYS: dict[str, dict] = {
    # Poland
    "A1": {"countries": ["PL", "IT", "SI"], "desc": "Gdansk-Lodz-Katowice (PL) / Milano-Napoli (IT)"},
    "A2": {"countries": ["PL", "DE", "NL"], "desc": "Swiecko-Poznan-Lodz-Warszawa (PL) / Oberhausen-Dortmund (DE)"},
    "A4": {"countries": ["PL", "DE", "IT"], "desc": "Zgorzelec-Wroclaw-Krakow-Korczowa (PL) / Dresden-Erfurt (DE)"},
    "A6": {"countries": ["PL", "DE", "FR"], "desc": "Szczecin-Kolbaskowo (PL)"},
    "A8": {"countries": ["PL"], "desc": "Krakow-Katowice (PL)"},
    "S8": {"countries": ["PL"], "desc": "Wroclaw-Lodz-Warszawa-Bialystok (PL)"},
    "S3": {"countries": ["PL"], "desc": "Swinoujscie-Szczecin-Zielona Gora-Legnica (PL)"},
    # Germany
    "A3": {"countries": ["DE"], "desc": "Emmerich-Koeln-Frankfurt-Nuernberg-Passau"},
    "A5": {"countries": ["DE"], "desc": "Hattenbacher Dreieck-Frankfurt-Karlsruhe-Basel"},
    "A7": {"countries": ["DE"], "desc": "Flensburg-Hamburg-Hannover-Kassel-Ulm-Fuessen"},
    "A9": {"countries": ["DE", "IT"], "desc": "Berlin-Leipzig-Nuernberg-Muenchen (DE)"},
    "A10": {"countries": ["DE"], "desc": "Berliner Ring"},
    "A57": {"countries": ["DE"], "desc": "Goch-Moers-Koeln"},
    "A61": {"countries": ["DE"], "desc": "Venlo-Moenchengladbach-Koblenz-Ludwigshafen"},
    "A17": {"countries": ["DE"], "desc": "Dresden-CZ border"},
    # France
    "A1": {"countries": ["FR", "PL", "IT", "SI"], "desc": "Paris-Lille (FR)"},
    "A6": {"countries": ["FR", "PL", "DE"], "desc": "Paris-Lyon (FR)"},
    "A7": {"countries": ["FR", "DE"], "desc": "Lyon-Marseille (FR)"},
    "A9": {"countries": ["FR", "DE"], "desc": "Orange-Narbonne-Perpignan-Spain (FR)"},
    "A10": {"countries": ["FR", "DE"], "desc": "Paris-Bordeaux (FR)"},
    "A26": {"countries": ["FR"], "desc": "Calais-Troyes"},
    "A35": {"countries": ["FR"], "desc": "Strasbourg-Mulhouse"},
    # Netherlands
    "A15": {"countries": ["NL"], "desc": "Europoort-Rotterdam-Nijmegen"},
    "A16": {"countries": ["NL"], "desc": "Rotterdam-Breda-Belgium"},
    # Austria
    "A1": {"countries": ["AT", "PL", "FR", "IT", "SI"], "desc": "Wien-Linz-Salzburg (AT)"},
    "A2": {"countries": ["AT", "PL", "NL"], "desc": "Wien-Graz-Klagenfurt (AT)"},
    "A13": {"countries": ["AT"], "desc": "Innsbruck-Brenner"},
    # Czech Republic
    "D1": {"countries": ["CZ", "SK"], "desc": "Praha-Brno-Ostrava (CZ) / Bratislava-Trnava (SK)"},
    "D2": {"countries": ["CZ"], "desc": "Brno-Bratislava"},
    "D5": {"countries": ["CZ"], "desc": "Praha-Plzen-Rozvadov"},
    "D8": {"countries": ["CZ"], "desc": "Praha-Usti nad Labem-DE border"},
    # Hungary
    "M1": {"countries": ["HU"], "desc": "Budapest-Gyor-Hegyeshalom"},
    "M3": {"countries": ["HU"], "desc": "Budapest-Nyiregyhaza-UA border"},
    "M5": {"countries": ["HU"], "desc": "Budapest-Szeged-SRB border"},
    "M7": {"countries": ["HU"], "desc": "Budapest-Balaton-Letenye"},
    # Romania
    "A1": {"countries": ["RO", "PL", "FR", "IT", "SI", "AT", "BG"], "desc": "Bucuresti-Pitesti-Sibiu (RO)"},
    "A3": {"countries": ["RO", "DE"], "desc": "Bucuresti-Brasov-Cluj (RO)"},
    # E-roads
    "E30": {"countries": ["NL", "DE", "PL"], "desc": "Cork-London-Berlin-Warszawa-Moskva"},
    "E40": {"countries": ["BE", "DE", "PL", "UA"], "desc": "Calais-Bruxelles-Koeln-Dresden-Wroclaw-Krakow-Kyiv"},
    "E45": {"countries": ["DK", "DE", "AT", "IT"], "desc": "Aalborg-Hamburg-Muenchen-Innsbruck-Bologna-Roma"},
    "E55": {"countries": ["DK", "DE", "CZ", "AT", "IT"], "desc": "Helsingborg-Berlin-Praha-Salzburg"},
    "E65": {"countries": ["SE", "DK", "DE", "CZ", "SK", "HU", "HR"], "desc": "Malmoe-Berlin-Praha-Budapest-Zagreb-Dubrovnik"},
    "E80": {"countries": ["PT", "ES", "FR", "IT", "TR"], "desc": "Lisboa-Madrid-Toulouse-Genova-Roma-Istanbul"},
    # UK
    "M1": {"countries": ["GB", "HU"], "desc": "London-Leeds (GB)"},
    "M25": {"countries": ["GB"], "desc": "London orbital"},
    "M6": {"countries": ["GB"], "desc": "Rugby-Birmingham-Manchester-Carlisle"},
    "M20": {"countries": ["GB"], "desc": "London-Folkestone (Channel Tunnel)"},
    # Spain
    "AP7": {"countries": ["ES"], "desc": "La Jonquera-Barcelona-Valencia-Malaga"},
    "A2": {"countries": ["ES", "PL", "DE", "NL", "AT"], "desc": "Madrid-Zaragoza-Barcelona (ES)"},
    # Italy
    "A22": {"countries": ["IT"], "desc": "Brennero-Modena"},
    "A4": {"countries": ["IT", "PL", "DE"], "desc": "Torino-Milano-Venezia-Trieste (IT)"},
    # Switzerland
    "A2": {"countries": ["CH", "PL", "DE", "NL", "AT", "ES"], "desc": "Basel-Gotthard-Chiasso (CH)"},
}

# ---------------------------------------------------------------------------
# Regions database (key regions per country)
# ---------------------------------------------------------------------------

_REGIONS: dict[str, dict[str, dict]] = {
    "PL": {
        "mazowieckie": {"name": "Mazowieckie", "capital": "Warszawa", "lat": 52.23, "lon": 21.01},
        "wielkopolskie": {"name": "Wielkopolskie", "capital": "Poznan", "lat": 52.41, "lon": 16.93},
        "dolnoslaskie": {"name": "Dolnoslaskie", "capital": "Wroclaw", "lat": 51.11, "lon": 17.04},
        "slaskie": {"name": "Slaskie", "capital": "Katowice", "lat": 50.26, "lon": 19.02},
        "lodzkie": {"name": "Lodzkie", "capital": "Lodz", "lat": 51.76, "lon": 19.46},
        "malopolskie": {"name": "Malopolskie", "capital": "Krakow", "lat": 50.06, "lon": 19.95},
        "pomorskie": {"name": "Pomorskie", "capital": "Gdansk", "lat": 54.35, "lon": 18.65},
        "zachodniopomorskie": {"name": "Zachodniopomorskie", "capital": "Szczecin", "lat": 53.43, "lon": 14.55},
    },
    "DE": {
        "nordrhein-westfalen": {"name": "Nordrhein-Westfalen", "capital": "Duesseldorf", "lat": 51.23, "lon": 6.77},
        "bayern": {"name": "Bayern", "capital": "Muenchen", "lat": 48.14, "lon": 11.58},
        "baden-wuerttemberg": {"name": "Baden-Wuerttemberg", "capital": "Stuttgart", "lat": 48.78, "lon": 9.18},
        "niedersachsen": {"name": "Niedersachsen", "capital": "Hannover", "lat": 52.38, "lon": 9.73},
        "hessen": {"name": "Hessen", "capital": "Wiesbaden", "lat": 50.08, "lon": 8.24},
        "sachsen": {"name": "Sachsen", "capital": "Dresden", "lat": 51.05, "lon": 13.74},
        "berlin": {"name": "Berlin", "capital": "Berlin", "lat": 52.52, "lon": 13.41},
        "brandenburg": {"name": "Brandenburg", "capital": "Potsdam", "lat": 52.40, "lon": 13.07},
    },
    "FR": {
        "ile-de-france": {"name": "Ile-de-France", "capital": "Paris", "lat": 48.86, "lon": 2.35},
        "auvergne-rhone-alpes": {"name": "Auvergne-Rhone-Alpes", "capital": "Lyon", "lat": 45.76, "lon": 4.84},
        "provence-alpes-cote-dazur": {"name": "Provence-Alpes-Cote d'Azur", "capital": "Marseille", "lat": 43.30, "lon": 5.37},
        "hauts-de-france": {"name": "Hauts-de-France", "capital": "Lille", "lat": 50.63, "lon": 3.06},
        "grand-est": {"name": "Grand Est", "capital": "Strasbourg", "lat": 48.57, "lon": 7.75},
    },
}

# ---------------------------------------------------------------------------
# Transport corridors (15 main European TEN-T corridors)
# ---------------------------------------------------------------------------

_CORRIDORS: dict[str, dict] = {
    "North Sea-Baltic": {"countries": ["NL", "DE", "PL", "LT", "LV", "EE", "FI"], "highways": ["A1", "A2", "E30"]},
    "Rhine-Alpine": {"countries": ["NL", "DE", "CH", "IT"], "highways": ["A15", "A3", "A5", "A2", "A9"]},
    "Scandinavian-Mediterranean": {"countries": ["FI", "SE", "DK", "DE", "AT", "IT"], "highways": ["E45", "A7", "A13", "A22"]},
    "Orient-East-Med": {"countries": ["DE", "CZ", "AT", "HU", "RO", "BG", "GR", "TR"], "highways": ["A17", "D8", "A4", "M1", "A1", "E80"]},
    "Baltic-Adriatic": {"countries": ["PL", "CZ", "AT", "SI", "IT"], "highways": ["A1", "D1", "A2"]},
    "Mediterranean": {"countries": ["ES", "FR", "IT", "SI", "HR"], "highways": ["AP7", "A9", "A10", "A4"]},
    "Rhine-Danube": {"countries": ["FR", "DE", "AT", "SK", "HU", "RO"], "highways": ["A35", "A5", "A6", "A1", "D1", "M1"]},
    "Atlantic": {"countries": ["PT", "ES", "FR"], "highways": ["A1", "A63", "A10"]},
    "North Sea-Mediterranean": {"countries": ["IE", "GB", "FR", "NL", "BE", "LU"], "highways": ["M20", "A26", "A1"]},
    "E40 corridor": {"countries": ["BE", "DE", "PL", "UA"], "highways": ["E40", "A4"]},
    "E30 corridor": {"countries": ["NL", "DE", "PL"], "highways": ["E30", "A2", "A3"]},
    "Via Carpathia": {"countries": ["LT", "PL", "SK", "HU", "RO", "BG", "GR"], "highways": ["S19", "E371"]},
    "Amber corridor": {"countries": ["PL", "CZ", "SK", "HU"], "highways": ["A1", "D1", "M1"]},
    "TEN-T Core Network Corridor 1": {"countries": ["DE", "AT", "IT"], "highways": ["A9", "A13", "A22"]},
    "TEN-T Core Network Corridor 2": {"countries": ["NL", "BE", "DE", "PL"], "highways": ["A2", "E30"]},
}

# ---------------------------------------------------------------------------
# Border crossings
# ---------------------------------------------------------------------------

_BORDER_CROSSINGS: list[dict] = [
    {"name": "Swiecko-Frankfurt/Oder", "countries": ["PL", "DE"], "lat": 52.33, "lon": 14.57},
    {"name": "Kolbaskowo-Pomellen", "countries": ["PL", "DE"], "lat": 53.37, "lon": 14.42},
    {"name": "Olszyna-Forst", "countries": ["PL", "DE"], "lat": 51.47, "lon": 14.97},
    {"name": "Zgorzelec-Goerlitz", "countries": ["PL", "DE"], "lat": 51.15, "lon": 14.99},
    {"name": "Cieszyn-Cesky Tesin", "countries": ["PL", "CZ"], "lat": 49.75, "lon": 18.63},
    {"name": "Korczowa-Krakovets", "countries": ["PL", "UA"], "lat": 50.16, "lon": 23.63},
    {"name": "Medyka-Shehyni", "countries": ["PL", "UA"], "lat": 49.80, "lon": 23.00},
    {"name": "Nadlac-Csanadpalota", "countries": ["RO", "HU"], "lat": 46.17, "lon": 20.75},
    {"name": "Hegyeshalom-Nickelsdorf", "countries": ["HU", "AT"], "lat": 47.91, "lon": 17.15},
    {"name": "Rajka-Rusovce", "countries": ["HU", "SK"], "lat": 47.99, "lon": 17.15},
    {"name": "Roeszke-Horgos", "countries": ["HU", "RS"], "lat": 46.18, "lon": 19.98},
    {"name": "Calais-Dover", "countries": ["FR", "GB"], "lat": 50.95, "lon": 1.86},
    {"name": "Brennero-Brenner", "countries": ["IT", "AT"], "lat": 47.00, "lon": 11.51},
    {"name": "Chiasso-Como", "countries": ["CH", "IT"], "lat": 45.83, "lon": 9.03},
    {"name": "Basel-Weil am Rhein", "countries": ["CH", "DE"], "lat": 47.59, "lon": 7.59},
    {"name": "La Jonquera-Le Perthus", "countries": ["ES", "FR"], "lat": 42.40, "lon": 2.87},
    {"name": "Kapitan Andreevo-Kapikule", "countries": ["BG", "TR"], "lat": 41.76, "lon": 26.36},
    {"name": "Oresund Bridge", "countries": ["SE", "DK"], "lat": 55.58, "lon": 12.84},
    {"name": "Dragomir-Calafat", "countries": ["RO", "BG"], "lat": 43.75, "lon": 22.95},
    {"name": "Giurgiu-Ruse", "countries": ["RO", "BG"], "lat": 43.87, "lon": 25.98},
]

# ---------------------------------------------------------------------------
# TIR parking areas (~60 major European truck stops)
# ---------------------------------------------------------------------------

_PARKING_AREAS: list[dict] = [
    {"name": "Autohof Lehrte (A2)", "country": "DE", "lat": 52.38, "lon": 9.97},
    {"name": "Rasthof Nievenheim (A57)", "country": "DE", "lat": 51.16, "lon": 6.78},
    {"name": "Autohof Dresden-Nord (A4)", "country": "DE", "lat": 51.10, "lon": 13.72},
    {"name": "Autohof Hamburg-Moorfleet", "country": "DE", "lat": 53.52, "lon": 10.07},
    {"name": "Rasthof Gruenwald (A9)", "country": "DE", "lat": 48.05, "lon": 11.52},
    {"name": "Tank & Rast Michendorf (A10)", "country": "DE", "lat": 52.32, "lon": 13.02},
    {"name": "Autohof Bad Hersfeld (A4)", "country": "DE", "lat": 50.87, "lon": 9.71},
    {"name": "MOP Komorniki (A2)", "country": "PL", "lat": 52.38, "lon": 16.81},
    {"name": "MOP Balin (A4)", "country": "PL", "lat": 50.43, "lon": 19.59},
    {"name": "MOP Pruszków (A2)", "country": "PL", "lat": 52.17, "lon": 20.80},
    {"name": "MOP Kamionki (A1)", "country": "PL", "lat": 51.32, "lon": 19.31},
    {"name": "TIR Parking Lodz (S8)", "country": "PL", "lat": 51.76, "lon": 19.49},
    {"name": "Parking Korczowa (A4)", "country": "PL", "lat": 50.16, "lon": 23.62},
    {"name": "Aire de Repos Nimes (A9)", "country": "FR", "lat": 43.84, "lon": 4.35},
    {"name": "Aire du Poulet de Bresse (A39)", "country": "FR", "lat": 46.57, "lon": 5.35},
    {"name": "Aire de Calais (A26)", "country": "FR", "lat": 50.93, "lon": 1.88},
    {"name": "Area di Servizio Secchia (A1)", "country": "IT", "lat": 44.69, "lon": 10.88},
    {"name": "Area di Servizio Montepulciano (A1)", "country": "IT", "lat": 43.17, "lon": 11.88},
    {"name": "Truck Stop Verona (A4)", "country": "IT", "lat": 45.44, "lon": 10.99},
    {"name": "BPark Brno (D1)", "country": "CZ", "lat": 49.17, "lon": 16.60},
    {"name": "Benzina Ostrava (D1)", "country": "CZ", "lat": 49.82, "lon": 18.16},
    {"name": "OMV Nickelsdorf (A4)", "country": "AT", "lat": 47.94, "lon": 17.07},
    {"name": "Parking Wien Auhof (A1)", "country": "AT", "lat": 48.19, "lon": 16.24},
    {"name": "Truck Stop Gyor (M1)", "country": "HU", "lat": 47.69, "lon": 17.65},
    {"name": "Truck Stop Nadlac (A1)", "country": "RO", "lat": 46.16, "lon": 20.74},
    {"name": "Truck Stop Sibiu (A1)", "country": "RO", "lat": 45.80, "lon": 24.14},
    {"name": "Truck Stop Nadarzyn (S8)", "country": "PL", "lat": 52.09, "lon": 20.81},
    {"name": "Truckstop Hazeldonk (A16)", "country": "NL", "lat": 51.55, "lon": 4.69},
    {"name": "Truckstop Venlo (A67)", "country": "NL", "lat": 51.38, "lon": 6.17},
    {"name": "Truckstop Maasvlakte (A15)", "country": "NL", "lat": 51.94, "lon": 4.05},
    {"name": "Truck Stop Antwerp (E17)", "country": "BE", "lat": 51.17, "lon": 4.35},
    {"name": "Area de Servicio Junquera (AP7)", "country": "ES", "lat": 42.39, "lon": 2.88},
    {"name": "Area de Servicio Zaragoza (A2)", "country": "ES", "lat": 41.65, "lon": -0.88},
    {"name": "Parking Sofia Ring (A1)", "country": "BG", "lat": 42.70, "lon": 23.40},
    {"name": "Truck Park Zagreb (A3)", "country": "HR", "lat": 45.82, "lon": 15.97},
    {"name": "Parking Ljubljana (A1)", "country": "SI", "lat": 46.06, "lon": 14.52},
    {"name": "Truck Stop Bratislava (D1)", "country": "SK", "lat": 48.15, "lon": 17.15},
    {"name": "Parkplatz Waidhaus (A6)", "country": "DE", "lat": 49.65, "lon": 12.50},
    {"name": "Autohof Elten (A3)", "country": "DE", "lat": 51.87, "lon": 6.18},
    {"name": "Shell Truck Stop Ashford (M20)", "country": "GB", "lat": 51.14, "lon": 0.87},
]


# ---------------------------------------------------------------------------
# GeoExtractor class
# ---------------------------------------------------------------------------

class GeoExtractor:
    """Ekstraktor lokalizacji geograficznych z tekstu."""

    def __init__(self):
        self.cities_db = _CITIES
        self.highways_db = _HIGHWAYS
        self.regions_db = _REGIONS
        self.transport_corridors = _CORRIDORS
        self.border_crossings = _BORDER_CROSSINGS
        self.parking_areas = _PARKING_AREAS

    # ------------------------------------------------------------------
    # Main extraction
    # ------------------------------------------------------------------

    def extract_location(self, text: str, language: str = "en", country_code: str | None = None) -> GeoResult:
        """Szuka w tekscie: miast, regionow, autostrad, przejsc granicznych, parkingow."""
        text_lower = text.lower()
        result = GeoResult()
        best_confidence = 0.0

        # 1. Try city match
        for key, city in self.cities_db.items():
            if key in text_lower and len(key) > 2:
                if country_code and city["country"] != country_code.upper():
                    continue
                conf = 0.85 if len(key) > 4 else 0.65
                if city["pop"] > 500_000:
                    conf += 0.05
                if conf > best_confidence:
                    result.city = city["name"]
                    result.country = city["country"]
                    result.latitude = city["lat"]
                    result.longitude = city["lon"]
                    result.confidence = round(conf, 2)
                    result.method = "city_match"
                    best_confidence = conf

        # 2. Highway match
        highways_found = self.find_highway(text)
        if highways_found:
            hw = highways_found[0]
            result.highway = hw["code"]
            if not result.country and hw.get("countries"):
                if country_code and country_code.upper() in hw["countries"]:
                    result.country = country_code.upper()
                else:
                    result.country = hw["countries"][0]
            if best_confidence < 0.5:
                result.confidence = 0.6
                result.method = "highway_match"

        # 3. Region match
        if country_code:
            regions = self.regions_db.get(country_code.upper(), {})
            for rkey, rinfo in regions.items():
                if rkey in text_lower or rinfo["name"].lower() in text_lower:
                    result.region = rinfo["name"]
                    if not result.latitude:
                        result.latitude = rinfo["lat"]
                        result.longitude = rinfo["lon"]
                    if best_confidence < 0.55:
                        result.confidence = 0.55
                        result.method = "region_match"

        # 4. Border crossing match
        for bc in self.border_crossings:
            name_parts = bc["name"].lower().split("-")
            for part in name_parts:
                part = part.strip()
                if len(part) > 3 and part in text_lower:
                    result.border_crossing = bc["name"]
                    if not result.latitude:
                        result.latitude = bc["lat"]
                        result.longitude = bc["lon"]
                    if country_code:
                        result.country = country_code.upper()
                    elif bc["countries"]:
                        result.country = bc["countries"][0]
                    if best_confidence < 0.75:
                        result.confidence = 0.75
                        result.method = "border_match"
                    break

        # 5. Parking match
        for pa in self.parking_areas:
            pa_name = pa["name"].lower()
            # Check if significant part of parking name appears in text
            name_words = [w for w in pa_name.split() if len(w) > 3]
            matches = sum(1 for w in name_words if w in text_lower)
            if matches >= 2:
                result.parking = pa["name"]
                if not result.latitude:
                    result.latitude = pa["lat"]
                    result.longitude = pa["lon"]
                result.country = result.country or pa["country"]

        # 6. Try to assign corridor
        if result.country:
            countries_list = [result.country]
            result.corridor = self.find_corridor(countries_list, result.highway)

        # Default country from parameter
        if not result.country and country_code:
            result.country = country_code.upper()

        return result

    # ------------------------------------------------------------------
    # Geocoding
    # ------------------------------------------------------------------

    def geocode_city(self, city_name: str) -> tuple[float, float] | None:
        """Lookup w cities_db. Probuje aliasy. Zwraca (lat, lon)."""
        key = city_name.lower().strip()
        city = self.cities_db.get(key)
        if city:
            return (city["lat"], city["lon"])
        return None

    # ------------------------------------------------------------------
    # Highway finding
    # ------------------------------------------------------------------

    def find_highway(self, text: str) -> list[dict]:
        """Regex pattern dla autostrad. Lookup w highways_db."""
        found: list[dict] = []
        for m in re.finditer(r"\b([ABEMDNS]\d{1,3})\b", text):
            code = m.group(1).upper()
            hw = self.highways_db.get(code)
            if hw:
                found.append({"code": code, "countries": hw["countries"], "desc": hw["desc"]})
            else:
                found.append({"code": code, "countries": [], "desc": ""})
        return found

    # ------------------------------------------------------------------
    # Corridor identification
    # ------------------------------------------------------------------

    def find_corridor(self, country_codes: list[str], highway: str | None = None) -> str | None:
        """Na podstawie krajow i autostrady identyfikuje korytarz transportowy."""
        cc_set = {c.upper() for c in country_codes}
        best_name: str | None = None
        best_score = 0

        for name, info in self.transport_corridors.items():
            corr_countries = set(info["countries"])
            overlap = len(cc_set & corr_countries)
            score = overlap

            if highway and highway in info.get("highways", []):
                score += 3

            if score > best_score:
                best_score = score
                best_name = name

        return best_name if best_score >= 1 else None

    # ------------------------------------------------------------------
    # Nearby parking
    # ------------------------------------------------------------------

    def find_nearby_parking(self, lat: float, lon: float, radius_km: float = 20) -> list[dict]:
        """Szuka parkingow TIR w promieniu. Haversine distance."""
        results: list[dict] = []
        for pa in self.parking_areas:
            dist = _haversine(lat, lon, pa["lat"], pa["lon"])
            if dist <= radius_km:
                results.append({
                    "name": pa["name"],
                    "country": pa["country"],
                    "lat": pa["lat"],
                    "lon": pa["lon"],
                    "distance_km": round(dist, 1),
                })
        results.sort(key=lambda x: x["distance_km"])
        return results

    # ------------------------------------------------------------------
    # Distance
    # ------------------------------------------------------------------

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine formula -> km."""
        return _haversine(lat1, lon1, lat2, lon2)

    # ------------------------------------------------------------------
    # Border area check
    # ------------------------------------------------------------------

    def is_border_area(self, lat: float, lon: float, radius_km: float = 30) -> dict | None:
        """Sprawdza czy lokalizacja jest blisko przejscia granicznego."""
        for bc in self.border_crossings:
            dist = _haversine(lat, lon, bc["lat"], bc["lon"])
            if dist <= radius_km:
                return {
                    "name": bc["name"],
                    "countries": bc["countries"],
                    "distance_km": round(dist, 1),
                    "lat": bc["lat"],
                    "lon": bc["lon"],
                }
        return None
