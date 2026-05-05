"""Anonimizacja danych osobowych w zdarzeniach transportowych.

Wykrywa i usuwa/zamienia dane osobowe osob fizycznych:
- Imiona i nazwiska -> '[osoba]'
- Numery telefonow -> usuniete
- Adresy email -> usuniete
- Numery rejestracyjne pojazdow prywatnych -> usuniete
  (firmowe zostawia jesli z oficjalnego zrodla)
- Numery PESEL/dowodu/NIP osob fizycznych -> usuniete
- Adresy zamieszkania osob -> usuniete

Wykorzystuje regex patterns + NER (Named Entity Recognition) z spaCy.
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

PHONE_PATTERN = re.compile(
    r"(?:\+\d{1,3}[\s-]?)?"
    r"(?:\(?\d{2,4}\)?[\s-]?)"
    r"\d{3,4}[\s-]?\d{2,4}"
)
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PESEL_PATTERN = re.compile(r"\b\d{11}\b")
NIP_PATTERN = re.compile(r"\b\d{3}[-]?\d{3}[-]?\d{2}[-]?\d{2}\b")
DOWOD_PATTERN = re.compile(r"\b[A-Z]{3}\s?\d{6}\b")
PLATE_PATTERN = re.compile(r"\b[A-Z]{1,3}\s?[A-Z0-9]{2,5}\s?\d{1,4}\b")
IBAN_PATTERN = re.compile(r"\b[A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{0,4}\b")


@dataclass
class AnonymizationReport:
    """Raport co zostalo zanonimizowane i dlaczego."""

    original_length: int = 0
    anonymized_length: int = 0
    removed_phones: int = 0
    removed_emails: int = 0
    removed_ids: int = 0
    removed_names: int = 0
    removed_plates: int = 0
    removed_addresses: int = 0
    details: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "original_length": self.original_length,
            "anonymized_length": self.anonymized_length,
            "removed_phones": self.removed_phones,
            "removed_emails": self.removed_emails,
            "removed_ids": self.removed_ids,
            "removed_names": self.removed_names,
            "removed_plates": self.removed_plates,
            "removed_addresses": self.removed_addresses,
            "details": self.details,
        }


class Anonymizer:
    """Anonimizer danych osobowych w tekście.

    Wykrywa PII za pomoca regex patterns i NER (spaCy)
    oraz usuwa/zamienia je na bezpieczne tokeny.
    """

    def __init__(self):
        self._nlp = None

    def _get_nlp(self):
        """Leniwe ladowanie modelu spaCy."""
        if self._nlp is None:
            try:
                import spacy
                self._nlp = spacy.load("xx_ent_wiki_sm")
            except (OSError, ImportError):
                logger.warning("spaCy lub model niedostepny — NER wylaczony")
                self._nlp = False
        return self._nlp

    def anonymize_personal_data(self, text: str) -> str:
        """Anonimizuje dane osobowe w tekscie.

        Zastepuje:
        - Imiona i nazwiska -> '[osoba]'
        - Numery telefonow -> '[telefon usuniety]'
        - Adresy email -> '[email usuniety]'
        - Numery PESEL/dowodu/NIP -> '[ID usuniete]'
        - Numery rejestracyjne prywatne -> '[rejestracja usunieta]'
        - IBAN -> '[konto usuniete]'
        """
        if not text:
            return text

        text = PHONE_PATTERN.sub("[telefon usuniety]", text)
        text = EMAIL_PATTERN.sub("[email usuniety]", text)
        text = PESEL_PATTERN.sub("[ID usuniete]", text)
        text = NIP_PATTERN.sub("[ID usuniete]", text)
        text = DOWOD_PATTERN.sub("[ID usuniete]", text)
        text = IBAN_PATTERN.sub("[konto usuniete]", text)

        nlp = self._get_nlp()
        if nlp:
            doc = nlp(text)
            replacements = []
            for ent in doc.ents:
                if ent.label_ == "PER":
                    replacements.append((ent.start_char, ent.end_char, "[osoba]"))
                elif ent.label_ == "LOC" and self._is_residential_address(ent.text):
                    replacements.append((ent.start_char, ent.end_char, "[adres usuniety]"))
            for start, end, repl in sorted(replacements, reverse=True):
                text = text[:start] + repl + text[end:]

        return text

    def anonymize_vehicle_plates(self, text: str, is_official_source: bool = False) -> str:
        """Anonimizuje numery rejestracyjne pojazdow prywatnych.

        Firmowe zostawia jesli dane pochodza z oficjalnego zrodla.
        """
        if is_official_source:
            return text
        return PLATE_PATTERN.sub("[rejestracja usunieta]", text)

    def contains_personal_data(self, text: str) -> bool:
        """Sprawdza czy tekst zawiera dane osobowe."""
        if not text:
            return False
        if PHONE_PATTERN.search(text):
            return True
        if EMAIL_PATTERN.search(text):
            return True
        if PESEL_PATTERN.search(text):
            return True

        nlp = self._get_nlp()
        if nlp:
            doc = nlp(text)
            for ent in doc.ents:
                if ent.label_ == "PER":
                    return True
        return False

    def get_anonymization_report(self, text: str) -> AnonymizationReport:
        """Generuje raport co zostaloby zanonimizowane i dlaczego."""
        report = AnonymizationReport(original_length=len(text) if text else 0)

        if not text:
            return report

        report.removed_phones = len(PHONE_PATTERN.findall(text))
        report.removed_emails = len(EMAIL_PATTERN.findall(text))
        report.removed_ids = (
            len(PESEL_PATTERN.findall(text))
            + len(NIP_PATTERN.findall(text))
            + len(DOWOD_PATTERN.findall(text))
        )
        report.removed_plates = len(PLATE_PATTERN.findall(text))

        nlp = self._get_nlp()
        if nlp:
            doc = nlp(text)
            report.removed_names = sum(1 for ent in doc.ents if ent.label_ == "PER")
            report.removed_addresses = sum(
                1 for ent in doc.ents
                if ent.label_ == "LOC" and self._is_residential_address(ent.text)
            )

        anonymized = self.anonymize_personal_data(text)
        report.anonymized_length = len(anonymized)
        return report

    def _is_residential_address(self, text: str) -> bool:
        """Heurystyka: czy encja lokalizacyjna to adres zamieszkania."""
        address_indicators = ["ul.", "ul ", "os.", "al.", "str.", "Str."]
        return any(ind in text for ind in address_indicators)
