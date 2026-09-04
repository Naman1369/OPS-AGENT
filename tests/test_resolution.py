"""Resolution Agent node tests -- grounding, citations and raw confidence."""

from __future__ import annotations

from ops_agent.agents.resolution import resolution_node
from ops_agent.state import RetrievedDoc, new_state


def _doc(doc_id: str, title: str, body: str, score: float = 0.8) -> RetrievedDoc:
    return RetrievedDoc(
        doc_id=doc_id, title=title, source="test", category="network",
        content=body, score=score, rank=1,
    )


GROUNDED_BODY = (
    "## Resolution\n"
    "1. Confirm the user is not on a captive-portal network.\n"
    "2. Set AssumeUDPEncapsulationContextOnSendRule to 2.\n"
    "3. Reboot the workstation.\n"
)


def _grounded_state():
    state = new_state("User cannot connect to the VPN, error code 809")
    state["category"] = "network"
    state["priority"] = "P3"
    state["keywords"] = ["vpn", "error 809"]
    state["retrieved_docs"] = [_doc("KB-0001", "VPN Error 809", GROUNDED_BODY, 0.86)]
    state["grounded"] = True
    return state


def test_generates_a_grounded_solution_with_steps(provider):
    update = resolution_node(_grounded_state(), provider=provider)
    assert update["draft_solution"]
    assert update["resolution_steps"]
    assert update["citations"] == ["KB-0001"]


def test_emits_a_raw_confidence_score_in_range(provider):
    update = resolution_node(_grounded_state(), provider=provider)
    assert isinstance(update["confidence_score"], float)
    assert 0.0 <= update["confidence_score"] <= 1.0
    assert update["agent_trace"][0]["payload"]["confidence_is_calibrated"] is False


def test_refuses_to_generate_without_retrieved_context(provider):
    """CLAUDE.md: never generate an answer without grounding it in context."""
    state = new_state("Some ticket with no evidence behind it")
    state["retrieved_docs"] = []
    state["grounded"] = False

    update = resolution_node(state, provider=provider)
    assert update["draft_solution"] == ""
    assert update["resolution_steps"] == []
    assert update["citations"] == []
    assert update["confidence_score"] == 0.0
    assert update["agent_trace"][0]["event"] == "refused_ungrounded"


def test_citations_outside_the_retrieved_set_are_stripped(provider):
    """A citation to a document that was never retrieved is a fabrication."""

    class FabricatingProvider:
        name, model = "fabricator", "test"

        def generate_json(self, prompt, **kwargs):
            payload = {
                "solution": "Do the thing.",
                "steps": ["Do the thing. [KB-9999]"],
                "citations": ["KB-0001", "KB-9999"],
                "rationale": "invented",
                "confidence": 0.95,
            }
            return payload, None

    update = resolution_node(_grounded_state(), provider=FabricatingProvider())
    assert update["citations"] == ["KB-0001"]
    assert update["confidence_score"] == 0.0
    assert update["agent_trace"][0]["payload"]["hallucinated_citations"] == ["KB-9999"]


def test_stronger_evidence_yields_higher_confidence(provider):
    weak = _grounded_state()
    weak["retrieved_docs"] = [_doc("KB-0001", "VPN Error 809", GROUNDED_BODY, 0.30)]
    strong = _grounded_state()
    strong["retrieved_docs"] = [_doc("KB-0001", "VPN Error 809", GROUNDED_BODY, 0.92)]

    assert (resolution_node(strong, provider=provider)["confidence_score"]
            > resolution_node(weak, provider=provider)["confidence_score"])


def test_confidence_is_zeroed_when_no_steps_are_produced():
    class EmptyProvider:
        name, model = "empty", "test"

        def generate_json(self, prompt, **kwargs):
            return {"solution": "", "steps": [], "citations": [], "confidence": 0.99}, None

    update = resolution_node(_grounded_state(), provider=EmptyProvider())
    assert update["confidence_score"] == 0.0
