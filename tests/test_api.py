"""FastAPI service tests (Weeks 15-16)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ops_agent.api.app import create_app
from ops_agent.audit import AuditLog
from ops_agent.graph import compile_pipeline


@pytest.fixture
def client(tmp_path):
    reports = tmp_path / "reports"
    (reports / "mock-test").mkdir(parents=True)
    (reports / "mock-test" / "summary.json").write_text(json.dumps({
        "provider": "mock:x", "embedder": "tfidf", "generated_at": "now", "alpha": 0.05,
        "canonical": {"n_heldout": 10, "heldout": {"naive_governed": {"automation_rate": 0.4,
                                                                       "unsafe_resolution_rate": 0.05}}},
    }), encoding="utf-8")
    app = create_app(pipeline=compile_pipeline(mode="raw"), audit=AuditLog(tmp_path / "a.sqlite3"),
                     reports_dir=reports)
    return TestClient(app)


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["pipeline_ready"] is True
    assert body["governance_mode"] == "raw"


def test_dashboard_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "OPS-AGENT" in response.text and "/api/tickets" in response.text


def test_submit_runs_the_pipeline_and_audits_it(client):
    response = client.post("/api/tickets", json={"text": "I clicked a link in a phishing email", "ticket_id": "TCK-API-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["ticket_id"] == "TCK-API-1"
    assert body["outcome"] == "escalated" and body["escalation_flag"] is True
    assert body["run_id"].startswith("RUN-")
    assert body["path"][0] == "intake" and body["path"][-1] == "escalate"
    assert len(body["policy_checks"]) == 7

    history = client.get("/api/tickets").json()
    assert history["runs"][0]["ticket_id"] == "TCK-API-1"
    assert "final_response" not in history["runs"][0]
    events = client.get("/api/tickets/TCK-API-1").json()["events"]
    assert events[-1]["event"] == "run_completed"
    assert client.get("/api/audit/verify").json()["ok"] is True


def test_input_is_validated(client):
    assert client.post("/api/tickets", json={"text": ""}).status_code == 422
    assert client.post("/api/tickets", json={"text": "x", "ticket_id": "bad id!"}).status_code == 422


def test_unknown_ticket_is_404(client):
    assert client.get("/api/tickets/NOPE").status_code == 404


def test_calibration_and_evaluation_endpoints(client):
    calibration = client.get("/api/calibration").json()
    assert calibration["mode"] == "raw" and calibration["profile"] is None
    evaluations = client.get("/api/evaluation").json()["evaluations"]
    assert evaluations[0]["variants"]["naive_governed"]["unsafe_resolution_rate"] == 0.05
