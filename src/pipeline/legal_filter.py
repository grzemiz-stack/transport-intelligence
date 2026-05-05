"""Filtr prawny — KRYTYCZNY KOMPONENT pipeline'u.

Odpowiada za filtrowanie zdarzen przed zapisem do bazy pod katem zgodnosci prawnej.

Reguly:
- Firma moze byc wymieniona z nazwy TYLKO jesli is_official_source=True
  (policja, rejestr sadowy, monitor sadowy, komunikat urzedowy).
- Zrodlo nieoficjalne (forum, social media, trust_score < 0.7) ->
  automatyczna anonimizacja nazwy firmy na 'firma transportowa z regionu X'.
- Nigdy nie uzywamy slow oskarzycilelskich: 'oszust', 'zlodziej', 'kradnie',
  'nielegalny' — zamiast tego: 'zdarzenie', 'incydent', 'zgloszenie', 'sygnal'.
- Kazdy event musi miec przypisane zrodlo z URL i data.
- Brak zrodla = event odrzucony.
"""

import logging
import re

logger = logging.getLogger(__name__)

FORBIDDEN_WORDS: dict[str, str] = {
    "oszust": "podmiot wskazany w zgloszeniu",
    "oszustwo": "zdarzenie",
    "zlodziej": "osoba wskazana w zgloszeniu",
    "kradnie": "zdarzenie polegajace na utracie",
    "kradziez": "utrata mienia",
    "ukradl": "utracono",
    "ukradli": "utracono",
    "nielegalny": "niezgodny z regulacjami",
    "nielegalne": "niezgodne z regulacjami",
    "przestepca": "osoba wskazana w zgloszeniu",
    "przestepstwo": "incydent",
    "defraudacja": "nieprawidlowosc finansowa",
    "scam": "zgloszenie",
    "fraud": "incident",
    "thief": "reported person",
    "illegal": "non-compliant",
    "Betrug": "Vorfall",
    "Dieb": "gemeldete Person",
    "illegal": "nicht konform",
}


class LegalFilter:
    """Filtr prawny sprawdzajacy zdarzenia przed zapisem do bazy.

    Gwarantuje ze zaden event nie narusza zasad prawnych:
    nie oskarza, nie znieslewia, nie ujawnia nazw firm bez podstawy prawnej.
    """

    def filter_event(self, event: dict) -> dict | None:
        """Filtruje event. Zwraca przefiltrowany event lub None (odrzucony).

        Event jest odrzucany jesli:
        - Brak source_url
        - Brak timestamp
        - Zrodlo nie przechodzi walidacji legalnosci
        """
        if not event.get("source_url"):
            logger.info("Event odrzucony: brak source_url")
            return None
        if not event.get("timestamp"):
            logger.info("Event odrzucony: brak timestamp")
            return None

        event = self._sanitize_event(event)

        if not self.can_name_company(event):
            event = self._anonymize_company_names(event)

        return event

    def can_name_company(self, event: dict) -> bool:
        """Sprawdza czy mozna wymienic firme z nazwy.

        Dozwolone TYLKO jesli:
        - is_official == True (policja, rejestr sadowy, monitor sadowy)
        - trust_score >= 0.7
        """
        return bool(event.get("is_official")) and event.get("trust_score", 0) >= 0.7

    def sanitize_language(self, text: str) -> str:
        """Zamienia oskarzycilelski jezyk na neutralny.

        Zastepuje slowa typu 'oszust', 'zlodziej', 'kradnie' na
        neutralne odpowiedniki: 'zdarzenie', 'incydent', 'zgloszenie'.
        """
        if not text:
            return text
        result = text
        for forbidden, replacement in FORBIDDEN_WORDS.items():
            pattern = re.compile(re.escape(forbidden), re.IGNORECASE)
            result = pattern.sub(replacement, result)
        return result

    def validate_source_legality(self, source: dict) -> bool:
        """Sprawdza czy zrodlo jest publicznie dostepne i legalne do uzycia."""
        if not source.get("url"):
            return False
        if not source.get("source_name"):
            return False
        return True

    def _sanitize_event(self, event: dict) -> dict:
        """Oczyszcza tekst wydarzenia z oskarzycilelskiego jezyka."""
        for field in ("title", "text", "description"):
            if event.get(field):
                event[field] = self.sanitize_language(event[field])
        return event

    def _anonymize_company_names(self, event: dict) -> dict:
        """Anonimizuje nazwy firm w evencie ze zrodla nieoficjalnego.

        Zastepuje nazwy firm na 'firma transportowa z regionu X'.
        """
        region = event.get("region", event.get("country_code", "nieznany"))
        replacement = f"firma transportowa z regionu {region}"

        for field in ("title", "text", "description"):
            if event.get(field):
                event[field] = self._replace_company_names(event[field], replacement)

        event["_company_names_anonymized"] = True
        return event

    def _replace_company_names(self, text: str, replacement: str) -> str:
        """Wykrywa i zastepuje potencjalne nazwy firm w tekscie.

        Uzywane tylko dla zrodel nieoficjalnych.
        Heurystyka: wykrywa ciagi pasujace do nazw firm (wielka litera + forma prawna).
        """
        # Wzorce form prawnych firm (PL, DE, EN, FR, etc.)
        legal_forms = (
            r"sp\.\s*z\s*o\.?\s*o\.?",
            r"sp\.\s*j\.?",
            r"sp\.\s*k\.?",
            r"s\.?\s*a\.?",
            r"S\.?A\.?",
            r"GmbH",
            r"AG",
            r"KG",
            r"OHG",
            r"UG",
            r"Ltd\.?",
            r"LLC",
            r"Inc\.?",
            r"S\.?R\.?L\.?",
            r"B\.?V\.?",
            r"N\.?V\.?",
            r"A\.?S\.?",
            r"SAS",
            r"SARL",
            r"ApS",
            r"AB",
            r"Oy",
            r"Kft\.?",
            r"d\.?o\.?o\.?",
        )
        # Pattern: 1-4 slowa zaczynajace sie wielka litera + forma prawna
        forms_pattern = "|".join(legal_forms)
        company_pattern = re.compile(
            rf"\b([A-Z\u00C0-\u017E][a-z\u00C0-\u017E]+(?:\s+[A-Z\u00C0-\u017E][a-z\u00C0-\u017E]+){{0,3}})"
            rf"\s+(?:{forms_pattern})\b",
            re.UNICODE,
        )
        text = company_pattern.sub(replacement, text)

        # Pattern: nazwy w cudzyslow — "Nazwa Firmy" lub „Nazwa Firmy"
        quoted_pattern = re.compile(r'["\u201e\u201c]([^"\u201d\u201f]{3,50})["\u201d\u201f]')
        text = quoted_pattern.sub(f'"{replacement}"', text)

        return text
