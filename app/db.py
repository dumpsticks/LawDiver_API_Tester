"""Local SQLite history for APITester only — never connects to LawDiver production DBs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "history.db"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(request_history)").fetchall()}
    if "machine_json" not in cols:
        conn.execute("ALTER TABLE request_history ADD COLUMN machine_json TEXT")
    if "view_json" not in cols:
        conn.execute("ALTER TABLE request_history ADD COLUMN view_json TEXT")


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS request_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                function_id TEXT NOT NULL,
                function_label TEXT NOT NULL,
                inputs_json TEXT NOT NULL,
                request_id TEXT,
                ok INTEGER NOT NULL,
                summary TEXT,
                error_message TEXT,
                machine_json TEXT,
                view_json TEXT
            )
            """
        )
        _ensure_columns(conn)
        conn.commit()


def log_request(
    *,
    function_id: str,
    function_label: str,
    inputs: dict[str, Any],
    request_id: Optional[str],
    ok: bool,
    summary: str,
    error_message: Optional[str] = None,
    machine: Optional[dict[str, Any]] = None,
    view: Optional[dict[str, Any]] = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        _ensure_columns(conn)
        cur = conn.execute(
            """
            INSERT INTO request_history
                (created_at, function_id, function_label, inputs_json, request_id, ok,
                 summary, error_message, machine_json, view_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                function_id,
                function_label,
                json.dumps(inputs, ensure_ascii=False),
                request_id,
                1 if ok else 0,
                summary,
                error_message,
                json.dumps(machine, ensure_ascii=False) if machine is not None else None,
                json.dumps(view, ensure_ascii=False) if view is not None else None,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_history(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        _ensure_columns(conn)
        rows = conn.execute(
            """
            SELECT id, created_at, function_id, function_label, inputs_json,
                   request_id, ok, summary, error_message,
                   CASE WHEN machine_json IS NOT NULL AND machine_json != '' THEN 1 ELSE 0 END AS has_machine,
                   CASE WHEN view_json IS NOT NULL AND view_json != '' THEN 1 ELSE 0 END AS has_view
            FROM request_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": row["id"],
                "createdAt": row["created_at"],
                "functionId": row["function_id"],
                "functionLabel": row["function_label"],
                "inputs": json.loads(row["inputs_json"] or "{}"),
                "requestId": row["request_id"],
                "ok": bool(row["ok"]),
                "summary": row["summary"],
                "errorMessage": row["error_message"],
                "hasMachine": bool(row["has_machine"]),
                "hasView": bool(row["has_view"]),
            }
        )
    return out


def get_history_item(item_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        _ensure_columns(conn)
        row = conn.execute(
            """
            SELECT id, created_at, function_id, function_label, inputs_json,
                   request_id, ok, summary, error_message, machine_json, view_json
            FROM request_history
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
    if not row:
        return None
    machine = None
    view = None
    if row["machine_json"]:
        try:
            machine = json.loads(row["machine_json"])
        except json.JSONDecodeError:
            machine = {"parseError": True, "raw": row["machine_json"][:500]}
    if row["view_json"]:
        try:
            view = json.loads(row["view_json"])
        except json.JSONDecodeError:
            view = None
    return {
        "id": row["id"],
        "createdAt": row["created_at"],
        "functionId": row["function_id"],
        "functionLabel": row["function_label"],
        "inputs": json.loads(row["inputs_json"] or "{}"),
        "requestId": row["request_id"],
        "ok": bool(row["ok"]),
        "summary": row["summary"],
        "errorMessage": row["error_message"],
        "machine": machine,
        "view": view,
    }
