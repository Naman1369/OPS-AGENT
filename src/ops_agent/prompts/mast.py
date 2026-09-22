"""LLM-as-a-judge prompt for MAST failure annotation (Weeks 10-12).

Synopsis Phase 6: two human annotators label a subset of 100-150 traces, an
LLM annotator is validated against them, and only then applied to the rest.
This prompt is that LLM annotator. It needs a real provider (Gemini/Ollama);
the offline MockProvider does not implement it, by design - a rule table
pretending to be an LLM judge would make the validation step meaningless.
"""

PROMPT_VERSION = "mast-annotator-v1"

SYSTEM_PROMPT = """\
You are an expert annotator of multi-agent system execution traces. You label
traces with the Multi-Agent System Failure Taxonomy (MAST; Cemri et al., 2025).

The system under test is OPS-AGENT, an IT incident pipeline: Intake (triage) ->
Retrieval (knowledge-base search) -> Resolution (cited remediation + confidence)
-> Governance (deterministic gate) -> Deliver or Escalate. A baseline variant may
use a single agent instead.

For EACH of the 14 failure modes below decide whether it occurred anywhere in
the trace. Mark a mode true only when the trace contains concrete evidence.

{mode_block}

Return one JSON object and nothing else:
{{
  "labels": {{"FM-1.1": false, "FM-1.2": false, ... all 14 codes ...}},
  "evidence": {{"FM-x.y": "one sentence quoting the trace", ...only for true modes...}}
}}
"""

USER_TEMPLATE = """\
Annotate this execution trace.

<TICKET>
{ticket_text}
</TICKET>

<GOLD>
{gold_block}
</GOLD>

<TRACE>
{trace_block}
</TRACE>

<FINAL>
{final_block}
</FINAL>

Return only the JSON object.
"""
