# OPS-AGENT — Design Decisions (Week 5-7)

Decisions taken while implementing Phase 3 of the project schedule, with the
reasoning behind each. Useful material for the methodology chapter of the report.

---

## D1. Flat `TypedDict` state, not per-agent namespaces

`OpsAgentState` is a single flat `TypedDict`. LangGraph merges each node's
returned dictionary into the state key by key, so a flat shape keeps the merge
trivial and keeps `confidence_score` and `escalation_flag` — the two fields the
research question turns on — at the top level, as CLAUDE.md requires.

Nested per-agent sub-dictionaries were considered and rejected: they express
ownership more clearly but bury the governance fields and complicate reducers.

Two channels are append-only via `operator.add`: `agent_trace` and `errors`.
Nodes contribute to them without clobbering earlier entries. `agent_trace` is
the seed of the Week 10-12 immutable audit trail — the audit work becomes a
persistence layer over an existing structure rather than a retrofit.

## D2. The Governance Agent is deterministic, not an LLM

This is the meaning of "Deterministic Governance" in the project title.

The literature this project builds on (Guo et al. 2017; the LLM calibration
work in §2.7 of the synopsis) shows that a model's own verbalised confidence is
an unreliable signal. A governance layer whose job is to catch exactly that
failure cannot itself be a stochastic model with the same weakness. So the
Governance Agent is a pure rule engine: seven checks, each a pure function of
the state. The same state always produces the same verdict, and the reason for
every verdict is recorded.

This also makes the Week 13-14 comparison meaningful. The difference between
the naively-governed and calibration-governed variants will be one number — the
confidence fed into check G3 — and not a difference in model behaviour.

`tests/test_governance.py::test_governance_does_not_call_an_llm` enforces this
architecturally: the test fails if the node ever reaches for a provider.

## D3. Grounding is enforced by graph topology, not by prompt wording

CLAUDE.md requires that the Resolution Agent never answer without retrieved
context. A prompt instruction is not an enforcement mechanism — it can be
undone by a later prompt edit.

Instead, `route_after_retrieval` sends ungrounded tickets straight from
Retrieval to Governance. The Resolution Agent is unreachable without evidence.
The same rule is additionally re-checked inside `resolution_node`, so it also
holds when the node is called directly in a test or a future pipeline variant.

Governance is likewise the only path to a terminal node: nothing reaches the
user without passing the gate.

## D4. Retrieval discards weak matches rather than passing them on

A passage retrieved at very low similarity is worse than no passage at all — it
gives the Resolution Agent something plausible-looking to anchor on, which is
precisely how grounded-looking hallucination happens. `min_relevance` filters
these out, and a ticket with nothing above the threshold is marked ungrounded.

## D5. Citations are verified against what was actually retrieved

The Resolution Agent's claimed citations are intersected with the set of
retrieved `doc_id`s. A citation to a document that was never retrieved is a
fabrication: it is stripped, confidence is zeroed, and the discard is recorded
in the trace as `hallucinated_citations`. Governance then fails check G2
independently. This is a MAST "task verification" failure mode caught at two
layers.

## D6. Confidence stays raw and uncalibrated

Per CLAUDE.md's *No Early Optimization* rule, no temperature scaling and no
conformal prediction appear anywhere in this milestone. Every trace entry that
carries a confidence value also carries `confidence_is_calibrated: false`, so
Week 5-7 traces are unambiguously identifiable in the later evaluation.

Week 8-9 changes **only the value that check G3 reads**. Checks G1, G2 and
G4-G7 are calibration-independent by construction.

## D7. Three LLM backends behind one interface

Agents depend on `LLMProvider`, never on an SDK. Gemini is primary per the
synopsis, Ollama is the local fallback, and `MockProvider` is a deterministic
rule-based backend.

`MockProvider` is not a throwaway stub. It is the reproducibility backstop:
it makes the whole pipeline and the entire test suite run offline with
byte-identical output, which is what makes execution traces replayable for the
Week 13-14 comparison. It parses the same `<TICKET>` and `<CONTEXT>` prompt
blocks the real providers receive, so switching to Gemini changes the quality
of the answer, not the shape of the state.

## D8. Embeddings: MiniLM primary, TF-IDF fallback

`all-MiniLM-L6-v2` via sentence-transformers is the primary embedder: local,
free, offline once cached, and deterministic.

The fallback is a TF-IDF vectoriser (`TfidfEmbedder`) rather than a random
hashing embedder. A hashing embedder has no inverse-document-frequency
weighting, so common words dominate and ranking becomes close to noise — it was
observed ranking an unrelated Windows Update article above the correct VPN
article for a VPN query. TF-IDF with sublinear term frequency and unigram plus
bigram tokens ranks correctly on the same query. The system therefore degrades
gracefully rather than badly when the transformer model is unavailable.

A TF-IDF vector is only meaningful against the vocabulary it was fitted on, so
the fitted vocabulary is persisted next to the Chroma collection as
`<collection>.embedder.json` and restored when the index is reopened.

## D9. Seed knowledge base

30 IT runbook articles, written for this milestone, covering all seven incident
categories. They are markdown with YAML frontmatter, with a consistent
Symptom / Cause / Resolution / Escalate-if structure — the numbered resolution
steps are what the pipeline turns into cited remediation steps.

This is scaffolding for Phase 3, not the Phase 2 deliverable. When the Kaggle
datasets land, point `OPS_KB_DIR` at the real corpus; the loader, embedder,
store and agents are unchanged.

---

## Open items for the next milestone

- Threshold selection is currently a configured default (0.70). Week 10-12
  requires selecting it empirically on the calibration split, not by choice.
- `agent_trace` lives in memory only. Week 10-12 persists it to SQLite or
  PostgreSQL as an append-only audit log.
- The evaluation harness (component E in the synopsis) is not built yet; it is
  Week 13-14 work and operates on traces after the fact.
