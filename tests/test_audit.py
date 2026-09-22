"""Audit trail tests (Weeks 10-12): append-only, hash-chained, deterministic."""

from __future__ import annotations

import sqlite3

import pytest

from ops_agent.audit import GENESIS_HASH, AuditLog, canonical_json
from ops_agent.graph import compile_pipeline, run_ticket


@pytest.fixture
def audit(tmp_path):
    return AuditLog(tmp_path / "audit.sqlite3")


@pytest.fixture(scope="module")
def pipeline():
    return compile_pipeline(mode="raw")


def test_a_run_is_recorded_event_by_event_plus_a_summary(audit, pipeline):
    final = run_ticket("VPN error 809 from the hotel", ticket_id="TCK-A1", pipeline=pipeline, audit=audit)
    events = audit.events(ticket_id="TCK-A1")
    assert [e["agent"] for e in events[:-1]] == [e["agent"] for e in final["agent_trace"]]
    summary = events[-1]
    assert summary["event"] == "run_completed"
    assert summary["payload"]["governance_verdict"] == final["governance_verdict"]
    assert summary["payload"]["policy_checks"] == final["policy_checks"]


def test_the_chain_links_from_genesis_and_verifies(audit, pipeline):
    run_ticket("Printer queue stuck", pipeline=pipeline, audit=audit)
    run_ticket("Purple.", pipeline=pipeline, audit=audit)
    rows = audit.events(ticket_id=audit.runs()[-1]["ticket_id"])
    assert rows[0]["prev_hash"] == GENESIS_HASH
    result = audit.verify()
    assert result.ok and result.rows_checked == audit.count()


def test_updates_and_deletes_are_refused_by_the_database(audit, pipeline):
    run_ticket("Outlook will not open", pipeline=pipeline, audit=audit)
    conn = sqlite3.connect(audit.db_path)
    try:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("UPDATE audit_log SET event = 'edited' WHERE seq = 1")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM audit_log WHERE seq = 1")
    finally:
        conn.close()


def test_tampering_outside_the_application_is_detected(audit, pipeline):
    run_ticket("Outlook will not open", pipeline=pipeline, audit=audit)
    run_ticket("VPN error 809", pipeline=pipeline, audit=audit)
    conn = sqlite3.connect(audit.db_path)
    conn.execute("DROP TRIGGER audit_log_no_update")  # an attacker with file access
    conn.execute("UPDATE audit_log SET payload_json = '{}' WHERE seq = 3")
    conn.commit()
    conn.close()
    result = audit.verify()
    assert not result.ok and result.first_bad_seq == 3


def test_runs_and_stats(audit, pipeline):
    run_ticket("I clicked a link in a phishing email", pipeline=pipeline, audit=audit)
    runs = audit.runs()
    assert runs[0]["outcome"] == "escalated"
    assert audit.stats() == {"runs": 1, "escalated": 1, "resolved": 0}


def test_audit_survives_reopening(tmp_path, pipeline):
    path = tmp_path / "audit.sqlite3"
    run_ticket("VPN error 809", pipeline=pipeline, audit=AuditLog(path))
    reopened = AuditLog(path)
    run_ticket("Printer stuck", pipeline=pipeline, audit=reopened)
    assert reopened.verify().ok and reopened.stats()["runs"] == 2


def test_events_requires_a_key(audit):
    with pytest.raises(ValueError):
        audit.events()


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
