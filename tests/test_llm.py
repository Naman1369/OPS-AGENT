"""LLM layer tests -- JSON recovery, provider selection, deterministic mock."""

from __future__ import annotations

import pytest

from ops_agent.config import LLMSettings
from ops_agent.llm import LLMError, MockProvider, OllamaProvider, extract_json, get_provider


def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_fenced_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_embedded_in_prose():
    assert extract_json('Sure! Here you go:\n{"a": 1}\nHope that helps.') == {"a": 1}


def test_extract_json_with_nested_braces_and_strings():
    text = 'prefix {"outer": {"inner": "a } brace in a string"}} suffix'
    assert extract_json(text)["outer"]["inner"] == "a } brace in a string"


def test_extract_json_raises_on_garbage():
    with pytest.raises(LLMError):
        extract_json("no json at all here")


def test_mock_provider_is_deterministic(provider):
    ticket = "<TICKET>VPN fails with error 809</TICKET>"
    first, _ = provider.generate_json(ticket, task="intake")
    second, _ = provider.generate_json(ticket, task="intake")
    assert first == second


def test_mock_intake_returns_the_expected_schema(provider):
    payload, response = provider.generate_json(
        "<TICKET>Outlook will not open my mailbox</TICKET>", task="intake"
    )
    assert set(payload) >= {"category", "priority", "keywords", "entities", "confidence"}
    assert response.provider == "mock"
    assert response.latency_ms >= 0


def test_mock_resolution_refuses_without_context(provider):
    payload, _ = provider.generate_json("<TICKET>x</TICKET>\n<CONTEXT></CONTEXT>", task="resolution")
    assert payload["confidence"] == 0.0
    assert payload["steps"] == []


def test_mock_resolution_extracts_steps_from_context(provider):
    prompt = (
        "<TICKET>vpn 809</TICKET>\n"
        "<CONTEXT>\n"
        "[doc_id=KB-0001 | title=VPN Error 809 | relevance=0.90]\n"
        "1. Enable NAT traversal.\n2. Reboot the workstation.\n"
        "</CONTEXT>"
    )
    payload, _ = provider.generate_json(prompt, task="resolution")
    assert payload["citations"] == ["KB-0001"]
    assert len(payload["steps"]) == 2
    assert all("[KB-0001]" in step for step in payload["steps"])
    assert payload["confidence"] > 0.0


def test_factory_defaults_to_mock_without_a_key():
    settings = LLMSettings()
    object.__setattr__(settings, "provider", "")
    object.__setattr__(settings, "gemini_api_key", "")
    assert isinstance(get_provider(settings), MockProvider)


def test_factory_falls_back_to_ollama_when_gemini_cannot_start():
    settings = LLMSettings()
    object.__setattr__(settings, "provider", "gemini")
    object.__setattr__(settings, "gemini_api_key", "")
    assert isinstance(get_provider(settings), OllamaProvider)


def test_explicit_mock_selection_is_honoured():
    settings = LLMSettings()
    object.__setattr__(settings, "provider", "mock")
    object.__setattr__(settings, "gemini_api_key", "looks-like-a-key")
    assert isinstance(get_provider(settings), MockProvider)
