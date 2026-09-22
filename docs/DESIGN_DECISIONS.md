# OPS-AGENT — Design Decisions (Weeks 5-16)

Decisions taken while implementing the project schedule, with the reasoning
behind each. D1-D9 cover Phase 3 (Weeks 5-7); D10-D24 cover Phases 2 and 4-8
(the rest of Weeks 3-4, and Weeks 8-16). Useful material for the methodology
chapter of the report and the research paper in `docs/research/`.

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

## Phase 2 completion (Weeks 3-4)

### D10. A purpose-built labeled evaluation set, with the public datasets kept separate

The comparative evaluation needs, for every ticket, the correct knowledge-base
article (to judge an answer) and whether policy requires a human (to judge an
escalation). Neither Kaggle dataset named in the synopsis carries labels tied
to this project's knowledge base, so neither can say whether an answer was
right. The evaluation set is therefore 430 tickets written for this project:
300 routine tickets (ten per runbook article, each naming its gold article)
and 130 adversarial tickets across eight failure-inducing types (ambiguous,
insufficient, multi-issue, out-of-KB, disguised security, disguised data loss,
P1 outages, prompt injection), as synopsis Phase 2 prescribes. The tickets were
authored with LLM assistance and are clearly marked synthetic. The Kaggle
datasets get their own adapter and script (`scripts/prepare_public_datasets.py`)
and are used for what their labels support: Intake agreement and
out-of-distribution escalation behaviour.

### D11. The escalation ground truth is a written rule, not a per-ticket judgement

`should_escalate` is derived by `policy_should_escalate`: security or data-loss
category, P1 priority, ambiguous / insufficient / multi-issue / injection, or no
documented fix. Writing the rule down before any variant ran is what keeps the
evaluation criteria frozen in advance (synopsis Phase 1) and makes the label
auditable and testable.

### D12. Stratified 70:15:15 splits with explicit roles

Splits are stratified by in-KB category and adversarial type so the small
calibration split always contains every kind of ticket. Train = development
only (the formative MAST analysis, D20); calibration = fitting the temperature
and the threshold; test = never touched until the comparison. Ties in the
largest-remainder allocation are broken by the seeded RNG so no split is
systematically favoured.

## Phase 4 - Calibration (Weeks 8-9)

### D13. One temperature, applied to the logit of the reported confidence

The Resolution Agent reports a single probability that its answer is correct,
so binary temperature scaling is used: p' = sigmoid(logit(p) / T), with T fitted
by minimising negative log-likelihood on the calibration split (Guo et al.,
2017). Exactly one parameter, as the synopsis specifies. The map is monotone,
so it cannot change which tickets rank highest (AUROC is unchanged); it changes
what the numbers mean, which is what a threshold needs.

A known limitation is recorded rather than hidden: with no bias term, the map
has a fixed point at 0.5 and cannot move a score across it. Under the TF-IDF
fallback nearly all raw scores sit below 0.5 while most answers are correct, so
the NLL optimum runs to the search bound (T = 20) and every score collapses
towards 0.5. The profile flags this (`temperature_at_search_bound`), and the
paper discusses Platt scaling as the natural next step.

### D14. A calibration node, and the raw score is never overwritten

Calibration is a node between Resolution and Governance, not a change inside
either agent, exactly as D6 promised. It writes `calibrated_confidence` next to
the untouched raw `confidence_score`, because the audit trail and the
evaluation both need the pair. It calls no model and has no prompt.

## Phase 5 - Escalation logic and audit trail (Weeks 10-12)

### D15. Only check G3 changes between naive and calibrated governance

In calibrated mode G3 compares the calibrated confidence with a threshold from
the calibration profile; in raw mode it compares the raw confidence with 0.70.
G1, G2 and G4-G7 are byte-identical in both modes, and a test asserts it. This
is what makes V3-versus-V4 a clean comparison of the confidence signal alone.

### D16. The threshold is selected with a finite-sample risk guarantee

"Selected by testing different values on the calibration set" is implemented
as Learn-then-Test fixed-sequence testing (Angelopoulos et al., 2025) over a
fixed, data-independent grid. The controlled quantity is the Unsafe Resolution
Rate - the share of ALL tickets that would be resolved autonomously and
unsafely - because its loss is monotone in the threshold, which makes the
fixed-sequence procedure exactly valid. Guarantee: URR <= alpha with probability
>= 1 - delta (defaults 0.05 / 0.10, fixed before the evaluation ran). Conformal
risk control (a split-conformal method; Angelopoulos et al., 2024) is available
as the in-expectation alternative. An earlier draft controlled the conditional
risk among delivered tickets; it was replaced because its data-dependent start
point breaks the exactness of fixed-sequence testing.

### D17. Fail closed

If no threshold can be certified, the profile stores 1.01 and G3 fails for every
ticket: nothing is resolved autonomously. A governance gate that silently
reverts to a default threshold when its evidence is insufficient is not a gate.

### D18. A calibration profile only applies to the configuration it was fitted on

A profile carries a fingerprint: provider, model, embedder, prompt versions,
knowledge-base hash, top-k and relevance threshold. `auto` governance mode
applies the first profile whose fingerprint matches the running configuration
and otherwise falls back to raw governance, recording why. Several profiles can
coexist (one per embedder) so the container image, which uses TF-IDF, and a
workstation with MiniLM each get the right one. This prevents the most likely
real-world misuse: applying a temperature fitted on one model to another.

### D19. Audit trail: append-only in SQL, tamper-evident by hash chain

Every trace event and one decision summary per run are written to one SQLite
table. Triggers abort UPDATE and DELETE; each row stores SHA-256(previous hash +
canonical JSON of the row), so any edit made outside the application breaks the
chain from that row on, and `verify()` names the row. Canonical JSON keeps the
hashes deterministic across machines. The schema ports to PostgreSQL unchanged;
SQLite's single writer is why the Kubernetes deployment runs one replica.

### D20. MAST labeling: operationalised detectors, two views, and a formative pass

Each of the 14 MAST modes (Cemri et al., 2025) has a written operationalisation
for this pipeline (`mast/taxonomy.py`) and a deterministic detector. Modes the
architecture makes impossible are still reported, as structural zeros. Two
views are counted: a failure anywhere in the trace, and a failure that reached
the user; a governance layer can only change the second. FM-3.2/3.3 are
labelled only when a flawed output was actually delivered, so the absence of a
gate is not counted as a failure when nothing went wrong.

The detectors were first run on the TRAIN split only (formative iteration,
`reports/evaluation/formative_iteration1_mast.json`). That pass found FM-2.6
(reasoning-action mismatch) in 191 of 302 traces: the offline provider cited
every retrieved article, not only those its steps used, contrary to the
Resolution prompt. It was corrected before the comparative evaluation. Human
double annotation and the LLM annotator are supported by
`scripts/mast_labeling_kit.py`; the human labels themselves are team work that
cannot be automated.

## Phases 7-8 - Evaluation and deployment (Weeks 13-16)

### D21. Four variants that differ in one thing at a time

V1 single agent (one call, raw-text retrieval, no relevance filter, self-check
at 0.70); V2 the four agents with no gate; V3 the gate with raw confidence; V4
the gate with calibrated confidence and a certified threshold. V1-V3 reuse the
same agents and provider, and V4 differs from V3 only in G3, so each step in
the sequence isolates one design choice. Because governance is a pure function
of the state, V4's decisions can also be REPLAYED from V3 traces; the
evaluation checks that replay and a real V4 run agree exactly, and uses replay
for the alpha-sensitivity analysis.

### D22. Primary population = everything not used for fitting; repeated splits

The synopsis asks for the variants to be tested "on the full dataset". The only
data used to fit anything is the calibration split, so the primary population
is every other ticket (n = 366), which gives the paired tests usable power; the
15% test split alone is also reported. Ten repeated stratified splits show how
much the results depend on which 64 tickets happened to calibrate, and let the
risk guarantee be checked empirically (it should fail in at most delta of them).

### D23. Deployment: small image, fail-safe defaults

The container installs the runtime requirements only and uses the TF-IDF
embedder unless built with `WITH_TRANSFORMERS=true`; it ships the calibration
profiles and the evaluation summaries, runs as a non-root user and keeps the
vector index and audit database on a volume. Kubernetes manifests validate
against the upstream schemas (`kubeconform -strict`). The API is a thin layer:
every decision still goes through the same compiled graph and is audited.

### D24. Retrieval breaks ties by document id

Chroma returns equally distant documents in an order that can change between
processes. With MiniLM exact ties practically never happen, but with the
sparse TF-IDF fallback a query that shares no vocabulary with the knowledge
base ("It's broken.") ties every article at similarity 0, and the single-agent
baseline, which has no relevance filter, then received a different set of
irrelevant articles on each run. Its decisions were unaffected, but its
retrieval-quality and token figures varied in the third decimal. The store now
fetches a candidate pool (the whole 30-article collection) and sorts it by
(distance, doc id), so every reported number, not just the decisions,
reproduces exactly; `tests/test_knowledge.py` pins the behaviour.

---

## Open items after Week 16

- **Human MAST annotation.** Two annotators label the sample produced by
  `scripts/mast_labeling_kit.py sample`; then compute kappa and validate the LLM
  annotator. Until then the MAST numbers come from the rule-based annotator only.
- **Run with the real model.** Every reported number comes from the offline
  deterministic provider. `OPS_LLM_PROVIDER=gemini python scripts/run_evaluation.py`
  repeats the whole study with Gemini; recalibrate first (`scripts/calibrate.py`).
- **Public datasets.** Download the two Kaggle datasets and run
  `scripts/prepare_public_datasets.py --evaluate 300`.
- **Calibration set size.** With 64 calibration tickets the guarantee is
  expensive; a larger labeled calibration set is the most direct way to raise
  automation at the same certified risk.
