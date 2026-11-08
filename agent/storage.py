"""Simple JSON-file storage for the agent's memory, tasks, and notes."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="minutes")


class JsonStore:
    """A list of dict records persisted to one JSON file, each with an integer id."""

    def __init__(self, name: str):
        self.path = DATA_DIR / f"{name}.json"

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Keep a copy of the unreadable file rather than silently overwriting it.
            backup = self.path.with_suffix(".corrupt.json")
            self.path.replace(backup)
            return []

    def save(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically so a crash never leaves a half-written file.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def add(self, **fields: Any) -> dict[str, Any]:
        records = self.load()
        next_id = max((r["id"] for r in records), default=0) + 1
        record = {"id": next_id, "created": _now(), **fields}
        records.append(record)
        self.save(records)
        return record

    def update(self, record_id: int, **fields: Any) -> dict[str, Any] | None:
        records = self.load()
        for r in records:
            if r["id"] == record_id:
                r.update(fields)
                self.save(records)
                return r
        return None

    def delete(self, record_id: int) -> bool:
        records = self.load()
        kept = [r for r in records if r["id"] != record_id]
        if len(kept) == len(records):
            return False
        self.save(kept)
        return True


memories = JsonStore("memories")
tasks = JsonStore("tasks")
notes = JsonStore("notes")
