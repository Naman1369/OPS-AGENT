"""Append-only, hash-chained audit trail (synopsis Phase 5, Weeks 10-12).

Every trace event of every run is written as one row of a single SQLite table,
followed by one ``run_completed`` row summarising the decision. The trail is
made trustworthy in two independent ways:

1. **Append-only at the database level.** SQL triggers abort any UPDATE or
   DELETE on the table, so an application bug cannot rewrite history.
2. **Tamper-evident at the data level.** Each row stores the SHA-256 of the
   previous row's hash plus its own canonical content (a hash chain, the same
   construction used by certificate-transparency logs). Editing, deleting or
   re-ordering any row - even by opening the file outside the application -
   breaks every later hash, and :meth:`AuditLog.verify` reports the first
   broken row.

Content is canonical JSON (sorted keys, fixed separators), so the same run
always hashes the same way on every machine: the trail is deterministic.
SQLite is used for a single-node deployment; the schema is plain SQL and ports
to PostgreSQL unchanged.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

GENESIS_HASH = "0" * 64
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT    NOT NULL,
    ticket_id    TEXT    NOT NULL,
    agent        TEXT    NOT NULL,
    event        TEXT    NOT NULL,
    event_ts     TEXT    NOT NULL,
    recorded_at  TEXT    NOT NULL,
    payload_json TEXT    NOT NULL,
    prev_hash    TEXT    NOT NULL,
    row_hash     TEXT    NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_audit_ticket ON audit_log(ticket_id);
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_log(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event);
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TABLE IF NOT EXISTS audit_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _row_hash(prev_hash: str, fields: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical_json(fields)).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class ChainVerification:
    ok: bool
    rows_checked: int
    first_bad_seq: int | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "rows_checked": self.rows_checked,
            "first_bad_seq": self.first_bad_seq,
            "detail": self.detail,
        }


class AuditLog:
    """SQLite-backed append-only audit trail with a SHA-256 hash chain."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO audit_meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @contextmanager
    def _connect(self):
        """A connection that commits on success, rolls back on error, always closes."""
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Writing
    # ------------------------------------------------------------------ #

    def _append(self, conn: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> int:
        last = conn.execute("SELECT row_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = last["row_hash"] if last else GENESIS_HASH
        count = 0
        for row in rows:
            fields = {
                "run_id": row["run_id"],
                "ticket_id": row["ticket_id"],
                "agent": row["agent"],
                "event": row["event"],
                "event_ts": row["event_ts"],
                "recorded_at": row["recorded_at"],
                "payload_json": canonical_json(row["payload"]),
            }
            row_hash = _row_hash(prev_hash, fields)
            conn.execute(
                "INSERT INTO audit_log(run_id, ticket_id, agent, event, event_ts, recorded_at, "
                "payload_json, prev_hash, row_hash) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    fields["run_id"], fields["ticket_id"], fields["agent"], fields["event"],
                    fields["event_ts"], fields["recorded_at"], fields["payload_json"],
                    prev_hash, row_hash,
                ),
            )
            prev_hash = row_hash
            count += 1
        return count

    def record_run(
        self,
        final_state: dict[str, Any],
        variant: str = "multi_agent",
        governance_note: str = "",
    ) -> str:
        """Persist a finished run: every trace event, then a decision summary."""
        run_id = f"RUN-{uuid4().hex[:12].upper()}"
        ticket_id = str(final_state.get("ticket_id") or "unknown")
        recorded_at = _now()
        rows: list[dict[str, Any]] = []
        for event in final_state.get("agent_trace") or []:
            rows.append(
                {
                    "run_id": run_id,
                    "ticket_id": ticket_id,
                    "agent": str(event.get("agent", "")),
                    "event": str(event.get("event", "")),
                    "event_ts": str(event.get("timestamp", recorded_at)),
                    "recorded_at": recorded_at,
                    "payload": {
                        "payload": event.get("payload", {}),
                        "latency_ms": event.get("latency_ms"),
                        "error": event.get("error"),
                    },
                }
            )
        summary = {
            "variant": variant,
            "governance_note": governance_note,
            "raw_text": final_state.get("raw_text"),
            "submitted_at": final_state.get("submitted_at"),
            "category": final_state.get("category"),
            "priority": final_state.get("priority"),
            "retrieved_doc_ids": [d.get("doc_id") for d in final_state.get("retrieved_docs") or []],
            "citations": final_state.get("citations") or [],
            "confidence_score": final_state.get("confidence_score"),
            "calibrated_confidence": final_state.get("calibrated_confidence"),
            "confidence_is_calibrated": bool(final_state.get("confidence_is_calibrated")),
            "confidence_basis": final_state.get("confidence_basis"),
            "confidence_threshold_applied": final_state.get("confidence_threshold_applied"),
            "calibration_profile_id": final_state.get("calibration_profile_id"),
            "governance_verdict": final_state.get("governance_verdict"),
            "escalation_flag": final_state.get("escalation_flag"),
            "policy_checks": final_state.get("policy_checks") or {},
            "governance_reasons": final_state.get("governance_reasons") or [],
            "outcome": final_state.get("outcome"),
            "final_response_sha256": hashlib.sha256(
                (final_state.get("final_response") or "").encode("utf-8")
            ).hexdigest(),
            "final_response": final_state.get("final_response"),
            "errors": final_state.get("errors") or [],
        }
        rows.append(
            {
                "run_id": run_id,
                "ticket_id": ticket_id,
                "agent": "audit",
                "event": "run_completed",
                "event_ts": recorded_at,
                "recorded_at": recorded_at,
                "payload": summary,
            }
        )
        with self._lock, self._connect() as conn:
            # IMMEDIATE takes the write lock before reading the chain head, so two
            # writers can never both link to the same previous row.
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._append(conn, rows)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return run_id

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #

    def verify(self) -> ChainVerification:
        """Recompute the whole chain; report the first row that does not match."""
        prev_hash = GENESIS_HASH
        checked = 0
        with self._connect() as conn:
            for row in conn.execute("SELECT * FROM audit_log ORDER BY seq ASC"):
                fields = {
                    "run_id": row["run_id"],
                    "ticket_id": row["ticket_id"],
                    "agent": row["agent"],
                    "event": row["event"],
                    "event_ts": row["event_ts"],
                    "recorded_at": row["recorded_at"],
                    "payload_json": row["payload_json"],
                }
                if row["prev_hash"] != prev_hash:
                    return ChainVerification(False, checked, row["seq"], "prev_hash does not link to the previous row")
                if _row_hash(prev_hash, fields) != row["row_hash"]:
                    return ChainVerification(False, checked, row["seq"], "row content does not match its hash")
                prev_hash = row["row_hash"]
                checked += 1
        return ChainVerification(True, checked, None, "chain intact")

    def runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Most recent run summaries, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT seq, run_id, ticket_id, recorded_at, payload_json, row_hash FROM audit_log "
                "WHERE event = 'run_completed' ORDER BY seq DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        out = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload.update(
                {"run_id": row["run_id"], "ticket_id": row["ticket_id"],
                 "recorded_at": row["recorded_at"], "row_hash": row["row_hash"], "seq": row["seq"]}
            )
            out.append(payload)
        return out

    def events(self, ticket_id: str | None = None, run_id: str | None = None) -> list[dict[str, Any]]:
        """All rows for one ticket or one run, in order."""
        if not ticket_id and not run_id:
            raise ValueError("ticket_id or run_id is required")
        column, value = ("run_id", run_id) if run_id else ("ticket_id", ticket_id)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM audit_log WHERE {column} = ? ORDER BY seq ASC", (value,)
            ).fetchall()
        return [
            {
                "seq": row["seq"], "run_id": row["run_id"], "ticket_id": row["ticket_id"],
                "agent": row["agent"], "event": row["event"], "event_ts": row["event_ts"],
                "recorded_at": row["recorded_at"], "payload": json.loads(row["payload_json"]),
                "prev_hash": row["prev_hash"], "row_hash": row["row_hash"],
            }
            for row in rows
        ]

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE event = 'run_completed'"
            ).fetchone()[0]
            escalated = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE event = 'run_completed' "
                "AND json_extract(payload_json, '$.outcome') = 'escalated'"
            ).fetchone()[0]
        return {"runs": int(total), "escalated": int(escalated), "resolved": int(total - escalated)}
