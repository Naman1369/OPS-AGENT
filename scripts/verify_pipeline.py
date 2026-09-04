#!/usr/bin/env python3
"""Verify LangGraph state transitions across the four agents.

Implements the project's `test-agent-pipeline` skill:
  1. Initialise state from a mock IT support ticket.
  2. Execute Intake        -> assert category, priority, keywords.
  3. Execute Retrieval     -> assert context documents were appended.
  4. Execute Resolution    -> assert a solution and a raw confidence score.
  5. Execute Governance    -> assert a Safe / Unsafe decision against the threshold.
  6. Print the final state dictionary to prove no data was lost between nodes.

It runs each node in isolation first (so a failure names the responsible agent),
then runs the compiled graph end to end on several tickets that exercise the
different routes through it.

Usage:
    python scripts/verify_pipeline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ops_agent.agents.governance import governance_node  # noqa: E402
from ops_agent.agents.intake import intake_node  # noqa: E402
from ops_agent.agents.resolution import resolution_node  # noqa: E402
from ops_agent.agents.retrieval import retrieval_node  # noqa: E402
from ops_agent.config import SETTINGS  # noqa: E402
from ops_agent.graph import compile_pipeline  # noqa: E402
from ops_agent.llm import get_provider  # noqa: E402
from ops_agent.state import new_state  # noqa: E402

MOCK_TICKET = "User cannot connect to the VPN, error code 809"

ROUTE_TICKETS = [
    ("Standard resolvable ticket", "Outlook hangs on loading profile and will not open on my Windows 11 laptop."),
    ("Security gate (G6)", "I think I received a phishing email and I clicked the link in it."),
    ("P1 priority gate (G5)", "The entire office cannot reach the internet, nobody can work."),
    ("Ungrounded / no evidence", "Purple."),
]

PASS = "PASS"
FAIL = "FAIL"
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    print(f"   [{status}] {label}" + (f" -> {detail}" if detail else ""))
    if not condition:
        _failures.append(label)


def rule(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> int:
    provider = get_provider()

    rule("OPS-AGENT :: Week 5-7 pipeline verification")
    print(f"LLM provider        : {provider.name} ({provider.model})")
    print(f"Confidence threshold: {SETTINGS.governance.confidence_threshold}")
    print(f"Min relevance       : {SETTINGS.retrieval.min_relevance}")
    print(f"Top K               : {SETTINGS.retrieval.top_k}")

    # ---- Step 1: initialise state ---------------------------------------- #
    rule("STEP 1 :: Initialise state from a mock ticket")
    state = new_state(MOCK_TICKET, ticket_id="TCK-VERIFY-01")
    print(f"   ticket_id : {state['ticket_id']}")
    print(f"   raw_text  : {state['raw_text']}")
    check("state initialised with ticket_id and raw_text", bool(state["ticket_id"] and state["raw_text"]))

    # ---- Step 2: Intake --------------------------------------------------- #
    rule("STEP 2 :: Execute the Intake Agent node")
    update = intake_node(state)
    state = {**state, **update, "agent_trace": state["agent_trace"] + update.get("agent_trace", [])}
    print(f"   category   : {state['category']}")
    print(f"   priority   : {state['priority']}")
    print(f"   keywords   : {state['keywords']}")
    print(f"   entities   : {state['entities']}")
    print(f"   confidence : {state['intake_confidence']}")
    check("category assigned", bool(state.get("category")), state["category"])
    check("category is network for a VPN ticket", state["category"] == "network", state["category"])
    check("priority assigned", bool(state.get("priority")), state["priority"])
    check("keywords extracted", len(state.get("keywords") or []) > 0, str(len(state["keywords"])))
    check("error code 809 captured", "809" in json.dumps(state.get("entities")) or "809" in " ".join(state["keywords"]))
    check("retrieval query built", bool(state.get("retrieval_query")))

    # ---- Step 3: Retrieval ------------------------------------------------ #
    rule("STEP 3 :: Execute the Retrieval Agent node")
    update = retrieval_node(state)
    state = {**state, **update, "agent_trace": state["agent_trace"] + update.get("agent_trace", [])}
    for doc in state.get("retrieved_docs") or []:
        print(f"   {doc['rank']}. [{doc['score']:.3f}] {doc['doc_id']} - {doc['title']}")
    check("context documents appended to state", len(state.get("retrieved_docs") or []) > 0)
    check("grounded flag set", bool(state.get("grounded")))
    check("top relevance recorded", float(state.get("top_relevance") or 0) > 0, f"{state.get('top_relevance')}")

    # ---- Step 4: Resolution ----------------------------------------------- #
    rule("STEP 4 :: Execute the Resolution Agent node")
    update = resolution_node(state)
    state = {**state, **update, "agent_trace": state["agent_trace"] + update.get("agent_trace", [])}
    print(f"   solution   : {state['draft_solution'][:120]}...")
    print(f"   steps      : {len(state['resolution_steps'])}")
    for step in state["resolution_steps"][:3]:
        print(f"      - {step[:100]}")
    print(f"   citations  : {state['citations']}")
    print(f"   confidence : {state['confidence_score']} (RAW, uncalibrated)")
    check("solution generated", bool(state.get("draft_solution")))
    check("actionable steps produced", len(state.get("resolution_steps") or []) > 0)
    check("raw confidence score emitted", isinstance(state.get("confidence_score"), float))
    check("every citation was actually retrieved",
          set(state["citations"]).issubset({d["doc_id"] for d in state["retrieved_docs"]}))

    # ---- Step 5: Governance ------------------------------------------------ #
    rule("STEP 5 :: Execute the Governance Agent node")
    update = governance_node(state)
    state = {**state, **update, "agent_trace": state["agent_trace"] + update.get("agent_trace", [])}
    print(f"   verdict         : {state['governance_verdict']}")
    print(f"   escalation_flag : {state['escalation_flag']}")
    for name, passed in state["policy_checks"].items():
        # 'ok'/'blocked' rather than PASS/FAIL: a failing policy check is the
        # gate doing its job, not a failure of this verification run.
        print(f"      ({'ok     ' if passed else 'blocked'}) {name}")
    for reason in state["governance_reasons"]:
        print(f"      * {reason}")
    check("verdict recorded", state.get("governance_verdict") in
          {"SAFE_TO_RESOLVE", "ESCALATE_TO_HUMAN", "BLOCKED"}, str(state.get("governance_verdict")))
    check("escalation_flag is a bool", isinstance(state.get("escalation_flag"), bool))
    check("all seven policy checks evaluated", len(state.get("policy_checks") or {}) == 7)
    check("verdict is consistent with the checks",
          (state["governance_verdict"] == "SAFE_TO_RESOLVE") == (not state["escalation_flag"]))

    # ---- Step 6: final state, no data loss --------------------------------- #
    rule("STEP 6 :: Final state after sequential node execution")
    print(json.dumps(_printable(state), indent=2)[:4000])
    for field in ("ticket_id", "raw_text", "category", "priority", "keywords",
                  "retrieved_docs", "draft_solution", "confidence_score",
                  "escalation_flag", "governance_verdict"):
        check(f"field survived all four agents: {field}", field in state)

    # ---- Full compiled graph ------------------------------------------------ #
    rule("STEP 7 :: Compiled LangGraph end-to-end runs")
    pipeline = compile_pipeline()
    check("graph compiles", pipeline is not None)

    for label, ticket in ROUTE_TICKETS:
        final = pipeline.invoke(new_state(ticket))
        path = " -> ".join(event["agent"] for event in final.get("agent_trace", []))
        print(f"\n   {label}")
        print(f"      ticket   : {ticket[:70]}")
        print(f"      path     : {path}")
        print(f"      verdict  : {final.get('governance_verdict')}  "
              f"(confidence {float(final.get('confidence_score') or 0):.2f})")
        print(f"      outcome  : {final.get('outcome')}")
        check(f"{label}: reached a terminal node", final.get("outcome") in {"resolved", "escalated"})
        check(f"{label}: governance ran", "governance" in path)
        check(f"{label}: a final response was produced", bool(final.get("final_response")))

    # Route-specific expectations.
    security = pipeline.invoke(new_state(ROUTE_TICKETS[1][1]))
    check("security ticket escalates (G6 category gate)", security["escalation_flag"] is True,
          security["governance_verdict"])
    check("security ticket is classified as security", security["category"] == "security",
          security["category"])

    nonsense = pipeline.invoke(new_state(ROUTE_TICKETS[3][1]))
    check("ungrounded ticket never reaches the Resolution Agent",
          "resolution" not in [e["agent"] for e in nonsense["agent_trace"]])
    check("ungrounded ticket escalates", nonsense["escalation_flag"] is True)

    # ---- Step 8: the autonomous-resolution branch ---------------------------- #
    rule("STEP 8 :: Deliver path (autonomous resolution)")
    print("   Retrieval similarity depends on the installed embedder, so this step")
    print("   relaxes the confidence threshold to prove the deliver branch works.")
    import ops_agent.agents.governance as gov
    from ops_agent.config import GovernanceSettings, Settings

    relaxed = GovernanceSettings()
    object.__setattr__(relaxed, "confidence_threshold", 0.05)
    original = gov.SETTINGS
    gov.SETTINGS = Settings(governance=relaxed)
    try:
        delivered = pipeline.invoke(new_state("VPN fails to connect with error 809 behind NAT."))
    finally:
        gov.SETTINGS = original

    path = " -> ".join(event["agent"] for event in delivered.get("agent_trace", []))
    print(f"      path    : {path}")
    print(f"      verdict : {delivered.get('governance_verdict')}")
    print(f"      outcome : {delivered.get('outcome')}")
    print("      response:")
    for line in (delivered.get("final_response") or "").splitlines():
        print(f"         {line}")
    check("deliver path reached", delivered.get("outcome") == "resolved")
    check("verdict is SAFE_TO_RESOLVE", delivered.get("governance_verdict") == "SAFE_TO_RESOLVE")
    check("escalation flag is clear", delivered.get("escalation_flag") is False)
    check("delivered response cites its sources", "Sources:" in (delivered.get("final_response") or ""))

    # ---- Summary -------------------------------------------------------------- #
    rule("VERIFICATION SUMMARY")
    if _failures:
        print(f"{len(_failures)} check(s) FAILED:")
        for failure in _failures:
            print(f"   - {failure}")
        return 1
    print("All checks passed. State transitions correctly across all four agents.")
    return 0


def _printable(state: dict) -> dict:
    """Trim document bodies so the printed state stays readable."""
    clone = dict(state)
    clone["retrieved_docs"] = [
        {k: (v[:120] + "..." if k == "content" and isinstance(v, str) and len(v) > 120 else v)
         for k, v in doc.items()}
        for doc in state.get("retrieved_docs", [])
    ]
    clone["agent_trace"] = [
        {"agent": e.get("agent"), "event": e.get("event"), "latency_ms": e.get("latency_ms")}
        for e in state.get("agent_trace", [])
    ]
    return clone


if __name__ == "__main__":
    raise SystemExit(main())
