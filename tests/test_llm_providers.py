"""Provider behaviour added after Week 5-7: current Gemini SDK, real token
counts, the single-agent mock task and the mock's citation discipline."""

from __future__ import annotations

import pytest

from ops_agent.llm import MockProvider
from ops_agent.llm.base import LLMProvider


def test_mock_single_agent_task_triages_and_answers(provider):
    prompt = (
        "<TICKET>VPN error 809 at the hotel</TICKET>\n<CONTEXT>\n"
        "[doc_id=KB-0001 | title=VPN Error 809 | relevance=0.80]\n1. Enable NAT traversal.\n"
        "</CONTEXT>"
    )
    payload, _ = provider.generate_json(prompt, task="single_agent")
    assert payload["category"] == "network"
    assert payload["citations"] == ["KB-0001"] and payload["confidence"] > 0


def test_mock_cites_only_documents_its_steps_use(provider):
    prompt = (
        "<TICKET>vpn 809</TICKET>\n<CONTEXT>\n"
        "[doc_id=KB-0001 | title=VPN 809 | relevance=0.80]\n1. A.\n2. B.\n3. C.\n4. D.\n5. E.\n6. F.\n7. G.\n8. H.\n\n"
        "[doc_id=KB-0002 | title=VPN loop | relevance=0.50]\n1. Unused step.\n"
        "</CONTEXT>"
    )
    payload, _ = provider.generate_json(prompt, task="resolution")
    assert payload["citations"] == ["KB-0001"]  # eight steps already came from KB-0001


def test_reported_token_usage_is_preferred_over_estimates():
    class Reporting(LLMProvider):
        name, model = "reporting", "r"

        def _complete(self, prompt, system, temperature, max_tokens, json_mode, task):
            self.last_usage = {"input_tokens": 120, "output_tokens": 30, "thinking_tokens": 5}
            return '{"ok": true}', None

    response = Reporting().generate("hello")
    assert (response.input_tokens, response.output_tokens, response.token_count) == (120, 35, "exact")
    assert MockProvider().generate("<TICKET>x</TICKET>", task="intake").token_count == "approximate"


def test_gemini_config_uses_the_current_sdk_and_minimal_thinking():
    pytest.importorskip("google.genai")
    from ops_agent.llm.gemini import GeminiProvider

    flash = GeminiProvider("test-key", "gemini-2.5-flash", thinking_budget=0)
    config = flash._config("system", 0.0, 256, True)
    assert config.temperature == 0.0 and config.response_mime_type == "application/json"
    assert config.thinking_config.thinking_budget == 0

    gemini3 = GeminiProvider("test-key", "gemini-3.8-flash", thinking_level="low")
    config = gemini3._config(None, 0.0, 256, True)
    assert config.temperature is None  # left at the model default on Gemini 3
    assert config.thinking_config.thinking_level is not None
