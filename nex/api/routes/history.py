"""
History API — prompt history storage (max 20 entries, 500KB cap).
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

HISTORY_FILE = Path.home() / ".nex" / "history.json"
MAX_ENTRIES = 20
MAX_FILE_BYTES = 500 * 1024  # 500KB


def _read_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _write_history(entries: list[dict]):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Enforce max entries
    while len(entries) > MAX_ENTRIES:
        entries.pop(0)  # Remove oldest
    text = json.dumps(entries, indent=2, ensure_ascii=False)
    # Enforce max file size
    while len(text.encode("utf-8")) > MAX_FILE_BYTES and len(entries) > 0:
        entries.pop(0)
        text = json.dumps(entries, indent=2, ensure_ascii=False)
    HISTORY_FILE.write_text(text, encoding="utf-8")


@router.get("/history")
async def get_history():
    entries = _read_history()
    file_size = HISTORY_FILE.stat().st_size if HISTORY_FILE.exists() else 0
    return {
        "entries": entries,
        "total": len(entries),
        "fileSizeBytes": file_size,
    }


@router.post("/history")
async def add_history_entry(entry: dict):
    # Sanitize — never store sensitive fields
    sanitized = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "userPrompt": str(entry.get("userPrompt", ""))[:500],
        "nexResponse": str(entry.get("nexResponse", ""))[:2000],
        "processingTimeMs": entry.get("processingTimeMs"),
        "servicesUsed": entry.get("servicesUsed", []),
    }
    entries = _read_history()
    entries.append(sanitized)
    _write_history(entries)
    return {"ok": True, "id": sanitized["id"]}


@router.delete("/history")
async def clear_history():
    _write_history([])
    return {"ok": True}
