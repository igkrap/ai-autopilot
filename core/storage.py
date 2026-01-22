from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass
class SessionInfo:
    session_id: str
    title: str
    created_at: str


@dataclass
class Message:
    role: str
    content: str
    timestamp: str
    attachment_path: str | None


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                attachment_path TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                session_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
            """
        )
        self.conn.commit()

    def create_session(self, session_id: str, title: str) -> None:
        created_at = datetime.utcnow().isoformat()
        self.conn.execute(
            "INSERT INTO sessions(session_id, title, created_at) VALUES (?, ?, ?)",
            (session_id, title, created_at),
        )
        self.conn.commit()

    def list_sessions(self) -> list[SessionInfo]:
        rows = self.conn.execute(
            "SELECT session_id, title, created_at FROM sessions ORDER BY created_at DESC"
        ).fetchall()
        return [SessionInfo(row["session_id"], row["title"], row["created_at"]) for row in rows]

    def delete_session(self, session_id: str) -> None:
        self.conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM settings WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM logs WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self.conn.commit()

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        attachment_path: str | None,
    ) -> None:
        timestamp = datetime.utcnow().isoformat()
        self.conn.execute(
            """
            INSERT INTO messages(session_id, role, content, timestamp, attachment_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, role, content, timestamp, attachment_path),
        )
        self.conn.commit()

    def list_messages(self, session_id: str) -> list[Message]:
        rows = self.conn.execute(
            """
            SELECT role, content, timestamp, attachment_path
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
        return [
            Message(row["role"], row["content"], row["timestamp"], row["attachment_path"])
            for row in rows
        ]

    def save_settings(self, session_id: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data)
        self.conn.execute(
            "INSERT OR REPLACE INTO settings(session_id, data) VALUES (?, ?)",
            (session_id, payload),
        )
        self.conn.commit()

    def load_settings(self, session_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT data FROM settings WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return {}
        return json.loads(row["data"])

    def log_action(self, session_id: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data)
        created_at = datetime.utcnow().isoformat()
        self.conn.execute(
            "INSERT INTO logs(session_id, data, created_at) VALUES (?, ?, ?)",
            (session_id, payload, created_at),
        )
        self.conn.commit()

    def export_session(self, session_id: str, dest_path: Path) -> None:
        messages = self.list_messages(session_id)
        settings = self.load_settings(session_id)
        logs = self.conn.execute(
            "SELECT data, created_at FROM logs WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        export_payload = {
            "session_id": session_id,
            "messages": [message.__dict__ for message in messages],
            "settings": settings,
            "logs": [dict(row) for row in logs],
        }
        dest_path.write_text(json.dumps(export_payload, ensure_ascii=False, indent=2))

    def close(self) -> None:
        self.conn.close()


class JsonLogWriter:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, entry: dict[str, Any]) -> None:
        timestamp = datetime.utcnow().isoformat()
        payload = {"timestamp": timestamp, **entry}
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class SessionFileManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def session_path(self, session_id: str) -> Path:
        path = self.root / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def captures_path(self, session_id: str) -> Path:
        path = self.session_path(session_id) / "captures"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def logs_path(self, session_id: str) -> Path:
        path = self.session_path(session_id) / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def latest_capture(self, session_id: str) -> Path | None:
        captures = list(self.captures_path(session_id).glob("*.png"))
        if not captures:
            return None
        return sorted(captures)[-1]

    def ensure_session_assets(self, session_id: str) -> None:
        self.session_path(session_id)
        self.captures_path(session_id)
        self.logs_path(session_id)

    def list_capture_files(self, session_id: str) -> Iterable[Path]:
        return sorted(self.captures_path(session_id).glob("*.png"))
