"""Silnik NLP obslugujacy wiele jezykow europejskich.

Analiza tekstu: detekcja jezyka, ekstrakcja encji (firmy, lokalizacje, kwoty,
pojazdy, cargo), analiza sentymentu, ekstrakcja slow kluczowych i szczegolow
transportowych — bez zaleznosci od zewnetrznych modeli ML.
"""

import re
from collections import Counter

# ---------------------------------------------------------------------------
# Language detection — common words per language
# ---------------------------------------------------------------------------

_LANG_WORDS: dict[str, set[str]] = {
    "de": {
        "der", "die", "das", "und", "ist", "von", "mit", "auf", "den", "des",
        "ein", "eine", "nicht", "sich", "auch", "wird", "nach", "bei", "aus",
        "wie", "aber", "hat", "wurde", "oder", "noch", "werden", "sind", "mehr",
        "lkw", "lastwagen", "fahrer", "autobahn", "diebstahl", "ladung", "fracht",
        "unfall", "polizei", "grenze", "insolvenz", "spedition", "transport",
    },
    "pl": {
        "nie", "jest", "sie", "na", "to", "do", "jak", "ale", "ze", "tak",
        "co", "czy", "za", "od", "po", "ich", "przez", "tylko", "jego", "tej",
        "dla", "przy", "ten", "jeszcze", "tym", "tego", "juz", "bardzo",
        "kierowca", "kradziez", "ladunek", "ciezarowka", "policja", "autostrada",
        "firma", "transport", "naczepa", "parking", "granica", "wypadek", "strata",
    },
    "fr": {
        "les", "des", "est", "une", "que", "pas", "dans", "qui", "pour", "sur",
        "par", "sont", "plus", "avec", "mais", "son", "ses", "aux", "tout",
        "cette", "fait", "comme", "ont", "peut", "entre", "aussi", "nous",
        "camion", "chauffeur", "vol", "cargaison", "autoroute", "police", "fret",
        "transport", "accident", "entreprise", "frontiere", "greve", "douane",
    },
    "en": {
        "the", "and", "was", "for", "are", "but", "not", "you", "all", "can",
        "had", "her", "one", "our", "out", "has", "his", "how", "its", "may",
        "new", "now", "old", "see", "way", "who", "did", "get", "let", "say",
        "she", "too", "use", "been", "have", "from", "with", "they", "this",
        "truck", "driver", "theft", "cargo", "highway", "police", "freight",
        "transport", "trailer", "parking", "border", "accident", "company",
    },
    "es": {
        "los", "las", "una", "del", "que", "por", "con", "para", "como", "mas",
        "pero", "sus", "fue", "han", "hay", "son", "muy", "sin", "sobre", "este",
        "entre", "cuando", "todo", "esta", "ser", "tiene", "desde", "donde",
        "camion", "conductor", "robo", "carga", "autopista", "policia", "transporte",
    },
    "it": {
        "che", "non", "una", "con", "per", "sono", "del", "gli", "dal", "dei",
        "alla", "nel", "sul", "delle", "dalla", "nelle", "questo", "anche",
        "come", "piu", "stato", "sua", "suo", "loro", "dopo", "tra", "essere",
        "camion", "autista", "furto", "carico", "autostrada", "polizia", "trasporto",
    },
    "nl": {
        "het", "een", "van", "dat", "met", "zijn", "voor", "niet", "maar",
        "ook", "nog", "aan", "bij", "uit", "door", "dit", "wat", "dan",
        "naar", "haar", "hun", "meer", "wel", "hem", "zou", "over", "tot",
        "vrachtwagen", "diefstal", "lading", "snelweg", "politie", "vervoer",
    },
    "cs": {
        "jsem", "jest", "jako", "tak", "ale", "pro", "pod", "pri", "byl", "jeho",
        "jsou", "bude", "bylo", "jste", "jsme", "bych", "aby", "tento", "tato",
        "kamion", "ridic", "kradez", "naklad", "dalnice", "policie", "preprava",
    },
    "sk": {
        "som", "nie", "tak", "ako", "ale", "pre", "pod", "pri", "bol", "jeho",
        "bude", "bolo", "boli", "sme", "ste", "aby", "alebo", "este", "tento",
        "kamion", "vodic", "kradez", "naklad", "dialnica", "policia", "preprava",
    },
    "hu": {
        "egy", "nem", "hogy", "van", "meg", "volt", "csak", "mint", "mar",
        "fel", "lett", "igen", "pedig", "majd", "meg", "lesz", "vagy", "kell",
        "kamion", "sofor", "lopas", "rakomany", "autopalya", "rendorseg", "szallitas",
    },
    "ro": {
        "este", "sunt", "care", "din", "pentru", "cele", "fost", "poate", "mai",
        "doar", "cum", "sau", "dar", "prin", "fiind", "daca", "fara", "acest",
        "camion", "sofer", "furt", "marfa", "autostrada", "politie", "transport",
    },
    "bg": {
        "che", "na", "za", "ot", "sa", "se", "ne", "po", "da", "pri",
        "kato", "ste", "ima", "samo", "tova", "koito", "edin", "sas", "oshte",
        "kamion", "krazhba", "tovar", "magistrala", "politsiya", "transport",
    },
    "hr": {
        "sam", "nije", "kao", "ali", "bio", "ima", "jos", "vec", "ili",
        "samo", "biti", "kod", "tog", "sve", "kad", "ovo", "tako", "ovaj",
        "kamion", "vozac", "kradja", "teret", "autocesta", "policija", "prijevoz",
    },
    "sl": {
        "sem", "kot", "ali", "bil", "ima", "vec", "tudi", "lahko", "vse",
        "samo", "biti", "pri", "tako", "brez", "zelo", "mora", "tega", "nato",
        "kamion", "voznik", "tatvina", "tovor", "avtocesta", "policija", "prevoz",
    },
    "sr": {
        "sam", "nije", "kao", "ali", "bio", "ima", "jos", "vec", "ili",
        "samo", "biti", "kod", "tog", "sve", "kad", "ovo", "tako", "ovaj",
        "kamion", "vozac", "kradja", "teret", "autoput", "policija", "prevoz",
    },
    "uk": {
        "shcho", "vin", "vona", "yak", "ale", "bulo", "tse", "vid", "pid",
        "bude", "yoho", "sviy", "tsey", "taka", "koli", "mozhe", "svoyi",
        "vantazhivka", "vodiy", "kradizhka", "vantazh", "avtostrada", "politsiya",
    },
    "tr": {
        "bir", "bu", "ile", "var", "ama", "daha", "icin", "olan", "gibi",
        "kadar", "sonra", "bunu", "olarak", "ancak", "ise", "hem", "onu",
        "kamyon", "surucu", "hirsizlik", "yuk", "otoban", "polis", "tasima",
    },
    "pt": {
        "que", "nao", "uma", "com", "para", "mas", "por", "dos", "das",
        "foi", "como", "mais", "tem", "ser", "seu", "sua", "nos", "esta",
        "camiao", "motorista", "roubo", "carga", "autoestrada", "policia", "transporte",
    },
    "sv": {
        "och", "att", "det", "som", "har", "med", "den", "inte", "var",
        "kan", "till", "ett", "sig", "men", "hon", "han", "alla", "sin",
        "lastbil", "forare", "stold", "last", "motorvag", "polis", "transport",
    },
    "no": {
        "og", "det", "som", "har", "med", "den", "ikke", "var", "kan",
        "til", "men", "hun", "han", "alle", "sin", "fra", "ble", "vil",
        "lastebil", "sjaafor", "tyveri", "last", "motorvei", "politi", "transport",
    },
    "da": {
        "og", "det", "som", "har", "med", "den", "ikke", "var", "kan",
        "til", "men", "hun", "han", "alle", "sin", "fra", "blev", "vil",
        "lastbil", "chauffeur", "tyveri", "last", "motorvej", "politi", "transport",
    },
    "fi": {
        "oli", "han", "mutta", "kun", "niin", "kuin", "olla", "tama",
        "ovat", "vain", "myos", "nyt", "tai", "sitten", "etta", "mita",
        "rekka", "kuljettaja", "varkaus", "lasti", "moottoritie", "poliisi", "kuljetus",
    },
    "el": {
        "kai", "sto", "gia", "apo", "pou", "den", "tha", "oti", "ena",
        "mia", "ton", "tin", "tis", "tous", "einai", "auto", "opos", "otan",
        "fortigo", "odigos", "klopi", "fortio", "aftokinitodromos", "astynomia",
    },
    "lt": {
        "kad", "yra", "tai", "bet", "dar", "jau", "tik", "nuo", "apie",
        "buvo", "dabar", "labai", "gali", "turi", "kuri", "tada", "arba",
        "sunkvezimis", "vairuotojas", "vagiste", "krovinys", "automagistrale", "policija",
    },
    "lv": {
        "kas", "bet", "vai", "par", "gan", "nav", "jau", "viss", "tik",
        "bija", "ari", "lai", "bus", "tad", "kur", "vel", "pec", "pie",
        "kravas", "soferis", "zaglis", "krava", "automagistrala", "policija",
    },
    "et": {
        "oli", "kas", "aga", "mis", "kui", "see", "juba", "siis", "veel",
        "oma", "tema", "seda", "mitte", "nii", "kuid", "ning", "voi", "kes",
        "veoauto", "juht", "vargus", "last", "kiirtee", "politsei", "transport",
    },
}


# ---------------------------------------------------------------------------
# Sentiment dictionaries per language
# ---------------------------------------------------------------------------

_SENTIMENT_NEGATIVE: dict[str, set[str]] = {
    "en": {
        "theft", "stolen", "robbery", "hijack", "loss", "damage", "accident",
        "crash", "delay", "bankrupt", "insolvency", "fraud", "seizure", "fire",
        "destroyed", "killed", "injured", "missing", "strike", "protest", "arrest",
        "illegal", "violation", "penalty", "fine", "revoked", "suspended",
    },
    "de": {
        "diebstahl", "gestohlen", "raub", "verlust", "schaden", "unfall",
        "verzoegerung", "insolvenz", "betrug", "brand", "zerstoert", "streik",
        "festnahme", "illegal", "verstoss", "strafe", "entzogen", "konkurs",
    },
    "pl": {
        "kradziez", "skradziono", "rabunek", "strata", "uszkodzenie", "wypadek",
        "opoznienie", "upadlosc", "bankructwo", "oszustwo", "pozar", "zniszczony",
        "strajk", "aresztowanie", "nielegalne", "naruszenie", "kara", "cofniecie",
        "niewypłacalnosc", "zaginiecie", "wyludzenie",
    },
    "fr": {
        "vol", "vole", "cambriolage", "perte", "dommage", "accident", "retard",
        "faillite", "fraude", "incendie", "detruit", "greve", "arrestation",
        "illegal", "amende", "revoque", "suspendu",
    },
    "es": {
        "robo", "robado", "asalto", "perdida", "dano", "accidente", "retraso",
        "quiebra", "fraude", "incendio", "destruido", "huelga", "arresto",
        "ilegal", "multa", "revocado",
    },
    "it": {
        "furto", "rubato", "rapina", "perdita", "danno", "incidente", "ritardo",
        "fallimento", "frode", "incendio", "distrutto", "sciopero", "arresto",
        "illegale", "multa", "revocato",
    },
    "nl": {
        "diefstal", "gestolen", "overval", "verlies", "schade", "ongeluk",
        "vertraging", "faillissement", "fraude", "brand", "vernietigd", "staking",
        "arrestatie", "illegaal", "boete", "ingetrokken",
    },
    "cs": {
        "kradez", "ukradeno", "loupez", "ztrata", "poskozeni", "nehoda",
        "zpozdeni", "upadek", "podvod", "pozar", "zniceny", "stavka",
        "zatceni", "ilegalni", "pokuta",
    },
    "ro": {
        "furt", "furat", "jaf", "pierdere", "dauna", "accident", "intarziere",
        "faliment", "frauda", "incendiu", "distrus", "greva", "arestare",
        "ilegal", "amenda", "revocat",
    },
    "tr": {
        "hirsizlik", "calindi", "soygun", "kayip", "hasar", "kaza", "gecikme",
        "iflas", "dolandiricilik", "yangin", "yikik", "grev", "tutuklama",
        "yasadisi", "ceza", "iptal",
    },
    "uk": {
        "kradizhka", "vkradeno", "pograbuvannya", "vtrata", "poshkodzhennya",
        "avariya", "zatrymka", "bankrutstvo", "shakhraystvo", "pozhezha",
        "zruynovaniy", "strayk", "aresht", "nezakonnyy", "shtraf",
    },
}

_SENTIMENT_POSITIVE: dict[str, set[str]] = {
    "en": {"safe", "secure", "recovered", "found", "awarded", "growth", "improvement", "timely", "successful"},
    "de": {"sicher", "geborgen", "gefunden", "ausgezeichnet", "wachstum", "verbesserung", "puenktlich", "erfolgreich"},
    "pl": {"bezpieczny", "odzyskano", "znaleziono", "nagroda", "rozwoj", "poprawa", "terminowy", "sukces"},
    "fr": {"securise", "recupere", "trouve", "recompense", "croissance", "amelioration", "ponctuel", "reussi"},
}


# ---------------------------------------------------------------------------
# Legal form patterns for company detection
# ---------------------------------------------------------------------------

_LEGAL_FORMS = (
    r"(?:sp\.?\s*z\s*o\.?\s*o\.?|sp\.?\s*j\.?|s\.?\s*a\.?|s\.?\s*c\.?)"
    r"|GmbH(?:\s*&\s*Co\.?\s*KG)?|AG|KG|OHG|UG"
    r"|Ltd\.?|Plc\.?|Inc\.?|LLC|LLP"
    r"|S\.?A\.?S\.?|S\.?A\.?R\.?L\.?|E\.?U\.?R\.?L\.?"
    r"|B\.?V\.?|N\.?V\.?"
    r"|s\.?r\.?o\.?|a\.?s\.?"
    r"|Kft\.?|Zrt\.?|Bt\.?"
    r"|d\.?o\.?o\.?"
    r"|S\.?R\.?L\.?"
    r"|A\.?[SB]\.?"
    r"|S\.?p\.?\s*A\.?"
    r"|S\.?L\.?"
    r"|O[yY]"
)

_COMPANY_RE = re.compile(
    rf"((?:[A-Z\u00C0-\u024F][\w\u00C0-\u024F-]*(?:\s+[A-Z\u00C0-\u024F][\w\u00C0-\u024F-]*)*)"
    rf"\s+(?:{_LEGAL_FORMS}))",
    re.UNICODE,
)

# Quoted company names
_QUOTED_COMPANY_RE = re.compile(
    r'["\u201e\u201c\u201d\u00ab\u00bb]([^"\u201e\u201c\u201d\u00ab\u00bb]{3,60})["\u201e\u201c\u201d\u00ab\u00bb]',
    re.UNICODE,
)

# ---------------------------------------------------------------------------
# Vehicle patterns
# ---------------------------------------------------------------------------

_VEHICLE_TYPES: dict[str, list[str]] = {
    "en": ["truck", "lorry", "trailer", "semi-trailer", "tanker", "van", "bus", "HGV", "TIR"],
    "de": ["LKW", "Lastwagen", "Sattelzug", "Anhaenger", "Tanklastwagen", "Transporter", "Bus", "TIR"],
    "pl": ["ciezarowka", "tir", "naczepa", "cysterna", "bus", "autobus", "pojazd", "samochod ciezarowy", "przyczepa"],
    "fr": ["camion", "semi-remorque", "remorque", "citerne", "fourgon", "bus", "poids lourd", "TIR"],
    "es": ["camion", "remolque", "semirremolque", "cisterna", "furgoneta", "autobus", "TIR"],
    "it": ["camion", "rimorchio", "semirimorchio", "cisterna", "furgone", "autobus", "TIR"],
}

# License plate patterns per country
_PLATE_RE = re.compile(
    r"\b("
    r"[A-Z]{2,3}[-\s]?\d{3,5}[-\s]?[A-Z]{0,3}"  # Generic EU
    r"|[A-Z]{1,3}\s?\d{1,4}\s?[A-Z]{1,3}"  # DE style
    r"|[A-Z]{2}\d{4}[A-Z]{2}"  # PL style
    r")\b"
)

# ---------------------------------------------------------------------------
# Cargo types
# ---------------------------------------------------------------------------

_CARGO_KEYWORDS: dict[str, list[str]] = {
    "electronics": ["electronics", "elektronika", "elektronik", "electronique", "telefon", "laptop", "computer", "TV", "smartphone", "tablet"],
    "fuel": ["fuel", "diesel", "paliwo", "benzyna", "kraftstoff", "carburant", "combustible", "nafta"],
    "food": ["food", "zywnosc", "lebensmittel", "alimentaire", "alimentos", "cibo", "meat", "mieso", "fleisch"],
    "pharmaceuticals": ["pharmaceutical", "pharma", "farmaceutyki", "leki", "medikamente", "medicaments", "medicine"],
    "textiles": ["textile", "clothing", "odzież", "tekstylia", "textilien", "vetements", "ropa", "tessili"],
    "alcohol": ["alcohol", "alkohol", "wine", "wino", "beer", "piwo", "spirits", "vodka", "whisky"],
    "tobacco": ["tobacco", "tyton", "tabak", "cigarettes", "papierosy", "zigaretten"],
    "metals": ["metal", "metale", "metall", "copper", "miedz", "aluminium", "steel", "stal", "stahl"],
    "chemicals": ["chemical", "chemia", "chemie", "chimique", "hazardous", "niebezpieczne", "gefahrgut"],
    "building_materials": ["building", "budowlane", "baumaterial", "cement", "beton", "concrete", "lumber", "drewno"],
    "automotive_parts": ["auto parts", "czesci", "autoteile", "spare parts", "ersatzteile"],
    "machinery": ["machinery", "maszyny", "maschinen", "equipment", "sprzet"],
}


# ---------------------------------------------------------------------------
# Amount / currency patterns
# ---------------------------------------------------------------------------

_AMOUNT_RE = re.compile(
    r"(?:EUR|USD|GBP|PLN|CZK|HUF|RON|SEK|NOK|DKK|CHF|TRY|BGN|HRK)"
    r"\s?(\d[\d\s.,]*\d|\d+)"
    r"|(\d[\d\s.,]*\d|\d+)\s?"
    r"(?:EUR|USD|GBP|PLN|CZK|HUF|RON|SEK|NOK|DKK|CHF|TRY|BGN|HRK|"
    r"\u20ac|\$|\u00a3|z[lł]|K[cč]|Ft|lei|kr|Fr|TL|лв|kn)",
    re.IGNORECASE,
)

# Date patterns
_DATE_RE = re.compile(
    r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})\b"
    r"|\b(\d{4})[./\-](\d{1,2})[./\-](\d{1,2})\b"
)

# Time of day patterns
_TIME_PATTERNS: dict[str, list[str]] = {
    "night": ["night", "noc", "nacht", "nuit", "noche", "notte", "natt",
              "02:00", "03:00", "04:00", "01:00", "00:00", "23:00", "22:00"],
    "morning": ["morning", "rano", "morgen", "matin", "manana", "mattina",
                "06:00", "07:00", "08:00", "09:00"],
    "day": ["afternoon", "dzien", "mittag", "apres-midi", "tarde", "pomeriggio",
            "12:00", "13:00", "14:00", "15:00"],
    "evening": ["evening", "wieczor", "abend", "soir", "tarde", "sera",
                "18:00", "19:00", "20:00", "21:00"],
}

# Transport keywords for extract_keywords
_TRANSPORT_KEYWORDS: dict[str, list[str]] = {
    "theft": ["theft", "stolen", "robbery", "hijack", "kradziez", "skradziono", "rabunek",
              "diebstahl", "gestohlen", "raub", "vol", "vole", "furto", "rubato", "robo"],
    "damage": ["damage", "damaged", "destroyed", "crash", "uszkodzenie", "zniszczony", "wypadek",
               "schaden", "unfall", "dommage", "accident", "danno", "incidente"],
    "delay": ["delay", "delayed", "late", "opoznienie", "spozniony", "verzoegerung", "retard"],
    "strike": ["strike", "protest", "blockade", "strajk", "blokada", "streik", "greve", "sciopero", "huelga"],
    "financial": ["bankrupt", "insolvency", "payment", "debt", "upadlosc", "bankructwo", "platnosc",
                  "insolvenz", "konkurs", "zahlung", "faillite", "paiement"],
    "route": ["highway", "motorway", "autobahn", "autostrada", "autoroute", "border", "granica",
              "grenze", "frontiere", "corridor", "korytarz"],
    "vehicle": ["truck", "lorry", "trailer", "tanker", "ciezarowka", "naczepa", "cysterna",
                "lkw", "lastwagen", "camion", "semi-remorque"],
}


# ---------------------------------------------------------------------------
# NLPEngine
# ---------------------------------------------------------------------------

class NLPEngine:
    """Wielojezyczny silnik przetwarzania jezyka naturalnego."""

    def __init__(self):
        self.supported_languages = list(_LANG_WORDS.keys())

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def analyze(self, text: str, language: str | None = None) -> dict:
        """Pelna analiza tekstu.

        Returns: {language, entities, keywords, sentiment, transport_details, summary}
        """
        if not text or not text.strip():
            return {"language": "en", "entities": {}, "keywords": [], "sentiment": {}, "transport_details": {}, "summary": ""}

        if not language:
            language = self.detect_language(text)

        entities = self.extract_entities(text, language)
        keywords = self.extract_keywords(text, language)
        sentiment = self.analyze_sentiment(text, language)
        transport = self.extract_transport_details(text, language)

        # Brief summary
        parts: list[str] = []
        if entities.get("companies"):
            parts.append(f"Companies: {', '.join(entities['companies'][:3])}")
        if entities.get("locations"):
            parts.append(f"Locations: {', '.join(entities['locations'][:3])}")
        if keywords:
            parts.append(f"Keywords: {', '.join(keywords[:5])}")
        summary = "; ".join(parts) if parts else "No significant entities detected."

        return {
            "language": language,
            "entities": entities,
            "keywords": keywords,
            "sentiment": sentiment,
            "transport_details": transport,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def detect_language(self, text: str) -> str:
        """Wykrywa jezyk tekstu na bazie common words. Fallback: 'en'."""
        if not text:
            return "en"

        words = set(re.findall(r"[a-z\u00C0-\u024F]{2,}", text.lower()))
        if not words:
            return "en"

        scores: dict[str, int] = {}
        for lang, lang_words in _LANG_WORDS.items():
            score = len(words & lang_words)
            if score > 0:
                scores[lang] = score

        if not scores:
            return "en"
        return max(scores, key=scores.get)

    # ------------------------------------------------------------------
    # Entity extraction
    # ------------------------------------------------------------------

    def extract_entities(self, text: str, language: str) -> dict:
        """Wyodrebnia encje: companies, locations, dates, amounts, vehicles, persons, cargo_types."""
        companies = self._extract_companies(text)
        locations = self._extract_locations(text)
        dates = self._extract_dates(text)
        amounts = self._extract_amounts(text)
        vehicles = self._extract_vehicles(text, language)
        persons = self._extract_persons(text)
        cargo_types = self._extract_cargo_types(text)

        return {
            "companies": companies,
            "locations": locations,
            "dates": dates,
            "amounts": amounts,
            "vehicles": vehicles,
            "persons": persons,
            "cargo_types": cargo_types,
        }

    def _extract_companies(self, text: str) -> list[str]:
        """Wykrywa nazwy firm (forma prawna + capitalized words)."""
        found: list[str] = []

        for m in _COMPANY_RE.finditer(text):
            name = m.group(1).strip()
            if len(name) > 3:
                found.append(name)

        for m in _QUOTED_COMPANY_RE.finditer(text):
            name = m.group(1).strip()
            # Likely a company if contains uppercase start or legal form hint
            if name[0].isupper() and len(name) > 3:
                found.append(name)

        return list(dict.fromkeys(found))  # deduplicate preserving order

    def _extract_locations(self, text: str) -> list[str]:
        """Wykrywa lokalizacje: miasta, regiony, kraje, autostrady."""
        locations: list[str] = []

        # Highways: A1, E40, M25, D1, etc.
        for m in re.finditer(r"\b([ABEMDNS]\d{1,4})\b", text):
            locations.append(m.group(1))

        # Country names
        _COUNTRY_NAMES = {
            "Poland", "Germany", "France", "Czech Republic", "Slovakia",
            "Hungary", "Romania", "Bulgaria", "Croatia", "Slovenia",
            "Austria", "Netherlands", "Belgium", "Italy", "Spain",
            "Portugal", "Sweden", "Norway", "Denmark", "Finland",
            "Greece", "Turkey", "United Kingdom", "Ireland", "Switzerland",
            "Polska", "Niemcy", "Francja", "Czechy", "Slowacja",
            "Wegry", "Rumunia", "Bulgaria", "Chorwacja", "Slowenia",
            "Austria", "Holandia", "Belgia", "Wlochy", "Hiszpania",
            "Deutschland", "Frankreich", "Tschechien", "Ungarn",
            "Rumaenien", "Bulgarien", "Kroatien", "Slowenien",
            "Oesterreich", "Niederlande", "Belgien", "Italien", "Spanien",
        }
        for name in _COUNTRY_NAMES:
            if name.lower() in text.lower():
                locations.append(name)

        # Capitalized words that might be cities (heuristic)
        for m in re.finditer(r"\b([A-Z\u00C0-\u024F][a-z\u00C0-\u024F]{2,}(?:\s[A-Z\u00C0-\u024F][a-z\u00C0-\u024F]{2,})?)\b", text):
            word = m.group(1)
            # Skip common non-location words
            skip = {"The", "This", "That", "Monday", "Tuesday", "Wednesday",
                    "Thursday", "Friday", "Saturday", "Sunday", "January",
                    "February", "March", "April", "May", "June", "July",
                    "August", "September", "October", "November", "December",
                    "Police", "Transport", "Company", "Polizei", "Policja"}
            if word not in skip and len(word) > 2:
                locations.append(word)

        return list(dict.fromkeys(locations))

    def _extract_dates(self, text: str) -> list[str]:
        """Wykrywa daty w tekście."""
        dates: list[str] = []
        for m in _DATE_RE.finditer(text):
            dates.append(m.group(0))
        # ISO dates
        for m in re.finditer(r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?", text):
            dates.append(m.group(0))
        return dates

    def _extract_amounts(self, text: str) -> list[str]:
        """Wykrywa kwoty z waluta."""
        amounts: list[str] = []
        for m in _AMOUNT_RE.finditer(text):
            amounts.append(m.group(0).strip())
        return amounts

    def _extract_vehicles(self, text: str, language: str) -> list[str]:
        """Wykrywa referencje do pojazdow (typy + nr rejestracyjne)."""
        vehicles: list[str] = []

        # Vehicle types
        type_words = _VEHICLE_TYPES.get(language, []) + _VEHICLE_TYPES.get("en", [])
        text_lower = text.lower()
        for vt in type_words:
            if vt.lower() in text_lower:
                vehicles.append(vt)

        # License plates
        for m in _PLATE_RE.finditer(text):
            plate = m.group(1).strip()
            if len(plate) >= 5:
                vehicles.append(f"plate:{plate}")

        return list(dict.fromkeys(vehicles))

    def _extract_persons(self, text: str) -> list[str]:
        """Heurystycznie wykrywa imiona i nazwiska (do anonimizacji)."""
        persons: list[str] = []
        # Pattern: Two capitalized words in a row (first + last name)
        for m in re.finditer(
            r"\b([A-Z\u00C0-\u024F][a-z\u00C0-\u024F]{1,20})\s+([A-Z\u00C0-\u024F][a-z\u00C0-\u024F]{1,20})\b",
            text,
        ):
            first, last = m.group(1), m.group(2)
            # Skip common word pairs that aren't names
            skip_first = {"The", "New", "Old", "North", "South", "East", "West", "San", "Saint", "Von", "Van"}
            if first not in skip_first and len(first) > 1 and len(last) > 1:
                persons.append(f"{first} {last}")
        return persons

    def _extract_cargo_types(self, text: str) -> list[str]:
        """Wykrywa typy ladunku w tekscie."""
        text_lower = text.lower()
        found: list[str] = []
        for cargo_type, keywords in _CARGO_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    found.append(cargo_type)
                    break
        return found

    # ------------------------------------------------------------------
    # Keywords
    # ------------------------------------------------------------------

    def extract_keywords(self, text: str, language: str) -> list[str]:
        """Wyciaga top 10 slow kluczowych zwiazanych z transportem i bezpieczenstwem."""
        text_lower = text.lower()
        scored: Counter = Counter()

        for category, kw_list in _TRANSPORT_KEYWORDS.items():
            for kw in kw_list:
                if kw.lower() in text_lower:
                    scored[kw.lower()] += 1

        # Also count words from language-specific negative sentiment
        neg = _SENTIMENT_NEGATIVE.get(language, set()) | _SENTIMENT_NEGATIVE.get("en", set())
        for word in neg:
            if word in text_lower:
                scored[word] += 1

        return [kw for kw, _ in scored.most_common(10)]

    # ------------------------------------------------------------------
    # Sentiment
    # ------------------------------------------------------------------

    def analyze_sentiment(self, text: str, language: str) -> dict:
        """Prosty analityk sentymentu: NEGATIVE, NEUTRAL, POSITIVE ze score -1..1."""
        text_lower = text.lower()
        words = set(re.findall(r"[a-z\u00C0-\u024F]{2,}", text_lower))

        neg_words = _SENTIMENT_NEGATIVE.get(language, set()) | _SENTIMENT_NEGATIVE.get("en", set())
        pos_words = _SENTIMENT_POSITIVE.get(language, set()) | _SENTIMENT_POSITIVE.get("en", set())

        neg_count = len(words & neg_words)
        pos_count = len(words & pos_words)
        total = neg_count + pos_count

        if total == 0:
            return {"label": "NEUTRAL", "score": 0.0, "negative_count": 0, "positive_count": 0}

        score = (pos_count - neg_count) / total  # -1 to 1
        score = round(score, 2)

        if score < -0.2:
            label = "NEGATIVE"
        elif score > 0.2:
            label = "POSITIVE"
        else:
            label = "NEUTRAL"

        return {"label": label, "score": score, "negative_count": neg_count, "positive_count": pos_count}

    # ------------------------------------------------------------------
    # Transport details
    # ------------------------------------------------------------------

    def extract_transport_details(self, text: str, language: str) -> dict:
        """Wyciaga szczegoly transportowe: route, vehicle, cargo, time, parking, highway, border."""
        text_lower = text.lower()

        # Route detection
        route = None
        # Pattern: City -> City or City - City
        route_m = re.search(
            r"([A-Z\u00C0-\u024F][a-z\u00C0-\u024F]+)\s*[\u2192\u2014\->]+\s*([A-Z\u00C0-\u024F][a-z\u00C0-\u024F]+)",
            text,
        )
        if route_m:
            route = f"{route_m.group(1)} \u2192 {route_m.group(2)}"
        # Highway
        hw_m = re.search(r"\b([ABEMD]\d{1,3})\b", text)
        if hw_m:
            route = (route + f" ({hw_m.group(1)})" if route else hw_m.group(1))

        # Vehicle type
        vehicle_type = None
        vt_words = _VEHICLE_TYPES.get(language, []) + _VEHICLE_TYPES.get("en", [])
        for vt in vt_words:
            if vt.lower() in text_lower:
                vehicle_type = vt
                break

        # Cargo type
        cargo_type = None
        for ct, keywords in _CARGO_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    cargo_type = ct
                    break
            if cargo_type:
                break

        # Time of day
        time_of_day = None
        for period, patterns in _TIME_PATTERNS.items():
            for pat in patterns:
                if pat.lower() in text_lower:
                    time_of_day = period
                    break
            if time_of_day:
                break

        # Parking mentioned
        parking_keywords = {"parking", "rest area", "raststaette", "raststatte", "aire de repos",
                           "area di servizio", "area de descanso", "parkomat", "autohof",
                           "truck stop", "parkplatz", "postoj"}
        parking_mentioned = any(pk in text_lower for pk in parking_keywords)

        # Highway mentioned
        highway_mentioned = bool(re.search(r"\b[ABEMD]\d{1,3}\b", text))

        # Border crossing
        border_keywords = {"border", "granica", "grenze", "frontiere", "frontera", "confine",
                          "customs", "celny", "zoll", "douane", "dogana", "aduana",
                          "crossing", "przejscie", "grenzuebergang"}
        border_mentioned = any(bk in text_lower for bk in border_keywords)

        return {
            "route": route,
            "vehicle_type": vehicle_type,
            "cargo_type": cargo_type,
            "time_of_day": time_of_day,
            "parking_mentioned": parking_mentioned,
            "highway_mentioned": highway_mentioned,
            "border_crossing_mentioned": border_mentioned,
        }
