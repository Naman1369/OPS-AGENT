"""Governance Agent policy text.

The Governance Agent in OPS-AGENT is DETERMINISTIC by design -- it is a rule engine,
not a language model. That is the point of the project title: a governance decision
that is reproducible, auditable and explainable cannot itself depend on a stochastic
model whose confidence is known to be miscalibrated.

The text below is therefore documentation of the policy, not a model prompt. It is
recorded in the trace so that every run states which policy version judged it, and it
is the specification that ``agents/governance.py`` implements check for check.
"""

PROMPT_VERSION = "governance-policy-v1"

POLICY_TEXT = """\
GOVERNANCE POLICY v1 -- OPS-AGENT
Scope: Week 5-7. Operates on RAW, uncalibrated resolution confidence.
Temperature scaling and split-conformal prediction arrive in Week 8-9 and will
replace check G3 only; every other check is unchanged by calibration.

A ticket is returned to the user autonomously only if ALL checks below pass.
Any failed check sets escalation_flag = True and routes the ticket to a human.

G1  GROUNDED
    At least one knowledge-base passage was retrieved at or above the minimum
    relevance threshold. An answer with no evidence behind it is never returned.

G2  CITED
    The resolution cites at least the configured minimum number of doc_ids, and
    every cited doc_id appears in the set of documents actually retrieved.
    A citation to a document that was not retrieved is a fabrication.

G3  CONFIDENT
    The raw confidence reported by the Resolution Agent is at or above the
    configured threshold.

G4  COMPLETE
    A non-empty solution and at least one actionable step were produced.

G5  PRIORITY GATE
    Tickets at an always-escalate priority (P1 by default) always go to a human,
    whatever the confidence. Blast radius outranks confidence.

G6  CATEGORY GATE
    Tickets in an always-escalate category (security, data_loss) always go to a
    human. These carry compliance and irreversibility risk that no autonomous
    confidence score may override.

G7  INTAKE CLARITY
    Intake confidence is not so low that the ticket was never understood well
    enough to be answered.

VERDICTS
    SAFE_TO_RESOLVE   all checks passed; deliver the answer to the user.
    ESCALATE_TO_HUMAN one or more checks failed; hand to an engineer with the
                      draft answer and the reasons attached, so the escalation is
                      useful rather than a dead end.
    BLOCKED           the pipeline errored before a resolution existed.

Every decision records the check results, the reasons, the confidence, the
threshold in force, and the retrieved doc_ids. Nothing is decided off the record.
"""
