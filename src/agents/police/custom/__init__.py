"""Custom police agent subclasses for countries with non-standard scraping logic.

DE, AT — dual source (official site + presseportal.de) with separate parsers.
TR     — dual source with per-source trust_score (EGM=1.0, AA=0.85).
CH     — card-based layout, "DD. MONTH YYYY" date format.
"""

from src.agents.police.custom.austria import AustrianPoliceAgent
from src.agents.police.custom.germany import BundespolizeiAgent
from src.agents.police.custom.switzerland import SwissPoliceAgent
from src.agents.police.custom.turkey import TurkishPoliceAgent

__all__ = [
    "AustrianPoliceAgent",
    "BundespolizeiAgent",
    "SwissPoliceAgent",
    "TurkishPoliceAgent",
]
