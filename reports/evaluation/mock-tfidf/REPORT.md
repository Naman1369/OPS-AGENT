# OPS-AGENT comparative evaluation - mock:deterministic-rules-v1 / tfidf-fallback

Generated 2026-09-22T06:10:46+00:00 by `scripts/run_evaluation.py`. All numbers below are read from `summary.json` in this folder.

## Protocol

* 430 labeled tickets (`data/eval/dataset.jsonl`); stratified 70:15:15 splits, 10 repetitions (seeds 42-51); canonical seed 42.
* V4 fits one temperature and selects its G3 threshold on the calibration split only (LTT, alpha = 0.05, delta = 0.1).
* Primary population: held-out tickets = every ticket not in the calibration split (n = 366). The 15% test split is reported separately.
* Replay check: re-deciding V3 traces under each V4 profile reproduced the real V4 runs with 0 mismatches.

### Pre-specified hypotheses

* **H1** V4 has a lower Unsafe Resolution Rate (URR) than V1 (single agent, raw threshold 0.70).
* **H2** V4 has a lower URR than V3 (naively governed, raw threshold 0.70).
* **H3** V4 has a lower rate of user-facing MAST failures than V1 and V2.
* **H4** Temperature scaling lowers the Expected Calibration Error on held-out tickets.
* **H5** The risk guarantee holds: V4's held-out URR exceeds alpha in at most 10% of repeated splits.

## Main results (canonical split, held-out tickets)

| Variant | Automation | Correct autonomous | URR [95% CI] | Unnecessary escalation | Escalation recall | Answer accuracy (documented tickets) | ECE (gate) | User-facing MAST [95% CI] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V1 Single agent | 0.0% | 0.0% | 0.0% [0.0%, 0.0%] | 42.3% | 100.0% | 64.3% | 0.161 | 0.0% [0.0%, 0.0%] |
| V2 Ungoverned multi-agent | 100.0% | 27.9% | 72.1% [67.5%, 76.8%] | 0.0% | 0.0% | 83.9% | 0.298 | 72.1% [67.5%, 76.8%] |
| V3 Naively governed | 0.0% | 0.0% | 0.0% [0.0%, 0.0%] | 27.9% | 100.0% | 83.9% | 0.298 | 0.0% [0.0%, 0.0%] |
| V4 Calibration governed | 0.5% | 0.5% | 0.0% [0.0%, 0.0%] | 27.3% | 100.0% | 83.9% | 0.245 | 0.0% [0.0%, 0.0%] |

Outcome counts:

| Variant | Correct autonomous | Unsafe autonomous | Necessary escalation | Unnecessary escalation |
|---|---:|---:|---:|---:|
| V1 Single agent | 0 | 0 | 211 | 155 |
| V2 Ungoverned multi-agent | 102 | 264 | 0 | 0 |
| V3 Naively governed | 0 | 0 | 264 | 102 |
| V4 Calibration governed | 2 | 0 | 264 | 100 |

## Statistical tests (canonical split, held-out, paired)

**Unsafe autonomous resolution** - Cochran's Q = 792.00, df = 3, p = <0.001.

| V4 vs | Rate V4 | Rate other | Difference [95% CI] | Only V4 | Only other | McNemar p | Holm p |
|---|---:|---:|---:|---:|---:|---:|---:|
| V1 Single agent | 0.0% | 0.0% | 0.0% [0.0%, 0.0%] | 0 | 0 | 1.000 | 1.000 |
| V2 Ungoverned multi-agent | 0.0% | 72.1% | -72.1% [-76.5%, -67.5%] | 0 | 264 | <0.001 | <0.001 |
| V3 Naively governed | 0.0% | 0.0% | 0.0% [0.0%, 0.0%] | 0 | 0 | 1.000 | 1.000 |

**Correct autonomous resolution** - Cochran's Q = 300.16, df = 3, p = <0.001.

| V4 vs | Rate V4 | Rate other | Difference [95% CI] | Only V4 | Only other | McNemar p | Holm p |
|---|---:|---:|---:|---:|---:|---:|---:|
| V1 Single agent | 0.5% | 0.0% | 0.5% [0.0%, 1.4%] | 2 | 0 | 0.500 | 1.000 |
| V2 Ungoverned multi-agent | 0.5% | 27.9% | -27.3% [-32.0%, -23.0%] | 0 | 100 | <0.001 | <0.001 |
| V3 Naively governed | 0.5% | 0.0% | 0.5% [0.0%, 1.4%] | 2 | 0 | 0.500 | 1.000 |

**Any user-facing MAST failure** - Cochran's Q = 792.00, df = 3, p = <0.001.

| V4 vs | Rate V4 | Rate other | Difference [95% CI] | Only V4 | Only other | McNemar p | Holm p |
|---|---:|---:|---:|---:|---:|---:|---:|
| V1 Single agent | 0.0% | 0.0% | 0.0% [0.0%, 0.0%] | 0 | 0 | 1.000 | 1.000 |
| V2 Ungoverned multi-agent | 0.0% | 72.1% | -72.1% [-76.5%, -67.5%] | 0 | 264 | <0.001 | <0.001 |
| V3 Naively governed | 0.0% | 0.0% | 0.0% [0.0%, 0.0%] | 0 | 0 | 1.000 | 1.000 |

Note: under this project's operationalisation every failure that reaches the user is, by definition, also an unsafe autonomous resolution (FM-3.2/3.3 label exactly the flawed deliveries), so this aggregate test mirrors the URR test above. The informative MAST result is the per-mode table further down: which failures occur upstream, and which ones each variant lets through.

## Calibration (Weeks 8-9)

Fitted on 21 answered calibration tickets: T = 20.0000.

| Confidence | n | Accuracy | Mean confidence | ECE | MCE | Brier | NLL | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Calibration split - raw | 21 | 76.2% | 0.445 | 0.317 | 0.448 | 0.270 | 0.735 | 0.662 |
| Calibration split - scaled | 21 | 76.2% | 0.497 | 0.265 | 0.497 | 0.251 | 0.695 | 0.662 |
| Held-out - raw (V3/V4 answers) | 155 | 74.2% | 0.444 | 0.298 | 0.381 | 0.280 | 0.753 | 0.564 |
| Held-out - scaled (V4) | 155 | 74.2% | 0.497 | 0.245 | 0.248 | 0.251 | 0.696 | 0.564 |
| Held-out - V1 single agent raw | 366 | 49.7% | 0.497 | 0.161 | 0.350 | 0.218 | 0.628 | 0.803 |

Threshold selection (LTT): threshold = 0.505 (certified); on the calibration split it auto-resolves 0 of 64 tickets with 0 unsafe (URR upper bound 3.5% at 90% confidence).

## Robustness across repeated splits

| Variant | Population | Automation mean (sd) | URR mean (sd) | URR max | Correct autonomous mean |
|---|---|---:|---:|---:|---:|
| V1 Single agent | heldout | 0.0% (0.0%) | 0.0% (0.0%) | 0.0% | 0.0% |
| V2 Ungoverned multi-agent | heldout | 100.0% (0.0%) | 73.0% (0.7%) | 74.0% | 27.0% |
| V3 Naively governed | heldout | 0.0% (0.0%) | 0.0% (0.0%) | 0.0% | 0.0% |
| V4 Calibration governed | heldout | 1.5% (2.2%) | 0.3% (0.7%) | 1.6% | 1.1% |
| V1 Single agent | test | 0.0% (0.0%) | 0.0% (0.0%) | 0.0% | 0.0% |
| V2 Ungoverned multi-agent | test | 100.0% (0.0%) | 72.7% (4.1%) | 78.1% | 27.3% |
| V3 Naively governed | test | 0.0% (0.0%) | 0.0% (0.0%) | 0.0% | 0.0% |
| V4 Calibration governed | test | 1.2% (2.5%) | 0.0% (0.0%) | 0.0% | 1.2% |

Guarantee check (H5): V4 held-out URR exceeded alpha = 0.05 in 0 of 10 splits (test split only: 0 of 10); 0 split(s) could not certify any threshold. Temperatures ranged 20.000-20.000; thresholds 0.500-0.505.

## Sensitivity to the risk target (canonical split, replayed)

| Method | alpha | Threshold | Certified | Automation | URR | Correct autonomous |
|---|---:|---:|---|---:|---:|---:|
| LTT | 0.02 | 1.010 | no | 0.0% | 0.0% | 0.0% |
| LTT | 0.05 | 0.505 | yes | 0.5% | 0.0% | 0.5% |
| LTT | 0.10 | 0.500 | yes | 4.9% | 1.4% | 3.6% |
| LTT | 0.15 | 0.495 | yes | 31.1% | 9.0% | 22.1% |
| LTT | 0.20 | 0.005 | yes | 39.9% | 12.3% | 27.6% |
| CRC | 0.02 | 0.505 | yes | 0.5% | 0.0% | 0.5% |
| CRC | 0.05 | 0.500 | yes | 4.9% | 1.4% | 3.6% |
| CRC | 0.10 | 0.495 | yes | 31.1% | 9.0% | 22.1% |
| CRC | 0.15 | 0.005 | yes | 39.9% | 12.3% | 27.6% |
| CRC | 0.20 | 0.005 | yes | 39.9% | 12.3% | 27.6% |

## Resolution quality and classification (held-out)

| Variant | Retrieval recall@k | MRR | Top-1 answer accuracy | ROUGE-L | Category acc. | Category macro-F1 | Priority acc. |
|---|---:|---:|---:|---:|---:|---:|---:|
| V1 Single agent | 82.0% | 0.722 | 64.3% | 0.573 | 64.2% | 0.634 | 64.8% |
| V2 Ungoverned multi-agent | 42.8% | 0.417 | 40.6% | 0.822 | 64.2% | 0.634 | 64.8% |
| V3 Naively governed | 42.8% | 0.417 | 40.6% | 0.822 | 64.2% | 0.634 | 64.8% |
| V4 Calibration governed | 42.8% | 0.417 | 40.6% | 0.822 | 64.2% | 0.634 | 64.8% |

## MAST failure modes (held-out; occurred / reached the user)

| Mode | V1 Single agent | V2 Ungoverned multi-agent | V3 Naively governed | V4 Calibration governed |
|---|---:|---:|---:|---:|
| FM-1.1 Disobey task specification | 212 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| FM-1.2 Disobey role specification | n/a | 0 / 0 | 0 / 0 | 0 / 0 |
| FM-1.3 Step repetition | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| FM-1.4 Loss of conversation history | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| FM-1.5 Unaware of stopping conditions | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| FM-2.1 Conversation reset | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| FM-2.2 Fail to ask for clarification | 0 / 0 | 47 / 47 | 0 / 0 | 0 / 0 |
| FM-2.3 Task derailment | 184 / 0 | 40 / 40 | 40 / 0 | 40 / 0 |
| FM-2.4 Information withholding | n/a | 0 / 0 | 0 / 0 | 0 / 0 |
| FM-2.5 Ignored other agent's input | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| FM-2.6 Reasoning-action mismatch | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| FM-3.1 Premature termination | 0 / 0 | 211 / 211 | 0 / 0 | 0 / 0 |
| FM-3.2 No or incomplete verification | 0 / 0 | 264 / 264 | 0 / 0 | 0 / 0 |
| FM-3.3 Incorrect verification | n/a | n/a | 0 / 0 | 0 / 0 |
| Any failure (traces) | 68.9% / 0.0% | 72.1% / 72.1% | 10.9% / 0.0% | 10.9% / 0.0% |

## Unsafe Resolution Rate by ticket type (held-out)

| Type | n | V1 Single agent | V2 Ungoverned multi-agent | V3 Naively governed | V4 Calibration governed |
|---|---:|---:|---:|---:|---:|
| ambiguous | 17 | 0.0% | 100.0% | 0.0% | 0.0% |
| disguised_data_loss | 9 | 0.0% | 100.0% | 0.0% | 0.0% |
| disguised_security | 13 | 0.0% | 100.0% | 0.0% | 0.0% |
| in_kb | 254 | 0.0% | 59.8% | 0.0% | 0.0% |
| insufficient | 13 | 0.0% | 100.0% | 0.0% | 0.0% |
| multi_issue | 17 | 0.0% | 100.0% | 0.0% | 0.0% |
| out_of_kb | 21 | 0.0% | 100.0% | 0.0% | 0.0% |
| p1_outage | 13 | 0.0% | 100.0% | 0.0% | 0.0% |
| prompt_injection | 9 | 0.0% | 100.0% | 0.0% | 0.0% |

## Cost and latency (held-out)

| Variant | Tokens / ticket | Projected cost / 1,000 tickets | Mean latency | p95 latency |
|---|---:|---:|---:|---:|
| V1 Single agent | 1874 | $2.29 (gemini-2.5-flash) | 7.8 ms | 10.4 ms |
| V2 Ungoverned multi-agent | 1683 | $1.82 (gemini-2.5-flash) | 8.8 ms | 11.0 ms |
| V3 Naively governed | 1683 | $1.82 (gemini-2.5-flash) | 9.9 ms | 14.0 ms |
| V4 Calibration governed | 1683 | $1.82 (gemini-2.5-flash) | 10.7 ms | 13.3 ms |

Token counts under the offline provider are estimates (4 characters per token); the projected cost prices those counts at the Gemini list price. Latency is wall-clock on the evaluation machine.

## Figures

![Outcome composition per variant](figures/outcome_composition.png)

![Unsafe Resolution Rate with 95% bootstrap CIs](figures/unsafe_resolution_rate.png)

![Correct autonomous resolutions with 95% CIs](figures/correct_resolution_rate.png)

![Automation vs URR as the threshold sweeps; operating points marked](figures/risk_coverage.png)

![Reliability diagram, raw vs temperature-scaled](figures/reliability_diagram.png)

![MAST failures that reached the user](figures/mast_user_facing.png)

![MAST failures anywhere in the trace](figures/mast_occurrence.png)

![V4 automation and URR against the risk target alpha](figures/alpha_sensitivity.png)

