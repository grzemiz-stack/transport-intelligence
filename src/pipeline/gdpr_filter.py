"""Filtr GDPR — sprawdza zgodnosc zdarzen z RODO/GDPR przed zapisem.

Reguly GDPR:
- Zadne dane osobowe osob fizycznych nie moga byc przechowywane.
- Dane firmowe (nazwa, KRS, NIP firmy) — OK, to nie sa dane osobowe.
- Dane z publicznych rejestrow — OK.
- Cytaty z forow — tylko jesli zanonimizowane.
- Zdjecia/screenshoty — NIE przechowujemy, tylko tekst.
- Kazde przetworzenie danych musi byc zalogowane (wymog GDPR art. 30).
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from src.pipeline.anonymizer import Anonymizer

logger = logging.getLogger(__name__)


@dataclass
class GDPRResult:
    """Wynik sprawdzenia GDPR compliance."""

    status: str  # "compliant", "non_compliant", "needs_review"
    reason: str
    pii_found: list[str]
    action_taken: str  # "none", "anonymized", "rejected"


class GDPRFilter:
    """Filtr zgodnosci z GDPR/RODO.

    Sprawdza czy zdarzenie moze byc przechowywane w systemie
    zgodnie z regulacjami ochrony danych osobowych.
    """

    def __init__(self):
        self._anonymizer = Anonymizer()

    def check_compliance(self, event: dict) -> dict:
        """Sprawdza zgodnosc eventu z GDPR.

        Zwraca dict z kluczem 'status':
        - 'compliant' — event OK do przechowywania
        - 'non_compliant' — event odrzucony
        - 'needs_review' — wymaga manualnej weryfikacji prawnej
        """
        issues = []

        if self._contains_images(event):
            return {
                "status": "non_compliant",
                "reason": "Event zawiera zdjecia/screenshoty — przechowujemy tylko tekst",
                "pii_found": ["image_data"],
                "action_taken": "rejected",
            }

        for field_name in ("title", "text", "description"):
            text = event.get(field_name, "")
            if text and self._anonymizer.contains_personal_data(text):
                issues.append(field_name)

        if not issues:
            self.log_processing(event, "compliance_check", "compliant")
            return {
                "status": "compliant",
                "reason": "Brak danych osobowych",
                "pii_found": [],
                "action_taken": "none",
            }

        is_forum_or_social = event.get("source_type") in ("forum", "telegram", "reddit")
        if is_forum_or_social:
            event = self.purge_pii(event)
            if self._still_has_pii(event):
                self.log_processing(event, "compliance_check", "needs_review_after_purge")
                return {
                    "status": "needs_review",
                    "reason": f"PII w polach: {issues} — zanonimizowane, wymaga weryfikacji",
                    "pii_found": issues,
                    "action_taken": "anonymized",
                }
            self.log_processing(event, "compliance_check", "anonymized")
            return {
                "status": "compliant",
                "reason": "PII zanonimizowane pomyslnie",
                "pii_found": issues,
                "action_taken": "anonymized",
            }

        if event.get("is_official"):
            self.log_processing(event, "compliance_check", "needs_review_official")
            return {
                "status": "needs_review",
                "reason": f"PII w polach: {issues} — zrodlo oficjalne, wymaga weryfikacji prawnej",
                "pii_found": issues,
                "action_taken": "none",
            }

        self.log_processing(event, "compliance_check", "non_compliant")
        return {
            "status": "non_compliant",
            "reason": f"PII w polach: {issues} — zrodlo nieoficjalne, brak podstawy prawnej",
            "pii_found": issues,
            "action_taken": "rejected",
        }

    def purge_pii(self, event: dict) -> dict:
        """Usuwa wszelkie PII z eventu."""
        for field_name in ("title", "text", "description"):
            if event.get(field_name):
                event[field_name] = self._anonymizer.anonymize_personal_data(event[field_name])
                is_official = event.get("is_official", False)
                event[field_name] = self._anonymizer.anonymize_vehicle_plates(
                    event[field_name], is_official_source=is_official
                )
        event["_gdpr_purged"] = True
        event["_gdpr_purged_at"] = datetime.utcnow().isoformat()
        return event

    def log_processing(self, event: dict, action: str, result: str) -> None:
        """Loguje przetworzenie danych — wymog GDPR art. 30.

        Zapis do audit log co zostalo przetworzone, kiedy i z jakim wynikiem.
        """
        logger.info(
            "GDPR audit: event_source=%s action=%s result=%s timestamp=%s",
            event.get("source_url", "?"),
            action,
            result,
            datetime.utcnow().isoformat(),
        )

    def _contains_images(self, event: dict) -> bool:
        """Sprawdza czy event zawiera dane obrazkowe."""
        for key in ("image", "screenshot", "photo", "image_url", "image_data"):
            if event.get(key):
                return True
        return False

    def _still_has_pii(self, event: dict) -> bool:
        """Sprawdza czy po anonimizacji nadal sa PII."""
        for field_name in ("title", "text", "description"):
            text = event.get(field_name, "")
            if text and self._anonymizer.contains_personal_data(text):
                return True
        return False
