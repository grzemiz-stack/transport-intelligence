"""Normalizacja danych: ujednolicanie formatu dat, nazw, tekstu, walut.

Przeksztalca dane z roznych zrodel do spojnego formatu gotowego do analizy.
Normalizuje encoding, biale znaki, country codes, daty do UTC, kwoty do EUR,
wykrywa jezyk tekstu, normalizuje nazwy firm (usuwa formy prawne).
"""

import logging
import re
import unicodedata
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language detection — common words per language
# ---------------------------------------------------------------------------

_LANG_WORDS: dict[str, set[str]] = {
    "de": {
        "und", "der", "die", "das", "ist", "von", "für", "mit", "auf", "ein",
        "eine", "den", "dem", "des", "nicht", "sich", "auch", "nach", "bei",
        "über", "noch", "werden", "kann", "wurde", "haben", "wird", "sind",
        "aber", "oder", "wenn", "nur", "schon", "mehr", "wie", "durch",
        "polizei", "autobahn", "fahrzeug", "unfall", "diebstahl", "lkw",
    },
    "pl": {
        "nie", "jest", "się", "jak", "ale", "tak", "już", "tylko", "czy",
        "był", "dla", "jego", "aby", "pod", "nad", "przed", "między", "ten",
        "bardzo", "przez", "jeszcze", "może", "został", "które", "tego",
        "firma", "kierowca", "kradzież", "policja", "autostrada", "ciężarówka",
        "ładunek", "towar", "wypadek", "transport", "droga", "samochód",
        "wszystkie", "które", "gdzie", "kiedy", "każdy", "także",
    },
    "fr": {
        "les", "des", "est", "une", "que", "dans", "pour", "pas", "sur",
        "sont", "avec", "plus", "par", "ont", "été", "mais", "cette", "tout",
        "fait", "peut", "aussi", "son", "comme", "être", "entre", "même",
        "après", "leurs", "autre", "encore", "sans", "depuis", "deux",
        "police", "autoroute", "camion", "vol", "accident", "chauffeur",
    },
    "en": {
        "the", "and", "for", "are", "was", "not", "but", "you", "all", "can",
        "had", "her", "one", "our", "out", "has", "this", "have", "from",
        "they", "been", "said", "each", "which", "their", "will", "other",
        "about", "many", "then", "them", "would", "make", "like", "time",
        "police", "highway", "truck", "theft", "driver", "cargo", "road",
    },
    "es": {
        "los", "las", "una", "del", "por", "con", "para", "como", "más",
        "pero", "sus", "ser", "sin", "sobre", "también", "fue", "han",
        "este", "entre", "cuando", "muy", "todos", "puede", "otro", "son",
        "policía", "autopista", "camión", "robo", "conductor", "carga",
    },
    "it": {
        "del", "della", "che", "per", "con", "una", "sono", "non", "come",
        "anche", "più", "suo", "gli", "fra", "tra", "stato", "molto", "dopo",
        "ancora", "essere", "fatto", "tutti", "ogni", "questa", "hanno",
        "polizia", "autostrada", "camion", "furto", "conducente", "carico",
    },
    "nl": {
        "het", "een", "van", "dat", "voor", "met", "zijn", "niet", "maar",
        "ook", "nog", "bij", "uit", "aan", "dan", "als", "wel", "wat",
        "wordt", "hebben", "deze", "naar", "kan", "meer", "worden", "moet",
        "politie", "snelweg", "vrachtwagen", "diefstal", "chauffeur", "lading",
    },
    "cs": {
        "pro", "ale", "tak", "aby", "byl", "být", "jejich", "jen", "jeho",
        "než", "kde", "pod", "nad", "velmi", "jako", "také", "může", "jsou",
        "nebo", "tento", "která", "které", "když", "mezi", "ještě", "bude",
        "policie", "dálnice", "kamion", "krádež", "řidič", "náklad",
    },
    "sk": {
        "pre", "ale", "tak", "aby", "bol", "jeho", "ich", "len", "ako",
        "kde", "pod", "nad", "veľmi", "než", "tiež", "môže", "alebo", "bude",
        "tento", "ktoré", "keď", "medzi", "ešte", "polícia", "diaľnica",
    },
    "hu": {
        "egy", "nem", "hogy", "van", "meg", "már", "csak", "mint", "azt",
        "még", "volt", "lehet", "sem", "fel", "igen", "után", "alatt",
        "rendőrség", "autópálya", "teherautó", "lopás", "sofőr", "rakomány",
    },
    "ro": {
        "este", "sunt", "pentru", "care", "din", "sau", "dar", "mai", "fost",
        "acest", "foarte", "poate", "până", "între", "după", "când", "doar",
        "poliție", "autostradă", "camion", "furt", "șofer", "marfă",
    },
    "bg": {
        "не", "на", "от", "за", "да", "но", "по", "със", "как", "или",
        "бе", "все", "при", "след", "между", "може", "също", "полиция",
    },
    "hr": {
        "nije", "ali", "kao", "ako", "biti", "ima", "već", "koji", "još",
        "samo", "može", "ovo", "kako", "između", "nakon", "prije", "policija",
    },
    "sl": {
        "ali", "kot", "lahko", "ima", "biti", "tudi", "samo", "bolj", "ker",
        "med", "kako", "tako", "policija", "avtocesta",
    },
    "sr": {
        "није", "али", "као", "ако", "има", "још", "само", "може", "како",
        "између", "после", "полиција",
    },
    "uk": {
        "не", "що", "але", "так", "вже", "або", "лише", "між", "після",
        "може", "також", "поліція", "автострада", "вантажівка", "крадіжка",
    },
    "tr": {
        "bir", "için", "olan", "ile", "ama", "çok", "kadar", "sonra",
        "daha", "gibi", "olarak", "ancak", "hem", "polis", "otoyol", "tır",
    },
    "pt": {
        "uma", "para", "com", "não", "por", "mas", "como", "mais", "foi",
        "são", "pode", "entre", "sobre", "muito", "depois", "ainda", "quando",
        "polícia", "autoestrada", "camião", "roubo", "motorista", "carga",
    },
    "sv": {
        "och", "att", "det", "som", "för", "med", "den", "var", "inte",
        "har", "kan", "ett", "men", "från", "hade", "alla", "efter", "vid",
        "polis", "motorväg", "lastbil", "stöld", "förare", "last",
    },
    "no": {
        "og", "det", "som", "for", "med", "den", "var", "ikke", "har",
        "kan", "fra", "men", "etter", "alle", "ved", "eller", "når",
        "politi", "motorvei", "lastebil", "tyveri", "sjåfør", "last",
    },
    "da": {
        "og", "det", "som", "til", "med", "den", "var", "ikke", "har",
        "kan", "fra", "men", "efter", "alle", "ved", "eller", "når",
        "politi", "motorvej", "lastbil", "tyveri", "chauffør", "last",
    },
    "fi": {
        "oli", "kun", "mutta", "niin", "kuin", "vain", "tai", "myös",
        "ovat", "olla", "sen", "joka", "hänen", "poliisi", "moottoritie",
    },
    "el": {
        "και", "που", "για", "από", "τον", "στο", "αλλά", "αυτό", "ότι",
        "μια", "αστυνομία", "αυτοκινητόδρομος",
    },
    "lt": {
        "yra", "kad", "bet", "kaip", "arba", "tik", "dar", "jau", "nuo",
        "policija", "greitkelis",
    },
    "lv": {
        "nav", "bet", "kur", "lai", "gan", "jau", "par", "policija",
    },
    "et": {
        "oli", "aga", "kui", "nii", "kas", "veel", "oma", "politsei",
    },
}


# ---------------------------------------------------------------------------
# Legal form patterns for company name normalization
# ---------------------------------------------------------------------------

_LEGAL_FORMS = [
    # Polish
    r"sp(?:ółka)?\.?\s*z\.?\s*o\.?\s*o\.?",
    r"sp(?:ółka)?\.?\s*j\.?",
    r"sp(?:ółka)?\.?\s*k\.?",
    r"sp(?:ółka)?\.?\s*komandytowa",
    r"sp(?:ółka)?\.?\s*akcyjna",
    r"s\.?\s*a\.?",
    # German
    r"GmbH\s*(?:&\s*Co\.?\s*KG)?",
    r"AG",
    r"KG",
    r"OHG",
    r"UG\s*(?:\(haftungsbeschränkt\))?",
    r"e\.?\s*K\.?",
    # English
    r"Ltd\.?",
    r"Limited",
    r"LLC",
    r"LLP",
    r"Inc\.?",
    r"Corp(?:oration)?\.?",
    r"PLC",
    r"Co\.?",
    # French
    r"SAS",
    r"SARL",
    r"SA",
    r"SCI",
    r"EURL",
    r"SNC",
    # Dutch/Belgian
    r"B\.?\s*V\.?",
    r"N\.?\s*V\.?",
    r"V\.?\s*O\.?\s*F\.?",
    # Italian
    r"S\.?\s*r\.?\s*l\.?",
    r"S\.?\s*p\.?\s*A\.?",
    r"S\.?\s*n\.?\s*c\.?",
    # Nordic
    r"ApS",
    r"A/S",
    r"AB",
    r"Oy",
    r"AS",
    r"ANS",
    # Eastern European
    r"Kft\.?",
    r"Rt\.?",
    r"Zrt\.?",
    r"d\.?\s*o\.?\s*o\.?",
    r"d\.?\s*d\.?",
    r"a\.?\s*s\.?",
    r"s\.?\s*r\.?\s*o\.?",
]

_LEGAL_FORM_PATTERN = re.compile(
    r"\b(?:" + "|".join(_LEGAL_FORMS) + r")\s*$",
    re.IGNORECASE,
)

# Takze na poczatku: "Spółka Xyz"
_LEGAL_PREFIX_PATTERN = re.compile(
    r"^(?:Firma|Spółka|Przedsiębiorstwo|Unternehmen|Société|Company)\s+",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Exchange rates (static, same as parser.py)
# ---------------------------------------------------------------------------

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


class EventNormalizer:
    """Normalizuje zdarzenia do wspolnego formatu."""

    def normalize(self, event: dict) -> dict:
        """Normalizuje event: tekst, country_code, daty, kwoty, encoding.

        - strip + collapse whitespace
        - country_code -> ISO 2-letter uppercase
        - daty -> UTC ISO 8601
        - kwoty -> EUR
        - encoding -> UTF-8 (NFC normalization)
        """
        result = event.copy()

        # Normalizuj pola tekstowe
        for field in ("title", "description", "raw_text"):
            text = result.get(field)
            if text:
                result[field] = self._normalize_text(text)

        # Country code -> uppercase ISO 2
        cc = result.get("country_code", "")
        if cc:
            result["country_code"] = cc.strip().upper()[:2]

        # Daty -> UTC ISO
        for date_field in ("date", "collected_at", "received_at"):
            val = result.get(date_field)
            if val:
                result[date_field] = self._normalize_date_to_utc(val)

        # Kwoty -> EUR
        amount = result.get("financial_impact_eur")
        currency = result.get("currency")
        if amount is not None and currency and currency != "EUR":
            rate = _EXCHANGE_RATES_TO_EUR.get(currency.upper(), 1.0)
            result["financial_impact_eur"] = round(float(amount) * rate, 2)
            result["original_currency"] = currency
            result["original_amount"] = amount

        # Wykryj jezyk jesli brak
        if not result.get("language"):
            text = f"{result.get('title', '')} {result.get('description', '')}"
            result["language"] = self.detect_language(text)

        return result

    def detect_language(self, text: str) -> str:
        """Prosty language detection na podstawie common words per jezyk.

        Obsluguje: de, pl, fr, en, es, it, nl, cs, sk, hu, ro, bg, hr, sl,
        sr, uk, tr, pt, sv, no, da, fi, el, lt, lv, et.
        Zwraca ISO 639-1 code.
        """
        if not text:
            return "en"

        text_lower = text.lower()
        # Tokenizuj: slowa alfanumeryczne
        words = set(re.findall(r"[\w\u00C0-\u024F\u0400-\u04FF\u0370-\u03FF]+", text_lower))

        best_lang = "en"
        best_score = 0

        for lang, lang_words in _LANG_WORDS.items():
            score = len(words & lang_words)
            if score > best_score:
                best_score = score
                best_lang = lang

        return best_lang

    def normalize_company_name(self, name: str) -> str:
        """Normalizuje nazwe firmy: usuwa formy prawne, trim, title case."""
        if not name:
            return ""

        # NFC normalization
        name = unicodedata.normalize("NFC", name)
        name = name.strip()

        # Usun formy prawne z konca
        name = _LEGAL_FORM_PATTERN.sub("", name).strip()

        # Usun prefiksy typu "Firma", "Spółka"
        name = _LEGAL_PREFIX_PATTERN.sub("", name).strip()

        # Usun cudzyslowy
        name = name.strip("\"'\u201e\u201c\u201d\u00bb\u00ab")

        # Usun podwojne spacje
        name = re.sub(r"\s+", " ", name)

        # Title case (ale zachowaj akronimy — slowa calkowicie uppercase)
        parts = name.split()
        normalized_parts = []
        for part in parts:
            if part.isupper() and len(part) > 1:
                # Akronim — zostaw
                normalized_parts.append(part)
            else:
                normalized_parts.append(part.title())
        name = " ".join(normalized_parts)

        return name.strip()

    # -- prywatne helpery -------------------------------------------------------

    def _normalize_text(self, text: str) -> str:
        """Normalizuje tekst: NFC, strip, collapse whitespace."""
        if not text:
            return ""
        # NFC normalization
        text = unicodedata.normalize("NFC", text)
        # Zamien rozne rodzaje spacji na normalna
        text = text.replace("\xa0", " ").replace("\t", " ")
        # Collapse multiple whitespace
        text = re.sub(r" {2,}", " ", text)
        # Collapse multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _normalize_date_to_utc(self, val: str) -> str:
        """Normalizuje date do UTC ISO 8601."""
        if not val:
            return val
        # Jesli juz jest ISO z timezone
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            dt_utc = dt.astimezone(timezone.utc)
            return dt_utc.isoformat()
        except (ValueError, TypeError):
            pass
        # Zwroc as-is jesli nie da sie sparsowac
        return val
