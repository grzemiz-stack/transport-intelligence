"""Shared transport keyword matching — dual-list filtering.

An article must contain BOTH a vehicle/infrastructure keyword AND an event keyword
to be considered transport-related. This eliminates false positives like
"bicycle theft" or "shoplifting" that matched on broad keywords like "theft" alone.

Usage:
    from src.agents.transport_keywords import is_transport_related
    if is_transport_related(text, "de"):
        ...
"""

# ── VEHICLE / INFRASTRUCTURE keywords (must match at least one) ──────────
# These identify that the article is about road freight / trucking.

VEHICLE_KEYWORDS: dict[str, list[str]] = {
    "de": [
        "lkw", "lastwagen", "lastkraftwagen", "sattelzug", "auflieger",
        "transporter", "lkw-fahrer", "fernfahrer", "spedition", "speditions",
        "autobahn", "rastplatz", "raststätte", "raststaette", "tankstelle",
        "güterverkehr", "gueterverkehr", "schwertransport",
        "logistik", "frachtführer", "nutzfahrzeug",
    ],
    "pl": [
        "tir", "ciężarówka", "ciezarowka", "ciężarówki", "naczepa", "naczepy",
        "ciągnik siodłowy", "ciagnik siodlowy", "kierowca", "kierowcy",
        "spedycja", "spedycji", "autostrada", "autostrady",
        "parking tir", "stacja paliw", "transport drogowy",
        "pojazd ciężarowy", "samochód ciężarowy", "samochod ciezarowy",
        "logistyka", "przewoźnik", "przewoznik", "fracht",
    ],
    "en": [
        "truck", "trucks", "lorry", "lorries", "hgv", "heavy goods vehicle",
        "trailer", "semi-trailer", "articulated", "freight", "cargo",
        "trucker", "haulier", "haulage", "motorway", "highway",
        "rest area", "truck stop", "lay-by", "service station",
        "logistics", "distribution", "consignment",
    ],
    "fr": [
        "camion", "camions", "poids lourd", "poids lourds",
        "remorque", "semi-remorque", "tracteur routier",
        "chauffeur routier", "chauffeurs routiers", "routier", "routiers",
        "autoroute", "autoroutes", "aire de repos", "aire de service",
        "fret", "transporteur", "logistique",
    ],
    "nl": [
        "vrachtwagen", "vrachtwagens", "vrachtauto", "oplegger", "trailer",
        "aanhanger", "chauffeur", "truckchauffeur", "snelweg", "autosnelweg",
        "tankstation", "verzorgingsplaats", "vrachtvervoer",
        "logistiek", "distributie", "transporteur",
    ],
    "it": [
        "camion", "autotreno", "autoarticolato", "tir",
        "rimorchio", "semirimorchio", "autista", "camionista",
        "autotrasporto", "autotrasportatore", "autostrada", "autostrade",
        "area di sosta", "area di servizio", "parcheggio",
        "logistica", "spedizione", "trasportatore",
    ],
    "es": [
        "camión", "camion", "camiones", "tráiler", "trailer",
        "remolque", "semirremolque", "conductor", "camionero",
        "autopista", "autovía", "autovia",
        "área de descanso", "área de servicio", "aparcamiento",
        "logística", "logistica", "transportista",
    ],
    "ro": [
        "camion", "camioane", "autocamion", "tir",
        "remorcă", "remorca", "semiremorcă", "șofer", "sofer",
        "autostradă", "autostrada", "conducător auto",
        "logistică", "logistica", "transportator",
        "parcare", "zonă de odihnă",
    ],
    "cs": [
        "kamion", "kamiony", "nákladní", "tir", "tahač", "tahac",
        "návěs", "naves", "přívěs", "řidič", "ridic", "kamioňák",
        "dálnice", "dalnice", "dálniční",
        "logistika", "spedice", "přeprava", "dopravní",
        "parkoviště", "parkoviste", "odpočívadlo",
    ],
    "hu": [
        "kamion", "kamionok", "teherautó", "teherauto",
        "pótkocsi", "félpótkocsi", "sofőr", "sofor", "gépkocsivezető",
        "autópálya", "autopalya", "autóút",
        "logisztika", "szállítmányozás", "fuvarozás",
        "parkoló", "pihenőhely",
    ],
    "sv": [
        "lastbil", "lastbilar", "trailer", "släp", "släpvagn",
        "förare", "chaufför", "motorväg", "motorvag",
        "rastplats", "truckstop", "logistik", "transport",
        "godstransport", "åkeri", "akeri",
    ],
    "da": [
        "lastbil", "lastbiler", "trailer", "sættevogn", "saettevogn",
        "chauffør", "chauffor", "motorvej", "motorvejen",
        "rasteplads", "logistik", "transport", "godstransport",
        "fragtmand", "vognmand",
    ],
    "no": [
        "lastebil", "lastebiler", "vogntog", "tilhenger", "semitrailer",
        "sjåfør", "sjafor", "transportør", "motorvei", "motorveien",
        "rasteplass", "logistikk", "godstransport",
        "frakt", "gods", "speditør",
    ],
    "fi": [
        "rekka", "kuorma-auto", "perävaunu", "puoliperävaunu",
        "kuljettaja", "rekkakuski", "moottoritie",
        "levähdysalue", "logistiikka", "kuljetus",
        "rahti", "tavaraliikenne",
    ],
    "hr": [
        "kamion", "kamioni", "teretno vozilo", "prikolica", "poluprikolica",
        "vozač", "vozac", "prijevoznik", "autocesta", "autoceste",
        "parkiralište", "odmorište", "logistika",
        "prijevoz", "transport", "teret",
    ],
    "sl": [
        "tovornjak", "tovornjaki", "prikolica", "polprikolica",
        "voznik", "šofer", "avtocesta", "avtoceste",
        "počivališče", "logistika", "prevoz", "transport",
        "tovor", "tovorno vozilo",
    ],
    "sr": [
        "камион", "камиони", "kamion", "kamioni",
        "приколица", "полуприколица", "prikolica",
        "возач", "возачи", "vozač", "vozac",
        "аутопут", "autoput", "магистрала", "magistrala",
        "логистика", "logistika", "транспорт", "transport",
        "терет", "teret",
    ],
    "bg": [
        "камион", "камиони", "тир", "ремарке", "полуремарке",
        "шофьор", "шофьори", "автомагистрала", "магистрала",
        "паркинг", "логистика", "транспорт",
        "товарен автомобил", "превозвач",
    ],
    "el": [
        "φορτηγό", "φορτηγά", "ρυμουλκούμενο", "νταλίκα",
        "οδηγός", "οδηγοί", "αυτοκινητόδρομος", "εθνική οδός",
        "στάθμευση", "logistics", "μεταφορέας",
        "μεταφορά", "μεταφορές", "φορτίο",
    ],
    "tr": [
        "kamyon", "kamyonlar", "tır", "tir", "dorse", "yarı römork",
        "şoför", "sofor", "sürücü", "otoyol", "otoban",
        "nakliye", "nakliyeci", "taşımacılık", "tasima",
        "lojistik", "tır parkı", "dinlenme tesisi",
    ],
    "uk": [
        "вантажівка", "вантажівки", "фура", "тягач",
        "причіп", "напівпричіп", "водій", "водії",
        "автострада", "автомагістраль", "траса",
        "парковка", "зона відпочинку", "логістика",
        "перевізник", "транспорт", "вантажоперевезення",
    ],
    "lt": [
        "sunkvežimis", "sunkvezimis", "sunkvežimiai", "vilkikas",
        "priekaba", "puspriekabė", "vairuotojas", "vairuotojai",
        "automagistralė", "automagistrale", "greitkelis",
        "logistika", "transportas", "krovinys",
    ],
    "lv": [
        "kravas auto", "kravas automobilis", "vilcējs", "piekabe",
        "šoferis", "soferis", "autoceļš", "autocels", "automaģistrāle",
        "loģistika", "logistika", "transports",
        "krava", "kravas pārvadājumi",
    ],
    "et": [
        "veok", "veoauto", "veoautod", "haagis", "poolhaagis",
        "juht", "autojuht", "maantee", "kiirtee",
        "logistika", "transport", "vedu", "kaubavedu",
    ],
    "sk": [
        "kamión", "kamion", "kamióny", "ťahač", "tahac",
        "náves", "príves", "vodič", "vodic", "šofér", "sofer",
        "diaľnica", "dialnica", "diaľničný",
        "logistika", "špeditér", "preprava", "doprava",
        "parkovisko", "odpočívadlo",
    ],
}

# ── EVENT keywords (must match at least one) ─────────────────────────────
# These identify what happened — theft, accident, smuggling, etc.

EVENT_KEYWORDS: dict[str, list[str]] = {
    "de": [
        "diebstahl", "gestohlen", "entwendet", "geraubt", "raub",
        "aufgebrochen", "plane aufgeschlitzt", "aufgeschlitzt",
        "diesel", "kraftstoff", "unfall", "unfälle",
        "ladung", "fracht", "schmuggel", "geschmuggelt", "sichergestellt",
        "insolvenz", "beschädigt", "beschaedigt", "überfall", "ueberfall",
        "beraubt", "einbruch", "brand",
    ],
    "pl": [
        "kradzież", "kradziez", "kradziezy", "skradziono", "ukradziono",
        "rozbój", "rozboj", "włamanie", "wlamanie", "napad",
        "plandeka", "paliwo", "diesel", "olej napędowy",
        "wypadek", "ładunek", "ladunek", "przemyt", "przemytu",
        "upadłość", "upadlosc", "uszkodzenie", "zniszczenie",
        "wandalizm", "pożar", "pozar",
    ],
    "en": [
        "theft", "thefts", "stolen", "stealing", "robbery", "robbed",
        "break-in", "broke into", "curtain slash", "slashed",
        "fuel", "diesel", "petrol", "accident", "crash",
        "cargo", "consignment", "smuggling", "smuggled", "seized",
        "bankruptcy", "damage", "damaged", "hijack", "hijacking",
        "vandalism", "arson",
    ],
    "fr": [
        "vol", "vols", "volé", "vole", "volée", "braquage",
        "effraction", "cambriolage",
        "bâche", "bache", "découpée", "decoupee",
        "carburant", "gasoil", "gazole", "accident",
        "fret", "marchandise", "contrebande", "saisie", "saisi",
        "faillite", "dégâts", "degats", "vandalisme", "incendie",
    ],
    "nl": [
        "diefstal", "gestolen", "ontvreemd", "overval", "beroving",
        "inbraak", "opengebroken",
        "brandstof", "diesel",
        "ongeluk", "ongeval", "lading", "smokkel", "gesmokkeld",
        "faillissement", "schade", "beschadigd", "vandalisme", "brand",
    ],
    "it": [
        "furto", "furti", "rubato", "rubata", "rapina", "assalto",
        "aggressione", "scasso",
        "carburante", "gasolio", "diesel",
        "incidente", "carico", "merce", "contrabbando", "sequestro",
        "fallimento", "danno", "danneggiato", "vandalismo", "incendio",
    ],
    "es": [
        "robo", "robos", "robado", "robada", "hurto", "atraco",
        "asalto", "agresión",
        "carburante", "combustible", "gasoil", "diésel", "diesel",
        "accidente", "carga", "mercancía", "mercancia",
        "contrabando", "incautación", "incautacion",
        "quiebra", "daño", "dano", "vandalismo", "incendio",
    ],
    "ro": [
        "furt", "furturi", "furat", "sustras", "jaf", "tâlhărie", "talharire",
        "agresiune", "spart",
        "carburant", "combustibil", "motorină", "motorina", "diesel",
        "accident", "marfă", "marfa", "contrabandă", "contrabanda",
        "faliment", "daune", "vandalism", "incendiu",
    ],
    "cs": [
        "krádež", "kradez", "krádeže", "odcizení", "odcizeni",
        "loupež", "loupez", "přepadení", "prepadeni", "vloupání",
        "nafta", "pohonné hmoty", "diesel",
        "nehoda", "náklad", "naklad", "pašování", "pasovani",
        "insolvence", "poškození", "poskozeni", "vandalismus", "požár",
    ],
    "hu": [
        "lopás", "lopas", "ellopták", "elloptak", "eltulajdonítás",
        "rablás", "rablas", "támadás", "tamadas", "betörés", "betores",
        "üzemanyag", "gázolaj", "dízel",
        "baleset", "szállítmány", "csempészet", "csempesz",
        "csőd", "kár", "rongálás", "vandalizmus", "tűz",
    ],
    "sv": [
        "stöld", "stold", "stulen", "stulet", "rån", "ran",
        "inbrott", "uppbruten",
        "bränsle", "bransle", "diesel",
        "olycka", "gods", "last", "smuggling", "smugglat", "beslag",
        "konkurs", "skada", "skadad", "vandalism", "brand",
    ],
    "da": [
        "tyveri", "tyverier", "stjålet", "stjaalet", "røveri", "roveri",
        "indbrud",
        "brændstof", "braendstof", "diesel",
        "ulykke", "gods", "last", "smugling", "smuglet", "beslaglagt",
        "konkurs", "skade", "beskadiget", "hærværk", "haervaerk", "brand",
    ],
    "no": [
        "tyveri", "tyverier", "stjålet", "stjaalet", "ran", "overfall",
        "innbrudd",
        "drivstoff", "diesel",
        "ulykke", "gods", "last", "smugling", "smuglet", "beslag",
        "konkurs", "skade", "skadet", "hærverk", "haerverk", "brann",
    ],
    "fi": [
        "varkaus", "varkaudet", "varastettu", "ryöstö", "ryosto",
        "murto",
        "polttoaine", "diesel",
        "onnettomuus", "rahti", "salakuljetus", "takavarikoitu",
        "konkurssi", "vahinko", "vaurioitunut", "ilkivalta", "tulipalo",
    ],
    "hr": [
        "krađa", "kradja", "krađe", "ukraden", "ukrađen",
        "razbojništvo", "razbojnistvo", "pljačka", "provalna",
        "gorivo", "dizel", "nafta",
        "nesreća", "teret", "roba", "krijumčarenje", "krijumcarenje",
        "stečaj", "šteta", "steta", "vandalizam", "požar",
    ],
    "sl": [
        "kraja", "ukraden", "rop", "napad", "vlom",
        "gorivo", "dizel",
        "nesreča", "tovor", "blago", "tihotapljenje", "zasežen",
        "stečaj", "škoda", "vandalizem", "požar",
    ],
    "sr": [
        "крађа", "крађе", "украден", "krađa", "kradja", "ukraden",
        "разбојништво", "razbojnistvo", "пљачка", "pljačka",
        "гориво", "gorivo", "дизел", "dizel",
        "несрећа", "nesreća", "терет", "teret", "кријумчарење", "krijumčarenje",
        "стечај", "stečaj", "штета", "šteta", "вандализам", "vandalizam",
    ],
    "bg": [
        "кражба", "кражби", "откраднат", "грабеж", "нападение",
        "взлом",
        "гориво", "дизел",
        "катастрофа", "инцидент", "товар", "контрабанда", "иззет",
        "фалит", "щета", "вандализъм", "пожар",
    ],
    "el": [
        "κλοπή", "κλοπές", "κλεμμένο", "ληστεία", "επίθεση",
        "διάρρηξη",
        "καύσιμα", "ντίζελ",
        "ατύχημα", "φορτίο", "εμπόρευμα", "λαθρεμπόριο", "κατάσχεση",
        "πτώχευση", "ζημιά", "βανδαλισμός", "εμπρησμός",
    ],
    "tr": [
        "hırsızlık", "hirsizlik", "çalıntı", "calinti", "soygun",
        "gasp", "baskın", "baskin",
        "yakıt", "yakit", "akaryakıt", "mazot",
        "kaza", "kargo", "yük", "kaçakçılık", "kacakcilik", "el konuldu",
        "iflas", "hasar", "vandalizm", "yangın", "yangin",
    ],
    "uk": [
        "крадіжка", "крадіжки", "викрадення", "вкрадено",
        "пограбування", "розбій", "напад", "зламано",
        "паливо", "дизель", "дизпаливо",
        "аварія", "ДТП", "вантаж", "товар", "контрабанда",
        "банкрутство", "пошкодження", "вандалізм", "пожежа",
    ],
    "lt": [
        "vagystė", "vagyste", "vagystės", "pavogtas", "apiplėšimas",
        "įsilaužimas",
        "kuras", "dyzelinas",
        "avarija", "krovinys", "kontrabanda", "konfiskuotas",
        "bankrotas", "žala", "vandalizmas", "gaisras",
    ],
    "lv": [
        "zādzība", "zadziba", "nozagts", "laupīšana", "laupišana",
        "ielaušanās", "ielausanas",
        "degviela", "dīzeļdegviela", "dizel",
        "avārija", "avarija", "krava", "kontrabanda", "konfiscēts",
        "bankrots", "bojājums", "vandālisms", "ugunsgrēks",
    ],
    "et": [
        "vargus", "varastatud", "rööv", "roov", "sissemurdmine",
        "kütus", "kutus", "diisel",
        "õnnetus", "onnetus", "kaup", "salakaubavedu", "konfiskeeritud",
        "pankrot", "kahju", "vandalism", "tulekahju",
    ],
    "sk": [
        "krádež", "kradez", "krádeže", "odcudzenie", "lúpež", "lupez",
        "prepadnutie", "vlámania", "vlamania",
        "nafta", "pohonné hmoty", "diesel",
        "nehoda", "náklad", "naklad", "pašovanie", "pasovanie",
        "insolvencia", "poškodenie", "poskodenie", "vandalizmus", "požiar",
    ],
}


def has_event_keyword(text: str, language: str) -> bool:
    """Check if text contains any event keyword (without vehicle requirement).

    Useful for trusted transport channels where the channel topic itself
    establishes the vehicle/infrastructure context.
    """
    text_lower = text.lower()
    for lang_code in (language, "en"):
        keywords = EVENT_KEYWORDS.get(lang_code, [])
        if any(kw in text_lower for kw in keywords):
            return True
    return False


def is_transport_related(text: str, language: str) -> bool:
    """Check if text is transport-related using dual-list matching.

    Returns True only if text contains BOTH:
    - at least one vehicle/infrastructure keyword (truck, motorway, etc.)
    - at least one event keyword (theft, accident, smuggling, etc.)

    This eliminates false positives like "bicycle theft" or "shop robbery".
    """
    text_lower = text.lower()

    vehicle_kw = VEHICLE_KEYWORDS.get(language, VEHICLE_KEYWORDS.get("en", []))
    event_kw = EVENT_KEYWORDS.get(language, EVENT_KEYWORDS.get("en", []))

    has_vehicle = any(kw in text_lower for kw in vehicle_kw)
    has_event = any(kw in text_lower for kw in event_kw)

    return has_vehicle and has_event
