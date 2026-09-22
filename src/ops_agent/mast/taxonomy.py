"""The Multi-Agent System Failure Taxonomy (MAST).

Source: Cemri, M., Pan, M. Z., Yang, S., et al. "Why Do Multi-Agent LLM Systems
Fail?" NeurIPS 2025 Datasets and Benchmarks Track (arXiv:2503.13657). MAST has
14 failure modes in 3 categories, derived from 1,600+ annotated traces across 7
multi-agent frameworks (inter-annotator Cohen's kappa 0.88).

``definition`` paraphrases the paper. ``operationalisation`` states exactly how
this project detects the mode in an OPS-AGENT trace, so a reader can check the
rule-based annotator against the taxonomy rather than trust it. Modes that the
pipeline's architecture makes impossible are marked ``structural`` and still
reported, so a zero is visibly a design property, not a missing measurement.
"""

from __future__ import annotations

from dataclasses import dataclass

CATEGORIES = {
    "FC1": "System design issues",
    "FC2": "Inter-agent misalignment",
    "FC3": "Task verification",
}


@dataclass(frozen=True)
class FailureMode:
    code: str
    name: str
    category: str
    definition: str
    operationalisation: str
    structural: bool = False


FAILURE_MODES: tuple[FailureMode, ...] = (
    FailureMode(
        "FM-1.1", "Disobey task specification", "FC1",
        "An agent fails to follow the constraints or requirements of the task as specified.",
        "A draft answer was produced that breaks the Resolution spec: generated without any passage "
        "at or above the relevance threshold, a step without a [doc_id] citation, more than 8 steps, "
        "or a non-empty solution with no citations.",
    ),
    FailureMode(
        "FM-1.2", "Disobey role specification", "FC1",
        "An agent acts outside its assigned role or takes over another agent's responsibility.",
        "Intake's recorded output carries remediation fields (steps or a solution). Not applicable "
        "to the single-agent baseline, which has no role separation to violate.",
        structural=True,
    ),
    FailureMode(
        "FM-1.3", "Step repetition", "FC1",
        "Unnecessary repetition of steps or actions already completed.",
        "Duplicate remediation steps (after normalisation), or the same node executed more than once.",
    ),
    FailureMode(
        "FM-1.4", "Loss of conversation history", "FC1",
        "Context established earlier is unexpectedly lost or truncated.",
        "A field produced by an upstream node is missing from the final state.",
        structural=True,
    ),
    FailureMode(
        "FM-1.5", "Unaware of stopping conditions", "FC1",
        "The system fails to recognise when the task is complete and should stop, or never stops.",
        "The run ended without a terminal outcome (neither delivered nor escalated).",
        structural=True,
    ),
    FailureMode(
        "FM-2.1", "Conversation reset", "FC2",
        "An unexpected restart of the dialogue that loses progress.",
        "An earlier node re-executes after a later one (the trace order goes backwards).",
        structural=True,
    ),
    FailureMode(
        "FM-2.2", "Fail to ask for clarification", "FC2",
        "Proceeding on ambiguous or incomplete information instead of requesting clarification.",
        "An ambiguous, insufficient or multi-issue ticket was resolved autonomously instead of being "
        "returned to a human for clarification.",
    ),
    FailureMode(
        "FM-2.3", "Task derailment", "FC2",
        "Deviation from the intended objective towards an irrelevant or different task.",
        "The draft answers a different problem: its primary cited article is not the ticket's gold "
        "article (or the ticket has no documented fix at all).",
    ),
    FailureMode(
        "FM-2.4", "Information withholding", "FC2",
        "An agent holds information relevant to others but does not share it.",
        "Intake extracted an error code that never reached the retrieval query.",
    ),
    FailureMode(
        "FM-2.5", "Ignored other agent's input", "FC2",
        "Input or recommendations from another agent are disregarded.",
        "The answer cites a document Retrieval never returned, or reports confidence at or above the "
        "naive threshold while Retrieval's best match is below the relevance threshold.",
    ),
    FailureMode(
        "FM-2.6", "Reasoning-action mismatch", "FC2",
        "The stated reasoning is inconsistent with the actions actually taken.",
        "The answer's declared citations disagree with the documents its steps actually cite, a "
        "non-zero confidence accompanies an empty answer, or the escalation flag contradicts the verdict.",
    ),
    FailureMode(
        "FM-3.1", "Premature termination", "FC3",
        "Ending the task before its objective is met or all necessary information is exchanged.",
        "An empty answer was delivered to the user, or a ticket with a documented fix never reached "
        "retrieval because triage stopped it.",
    ),
    FailureMode(
        "FM-3.2", "No or incomplete verification", "FC3",
        "Outputs are not checked, or checked only partially, before being finalised.",
        "A flawed output (wrong or empty answer, or one policy required a human to handle) was delivered "
        "with no independent verification of grounding, citations and policy - no gate at all, or only "
        "the answering model's own confidence.",
    ),
    FailureMode(
        "FM-3.3", "Incorrect verification", "FC3",
        "Verification is performed but fails to catch errors or approves a flawed output.",
        "The independent Governance gate ran and approved delivery of an answer that was wrong or that "
        "policy required a human to handle. Not applicable to variants without an independent gate.",
    ),
)

MODE_CODES: tuple[str, ...] = tuple(mode.code for mode in FAILURE_MODES)
MODES_BY_CODE: dict[str, FailureMode] = {mode.code: mode for mode in FAILURE_MODES}


def modes_in_category(category: str) -> tuple[str, ...]:
    return tuple(mode.code for mode in FAILURE_MODES if mode.category == category)
