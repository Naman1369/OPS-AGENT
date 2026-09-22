"""FastAPI service and dashboard (synopsis Phase 8, Weeks 15-16).

Endpoints
    GET  /                      dashboard (ticket flow, confidence, escalation history)
    GET  /health                liveness/readiness and the active configuration
    POST /api/tickets           run one ticket through the governed pipeline
    GET  /api/tickets           recent decisions from the audit trail
    GET  /api/tickets/{id}      every audit row for one ticket
    GET  /api/audit/verify      recompute the audit hash chain
    GET  /api/calibration       the calibration profile in force (or why none is)
    GET  /api/evaluation        headline results of the latest evaluation runs

Run:  uvicorn ops_agent.api.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..audit import AuditLog
from ..config import PROJECT_ROOT, SETTINGS
from ..graph import Pipeline, compile_pipeline
from ..state import new_state

DASHBOARD = Path(__file__).with_name("dashboard.html")


class TicketIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000, description="The ticket as the user wrote it")
    ticket_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")


class TicketOut(BaseModel):
    ticket_id: str
    run_id: str | None
    outcome: str
    governance_verdict: str
    escalation_flag: bool
    category: str
    priority: str
    confidence_score: float
    calibrated_confidence: float | None
    confidence_basis: str
    confidence_threshold_applied: float | None
    policy_checks: dict[str, bool]
    governance_reasons: list[str]
    citations: list[str]
    retrieved: list[dict[str, Any]]
    path: list[str]
    final_response: str


def _latest_evaluations(reports_dir: Path) -> list[dict[str, Any]]:
    results = []
    for summary_path in sorted(reports_dir.glob("*/summary.json")):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        heldout = summary.get("canonical", {}).get("heldout", {})
        results.append({
            "configuration": summary_path.parent.name,
            "provider": summary.get("provider"),
            "embedder": summary.get("embedder"),
            "generated_at": summary.get("generated_at"),
            "alpha": summary.get("alpha"),
            "n_heldout": summary.get("canonical", {}).get("n_heldout"),
            "variants": {
                variant: {
                    key: metrics.get(key)
                    for key in ("automation_rate", "correct_resolution_rate", "unsafe_resolution_rate",
                                "unnecessary_escalation_rate", "mast_any_user_facing_rate")
                }
                for variant, metrics in heldout.items()
            },
        })
    return results


def create_app(
    pipeline: Pipeline | None = None,
    audit: AuditLog | None = None,
    reports_dir: Path | str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="OPS-AGENT",
        version=__version__,
        description="Multi-agent IT incident resolution with deterministic, calibrated governance.",
    )
    lock = threading.Lock()
    holder: dict[str, Any] = {"pipeline": pipeline}
    audit_log = audit if audit is not None else (AuditLog(SETTINGS.audit.db_path) if SETTINGS.audit.enabled else None)
    reports = Path(reports_dir) if reports_dir else PROJECT_ROOT / "reports" / "evaluation"

    def get_pipeline() -> Pipeline:
        with lock:
            if holder["pipeline"] is None:
                holder["pipeline"] = compile_pipeline()
            return holder["pipeline"]

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard() -> str:
        return DASHBOARD.read_text(encoding="utf-8")

    @app.get("/health")
    def health() -> dict[str, Any]:
        active = holder["pipeline"]
        return {
            "status": "ok",
            "version": __version__,
            "pipeline_ready": active is not None,
            "governance_mode": active.mode if active else SETTINGS.governance.mode,
            "governance_note": active.note if active else "pipeline compiles on first request",
            "provider": SETTINGS.llm.resolved_provider(),
            "audit_enabled": audit_log is not None,
        }

    @app.post("/api/tickets", response_model=TicketOut)
    def submit(ticket: TicketIn) -> TicketOut:
        active = get_pipeline()
        final = active.invoke(new_state(ticket.text, ticket_id=ticket.ticket_id))
        run_id = None
        if audit_log is not None:
            run_id = audit_log.record_run(final, variant=f"multi_agent_{active.mode}", governance_note=active.note)
        calibrated = final.get("calibrated_confidence") if final.get("confidence_is_calibrated") else None
        return TicketOut(
            ticket_id=final["ticket_id"],
            run_id=run_id,
            outcome=final.get("outcome", ""),
            governance_verdict=final.get("governance_verdict", ""),
            escalation_flag=bool(final.get("escalation_flag")),
            category=final.get("category", "other"),
            priority=final.get("priority", "P3"),
            confidence_score=float(final.get("confidence_score") or 0.0),
            calibrated_confidence=float(calibrated) if calibrated is not None else None,
            confidence_basis=final.get("confidence_basis", "raw"),
            confidence_threshold_applied=final.get("confidence_threshold_applied"),
            policy_checks=final.get("policy_checks") or {},
            governance_reasons=final.get("governance_reasons") or [],
            citations=final.get("citations") or [],
            retrieved=[
                {"doc_id": d.get("doc_id"), "title": d.get("title"), "score": d.get("score")}
                for d in final.get("retrieved_docs") or []
            ],
            path=[str(e.get("agent")) for e in final.get("agent_trace") or []],
            final_response=final.get("final_response", ""),
        )

    @app.get("/api/tickets")
    def history(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        if audit_log is None:
            return {"runs": [], "stats": {}, "audit_enabled": False}
        runs = audit_log.runs(limit)
        for run in runs:
            run.pop("final_response", None)
        return {"runs": runs, "stats": audit_log.stats(), "audit_enabled": True}

    @app.get("/api/tickets/{ticket_id}")
    def ticket_events(ticket_id: str) -> dict[str, Any]:
        if audit_log is None:
            raise HTTPException(status_code=404, detail="audit trail disabled")
        events = audit_log.events(ticket_id=ticket_id)
        if not events:
            raise HTTPException(status_code=404, detail=f"no audit record for {ticket_id}")
        return {"ticket_id": ticket_id, "events": events}

    @app.get("/api/audit/verify")
    def verify() -> dict[str, Any]:
        if audit_log is None:
            return {"ok": None, "detail": "audit trail disabled"}
        return audit_log.verify().to_dict()

    @app.get("/api/calibration")
    def calibration() -> dict[str, Any]:
        active = get_pipeline()
        return {
            "mode": active.mode,
            "note": active.note,
            "profile": active.profile.to_dict() if active.profile else None,
            "naive_threshold": SETTINGS.governance.confidence_threshold,
        }

    @app.get("/api/evaluation")
    def evaluation() -> dict[str, Any]:
        return {"evaluations": _latest_evaluations(reports)}

    return app


app = create_app()
