"""Shared JSONL writer for road alerts — used by Telegram & Discord agents.

Writes road alert events to data/road_alerts.jsonl with file locking (fcntl).
"""

import fcntl
import json
import re
from datetime import datetime
from pathlib import Path

from src.agents.road_alerts_keywords import classify_alert_type

DATA_DIR = Path(__file__).parent.parent.parent / "data"
ROAD_ALERTS_FILE = DATA_DIR / "road_alerts.jsonl"

# Regex for road identifiers like "A2 km 340", "E40", "S7 km 12", "DK1"
_ROAD_RE = re.compile(
    r"\b([AEDSB]\d{1,3})\b"           # A2, E40, S7, B12, D1
    r"(?:\s*km\s*(\d{1,4}(?:[.,]\d)?))?",  # optional "km 340" or "km 12.5"
    re.IGNORECASE,
)


def _extract_location(text: str) -> str | None:
    """Extract road location from text (e.g. 'A2 km 340')."""
    if not text:
        return None
    match = _ROAD_RE.search(text)
    if match:
        road = match.group(1).upper()
        km = match.group(2)
        return f"{road} km {km}" if km else road
    return None


def save_road_alert(event: dict, channel_cfg: dict) -> None:
    """Append a road alert to road_alerts.jsonl (thread-safe)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    raw_text = event.get("raw_text", "")
    language = event.get("language", "en")

    alert = {
        "timestamp": event.get("date") or datetime.utcnow().isoformat() + "Z",
        "country": channel_cfg.get("country_code", "XX"),
        "type": classify_alert_type(raw_text, language),
        "location": _extract_location(raw_text),
        "description": (event.get("description") or event.get("title", ""))[:500],
        "source_channel": channel_cfg.get("name", "unknown"),
        "language": language,
        "raw_text": (raw_text or "")[:2000],
    }

    with open(ROAD_ALERTS_FILE, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(alert, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
