"""Deterministic offline backend.

This is not a toy stub -- it is the reproducibility backstop for the project.
It lets the whole LangGraph pipeline, the pytest suite and the Week 13-14
comparative evaluation run with zero API calls and byte-identical output, which
is what makes execution traces replayable.

It parses the same structured prompt blocks the real providers receive
(``<TICKET>`` and ``<CONTEXT>``), so swapping in Gemini changes the quality of
the answer, not the shape of the state.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .base import LLMProvider

# --------------------------------------------------------------------------- #
# Prompt block parsing
# --------------------------------------------------------------------------- #

_TICKET_RE = re.compile(r"<TICKET>(.*?)</TICKET>", re.DOTALL | re.IGNORECASE)
_CONTEXT_RE = re.compile(r"<CONTEXT>(.*?)</CONTEXT>", re.DOTALL | re.IGNORECASE)
_DOC_HEADER_RE = re.compile(
    r"\[doc_id=(?P<doc_id>[^\s|\]]+)\s*\|\s*title=(?P<title>[^|\]]*?)\s*\|\s*relevance=(?P<score>[0-9.]+)\]"
)
_ERROR_CODE_RE = re.compile(
    r"\b(?:error|err|code|status|0x)[\s:#-]*([0-9a-fA-F]{2,8})\b|\b(0x[0-9a-fA-F]{4,8})\b"
)

# --------------------------------------------------------------------------- #
# Rule tables -- deterministic stand-ins for LLM judgement
# --------------------------------------------------------------------------- #

_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "security",
        ("phishing", "malware", "ransomware", "virus", "breach", "suspicious login",
         "unauthorized", "compromised", "spam attack", "credential theft"),
    ),
    (
        "data_loss",
        ("deleted file", "deleted folder", "deleted a folder", "accidentally deleted",
         "data loss", "lost my files", "missing files", "corrupted database",
         "overwritten", "cannot recover", "recover the", "restore backup",
         "restore the data", "data restored", "restored from backup", "wiped",
         "truncated", "point-in-time recovery"),
    ),
    (
        "network",
        ("vpn", "wifi", "wi-fi", "network", "internet", "dns", "ip address",
         "connection", "latency", "packet", "proxy", "firewall", "ethernet",
         "cannot connect", "disconnect"),
    ),
    (
        "access",
        ("password", "locked out", "account lock", "login", "log in", "sign in",
         "mfa", "2fa", "authenticator", "permission", "access denied",
         "active directory", "sso", "credential"),
    ),
    (
        "email",
        ("outlook", "email", "mailbox", "smtp", "imap", "exchange", "ost", "pst",
         "calendar invite", "distribution list"),
    ),
    (
        "hardware",
        ("laptop", "monitor", "keyboard", "mouse", "printer", "docking station",
         "battery", "overheating", "hard drive", "ssd", "webcam", "headset",
         "not powering", "won't turn on"),
    ),
    (
        "software",
        ("install", "update", "crash", "freeze", "excel", "teams", "chrome",
         "application", "licence", "license", "software", "error message",
         "not responding", "slow"),
    ),
)

_P1_SIGNALS = (
    "entire office", "all users", "everyone", "company-wide", "site down",
    "production down", "outage", "cannot work", "business critical", "revenue",
)
_P2_SIGNALS = ("urgent", "asap", "blocked", "deadline", "several users", "whole team", "client demo")
_P4_SIGNALS = ("whenever", "no rush", "low priority", "question", "how do i", "request for")

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "have", "has", "was", "are", "but",
    "not", "can", "cannot", "cant", "you", "your", "our", "from", "when", "what",
    "will", "would", "there", "their", "been", "into", "them", "they", "please",
    "help", "issue", "problem", "hello", "hi", "team", "getting", "trying", "tried",
    "using", "since", "also", "able", "unable", "still", "just", "any", "all",
}


class MockProvider(LLMProvider):
    """Rule-based, fully deterministic provider."""

    name = "mock"
    model = "deterministic-rules-v1"

    def _complete(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        task: str | None,
    ) -> tuple[str, Any]:
        hint = (task or "").strip().lower()
        if not hint:
            hint = self._infer_task(system or "", prompt)

        if hint == "intake":
            payload = self._intake(prompt)
        elif hint == "resolution":
            payload = self._resolution(prompt)
        elif hint == "single_agent":
            payload = self._single_agent(prompt)
        else:
            payload = {"response": "MockProvider has no behaviour registered for this task."}

        return json.dumps(payload, indent=2), payload

    # ------------------------------------------------------------------ #
    # Task routing
    # ------------------------------------------------------------------ #

    @staticmethod
    def _infer_task(system: str, prompt: str) -> str:
        blob = f"{system}\n{prompt}".lower()
        if "it support assistant" in blob:
            return "single_agent"
        if "intake agent" in blob or "triage" in blob:
            return "intake"
        if "resolution agent" in blob or "<context>" in blob:
            return "resolution"
        return "unknown"

    # ------------------------------------------------------------------ #
    # Intake behaviour
    # ------------------------------------------------------------------ #

    def _intake(self, prompt: str) -> dict[str, Any]:
        ticket = self._block(_TICKET_RE, prompt) or prompt
        lowered = ticket.lower()

        category, matched_terms = self._classify(lowered)
        priority = self._prioritise(lowered, category)
        entities = self._entities(ticket, lowered)
        keywords = self._keywords(ticket, matched_terms, entities)

        # Deterministic stand-in for intake self-confidence: more rule hits and
        # more recognised entities mean a cleaner, less ambiguous ticket.
        signal = len(matched_terms) + sum(1 for value in entities.values() if value)
        confidence = min(0.95, 0.45 + 0.1 * signal)
        if len(ticket.split()) < 5:
            confidence = min(confidence, 0.4)

        summary = " ".join(ticket.split())
        if len(summary) > 220:
            summary = summary[:217].rstrip() + "..."

        return {
            "category": category,
            "priority": priority,
            "keywords": keywords,
            "entities": entities,
            "summary": summary,
            "retrieval_query": " ".join(keywords[:8]) or summary,
            "confidence": round(confidence, 3),
        }

    @staticmethod
    def _classify(lowered: str) -> tuple[str, list[str]]:
        best_category = "other"
        best_hits: list[str] = []
        for category, terms in _CATEGORY_RULES:
            hits = [term for term in terms if term in lowered]
            if len(hits) > len(best_hits):
                best_category, best_hits = category, hits
        return best_category, best_hits

    @staticmethod
    def _prioritise(lowered: str, category: str) -> str:
        if any(signal in lowered for signal in _P1_SIGNALS):
            return "P1"
        if category in ("security", "data_loss"):
            return "P1"
        if any(signal in lowered for signal in _P2_SIGNALS):
            return "P2"
        if any(signal in lowered for signal in _P4_SIGNALS):
            return "P4"
        return "P3"

    @staticmethod
    def _entities(ticket: str, lowered: str) -> dict[str, Any]:
        operating_system = next(
            (name for name in ("windows 11", "windows 10", "macos", "ubuntu", "linux", "android", "ios")
             if name in lowered),
            "",
        )
        application = next(
            (name for name in ("outlook", "teams", "excel", "word", "chrome", "edge", "zoom",
                               "onedrive", "sharepoint", "vpn client", "citrix", "sap", "jira")
             if name in lowered),
            "",
        )
        device = next(
            (name for name in ("laptop", "desktop", "printer", "monitor", "docking station",
                               "phone", "server", "router")
             if name in lowered),
            "",
        )
        network = next(
            (name for name in ("vpn", "wifi", "wi-fi", "ethernet", "dns", "proxy", "firewall")
             if name in lowered),
            "",
        )
        codes = [group for match in _ERROR_CODE_RE.findall(ticket) for group in match if group]
        return {
            "operating_system": operating_system,
            "application": application,
            "device": device,
            "network": network,
            "error_code": codes[0] if codes else "",
        }

    @staticmethod
    def _keywords(ticket: str, matched_terms: list[str], entities: dict[str, Any]) -> list[str]:
        tokens = [
            token
            for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-_.]{2,}", ticket.lower())
            if token not in _STOPWORDS
        ]
        ordered: list[str] = []
        for candidate in list(matched_terms) + [v for v in entities.values() if v] + tokens:
            candidate = str(candidate).strip()
            if candidate and candidate not in ordered:
                ordered.append(candidate)
        return ordered[:12]

    # ------------------------------------------------------------------ #
    # Resolution behaviour
    # ------------------------------------------------------------------ #

    def _resolution(self, prompt: str) -> dict[str, Any]:
        ticket = self._block(_TICKET_RE, prompt) or ""
        context = self._block(_CONTEXT_RE, prompt) or ""
        docs = self._parse_context(context)

        if not docs:
            # Grounding is mandatory: refuse rather than invent an answer.
            return {
                "solution": "",
                "steps": [],
                "citations": [],
                "rationale": "No knowledge-base evidence was supplied, so no grounded answer can be produced.",
                "confidence": 0.0,
            }

        steps: list[str] = []
        for doc in docs:
            for line in doc["body"].splitlines():
                line = line.strip()
                if re.match(r"^(?:\d+[.)]|[-*])\s+", line):
                    cleaned = re.sub(r"^(?:\d+[.)]|[-*])\s+", "", line).strip()
                    if cleaned and cleaned not in steps:
                        steps.append(f"{cleaned} [{doc['doc_id']}]")
        if not steps:
            steps = [
                f"Apply the documented procedure in '{doc['title']}' [{doc['doc_id']}]." for doc in docs
            ]
        steps = steps[:8]

        headline = docs[0]["title"] or "the matched knowledge-base article"
        subject = " ".join(ticket.split())[:160] or "the reported incident"
        solution = (
            f"Based on {len(docs)} retrieved knowledge-base article(s), the closest documented "
            f"match for this incident is '{headline}'. Recommended remediation for: {subject}"
        )

        # Deterministic raw confidence: evidence strength x evidence agreement.
        top_score = max(doc["score"] for doc in docs)
        breadth = min(1.0, len(docs) / 3.0)
        raw_confidence = 0.15 + (0.65 * top_score) + (0.20 * breadth)
        raw_confidence = round(max(0.0, min(0.99, raw_confidence)), 3)

        # Cite exactly the documents the steps were drawn from, as the
        # Resolution prompt requires ("every doc_id you actually used - not every
        # doc_id you were given"). Iteration 1 of this provider cited every
        # retrieved document; the formative MAST analysis flagged that as a
        # reasoning-action mismatch (FM-2.6) and it was corrected before the
        # comparative evaluation. See reports/evaluation/formative_iteration1_mast.json.
        used: list[str] = []
        for step in steps:
            for doc_id in re.findall(r"\[([^\]]+)\]\s*$", step):
                if doc_id not in used:
                    used.append(doc_id)

        return {
            "solution": solution,
            "steps": steps,
            "citations": used or [doc["doc_id"] for doc in docs],
            "rationale": (
                f"Top evidence '{docs[0]['doc_id']}' matched at similarity {top_score:.2f}; "
                f"{len(docs)} supporting article(s) were consistent with the reported symptoms."
            ),
            "confidence": raw_confidence,
        }

    # ------------------------------------------------------------------ #
    # Single-agent baseline behaviour (evaluation variant V1)
    # ------------------------------------------------------------------ #

    def _single_agent(self, prompt: str) -> dict[str, Any]:
        """Triage and answer in one pass, as a monolithic assistant would.

        Reuses the same deterministic triage and answering rules as the
        multi-agent path, so the V1-versus-V3 comparison measures the
        architecture (no separate retrieval query, no relevance filter, no
        independent gate), not a difference in the stand-in model.
        """
        ticket = self._block(_TICKET_RE, prompt) or ""
        triage = self._intake(f"<TICKET>{ticket}</TICKET>")
        answer = self._resolution(prompt)
        return {
            "category": triage["category"],
            "priority": triage["priority"],
            "solution": answer["solution"],
            "steps": answer["steps"],
            "citations": answer["citations"],
            "rationale": answer["rationale"],
            "confidence": answer["confidence"],
        }

    @staticmethod
    def _parse_context(context: str) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        matches = list(_DOC_HEADER_RE.finditer(context))
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(context)
            docs.append(
                {
                    "doc_id": match.group("doc_id"),
                    "title": match.group("title").strip(),
                    "score": float(match.group("score")),
                    "body": context[start:end].strip(),
                }
            )
        return docs

    # ------------------------------------------------------------------ #

    @staticmethod
    def _block(pattern: re.Pattern[str], text: str) -> str:
        match = pattern.search(text)
        return match.group(1).strip() if match else ""
