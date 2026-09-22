# OPS-AGENT

**Multi-Agent IT Incident Resolution with Deterministic Governance**

D. Y. Patil College of Engineering and Technology, Kolhapur — CSE (AI & ML), 2026-27.

---

## Status: all sixteen weeks complete ✅

| Phase | Weeks | Status | Where |
|---|---|---|---|
| Literature review & requirement analysis | 1-2 | Complete | synopsis; verified references in `docs/research/REFERENCES.md` |
| Data acquisition & preprocessing | 3-4 | Complete | `data/eval/` (430 labeled tickets), `scripts/build_dataset.py`, Kaggle adapter |
| Agent & pipeline design | 5-7 | Complete | `src/ops_agent/agents/`, `graph.py` |
| Calibration module | 8-9 | Complete | `src/ops_agent/calibration/`, `scripts/calibrate.py` |
| Escalation logic, audit trail & MAST labeling | 10-12 | Complete* | `calibration/risk_control.py`, `audit/`, `mast/`, `scripts/mast_labeling_kit.py` |
| Comparative evaluation | 13-14 | Complete | `evaluation/`, `scripts/run_evaluation.py`, `reports/evaluation/` |
| Deployment & documentation | 15-16 | Complete | `api/`, `Dockerfile`, `deploy/k8s/`, `docs/research/` |

\* The **human** part of MAST labeling — two annotators on 100-150 traces — cannot be
automated. The kit that samples the traces, writes the blank annotation sheets and the
codebook, and computes Cohen's kappa is ready; the team fills in the sheets.

All reported results use the **offline deterministic provider** (so every number is
exactly reproducible). The same scripts run unchanged against Gemini — see
[Running with Gemini](#running-with-gemini).

---

## Headline result

Held-out tickets (n = 366), MiniLM retrieval, canonical split — full tables in
`reports/evaluation/mock-minilm/REPORT.md`:

| Variant | Automation | Correct autonomous | Unsafe Resolution Rate |
|---|---:|---:|---:|
| V1 Single agent, raw threshold 0.70 | 53.6% | 44.3% | 9.3% |
| V2 Four agents, no governance | 100.0% | 58.2% | 41.8% |
| V3 Governed, raw threshold 0.70 | 36.9% | 32.0% | 4.9% |
| **V4 Governed, calibrated + risk-controlled threshold** | 8.7% | 8.5% | **0.3%** |

V4's URR is significantly lower than every baseline (exact McNemar, Holm-adjusted
p < 0.001). Temperature scaling cut held-out ECE from 0.148 to 0.057. Across ten
repeated splits the certified bound (URR ≤ 5% with 90% confidence) was never
exceeded; mean automation was 18.3%. The price of the guarantee is automation — see
the paper's discussion and the alpha-sensitivity table.

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
┌──▼──────────┐           │
│ CALIBRATION │  temperature-scaled confidence (calibrated mode only)
└──┬──────────┘           │
┌──▼──────────────────────▼──┐
│      GOVERNANCE            │  deterministic 7-check gate
└──┬──────────────────┬──────┘
   │ SAFE             │ ESCALATE / BLOCKED
┌──▼──────┐      ┌────▼─────┐
│ DELIVER │      │ ESCALATE │
└────┬────┘      └────┬─────┘
     └────── END ─────┘            every event → append-only, hash-chained audit trail
```

**Two rules are enforced by graph topology, not by prompt wording:** the Resolution
Agent is unreachable without retrieved evidence, and Governance is the only path to a
terminal node.

### The seven governance checks

| Check | Rule |
|---|---|
| G1 grounded | At least one passage retrieved above the relevance threshold |
| G2 cited | Minimum citations met, and every cited doc was actually retrieved |
| G3 confident | raw mode: raw confidence ≥ 0.70 · calibrated mode: calibrated confidence ≥ the certified threshold |
| G4 complete | A non-empty solution and at least one actionable step exist |
| G5 priority gate | P1 always goes to a human, whatever the confidence |
| G6 category gate | `security` and `data_loss` always go to a human |
| G7 intake clarity | The ticket was understood well enough to be answered |

The Governance Agent is a **deterministic rule engine** — no LLM (a test enforces it).
Only **G3** differs between raw and calibrated governance.

### Calibrated governance in one paragraph

The Resolution Agent's raw confidence `p` is mapped to `p' = sigmoid(logit(p) / T)`,
with one temperature `T` fitted on the calibration split (Guo et al., 2017). The G3
threshold is then **selected on the calibration split with a guarantee**: Learn-then-Test
fixed-sequence testing picks the lowest threshold for which the Unsafe Resolution Rate
(share of all tickets resolved autonomously but wrongly or against policy) is ≤ alpha
with probability ≥ 1 − delta (defaults 0.05 / 0.10). If nothing can be certified the gate
**fails closed**. The result is stored as a *calibration profile* with a fingerprint of
the configuration it was fitted for (provider, model, embedder, prompts, knowledge base);
`auto` mode applies a profile only when the fingerprint matches.

---

## Project layout

```
OPS-AGENT/
├── CLAUDE.md                      coding conventions (read first)
├── requirements.txt               full development environment
├── requirements-runtime.txt       container / API only
├── Dockerfile · docker-compose.yml · deploy/k8s/   deployment (Weeks 15-16)
├── artifacts/calibration/         fitted calibration profiles (one per configuration)
├── data/
│   ├── knowledge_base/            30 IT runbook articles
│   └── eval/                      labeled evaluation set, splits, dataset card
├── src/ops_agent/
│   ├── state.py · config.py · graph.py
│   ├── agents/                    intake, retrieval, resolution, calibration, governance
│   ├── calibration/               metrics, temperature scaling, risk control, profiles
│   ├── audit/                     append-only hash-chained SQLite audit trail
│   ├── mast/                      MAST taxonomy, rule & LLM annotators, Cohen's kappa
│   ├── evaluation/                variants, harness, metrics, statistics, replay, figures
│   ├── data/                      schema, cleaning, stratified splits, Kaggle adapters
│   ├── api/                       FastAPI service + dashboard
│   ├── knowledge/                 loader, embeddings (MiniLM / TF-IDF), Chroma store
│   ├── llm/                       Gemini (google-genai) | Ollama | deterministic mock
│   └── prompts/                   versioned prompts
├── scripts/                       build_dataset · calibrate · run_evaluation · mast_labeling_kit
│                                  prepare_public_datasets · ingest_kb · verify_pipeline
├── reports/                       evaluation and calibration reports + figures
├── tests/                         219 pytest tests
└── docs/
    ├── DESIGN_DECISIONS.md        D1-D24, the reasoning behind every design choice
    ├── OPS-AGENT-Walkthrough.html plain-English walkthrough (with the research)
    └── research/                  research paper (DOCX + PDF), verified references
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

Everything runs **offline** out of the box: with no `GEMINI_API_KEY` the LLM layer uses
the deterministic `MockProvider`. The first MiniLM run downloads the model (~90 MB);
without it the TF-IDF fallback is used automatically.

```bash
pytest                                        # 219 tests, ~8 s
python scripts/verify_pipeline.py             # 54 state-transition checks
python scripts/build_dataset.py               # rebuild data/eval/ from data/eval/raw/
python scripts/calibrate.py --embedder minilm # fit T + certified threshold -> artifacts/calibration/
python scripts/run_evaluation.py --embedder minilm   # the full four-variant comparison (~2 min)
python scripts/run_evaluation.py --embedder tfidf    # the retrieval ablation
```

If you switch embedders, the persisted index in `data/chroma/` is detected as stale and
rebuilt automatically.

## Running a ticket

```python
from ops_agent.audit import AuditLog
from ops_agent.graph import compile_pipeline, run_ticket

pipeline = compile_pipeline()            # "auto": calibrated if a matching profile exists
print(pipeline.mode, "-", pipeline.note)

final = run_ticket("User cannot connect to the VPN, error code 809",
                   pipeline=pipeline, audit=AuditLog("data/audit/audit.sqlite3"))
print(final["confidence_score"], final.get("calibrated_confidence"))
print(final["governance_verdict"], final["policy_checks"])
print(final["final_response"])
```

## API, dashboard and deployment

```bash
uvicorn ops_agent.api.app:app --app-dir src --port 8000    # then open http://localhost:8000
docker compose up --build                                   # same, containerised
kubectl apply -k deploy/k8s                                 # Minikube / Kind (see below)
```

| Endpoint | Purpose |
|---|---|
| `GET /` | dashboard: ticket flow, checks, raw vs calibrated confidence, escalation history, evaluation |
| `POST /api/tickets` | run a ticket through the governed pipeline (audited) |
| `GET /api/tickets`, `GET /api/tickets/{id}` | decision history and full audit rows |
| `GET /api/audit/verify` | recompute the audit hash chain |
| `GET /api/calibration` | the calibration profile in force, or why none is |
| `GET /api/evaluation` | headline evaluation results |
| `GET /health` | liveness/readiness |

Minikube: `minikube image build -t ops-agent:1.0.0 .` then `kubectl apply -k deploy/k8s`
and open `http://$(minikube ip):30080`. The image uses the TF-IDF embedder by default
(small image) and ships a matching calibration profile; build with
`--build-arg WITH_TRANSFORMERS=true` for MiniLM. One replica only: SQLite has a single
writer and the audit chain must stay linear.

## Running with Gemini

```bash
# .env: OPS_LLM_PROVIDER=gemini, GEMINI_API_KEY=..., GEMINI_MODEL=gemini-2.5-flash
python scripts/calibrate.py --embedder minilm          # calibration is model-specific
python scripts/run_evaluation.py --embedder minilm --seeds 3
```

The Gemini provider uses the current `google-genai` SDK with temperature 0 and minimal
thinking for reproducibility, and records real token counts for the cost metrics. A
profile fitted on the mock never applies to Gemini: `auto` mode falls back to raw
governance until you recalibrate.

## MAST human annotation (team task)

```bash
python scripts/mast_labeling_kit.py sample --n 120    # reports/mast/annotator_A.csv, _B.csv, CODEBOOK.md
# two people fill the sheets independently (0/1 per failure mode)
python scripts/mast_labeling_kit.py agreement         # Cohen's kappa: A-B, and each vs the rule annotator
OPS_LLM_PROVIDER=gemini python scripts/mast_labeling_kit.py llm   # optional LLM annotator
```

## Public datasets (Kaggle)

```bash
kaggle datasets download -d adisongoh/it-service-ticket-classification-dataset -p data/raw --unzip
kaggle datasets download -d tobiasbueck/multilingual-customer-support-tickets -p data/raw --unzip
python scripts/prepare_public_datasets.py --evaluate 300
```

## Documentation

- `docs/research/OPS-AGENT_Research_Paper.docx` / `.pdf` — the research paper
  (design-science methodology, hypotheses, results, threats to validity, 60+ verified references).
- `docs/research/REFERENCES.md` — literature-review protocol, verification of every synopsis
  reference (with corrections), annotated bibliography.
- `docs/DESIGN_DECISIONS.md` — the 24 design decisions and their rationale.
- `docs/OPS-AGENT-Walkthrough.html` — plain-English walkthrough of the whole project.
- `reports/evaluation/*/REPORT.md`, `reports/calibration/*/` — generated results.
