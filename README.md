# OPS-AGENT

**Multi-Agent IT Incident Resolution with Deterministic Governance**

D. Y. Patil College of Engineering and Technology, Kolhapur — CSE (AI & ML), 2026-27.

---

## Status: Week 5-7 — Agent & Pipeline Design ✅

This repository currently implements **Phase 3** of the project schedule only.

| Phase | Weeks | Status |
|---|---|---|
| Literature review & requirement analysis | 1-2 | Complete (synopsis) |
| Data acquisition & preprocessing | 3-4 | Seed corpus in place; real datasets pending |
| **Agent & pipeline design** | **5-7** | **Complete — this codebase** |
| Calibration module | 8-9 | Not started (deliberately) |
| Escalation logic, audit trail & MAST labeling | 10-12 | Not started |
| Comparative evaluation | 13-14 | Not started |
| Deployment & documentation | 15-16 | Not started |

Confidence scores in this milestone are **raw and uncalibrated** by design.
Temperature scaling and split-conformal prediction belong to Week 8-9 and are
absent on purpose (CLAUDE.md: *No Early Optimization*).

---

## Architecture

```
        START
          │
     ┌────▼────┐
     │ INTAKE  │  raw ticket → category, priority, keywords, entities
     └────┬────┘
          │  route_after_intake
   ┌──────┴───────────────┐
   │ (triaged)            │ (unintelligible)
┌──▼────────┐             │
│ RETRIEVAL │  semantic search over the KB (Chroma + MiniLM)
└──┬────────┘             │
   │  route_after_retrieval
   │                      │
   │ (grounded)  (no evidence)
┌──▼─────────┐            │
│ RESOLUTION │  cited remediation + RAW confidence
└──┬─────────┘            │
   │                      │
┌──▼──────────────────────▼──┐
│      GOVERNANCE            │  deterministic 7-check gate
└──┬──────────────────┬──────┘
   │ SAFE             │ ESCALATE / BLOCKED
┌──▼──────┐      ┌────▼─────┐
│ DELIVER │      │ ESCALATE │
└────┬────┘      └────┬─────┘
     └────── END ─────┘
```

**Two rules are enforced by graph topology, not by prompt wording:**

1. The Resolution Agent is **unreachable without retrieved evidence**. If
   retrieval finds nothing above the relevance threshold, control skips straight
   to Governance. No prompt change can bypass this.
2. **Governance is the only path to a terminal node.** Nothing reaches the user
   without passing the gate.

### Why Governance is not an LLM

The Governance Agent is a **deterministic rule engine**. That is the meaning of
"Deterministic Governance" in the project title. A decision that must be
auditable, reproducible and defensible cannot rest on a stochastic model whose
own confidence the literature shows to be miscalibrated. The same state always
yields the same verdict, and every verdict records its reasons.

| Check | Rule |
|---|---|
| G1 grounded | At least one passage retrieved above the relevance threshold |
| G2 cited | Minimum citations met, and every cited doc was actually retrieved |
| G3 confident | Raw confidence ≥ threshold *(Week 8-9 swaps in a calibrated value here)* |
| G4 complete | A non-empty solution and at least one actionable step exist |
| G5 priority gate | P1 always goes to a human, whatever the confidence |
| G6 category gate | `security` and `data_loss` always go to a human |
| G7 intake clarity | The ticket was understood well enough to be answered |

---

## Project layout

```
OPS-AGENT/
├── CLAUDE.md                    # coding conventions (read first)
├── requirements.txt
├── pyproject.toml
├── .env.example                 # copy to .env
├── data/
│   ├── knowledge_base/          # 30 seed IT runbook articles (markdown + frontmatter)
│   └── chroma/                  # persisted vector index (git-ignored)
├── src/ops_agent/
│   ├── config.py                # every tunable knob, env-driven
│   ├── state.py                 # OpsAgentState (flat TypedDict)
│   ├── graph.py                 # the LangGraph state graph
│   ├── agents/                  # one module per agent
│   │   ├── intake.py
│   │   ├── retrieval.py
│   │   ├── resolution.py
│   │   └── governance.py
│   ├── prompts/                 # versioned prompts, one module per agent
│   ├── knowledge/               # loader, embeddings, Chroma vector store
│   └── llm/                     # Gemini | Ollama | deterministic Mock
├── scripts/
│   ├── ingest_kb.py             # build the vector index
│   └── verify_pipeline.py       # state-transition verification
└── tests/                       # pytest, per agent then the full graph
```

---

## Setup

```bash
# Windows
py -3.10 -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env          # cp on macOS/Linux
```

The pipeline runs **fully offline** out of the box: with no `GEMINI_API_KEY`
set, the LLM layer selects the deterministic `MockProvider` and embeddings run
locally. Add your key to `.env` to switch the reasoning agents to Gemini.

```bash
# Build the vector index
python scripts/ingest_kb.py --probe "vpn error 809"

# Verify state transitions across all four agents
python scripts/verify_pipeline.py

# Run the test suite
pytest
```

---

## Running a ticket

```python
from ops_agent.graph import run_ticket

final = run_ticket("User cannot connect to the VPN, error code 809")

print(final["category"])           # network
print(final["confidence_score"])   # raw, uncalibrated
print(final["escalation_flag"])    # deterministic governance decision
print(final["final_response"])
print(final["agent_trace"])        # append-only, one entry per node
```

---

## Embeddings and retrieval

| Backend | When it is used | Quality |
|---|---|---|
| `all-MiniLM-L6-v2` (sentence-transformers) | Default, once installed | Semantic — the intended path |
| `TfidfEmbedder` | Automatic fallback if sentence-transformers or its model download is unavailable | Lexical — ranks correctly, weaker on paraphrase |

The fallback exists so a locked-down or air-gapped machine degrades *gracefully*
rather than returning noise. A TF-IDF vector only means something against the
vocabulary it was fitted on, so that vocabulary is persisted next to the Chroma
collection and restored automatically.

**With the TF-IDF fallback the pipeline escalates nearly everything.** Similarity
scores are lower, so raw confidence rarely clears the 0.70 threshold. That is
correct fail-safe behaviour, not a defect — install sentence-transformers to see
the autonomous-resolution path open up:

```bash
pip install sentence-transformers
python scripts/ingest_kb.py --rebuild --probe "vpn error 809"
```

## LLM provider selection

| `OPS_LLM_PROVIDER` | Behaviour |
|---|---|
| *(unset)* | Gemini if `GEMINI_API_KEY` is present, otherwise `mock` |
| `gemini` | Gemini API — primary, per the synopsis |
| `ollama` | Local open-weight model — the deterministic fallback |
| `mock` | Rule-based, offline, byte-identical every run |

`MockProvider` is not a throwaway stub: it is the reproducibility backstop that
makes execution traces replayable for the Week 13-14 comparative evaluation, and
it keeps the whole test suite hermetic.

---

## Design notes

`docs/DESIGN_DECISIONS.md` records the nine architectural decisions taken in
this milestone and the reasoning behind each — written to be reusable in the
methodology chapter of the report.

## What comes next (do not start early)

- **Week 8-9** — record raw scores on the calibration split, fit a single
  temperature, evaluate with Expected Calibration Error and reliability diagrams.
  Only check **G3** changes; the other six checks are calibration-independent.
- **Week 10-12** — threshold selection on the calibration set, persist
  `agent_trace` to SQLite/PostgreSQL as an immutable audit trail, MAST labeling.
- **Week 13-14** — four pipeline variants compared on the same tickets.
- **Week 15-16** — FastAPI dashboard, Docker, Kubernetes.
