"""Klasyfikacja zdarzen transportowych na podstawie keyword matching.

Przypisuje event_type (THEFT_CARGO, THEFT_FUEL, THEFT_VEHICLE, DAMAGE, DELAY,
STRIKE, PAYMENT_ISSUE, BANKRUPTCY, RESTRUCTURING, LICENSE_REVOKED,
ROUTE_CLOSURE, OTHER), severity (CRITICAL/HIGH/MEDIUM/LOW/INFO)
oraz tags na podstawie slow kluczowych per jezyk.
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    THEFT_CARGO = "theft_cargo"
    THEFT_FUEL = "theft_fuel"
    THEFT_VEHICLE = "theft_vehicle"
    DAMAGE = "damage"
    DELAY = "delay"
    STRIKE = "strike"
    PAYMENT_ISSUE = "payment_issue"
    BANKRUPTCY = "bankruptcy"
    RESTRUCTURING = "restructuring"
    LICENSE_REVOKED = "license_revoked"
    ROUTE_CLOSURE = "route_closure"
    OTHER = "other"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ---------------------------------------------------------------------------
# Keywords per event_type per language
# ---------------------------------------------------------------------------

KEYWORDS: dict[str, dict[str, list[str]]] = {
    # ===== THEFT_CARGO =====
    "theft_cargo": {
        "en": [
            "cargo theft", "stolen cargo", "cargo stolen", "freight theft",
            "load stolen", "goods stolen", "lorry theft", "truck robbery",
            "cargo robbery", "stolen goods", "theft of goods", "load theft",
            "cargo missing", "shipment stolen", "container theft",
            "hijacked truck", "hijacked lorry", "stolen shipment",
        ],
        "de": [
            "ladungsdiebstahl", "fracht gestohlen", "diebstahl von fracht",
            "ladung gestohlen", "fracht verschwunden", "ladung verschwunden",
            "lkw beraubt", "lkw-raub", "lkw raub", "ladungsraub",
            "güterdiebstahl", "containerdiebstahl", "warendiebstahl",
            "gestohlene fracht", "gestohlene ladung", "frachtdiebstahl",
            "lkw-diebstahl ladung", "geraubte ladung", "ladung geraubt",
        ],
        "pl": [
            "kradzież ładunku", "skradziono towar", "ukradziono ładunek",
            "kradzież towaru", "zaginął ładunek", "rabunek ładunku",
            "rabunek towaru", "skradziony ładunek", "skradzione towary",
            "utrata ładunku", "napad na ciężarówkę", "napad na tira",
            "kradzież z naczepy", "kradzież z ciężarówki", "okradziono kierowcę",
            "skradziono z naczepy", "rabunek transportu", "zaginięcie ładunku",
            "kradzież przesyłki", "skradzione mienie", "rozbój na kierowcę",
        ],
        "fr": [
            "vol de marchandises", "vol de fret", "vol de cargaison",
            "cargaison volée", "marchandises volées", "fret volé",
            "vol de camion", "braquage de camion", "vol de chargement",
            "détournement de fret", "camion dévalisé", "chargement volé",
            "vol de conteneur", "pillage de camion",
        ],
        "es": [
            "robo de carga", "carga robada", "robo de mercancías",
            "mercancías robadas", "robo de camión", "asalto a camión",
            "hurto de carga", "carga desaparecida", "robo de contenedor",
            "atraco a camión", "sustracción de mercancía",
        ],
        "it": [
            "furto di carico", "carico rubato", "furto di merce",
            "merce rubata", "rapina al camion", "furto di merci",
            "carico scomparso", "furto di container", "furto del carico",
            "rapina di carico", "trafugamento di merce",
        ],
        "nl": [
            "ladingdiefstal", "lading gestolen", "vracht gestolen",
            "vrachtdiefstal", "gestolen lading", "diefstal van lading",
            "truck overvallen", "containerdiefstal", "goederendiefstal",
        ],
        "cs": [
            "krádež nákladu", "odcizení nákladu", "ukradený náklad",
            "loupež nákladu", "krádež zboží", "přepadení kamionu",
        ],
        "ro": [
            "furt de marfă", "marfă furată", "jaf de transport",
            "furt de încărcătură", "furt din camion",
        ],
        "uk": [
            "крадіжка вантажу", "вкрадено вантаж", "пограбування вантажівки",
            "викрадення вантажу", "крадіжка товару", "зникнення вантажу",
        ],
        "tr": [
            "yük hırsızlığı", "kargo hırsızlığı", "çalınan yük",
            "tır soygunu", "kamyon soygunu", "yük soygunu",
        ],
    },

    # ===== THEFT_FUEL =====
    "theft_fuel": {
        "en": [
            "fuel theft", "diesel theft", "stolen fuel", "fuel stolen",
            "siphoning fuel", "fuel siphoned", "diesel siphoned",
            "fuel drain", "tank drained",
        ],
        "de": [
            "dieseldiebstahl", "kraftstoffdiebstahl", "diesel gestohlen",
            "tankdiebstahl", "kraftstoff abgezapft", "diesel abgezapft",
            "spritdiebstahl", "tankinhalt gestohlen",
        ],
        "pl": [
            "kradzież paliwa", "ukradziono paliwo", "kradzież diesla",
            "skradziono paliwo", "wyssanie paliwa", "kradzież oleju napędowego",
            "spuszczenie paliwa", "kradzież z baku", "opróżniony zbiornik",
        ],
        "fr": [
            "vol de carburant", "vol de diesel", "carburant volé",
            "siphonnage de carburant", "diesel volé",
        ],
        "es": [
            "robo de combustible", "robo de diésel", "combustible robado",
            "sifón de combustible",
        ],
        "it": [
            "furto di carburante", "furto di gasolio", "carburante rubato",
            "gasolio rubato",
        ],
        "nl": [
            "brandstof diefstal", "diesel gestolen", "brandstof gestolen",
        ],
        "cs": [
            "krádež paliva", "krádež nafty", "odcizení paliva",
        ],
        "ro": [
            "furt de combustibil", "furt de motorină",
        ],
        "uk": [
            "крадіжка палива", "вкрадено паливо", "крадіжка дизеля",
        ],
        "tr": [
            "yakıt hırsızlığı", "mazot hırsızlığı", "çalınan yakıt",
        ],
    },

    # ===== THEFT_VEHICLE =====
    "theft_vehicle": {
        "en": [
            "truck stolen", "vehicle theft", "stolen truck", "lorry stolen",
            "stolen vehicle", "vehicle stolen", "hijacked vehicle",
            "carjacking", "trailer stolen", "stolen trailer",
        ],
        "de": [
            "lkw gestohlen", "fahrzeugdiebstahl", "gestohlener lkw",
            "fahrzeug gestohlen", "auflieger gestohlen", "sattelzug gestohlen",
            "fahrzeug entwendet", "lkw entwendet",
        ],
        "pl": [
            "kradzież pojazdu", "skradziono pojazd", "ukradziono ciężarówkę",
            "kradzież ciężarówki", "skradziono tira", "skradziona naczepa",
            "kradzież naczepy", "ukradziono samochód ciężarowy",
            "skradziona ciężarówka", "porwanie pojazdu",
        ],
        "fr": [
            "vol de véhicule", "camion volé", "véhicule volé",
            "vol de camion", "remorque volée", "vol de remorque",
        ],
        "es": [
            "robo de vehículo", "camión robado", "vehículo robado",
            "robo de camión", "remolque robado",
        ],
        "it": [
            "furto di veicolo", "camion rubato", "veicolo rubato",
            "furto di camion", "rimorchio rubato",
        ],
        "nl": [
            "voertuig gestolen", "vrachtwagen gestolen", "voertuigdiefstal",
            "trailer gestolen", "oplegger gestolen",
        ],
        "cs": [
            "krádež vozidla", "ukradený kamion", "odcizení vozidla",
        ],
        "ro": [
            "furt de vehicul", "camion furat", "vehicul furat",
        ],
        "uk": [
            "крадіжка транспорту", "вкрадено вантажівку", "викрадення авто",
        ],
        "tr": [
            "araç hırsızlığı", "tır çalındı", "kamyon çalındı",
        ],
    },

    # ===== DAMAGE =====
    "damage": {
        "en": [
            "accident", "crash", "collision", "damaged", "road accident",
            "traffic accident", "truck accident", "pile-up", "pileup",
            "overturned", "rollover", "derailed",
        ],
        "de": [
            "unfall", "zusammenstoß", "kollision", "beschädigt",
            "verkehrsunfall", "lkw-unfall", "massenkarambolage",
            "umgekippt", "auffahrunfall", "schwerer unfall",
        ],
        "pl": [
            "wypadek", "kolizja", "zderzenie", "uszkodzony", "wypadek drogowy",
            "wypadek ciężarówki", "karambol", "przewrócony", "dachowanie",
            "wypadek na autostradzie", "wypadek tira", "zderzenie pojazdów",
        ],
        "fr": [
            "accident", "collision", "carambolage", "endommagé",
            "accident de la route", "accident de camion", "renversement",
        ],
        "es": [
            "accidente", "colisión", "choque", "dañado", "accidente de tráfico",
            "accidente de camión", "volcadura",
        ],
        "it": [
            "incidente", "collisione", "scontro", "danneggiato",
            "incidente stradale", "incidente camion", "ribaltamento",
        ],
        "nl": [
            "ongeluk", "aanrijding", "botsing", "beschadigd",
            "verkeersongeval", "vrachtwagen ongeluk", "gekanteld",
        ],
        "cs": [
            "nehoda", "kolize", "havárie", "poškozený", "dopravní nehoda",
        ],
        "ro": [
            "accident", "coliziune", "avariat", "accident rutier",
        ],
        "uk": [
            "аварія", "зіткнення", "дтп", "пошкоджений", "дорожня пригода",
        ],
        "tr": [
            "kaza", "çarpışma", "hasar", "trafik kazası", "tır kazası",
        ],
    },

    # ===== DELAY =====
    "delay": {
        "en": [
            "delay", "delayed", "congestion", "traffic jam", "queue",
            "waiting time", "border delay", "customs delay", "slow traffic",
            "standstill", "gridlock",
        ],
        "de": [
            "verzögerung", "verspätung", "stau", "verkehrsstau",
            "wartezeit", "grenzverzögerung", "zollverzögerung",
            "stillstand", "stockender verkehr",
        ],
        "pl": [
            "opóźnienie", "opóźnienia", "korek", "zator", "kolejka",
            "czas oczekiwania", "opóźnienie na granicy", "opóźnienie celne",
            "wstrzymanie ruchu", "blokada drogi", "utrudnienia",
        ],
        "fr": [
            "retard", "embouteillage", "bouchon", "congestion",
            "ralentissement", "attente à la frontière",
        ],
        "es": [
            "retraso", "atasco", "congestión", "embotellamiento",
            "demora", "cola", "retención",
        ],
        "it": [
            "ritardo", "ingorgo", "congestione", "coda",
            "rallentamento", "ritardo alla frontiera",
        ],
        "nl": [
            "vertraging", "file", "opstopping", "wachttijd",
            "grensvertraging",
        ],
        "cs": [
            "zpoždění", "zácpa", "dopravní zácpa", "čekání",
        ],
        "ro": [
            "întârziere", "ambuteiaj", "congestie", "așteptare",
        ],
        "uk": [
            "затримка", "затор", "черга", "очікування", "корок",
        ],
        "tr": [
            "gecikme", "trafik sıkışıklığı", "tıkanıklık", "bekleme",
        ],
    },

    # ===== STRIKE =====
    "strike": {
        "en": [
            "strike", "industrial action", "walkout", "protest", "blockade",
            "work stoppage", "labour dispute", "driver strike", "trucker strike",
        ],
        "de": [
            "streik", "arbeitskampf", "arbeitsniederlegung", "protest",
            "blockade", "fahrerstreik", "lkw-fahrer streik", "warnstreik",
        ],
        "pl": [
            "strajk", "protest", "blokada", "strajk kierowców",
            "akcja protestacyjna", "blokada drogi", "strajk generalny",
            "protest kierowców", "blokada granicy",
        ],
        "fr": [
            "grève", "greve", "manifestation", "blocage", "barrage routier",
            "grève des routiers", "grève des chauffeurs",
        ],
        "es": [
            "huelga", "protesta", "bloqueo", "paro", "huelga de camioneros",
            "huelga de transportistas",
        ],
        "it": [
            "sciopero", "protesta", "blocco", "sciopero dei camionisti",
            "sciopero dei trasporti",
        ],
        "nl": [
            "staking", "protest", "blokkade", "chauffeursstaking",
            "werkonderbreking",
        ],
        "cs": [
            "stávka", "protest", "blokáda", "stávka řidičů",
        ],
        "ro": [
            "grevă", "protest", "blocaj", "grevă a șoferilor",
        ],
        "uk": [
            "страйк", "протест", "блокада", "страйк водіїв",
        ],
        "tr": [
            "grev", "protesto", "barikat", "iş bırakma", "sürücü grevi",
        ],
    },

    # ===== PAYMENT_ISSUE =====
    "payment_issue": {
        "en": [
            "payment delay", "unpaid", "non-payment", "payment dispute",
            "overdue payment", "debt", "outstanding invoice", "payment default",
            "not paid", "withheld payment",
        ],
        "de": [
            "zahlungsverzug", "unbezahlt", "zahlungsausfall", "zahlungsstreit",
            "ausstehende zahlung", "schulden", "offene rechnung",
            "nicht bezahlt", "zahlungsverweigerung",
        ],
        "pl": [
            "brak zapłaty", "niezapłacone", "zaległość płatnicza",
            "spór o zapłatę", "nieterminowa płatność", "długi",
            "niezapłacona faktura", "brak płatności", "opóźnienie płatności",
            "windykacja", "wierzytelności", "nieopłacone zlecenie",
        ],
        "fr": [
            "retard de paiement", "impayé", "non-paiement", "litige de paiement",
            "dette", "facture impayée", "défaut de paiement",
        ],
        "es": [
            "impago", "deuda", "falta de pago", "morosidad",
            "factura impagada", "retraso en el pago",
        ],
        "it": [
            "mancato pagamento", "insolvenza", "debito", "ritardo di pagamento",
            "fattura non pagata",
        ],
        "nl": [
            "wanbetaling", "onbetaald", "betalingsachterstand", "schuld",
            "openstaande factuur",
        ],
        "cs": [
            "nezaplaceno", "dluh", "prodlení s platbou", "neuhrazená faktura",
        ],
        "ro": [
            "neplată", "datorie", "întârziere de plată", "factură neplătită",
        ],
        "uk": [
            "несплата", "борг", "затримка оплати", "неоплачений рахунок",
        ],
        "tr": [
            "ödeme gecikmesi", "ödenmemiş", "borç", "ödeme anlaşmazlığı",
        ],
    },

    # ===== BANKRUPTCY =====
    "bankruptcy": {
        "en": [
            "bankruptcy", "insolvent", "insolvency", "bankrupt", "filed for bankruptcy",
            "liquidation", "winding up", "administration", "receivership",
            "ceased trading", "gone bust",
        ],
        "de": [
            "insolvenz", "insolvenzverfahren", "insolvent", "konkurs",
            "pleite", "zahlungsunfähig", "insolvenzantrag",
            "liquidation", "abwicklung", "geschäftsaufgabe",
        ],
        "pl": [
            "upadłość", "bankructwo", "niewypłacalność", "upadłość firmy",
            "ogłoszenie upadłości", "syndyk", "masa upadłościowa",
            "likwidacja firmy", "likwidacja", "wniosek o upadłość",
            "postępowanie upadłościowe", "upadły", "plajta",
        ],
        "fr": [
            "faillite", "insolvabilité", "liquidation judiciaire",
            "redressement judiciaire", "cessation de paiement",
            "mise en liquidation", "dépôt de bilan",
        ],
        "es": [
            "quiebra", "insolvencia", "bancarrota", "concurso de acreedores",
            "liquidación", "suspensión de pagos",
        ],
        "it": [
            "fallimento", "insolvenza", "bancarotta", "liquidazione",
            "procedura fallimentare", "concordato preventivo",
        ],
        "nl": [
            "faillissement", "insolvent", "failliet", "liquidatie",
            "surseance van betaling",
        ],
        "cs": [
            "insolvence", "úpadek", "bankrot", "likvidace", "konkurz",
        ],
        "ro": [
            "insolvență", "faliment", "lichidare", "intrare în insolvență",
        ],
        "uk": [
            "банкрутство", "неплатоспроможність", "ліквідація", "банкрут",
        ],
        "tr": [
            "iflas", "ödeme güçlüğü", "tasfiye", "konkordato",
        ],
    },

    # ===== RESTRUCTURING =====
    "restructuring": {
        "en": [
            "restructuring", "reorganization", "turnaround", "debt restructuring",
            "corporate restructuring", "rescue plan", "recovery plan",
        ],
        "de": [
            "restrukturierung", "sanierung", "umstrukturierung",
            "rettungsplan", "sanierungsverfahren",
        ],
        "pl": [
            "restrukturyzacja", "postępowanie restrukturyzacyjne",
            "układ z wierzycielami", "sanacja", "plan restrukturyzacji",
            "postępowanie sanacyjne", "postępowanie naprawcze",
        ],
        "fr": [
            "restructuration", "redressement", "plan de sauvegarde",
            "plan de restructuration",
        ],
        "es": [
            "reestructuración", "reorganización", "plan de reestructuración",
        ],
        "it": [
            "ristrutturazione", "riorganizzazione", "piano di ristrutturazione",
        ],
        "nl": [
            "herstructurering", "reorganisatie", "herstructureringsplan",
        ],
        "cs": [
            "restrukturalizace", "reorganizace", "ozdravný plán",
        ],
        "ro": [
            "restructurare", "reorganizare", "plan de restructurare",
        ],
        "uk": [
            "реструктуризація", "реорганізація", "план санації",
        ],
        "tr": [
            "yeniden yapılandırma", "reorganizasyon",
        ],
    },

    # ===== LICENSE_REVOKED =====
    "license_revoked": {
        "en": [
            "license revoked", "licence revoked", "license suspended",
            "permit revoked", "operating license", "transport license revoked",
            "banned from operating", "license cancelled",
        ],
        "de": [
            "lizenz entzogen", "genehmigung entzogen", "betriebserlaubnis entzogen",
            "lizenz widerrufen", "fahrverbot", "berufsverbot",
            "transportgenehmigung entzogen",
        ],
        "pl": [
            "cofnięcie licencji", "odebranie licencji", "zawieszenie licencji",
            "cofnięta licencja", "utrata licencji", "zakaz wykonywania",
            "cofnięcie zezwolenia", "odebranie uprawnień",
            "wykreślenie z rejestru",
        ],
        "fr": [
            "licence révoquée", "licence retirée", "suspension de licence",
            "retrait de licence", "interdiction d'exercer",
        ],
        "es": [
            "licencia revocada", "licencia suspendida", "retirada de licencia",
        ],
        "it": [
            "licenza revocata", "licenza sospesa", "ritiro della licenza",
        ],
        "nl": [
            "vergunning ingetrokken", "licentie ingetrokken",
        ],
        "cs": [
            "odebrání licence", "zrušení licence", "pozastavení licence",
        ],
        "ro": [
            "licență revocată", "licență suspendată", "retragerea licenței",
        ],
        "uk": [
            "відкликання ліцензії", "позбавлення ліцензії",
        ],
        "tr": [
            "lisans iptali", "ruhsat iptali", "faaliyet yasağı",
        ],
    },

    # ===== ROUTE_CLOSURE =====
    "route_closure": {
        "en": [
            "road closure", "route closed", "road closed", "highway closed",
            "motorway closed", "road blocked", "bridge closed", "tunnel closed",
            "detour", "diversion", "road works", "roadwork",
        ],
        "de": [
            "straßensperrung", "strecke gesperrt", "straße gesperrt",
            "autobahn gesperrt", "umleitung", "brücke gesperrt",
            "tunnel gesperrt", "baustelle", "vollsperrung",
        ],
        "pl": [
            "zamknięcie drogi", "droga zamknięta", "zamknięta autostrada",
            "objazd", "blokada drogi", "most zamknięty", "tunel zamknięty",
            "remont drogi", "roboty drogowe", "zamknięcie trasy",
            "zakaz wjazdu", "droga nieprzejezdna",
        ],
        "fr": [
            "route fermée", "autoroute fermée", "déviation", "route barrée",
            "fermeture de route", "travaux routiers", "pont fermé",
        ],
        "es": [
            "carretera cerrada", "autopista cerrada", "desvío",
            "corte de carretera", "obras en la carretera",
        ],
        "it": [
            "strada chiusa", "autostrada chiusa", "deviazione",
            "chiusura stradale", "lavori stradali",
        ],
        "nl": [
            "weg afgesloten", "snelweg afgesloten", "omleiding",
            "wegafsluiting", "wegwerkzaamheden",
        ],
        "cs": [
            "uzavírka silnice", "silnice uzavřena", "objížďka",
        ],
        "ro": [
            "drum închis", "autostradă închisă", "deviere",
        ],
        "uk": [
            "дорога перекрита", "автострада закрита", "об'їзд",
        ],
        "tr": [
            "yol kapalı", "otoyol kapalı", "yol çalışması", "sapma",
        ],
    },
}

# ---------------------------------------------------------------------------
# Tag keywords
# ---------------------------------------------------------------------------

_TAG_KEYWORDS: dict[str, list[str]] = {
    "nocna": ["noc", "nocna", "night", "nacht", "nuit", "noche", "notte", "22:", "23:", "00:", "01:", "02:", "03:", "04:"],
    "autostrada": ["autostrada", "autobahn", "autoroute", "motorway", "highway", "snelweg", "autopista", "autostrada"],
    "parking": ["parking", "parkplatz", "aire de repos", "rastplatz", "rest area", "rest stop", "mop", "stacja benzynowa"],
    "elektronika": ["elektronika", "electronics", "elektronik", "électronique", "electrónica", "elettronica", "tv", "laptop", "telefon", "computer"],
    "paliwo": ["paliwo", "diesel", "fuel", "kraftstoff", "carburant", "combustible", "carburante", "benzyna", "tankowanie"],
    "żywność": ["żywność", "food", "lebensmittel", "nourriture", "alimentos", "cibo", "artykuły spożywcze", "mięso", "nabiał"],
    "farmaceutyki": ["farmaceutyki", "pharmaceutical", "pharma", "medikamente", "médicaments", "medicamentos", "medicinali", "leki"],
    "tekstylia": ["tekstylia", "textiles", "textilien", "textiles", "tessili", "odzież", "ubrania", "clothing"],
    "tytoń": ["tytoń", "tobacco", "tabak", "tabac", "tabaco", "tabacco", "papierosy", "cigarettes"],
    "alkohol": ["alkohol", "alcohol", "alkohol", "alcool", "alcohol", "alcol", "wódka", "piwo", "wino"],
    "metale": ["metale", "metals", "metalle", "métaux", "metales", "metalli", "miedź", "aluminium", "copper", "steel"],
    "chemia": ["chemia", "chemicals", "chemikalien", "chimiques", "químicos", "chimici", "substancje chemiczne"],
    "granica": ["granica", "border", "grenze", "frontière", "frontera", "confine", "grens", "celny", "customs", "zoll"],
    "zorganizowana": ["zorganizowana", "organized", "organisiert", "organisé", "gang", "banda", "mafia", "grupa przestępcza"],
    "recydywa": ["powtórna", "recydywa", "repeated", "wiederholte", "récidive", "serie", "kolejna"],
    "międzynarodowa": ["międzynarodowa", "international", "grenzüberschreitend", "transfrontalier", "cross-border"],
}

# ---------------------------------------------------------------------------
# Severity rules
# ---------------------------------------------------------------------------


def _determine_severity(event_type: str, text: str, financial_impact: float | None) -> str:
    """Okreslenie severity na podstawie typu eventu, tekstu i kwoty."""
    text_lower = text.lower() if text else ""

    # CRITICAL: kradziez pojazdu/cargo > 50k EUR
    if event_type in ("theft_cargo", "theft_vehicle"):
        if financial_impact and financial_impact > 50000:
            return Severity.CRITICAL
    # CRITICAL: duza upadlosc
    if event_type == "bankruptcy":
        if financial_impact and financial_impact > 1000000:
            return Severity.CRITICAL

    # HIGH
    if event_type == "theft_cargo":
        return Severity.HIGH
    if event_type == "theft_vehicle":
        return Severity.HIGH
    if event_type == "bankruptcy":
        return Severity.HIGH
    if event_type == "license_revoked":
        return Severity.HIGH

    # MEDIUM/HIGH for strike depending on scale
    if event_type == "strike":
        scale_words = ["general", "nationwide", "generalny", "ogólnokrajowy", "generalstreik",
                       "national", "blockade", "blokada", "grenzblockade"]
        if any(w in text_lower for w in scale_words):
            return Severity.HIGH
        return Severity.MEDIUM

    # MEDIUM
    if event_type == "theft_fuel":
        return Severity.MEDIUM
    if event_type == "damage":
        return Severity.MEDIUM
    if event_type == "payment_issue":
        return Severity.MEDIUM
    if event_type == "restructuring":
        return Severity.MEDIUM
    if event_type == "route_closure":
        return Severity.MEDIUM

    # LOW
    if event_type == "delay":
        return Severity.LOW

    return Severity.INFO


# ---------------------------------------------------------------------------
# EventClassifier
# ---------------------------------------------------------------------------


class EventClassifier:
    """Klasyfikator zdarzen oparty na keyword matching per jezyk."""

    def __init__(self):
        self._keywords = KEYWORDS
        self._tag_keywords = _TAG_KEYWORDS

    def classify(self, event: dict) -> dict:
        """Klasyfikuje event na podstawie tekstu (title + description).

        Dodaje: event_type, severity, tags.
        Zwraca event z dodanymi polami.
        """
        result = event.copy()

        title = event.get("title", "")
        description = event.get("description", "")
        raw_text = event.get("raw_text", "")
        language = event.get("language", "en")
        financial_impact = event.get("financial_impact_eur")

        full_text = f"{title} {description} {raw_text}"
        text_lower = full_text.lower()

        # Klasyfikacja event_type
        event_type = self._classify_type(text_lower, language)
        result["event_type"] = event_type

        # Severity
        result["severity"] = _determine_severity(event_type, full_text, financial_impact)

        # Tags
        result["tags"] = self._extract_tags(text_lower)

        return result

    def _classify_type(self, text_lower: str, language: str) -> str:
        """Dopasowuje event_type na podstawie keyword matching.

        Sprawdza najpierw keywords w jezyku zrodlowym, potem w angielskim (fallback).
        Zwraca event_type z najwyzszym score (liczbą dopasowanych keywords).
        """
        scores: dict[str, int] = {}

        for etype, lang_keywords in self._keywords.items():
            score = 0
            # Jezyk zrodlowy
            keywords_list = lang_keywords.get(language, [])
            for kw in keywords_list:
                if kw.lower() in text_lower:
                    score += 2  # wyzszy priorytet dla jezyka zrodlowego

            # Angielski jako fallback
            if language != "en":
                en_keywords = lang_keywords.get("en", [])
                for kw in en_keywords:
                    if kw.lower() in text_lower:
                        score += 1

            if score > 0:
                scores[etype] = score

        if scores:
            best_type = max(scores, key=scores.get)
            return best_type

        return EventType.OTHER

    def _extract_tags(self, text_lower: str) -> list[str]:
        """Wyciaga tagi na podstawie keywords w tekscie."""
        tags = []
        for tag, keywords in self._tag_keywords.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    tags.append(tag)
                    break
        return tags

    def _get_keywords(self) -> dict:
        """Zwraca slownik keywords per event_type per jezyk."""
        return self._keywords
