"""One durable desk snapshot, committed atomically by the single API process."""

import json
import sqlite3
from pathlib import Path


class DeskStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS desk (id INTEGER PRIMARY KEY CHECK(id = 1), body TEXT NOT NULL)")

    def load(self) -> dict | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT body FROM desk WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else None

    def save(self, state: dict) -> None:
        body = json.dumps(state, ensure_ascii=False, allow_nan=False)
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO desk VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (body,))
