"""Generowanie disclaimerow prawnych per kraj i jezyk.

Disclaimer zawiera:
- 'Raport oparty wylacznie na publicznie dostepnych zrodlach informacji'
- 'Nie stanowi oskarzenia wobec jakiejkolwiek osoby lub podmiotu'
- 'Dane prezentowane w celach analitycznych i informacyjnych'
- 'Nazwy firm wymienione wylacznie na podstawie oficjalnych zrodel'
- 'Sekcja Sygnaly rynkowe zawiera informacje z nieoficjalnych zrodel
   o nizszym stopniu weryfikacji'
- 'Odbiorca ponosi odpowiedzialnosc za sposob wykorzystania danych'

Disclaimery dostepne w jezykach: EN, DE, PL, FR (minimum).
"""

from datetime import datetime

DISCLAIMERS: dict[str, str] = {
    "en": (
        "LEGAL DISCLAIMER\n\n"
        "This report is based exclusively on publicly available information sources "
        "including official police communications, court registries, public business "
        "registries, news publications, and publicly accessible online forums.\n\n"
        "This report does not constitute an accusation against any person or entity. "
        "Company names are included only when sourced from official public records "
        "(police statements, court filings, business registries).\n\n"
        "The \"Market Signals\" section contains information from unofficial sources "
        "with lower verification levels. These signals are presented for informational "
        "purposes only and should not be treated as confirmed facts.\n\n"
        "Data is presented for analytical and informational purposes. The recipient "
        "bears full responsibility for how this data is used in their business decisions.\n\n"
        "This report does not constitute legal, financial, or insurance advice. "
        "Recipients are advised to conduct their own due diligence before making "
        "business decisions based on this report.\n\n"
        "All personal data has been removed in compliance with GDPR "
        "(EU Regulation 2016/679). Processing records are maintained as required "
        "by Article 30.\n\n"
        "\u00a9 {year} Transport Intelligence. All rights reserved."
    ),
    "de": (
        "RECHTLICHER HINWEIS\n\n"
        "Dieser Bericht basiert ausschliesslich auf oeffentlich zugaenglichen "
        "Informationsquellen, einschliesslich offizieller Polizeimeldungen, "
        "Gerichtsregister, oeffentlicher Handelsregister, Nachrichtenpublikationen "
        "und oeffentlich zugaenglicher Online-Foren.\n\n"
        "Dieser Bericht stellt keine Anschuldigung gegen eine Person oder ein "
        "Unternehmen dar. Firmennamen werden nur dann genannt, wenn sie aus "
        "offiziellen oeffentlichen Aufzeichnungen stammen (Polizeimeldungen, "
        "Gerichtsakten, Handelsregister).\n\n"
        "Der Abschnitt \"Marktsignale\" enthaelt Informationen aus inoffiziellen "
        "Quellen mit einem geringeren Verifizierungsgrad. Diese Signale werden "
        "ausschliesslich zu Informationszwecken praesentiert und sollten nicht "
        "als bestaetigte Fakten behandelt werden.\n\n"
        "Die Daten werden zu analytischen und informativen Zwecken praesentiert. "
        "Der Empfaenger traegt die volle Verantwortung fuer die Verwendung "
        "dieser Daten bei Geschaeftsentscheidungen.\n\n"
        "Dieser Bericht stellt keine Rechts-, Finanz- oder Versicherungsberatung dar. "
        "Den Empfaengern wird empfohlen, eigene Sorgfaltspruefungen durchzufuehren, "
        "bevor sie Geschaeftsentscheidungen auf der Grundlage dieses Berichts treffen.\n\n"
        "Alle personenbezogenen Daten wurden gemaess DSGVO "
        "(EU-Verordnung 2016/679) entfernt. Verarbeitungsaufzeichnungen werden "
        "gemaess Artikel 30 gefuehrt.\n\n"
        "\u00a9 {year} Transport Intelligence. Alle Rechte vorbehalten."
    ),
    "pl": (
        "ZASTRZEZENIE PRAWNE\n\n"
        "Niniejszy raport opiera sie wylacznie na publicznie dostepnych zrodlach "
        "informacji, w tym oficjalnych komunikatach policji, rejestrach sadowych, "
        "publicznych rejestrach gospodarczych, publikacjach prasowych oraz publicznie "
        "dostepnych forach internetowych.\n\n"
        "Niniejszy raport nie stanowi oskarzenia wobec jakiejkolwiek osoby lub podmiotu. "
        "Nazwy firm sa zamieszczane wylacznie wtedy, gdy pochodza z oficjalnych "
        "dokumentow publicznych (komunikaty policji, akta sadowe, rejestry gospodarcze).\n\n"
        "Sekcja \"Sygnaly rynkowe\" zawiera informacje z nieoficjalnych zrodel o nizszym "
        "stopniu weryfikacji. Sygnaly te sa przedstawiane wylacznie w celach "
        "informacyjnych i nie powinny byc traktowane jako potwierdzone fakty.\n\n"
        "Dane sa prezentowane w celach analitycznych i informacyjnych. Odbiorca ponosi "
        "pelna odpowiedzialnosc za sposob wykorzystania tych danych w swoich "
        "decyzjach biznesowych.\n\n"
        "Niniejszy raport nie stanowi porady prawnej, finansowej ani ubezpieczeniowej. "
        "Odbiorcom zaleca sie przeprowadzenie wlasnej analizy due diligence przed "
        "podjemowaniem decyzji biznesowych na podstawie niniejszego raportu.\n\n"
        "Wszystkie dane osobowe zostaly usuniete zgodnie z RODO "
        "(Rozporzadzenie UE 2016/679). Rejestry przetwarzania sa prowadzone "
        "zgodnie z wymogami Artykulu 30.\n\n"
        "\u00a9 {year} Transport Intelligence. Wszelkie prawa zastrzezone."
    ),
    "fr": (
        "AVERTISSEMENT JURIDIQUE\n\n"
        "Ce rapport est base exclusivement sur des sources d'information accessibles "
        "au public, y compris les communications officielles de la police, les registres "
        "judiciaires, les registres commerciaux publics, les publications de presse et "
        "les forums en ligne accessibles au public.\n\n"
        "Ce rapport ne constitue pas une accusation contre une personne ou une entite. "
        "Les noms d'entreprises ne sont inclus que lorsqu'ils proviennent de documents "
        "publics officiels (declarations de police, dossiers judiciaires, registres "
        "commerciaux).\n\n"
        "La section \"Signaux du marche\" contient des informations provenant de sources "
        "non officielles avec des niveaux de verification inferieurs. Ces signaux sont "
        "presentes a titre informatif uniquement et ne doivent pas etre consideres "
        "comme des faits confirmes.\n\n"
        "Les donnees sont presentees a des fins analytiques et informatives. Le "
        "destinataire assume l'entiere responsabilite de l'utilisation de ces donnees "
        "dans ses decisions commerciales.\n\n"
        "Ce rapport ne constitue pas un conseil juridique, financier ou d'assurance. "
        "Il est conseille aux destinataires de mener leur propre diligence raisonnable "
        "avant de prendre des decisions commerciales basees sur ce rapport.\n\n"
        "Toutes les donnees personnelles ont ete supprimees conformement au RGPD "
        "(Reglement UE 2016/679). Les registres de traitement sont tenus conformement "
        "a l'article 30.\n\n"
        "\u00a9 {year} Transport Intelligence. Tous droits reserves."
    ),
}

# ---------------------------------------------------------------------------
# Per-country legal references
# ---------------------------------------------------------------------------

_COUNTRY_CLAUSES: dict[str, dict[str, str]] = {
    "DE": {
        "en": (
            "For Germany: This report complies with the Federal Data Protection Act "
            "(Bundesdatenschutzgesetz \u2014 BDSG) and the German implementation of GDPR. "
            "Company data sourced from the Handelsregister is public by law "
            "(HGB \u00a78 et seq.)."
        ),
        "de": (
            "Fuer Deutschland: Dieser Bericht entspricht dem Bundesdatenschutzgesetz "
            "(BDSG) und der deutschen Umsetzung der DSGVO. Unternehmensdaten aus dem "
            "Handelsregister sind gesetzlich oeffentlich (HGB \u00a78 ff.)."
        ),
    },
    "PL": {
        "en": (
            "For Poland: This report complies with the Act on the Protection of Personal Data "
            "as supervised by UODO (Urzad Ochrony Danych Osobowych). Company data sourced "
            "from KRS (Krajowy Rejestr Sadowy) is public by law."
        ),
        "pl": (
            "Dla Polski: Niniejszy raport jest zgodny z Ustawa o Ochronie Danych Osobowych "
            "nadzorowana przez UODO (Urzad Ochrony Danych Osobowych). Dane firm pochodzace "
            "z KRS (Krajowy Rejestr Sadowy) sa publicznie dostepne na mocy prawa."
        ),
    },
    "GB": {
        "en": (
            "For the United Kingdom: This report complies with the UK GDPR and the "
            "Data Protection Act 2018. Company data sourced from Companies House is "
            "public by law."
        ),
    },
    "FR": {
        "en": (
            "For France: This report complies with the provisions of the CNIL "
            "(Commission Nationale de l'Informatique et des Libertes) and the "
            "Loi Informatique et Libertes. Company data sourced from the Registre "
            "du Commerce et des Societes (RCS) is public by law."
        ),
        "fr": (
            "Pour la France : Ce rapport est conforme aux dispositions de la CNIL "
            "(Commission Nationale de l'Informatique et des Libertes) et de la "
            "Loi Informatique et Libertes. Les donnees d'entreprises provenant du "
            "Registre du Commerce et des Societes (RCS) sont publiques par la loi."
        ),
    },
    "NL": {
        "en": (
            "For the Netherlands: This report complies with the Uitvoeringswet AVG "
            "(UAVG). Company data sourced from the Kamer van Koophandel (KvK) is "
            "public by law."
        ),
    },
    "IT": {
        "en": (
            "For Italy: This report complies with the Italian Data Protection Code "
            "(Codice in materia di protezione dei dati personali, D.Lgs. 196/2003). "
            "Company data from the Registro delle Imprese is public by law."
        ),
    },
    "ES": {
        "en": (
            "For Spain: This report complies with the Ley Organica de Proteccion de "
            "Datos Personales y Garantia de los Derechos Digitales (LOPDGDD). "
            "Company data from the Registro Mercantil is public by law."
        ),
    },
    "CZ": {
        "en": (
            "For Czech Republic: This report complies with Act No. 110/2019 Coll. on "
            "Personal Data Processing. Company data from the Obchodni rejstrik is "
            "public by law."
        ),
    },
    "AT": {
        "en": (
            "For Austria: This report complies with the Austrian Data Protection Act "
            "(Datenschutzgesetz \u2014 DSG). Company data from the Firmenbuch is "
            "public by law."
        ),
    },
    "HU": {
        "en": (
            "For Hungary: This report complies with Act CXII of 2011 on Informational "
            "Self-Determination and Freedom of Information. Company data from the "
            "Cegjegyzek is public by law."
        ),
    },
    "RO": {
        "en": (
            "For Romania: This report complies with Law No. 190/2018 implementing GDPR. "
            "Company data from the Registrul Comertului is public by law."
        ),
    },
}


class DisclaimerGenerator:
    """Generator disclaimerow prawnych dla raportow."""

    def generate_disclaimer(
        self, report_type: str, countries: list[str], language: str = "en",
    ) -> str:
        """Generuje pelny disclaimer prawny dla raportu.

        Args:
            report_type: typ raportu (biweekly/monthly/alert)
            countries: lista kodow krajow objetych raportem
            language: kod jezyka (en/de/pl/fr)
        """
        year = datetime.utcnow().year
        base = DISCLAIMERS.get(language, DISCLAIMERS["en"]).format(year=year)

        # Header with report metadata
        countries_str = ", ".join(countries) if countries else "All monitored"
        type_labels = {
            "biweekly": "Bi-Weekly Report",
            "monthly": "Monthly Report",
            "alert": "Alert Report",
            "sales": "Sales Intelligence Report",
            "due_diligence": "Due Diligence Investigation Report",
        }
        header = f"Report type: {type_labels.get(report_type, report_type)} | Countries: {countries_str}\n\n"

        # Append per-country clauses
        country_clauses: list[str] = []
        for cc in countries:
            clause = self._get_country_clause(cc.upper(), language)
            if clause:
                country_clauses.append(clause)

        result = header + base
        if country_clauses:
            result += "\n\n" + "\n\n".join(country_clauses)

        return result

    def generate_disclaimer_per_country(
        self, country_code: str, language: str = "en",
    ) -> str:
        """Generuje disclaimer uwzgledniajacy lokalne prawo danego kraju.

        Rozszerza bazowy disclaimer o specyficzne regulacje prawne kraju.
        """
        year = datetime.utcnow().year
        base = DISCLAIMERS.get(language, DISCLAIMERS["en"]).format(year=year)

        country_clause = self._get_country_clause(country_code.upper(), language)
        if country_clause:
            return base + "\n\n" + country_clause
        return base

    def _get_country_clause(self, country_code: str, language: str) -> str | None:
        """Zwraca klauzule prawna specyficzna dla kraju."""
        clauses = _COUNTRY_CLAUSES.get(country_code)
        if not clauses:
            return None
        # Try requested language, fall back to English
        return clauses.get(language) or clauses.get("en")
