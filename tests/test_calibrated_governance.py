"""Calibrated governance tests (Weeks 8-12): the calibration node, check G3 in
calibrated mode, fail-closed behaviour, and governance-mode resolution."""

from __future__ import annotations

import pytest

from ops_agent.agents.calibration import calibration_node
from ops_agent.agents.governance import SAFE_TO_RESOLVE, governance_node
from ops_agent.calibration import UNCERTIFIABLE_THRESHOLD, CalibrationProfile
from ops_agent.config import GovernanceSettings
from ops_agent.graph import build_graph, compile_pipeline, current_fingerprint, resolve_governance
from ops_agent.state import new_state

from test_governance import passing_state


def _profile(threshold=0.9, temperature=0.5, feasible=True, fingerprint=None) -> CalibrationProfile:
    return CalibrationProfile(
        temperature=temperature, threshold=threshold, alpha=0.05, delta=0.1, feasible=feasible,
        fingerprint=fingerprint or {"provider": "mock"},
    )


# --------------------------------------------------------------------------- #
# Calibration node
# --------------------------------------------------------------------------- #


def test_calibration_node_keeps_the_raw_score_and_adds_a_calibrated_one():
    state = passing_state(confidence_score=0.7)
    update = calibration_node(state, _profile(temperature=0.5))
    assert "confidence_score" not in update  # raw is never overwritten
    assert update["confidence_is_calibrated"] is True
    assert update["calibrated_confidence"] > 0.7  # T < 1 sharpens
    payload = update["agent_trace"][0]["payload"]
    assert payload["confidence_score"] == 0.7 and payload["temperature"] == 0.5


def test_calibration_node_without_a_profile_is_an_honest_passthrough():
    update = calibration_node(passing_state(confidence_score=0.4), None)
    assert update["confidence_is_calibrated"] is False
    assert update["calibrated_confidence"] == 0.4


# --------------------------------------------------------------------------- #
# Governance in calibrated mode
# --------------------------------------------------------------------------- #


def test_g3_reads_the_calibrated_confidence_and_profile_threshold():
    profile = _profile(threshold=0.9, temperature=0.5)
    state = passing_state(confidence_score=0.75)  # raw 0.75 -> calibrated ~0.90
    state.update(calibration_node(state, profile))
    update = governance_node(state, settings=GovernanceSettings(), profile=profile)
    assert update["confidence_basis"] == "calibrated"
    assert update["confidence_threshold_applied"] == 0.9
    assert update["policy_checks"]["G3_confident"] == (state["calibrated_confidence"] >= 0.9)


def test_calibrated_mode_changes_only_g3():
    state = passing_state(confidence_score=0.72)
    raw = governance_node(state, settings=GovernanceSettings())
    calibrated = governance_node(state, settings=GovernanceSettings(), profile=_profile(threshold=0.99))
    for check in raw["policy_checks"]:
        if check != "G3_confident":
            assert raw["policy_checks"][check] == calibrated["policy_checks"][check]
    assert raw["policy_checks"]["G3_confident"] is True
    assert calibrated["policy_checks"]["G3_confident"] is False


def test_governance_calibrates_when_the_calibration_node_was_skipped():
    profile = _profile(threshold=0.5)
    update = governance_node(passing_state(confidence_score=0.8), profile=profile)
    assert update["calibrated_confidence"] == pytest.approx(profile.transform(0.8))


def test_uncertifiable_profile_fails_closed():
    profile = _profile(threshold=UNCERTIFIABLE_THRESHOLD, feasible=False)
    update = governance_node(passing_state(confidence_score=0.99), profile=profile)
    assert update["escalation_flag"] is True
    assert any("fail closed" in reason for reason in update["governance_reasons"])


def test_policy_gates_still_override_a_calibrated_confidence():
    update = governance_node(passing_state(category="security", priority="P1", confidence_score=0.99),
                             profile=_profile(threshold=0.1))
    assert update["policy_checks"]["G3_confident"] is True
    assert update["escalation_flag"] is True


def test_calibrated_trace_records_both_confidences_and_the_profile():
    profile = _profile()
    payload = governance_node(passing_state(), profile=profile)["agent_trace"][0]["payload"]
    assert payload["confidence_is_calibrated"] is True
    assert payload["calibration_profile_id"] == profile.profile_id
    assert payload["confidence_score"] is not None and payload["calibrated_confidence"] is not None


# --------------------------------------------------------------------------- #
# Graph and mode resolution
# --------------------------------------------------------------------------- #


def test_calibrated_graph_inserts_the_calibration_node():
    pipeline = build_graph("calibrated", _profile(threshold=0.05)).compile()
    final = pipeline.invoke(new_state("Outlook hangs on loading profile and will not start."))
    path = [event["agent"] for event in final["agent_trace"]]
    assert path[:5] == ["intake", "retrieval", "resolution", "calibration", "governance"]
    assert final["confidence_is_calibrated"] is True


def test_calibrated_graph_can_deliver():
    pipeline = build_graph("calibrated", _profile(threshold=0.05)).compile()
    final = pipeline.invoke(new_state("VPN fails to connect with error 809 behind NAT."))
    assert final["outcome"] == "resolved"
    assert "calibrated" in final["final_response"]


def test_calibrated_mode_requires_a_profile():
    with pytest.raises(ValueError):
        build_graph("calibrated", None)
    with pytest.raises(ValueError):
        build_graph("auto")


def test_auto_mode_without_profiles_falls_back_to_raw(tmp_path):
    settings = GovernanceSettings()
    object.__setattr__(settings, "calibration_path", tmp_path)
    resolution = resolve_governance("auto", settings)
    assert resolution.mode == "raw" and "no calibration profile" in resolution.note


def test_auto_mode_rejects_a_profile_for_another_configuration(tmp_path):
    fingerprint = current_fingerprint()
    _profile(fingerprint={**fingerprint, "embedder": "some-other-model"}).save(tmp_path / "p.json")
    settings = GovernanceSettings()
    object.__setattr__(settings, "calibration_path", tmp_path)
    resolution = resolve_governance("auto", settings, fingerprint)
    assert resolution.mode == "raw" and "embedder" in resolution.note


def test_auto_mode_applies_a_matching_profile(tmp_path):
    fingerprint = current_fingerprint()
    profile = _profile(fingerprint=fingerprint)
    profile.save(tmp_path / "p.json")
    settings = GovernanceSettings()
    object.__setattr__(settings, "calibration_path", tmp_path)
    resolution = resolve_governance("auto", settings, fingerprint)
    assert resolution.mode == "calibrated"
    assert resolution.profile.profile_id == profile.profile_id


def test_compile_pipeline_reports_its_mode():
    pipeline = compile_pipeline(mode="raw")
    assert pipeline.mode == "raw" and pipeline.profile is None
    calibrated = compile_pipeline(profile=_profile(threshold=0.5))
    assert calibrated.mode == "calibrated"
    final = calibrated.invoke(new_state("printer queue stuck, nothing prints"))
    assert final["confidence_basis"] == "calibrated"


def test_raw_pipeline_verdicts_are_unchanged_by_the_new_fields():
    final = compile_pipeline(mode="raw").invoke(new_state("I clicked a link in a phishing email."))
    assert final["confidence_basis"] == "raw"
    assert final["governance_verdict"] != SAFE_TO_RESOLVE
