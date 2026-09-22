# OPS-AGENT — Literature review and verified references

Companion to `OPS-AGENT_Research_Paper.docx`. Every reference below was checked on
**21 September 2026** against its publisher page, arXiv record, conference site or the
source web page. Where the synopsis (`Final Synopsis .pdf`) cites a source differently,
the correction is noted — use the corrected form in the final report.

Legend: ✅ verified as cited · ✏️ verified, synopsis entry needs correction ·
⚠️ exists, but metadata could not be fully verified

---

## 1. Review protocol (summary)

A lightweight version of the Kitchenham–Charters protocol for systematic reviews in
software engineering:

| Step | What was done |
|---|---|
| Questions | (1) How are LLM agents used in incident / ticket management? (2) How is LLM or agent confidence calibrated? (3) How can an abstain/escalate threshold be chosen with a guarantee? (4) How are failures of multi-agent systems classified? (5) What do regulation and practice require of human oversight? |
| Search strings | {multi-agent, LLM agent} × {incident, ticket, ITSM, SRE, root cause}; {calibration, temperature scaling, verbalized confidence, conformal, selective prediction, abstention, risk control, learn then test}; {escalation, defer, human oversight, failure taxonomy, MAST} |
| Sources | arXiv, ACM Digital Library, IEEE Xplore, NeurIPS/ICLR/ICML proceedings, OpenReview, vendor newsrooms, Kaggle, official regulation texts |
| Window | 2017–2026, plus foundational statistics (1927–1998) |
| Inclusion | Directly informs a design decision or an evaluation choice of this project |
| Verification | Title, authors, venue, year and identifier confirmed on the source page |

---

## 2. Synopsis references — verification

| # | Synopsis entry | Status | Verified citation / correction |
|---|---|---|---|
| 1 | Microsoft Research, "Triangle: Empowering Incident Triage with Multi-LLM-Agents," ESEC/FSE 2025 | ✏️ | Published at **ASE 2025** (40th IEEE/ACM Int. Conf. on Automated Software Engineering, experience paper) as "Triangle: Empowering Incident Triage with **Multi-Agent**", Z. Yu, A. Fang, M. Ma, J. S. Walia, C. Zhang, S. Chi, Z. Li, M. Chintalapati, X. Zhang, R. Wang, C. Bansal, S. Rajmohan, Q. Lin, S. Zhang, D. Pei, P. He. DOI 10.1109/ASE63991.2025.00062. (The "Multi-LLM-Agents" title is Microsoft's earlier FSE-labelled preprint.) |
| 2 | "Multi-Agent LLM Orchestration Achieves Deterministic, High-Quality Decision Support for Incident Response," 2026, arXiv:2511.15755 | ✏️ | Author **P. Drammeh**; submitted **19 Nov 2025** (year 2025, not 2026). 348 controlled trials; introduces the Decision Quality (DQ) metric. |
| 3 | "Intelligent Site Reliability Engineering: A Multi-Agent LLM Framework…," 2025, ResearchGate | ⚠️ | Exists (ResearchGate publication 399119176, 2025). Author names and venue could not be retrieved from accessible metadata — add them from the PDF before submission. |
| 4 | "LLM Agents Security Duality…," 2026, arXiv:2606.28450 | ✅ | Y. Xu, Y. Zhuang, X. Liu, T. Zhang, B. Xiao, X. Xu, D. Jiang, J. Wang, H. Hu; submitted 26 Jun 2026. |
| 5 | PagerDuty, "Operations Cloud Spring 2026 Release Notes" | ✏️ | Press release title: "PagerDuty Unveils Next Generation of the Operations Cloud Platform with the Spring 2026 Release," 12 Mar 2026. |
| 6 | ServiceNow, "Completes Acquisition of Moveworks; Launches EmployeeWorks," 2026 | ✏️ | Two releases: "ServiceNow completes acquisition of Moveworks" (newsroom, **2025**) and "ServiceNow launches Autonomous Workforce that thinks and acts; adds Moveworks to the ServiceNow AI Platform" (2026), which introduced EmployeeWorks. Cite the one you use. |
| 7 | systempromptio, "awesome-ai-agent-governance," GitHub | ✅ | github.com/systempromptio/awesome-ai-agent-governance |
| 8 | Strata Identity, "Human-in-the-Loop: A 2026 Guide to AI Oversight" | ✅ | strata.io blog (grey literature). |
| 9 | Digital Applied, "Human-in-the-Loop Escalation Design for AI Agents 2026" | ✅ | digitalapplied.com blog (grey literature). |
| 10 | Zylos AI Research, "AI Agent Governance and Compliance in 2026" | ✅ | Full title "…: Frameworks, Audit Trails, and the Regulatory Reckoning," 1 May 2026 (grey literature). |
| 11 | Zylos AI Research, "LLM Calibration and Uncertainty Quantification in Production AI Agents" | ✅ | 18 Apr 2026 (grey literature). For the calibration claim prefer the peer-reviewed sources in §3.2. |
| 12 | Cemri et al., "Why Do Multi-Agent LLM Systems Fail?" arXiv:2503.13657 | ✏️ | Now published at **NeurIPS 2025 (Datasets and Benchmarks Track)**. The final version analyses **1,600+ traces (MAST-Data: 1,642) across 7 frameworks**, κ = 0.88 — not "over 150 traces" (that figure is from the first preprint). 14 modes in 3 categories: FM-1.1–1.5, FM-2.1–2.6, FM-3.1–3.3. |
| 13 | "The Six Sigma Agent…," 2026, arXiv:2601.22290 | ✅ | K. Patel, S. Surendira, J. George, S. Kapale (Lyzr Research). |
| 14 | "Think Locally, Explain Globally…," 2026, arXiv:2601.17915 | ✅ | S. Jha, R. Arora, Bhavya, N. Zheutlin, P. Toro Isaza, L. Shwartz, Y. Deng, D. Sow, R. Mahindru, R. Puri (IBM Research). |
| 15 | "Act or Escalate? Evaluating Escalation Behavior in Automation with Language Models," 2026, arXiv:2604.08588 | ✅ | M. DosSantos DiSorbo (Harvard Business School), H. Ju (Johns Hopkins). |
| 16 | "Calibrating Conservatism for Scalable Oversight," 2026, arXiv:2605.28807 | ✅ | W. Overman, M. Bayati (Stanford GSB). |
| 17 | "Conformal Constrained Policy Optimization for Cost-Effective LLM Agents," 2026, arXiv:2511.11828 | ✏️ | W. Si, S. Jang, I. Lee, O. Bastani; submitted **14 Nov 2025** (year 2025). |
| 18 | "Conformal Agent Error Attribution," 2026, arXiv:2605.06788 | ✅ | N. Feng, Y. Sui, S. Hou, G. Wu, J. C. Cresswell. |
| 19 | Guo, Pleiss, Sun, Weinberger, ICML 2017 | ✅ | PMLR 70:1321–1330. |
| 20 | Vovk, Gammerman, Shafer, *Algorithmic Learning in a Random World*, Springer 2005 | ✅ | (2nd ed. 2022 exists.) |
| 21 | Peffers et al., JMIS 24(3):45–77, 2007 | ✅ | |
| 22 | "Ticket-BERT," 2023, arXiv:2307.00108 | ✅ | Z. Liu, C. Benge, S. Jiang. States that no large-scale labeled incident dataset was available. |
| 23 | Goh, "IT Service Ticket Classification Dataset," Kaggle 2024 | ✅ | kaggle.com/datasets/adisongoh/it-service-ticket-classification-dataset |
| 24 | Bueck, "Customer IT Support – Ticket Dataset," Kaggle 2025 | ✅ | kaggle.com/datasets/tobiasbueck/multilingual-customer-support-tickets — note: the dataset is **synthetic**. |
| 25 | Unthread.io, "23 Support Ticket Resolution Statistics by Complexity (2026)" | ✅ | Grey literature. |
| 26 | DEV Community, "LangGraph vs CrewAI vs AutoGen…2026" | ✅ | dev.to (grey literature). |
| 27 | Presenc AI Research, "Multi-Agent Orchestration Frameworks 2026" | ✅ | presenc.ai/research (grey literature). |

**Recommendation for the final report:** keep grey literature (7–11, 25–27) for industry
context only, and support every technical claim with the peer-reviewed sources below.

---

## 3. Additional references used in the paper (annotated)

### 3.1 Agents for incident and ticket management
- **T. Ahmed et al., ICSE 2023** — "Recommending Root-Cause and Mitigation Steps for Cloud Incidents using Large Language Models." Early large-scale evaluation of LLMs on real incidents; motivates grounding in organisational knowledge.
- **Y. Chen et al., EuroSys 2024** — "Automatic Root Cause Analysis via Large Language Models for Cloud Incidents" (RCACopilot). Retrieval-augmented RCA in production.
- **F. Liu et al., FSE 2025 (companion)** — "TickIt: Leveraging Large Language Models for Automated Ticket Escalation," DOI 10.1145/3696630.3728558. Escalation *routing*, deployed at ByteDance — complementary to escalation *to humans*.

### 3.2 Calibration of model confidence
- **M. P. Naeini, G. F. Cooper, M. Hauskrecht, AAAI 2015** — Bayesian binning; the origin of the ECE metric used here.
- **J. Platt, 1999** — sigmoid (Platt) scaling; temperature scaling is its one-parameter, no-bias special case. Cited as the fix for the TF-IDF limitation.
- **G. W. Brier, 1950** — the Brier score.
- **S. Kadavath et al., arXiv:2207.05221, 2022** — LLMs can partly self-evaluate.
- **M. Xiong et al., ICLR 2024** — verbalised LLM confidence is typically over-confident.
- **K. Tian et al., EMNLP 2023** — elicitation strategy changes calibration of RLHF models.
- **J. Zhang, C. Xiong, C.-S. Wu, arXiv:2601.15778, 2026** — "Agentic Confidence Calibration": calibrating whole agent trajectories.
- **C. Oh et al., arXiv:2602.05073, 2026** — uncertainty quantification framework for multi-turn LLM agents.

### 3.3 Selective prediction, conformal prediction, risk control
- **C. K. Chow, IEEE Trans. IT 16(1):41–46, 1970** — the reject option.
- **Y. Geifman, R. El-Yaniv, NeurIPS 2017** — selective classification with guaranteed risk.
- **A. N. Angelopoulos, S. Bates, FnT ML 16(4), 2023** — "Conformal Prediction: A Gentle Introduction."
- **A. N. Angelopoulos, S. Bates, A. Fisch, L. Lei, T. Schuster, ICLR 2024** — Conformal Risk Control (the CRC option in `risk_control.py`).
- **A. N. Angelopoulos, S. Bates, E. J. Candès, M. I. Jordan, L. Lei, Annals of Applied Statistics 19(2), 2025**, doi 10.1214/24-AOAS1998 — Learn then Test (the primary threshold-selection method).
- **A. Z. Ren et al., CoRL 2023** — "Robots That Ask For Help": conformal prediction deciding when an LLM planner should ask a human.
- **C. J. Clopper, E. S. Pearson, Biometrika 26(4), 1934** — exact binomial bound reported with each threshold.

### 3.4 Escalation, deferral, oversight
- **H. Mozannar, D. Sontag, ICML 2020** — learning to defer to an expert.
- **Regulation (EU) 2024/1689 (AI Act), Article 14** — human oversight of high-risk AI systems.
- **NIST AI 100-1, AI RMF 1.0, 2023** — risk management framework.
- **HumanLayer** (GitHub) — approval gates for agent actions.

### 3.5 Foundations used by the system
- **P. Lewis et al., NeurIPS 2020** — retrieval-augmented generation.
- **N. Reimers, I. Gurevych, EMNLP-IJCNLP 2019** — Sentence-BERT.
- **W. Wang et al., NeurIPS 2020** — MiniLM (all-MiniLM-L6-v2 is the retrieval embedder).
- **Z. Ji et al., ACM CSUR 55(12), 2023** — survey of hallucination.
- **S. Yao et al., ICLR 2023** — ReAct; **Q. Wu et al., COLM 2024** — AutoGen (contrasting agent frameworks).
- **K. Greshake et al., AISec 2023** — indirect prompt injection (basis for the injection tickets).
- **L. Zheng et al., NeurIPS 2023 D&B** — LLM-as-a-judge (the MAST LLM annotator).
- **C.-Y. Lin, 2004** — ROUGE.
- **B. Laurie, A. Langley, E. Kasper, RFC 6962, 2013** — Certificate Transparency; **S. A. Crosby, D. S. Wallach, USENIX Security 2009** — tamper-evident logging (the audit hash chain).
- **T. Gebru et al., CACM 64(12), 2021** — Datasheets for Datasets (the dataset card).

### 3.6 Research methodology and statistics
- **A. R. Hevner, S. T. March, J. Park, S. Ram, MIS Quarterly 28(1), 2004** — design science in IS research.
- **K. Peffers et al., JMIS 24(3), 2007** — DSRM (synopsis ref. 21).
- **B. Kitchenham, S. Charters, EBSE-2007-01, 2007** — literature review protocol.
- **C. Wohlin et al., Springer 2012** — experimentation in software engineering; threats-to-validity classification.
- **Q. McNemar, Psychometrika 12(2), 1947**; **W. G. Cochran, Biometrika 37(3/4), 1950**; **S. Holm, Scand. J. Stat. 6(2), 1979**; **B. Efron, R. J. Tibshirani, 1993** (bootstrap); **T. G. Dietterich, Neural Computation 10(7), 1998** (why McNemar for paired classifier comparison).
- **J. Cohen, EPM 20(1), 1960**; **J. R. Landis, G. G. Koch, Biometrics 33(1), 1977** — Cohen's kappa and its interpretation bands (MAST annotation agreement).

### 3.7 Tools and platforms
- **LangGraph documentation** (LangChain) — orchestration.
- **Google Gemini API documentation** (models, pricing, deprecations; read 21 Sep 2026) — `gemini-1.5-*` is retired; the project defaults to `gemini-2.5-flash` through the `google-genai` SDK.
