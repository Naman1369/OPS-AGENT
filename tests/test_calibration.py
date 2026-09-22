"""Calibration tests (Weeks 8-9): metrics, temperature scaling, risk control, profiles."""

from __future__ import annotations

import json

import numpy as np
import pytest

from ops_agent.calibration import (
    UNCERTIFIABLE_THRESHOLD,
    CalibrationProfile,
    TemperatureScaler,
    aurc,
    auroc,
    binomial_pvalue,
    brier_score,
    calibration_summary,
    clopper_pearson_upper,
    expected_calibration_error,
    kb_fingerprint,
    load_profile,
    load_profiles,
    reliability_bins,
    select_profile,
    select_threshold,
)
from ops_agent.config import SETTINGS


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


def test_ece_is_zero_when_accuracy_matches_confidence_in_every_bin():
    conf = [0.25] * 4 + [0.75] * 4
    correct = [1, 0, 0, 0, 1, 1, 1, 0]
    assert expected_calibration_error(conf, correct) == pytest.approx(0.0)


def test_ece_known_value():
    # One bin, confidence 0.9, accuracy 0.5 -> gap 0.4
    assert expected_calibration_error([0.9, 0.9], [1, 0]) == pytest.approx(0.4)


def test_reliability_bins_count_every_sample_including_one():
    bins = reliability_bins([0.0, 0.5, 1.0], [0, 1, 1], n_bins=10)
    assert sum(b["count"] for b in bins) == 3
    assert bins[-1]["count"] == 1


def test_brier_and_auroc():
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0
    assert auroc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0
    assert auroc([0.5, 0.5], [1, 1]) is None


def test_aurc_prefers_confident_correct_answers():
    good = aurc([0.9, 0.8, 0.2], [1, 1, 0])
    bad = aurc([0.2, 0.8, 0.9], [1, 1, 0])
    assert good < bad


def test_metrics_reject_bad_input():
    with pytest.raises(ValueError):
        expected_calibration_error([1.2], [1])
    with pytest.raises(ValueError):
        brier_score([0.5], [2])


# --------------------------------------------------------------------------- #
# Temperature scaling
# --------------------------------------------------------------------------- #


def _synthetic(true_temperature: float, n: int = 4000, seed: int = 0):
    """Scores generated so that sigmoid(logit / T_true) is the true probability."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0.0, 2.0, n)
    raw = 1 / (1 + np.exp(-z))
    true_p = 1 / (1 + np.exp(-z / true_temperature))
    correct = (rng.random(n) < true_p).astype(float)
    return raw, correct


@pytest.mark.parametrize("true_t", [0.5, 2.0])
def test_temperature_scaling_recovers_the_true_temperature(true_t):
    raw, correct = _synthetic(true_t)
    scaler = TemperatureScaler().fit(raw, correct)
    assert scaler.temperature == pytest.approx(true_t, rel=0.15)
    assert scaler.nll_after <= scaler.nll_before


def test_temperature_scaling_lowers_ece_on_miscalibrated_scores():
    raw, correct = _synthetic(2.0)
    scaled = TemperatureScaler().fit(raw, correct).transform(raw)
    assert expected_calibration_error(scaled, correct) < expected_calibration_error(raw, correct)


def test_temperature_scaling_is_monotone_so_auroc_is_unchanged():
    raw, correct = _synthetic(2.0, n=500)
    scaled = TemperatureScaler(temperature=3.0, fitted=True).transform(raw)
    assert np.all(np.diff(scaled[np.argsort(raw)]) >= -1e-12)
    assert auroc(scaled, correct) == pytest.approx(auroc(raw, correct))


def test_temperature_scaling_needs_enough_samples():
    with pytest.raises(ValueError):
        TemperatureScaler().fit([0.6] * 5, [1] * 5)


def test_transform_accepts_scalars():
    assert isinstance(TemperatureScaler(temperature=2.0).transform(0.8), float)


# --------------------------------------------------------------------------- #
# Risk-controlled threshold selection
# --------------------------------------------------------------------------- #


def test_binomial_pvalue_and_clopper_pearson():
    assert binomial_pvalue(0, 64, 0.05) == pytest.approx(0.95 ** 64)
    upper = clopper_pearson_upper(0, 64, 0.10)
    assert 0.0 < upper < 0.05
    assert clopper_pearson_upper(3, 3, 0.1) == 1.0


def test_threshold_is_certified_when_confident_tickets_are_safe():
    scores = np.linspace(0.3, 0.99, 80)
    unsafe = (scores < 0.6).astype(int)  # only low-confidence tickets are unsafe
    result = select_threshold(scores, unsafe, alpha=0.05, delta=0.1)
    assert result.feasible
    assert result.unsafe_auto_resolved / result.n_calibration <= 0.05
    assert result.threshold >= 0.6 - 0.01


def test_threshold_fails_closed_when_nothing_can_be_certified():
    scores = np.full(20, 0.9)
    result = select_threshold(scores, np.ones(20, dtype=int), alpha=0.05, delta=0.1)
    assert not result.feasible
    assert result.threshold == UNCERTIFIABLE_THRESHOLD
    assert result.coverage == 0.0


def test_ineligible_tickets_never_count_as_deliveries():
    scores = np.full(60, 0.95)
    unsafe = np.ones(60, dtype=int)
    eligible = np.zeros(60, dtype=int)  # other gates block them all
    result = select_threshold(scores, unsafe, eligible, alpha=0.05, delta=0.1)
    assert result.feasible and result.n_auto_resolved == 0


def test_crc_is_less_conservative_than_ltt_at_the_same_alpha():
    rng = np.random.default_rng(3)
    scores = rng.random(200)
    unsafe = (rng.random(200) > scores).astype(int)
    ltt = select_threshold(scores, unsafe, alpha=0.1, delta=0.1, method="ltt")
    crc = select_threshold(scores, unsafe, alpha=0.1, delta=0.1, method="crc")
    assert crc.threshold <= ltt.threshold


def test_ltt_guarantee_holds_in_simulation():
    """Across many calibration draws, URR at the chosen threshold exceeds alpha
    (on a large fresh sample from the same distribution) at most ~delta of the time."""
    rng = np.random.default_rng(11)
    alpha, delta, failures, trials = 0.1, 0.1, 0, 150

    def draw(n):
        s = rng.random(n)
        return s, (rng.random(n) > 0.3 + 0.7 * s).astype(int)

    test_s, test_u = draw(20000)
    for _ in range(trials):
        s, u = draw(100)
        result = select_threshold(s, u, alpha=alpha, delta=delta)
        urr = np.mean((test_s >= result.threshold) * test_u)
        failures += urr > alpha
    assert failures / trials <= delta + 0.05


def test_select_threshold_validates_input():
    with pytest.raises(ValueError):
        select_threshold([0.5], [0, 1])
    with pytest.raises(ValueError):
        select_threshold([0.5], [0], alpha=1.5)
    with pytest.raises(ValueError):
        select_threshold([0.5], [0], method="magic")


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #


def _profile(**overrides) -> CalibrationProfile:
    values = dict(temperature=0.5, threshold=0.9, alpha=0.05, delta=0.1, feasible=True,
                  fingerprint={"provider": "mock", "model": "m", "embedder": "tfidf-fallback",
                               "intake_prompt": "intake-v1", "resolution_prompt": "resolution-v1",
                               "kb_hash": "abc", "top_k": 4, "min_relevance": 0.25})
    values.update(overrides)
    return CalibrationProfile(**values)


def test_profile_round_trips_and_has_a_stable_id(tmp_path):
    profile = _profile()
    path = profile.save(tmp_path / "p.json")
    loaded = load_profile(path)
    assert loaded.profile_id == profile.profile_id
    assert loaded.transform(0.7) == pytest.approx(profile.transform(0.7))
    assert json.loads(path.read_text())["profile_id"] == profile.profile_id


def test_profile_matching_names_the_mismatched_keys():
    ok, mismatched = _profile().matches({**_profile().fingerprint, "embedder": "minilm"})
    assert not ok and mismatched == ["embedder"]


def test_select_profile_picks_the_matching_one(tmp_path):
    first = _profile()
    second = _profile(fingerprint={**first.fingerprint, "embedder": "minilm"}, threshold=0.8)
    first.save(tmp_path / "a.json")
    second.save(tmp_path / "b.json")
    chosen, mismatches = select_profile(load_profiles(tmp_path), second.fingerprint)
    assert chosen.profile_id == second.profile_id
    assert list(mismatches.values()) == [["embedder"]]


def test_unreadable_profile_is_ignored(tmp_path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert load_profile(tmp_path / "broken.json") is None
    assert load_profiles(tmp_path) == []


def test_kb_fingerprint_is_line_ending_independent(tmp_path):
    (tmp_path / "a.md").write_bytes(b"line one\nline two\n")
    unix = kb_fingerprint(tmp_path)
    (tmp_path / "a.md").write_bytes(b"line one\r\nline two\r\n")
    assert kb_fingerprint(tmp_path) == unix
    assert kb_fingerprint(SETTINGS.retrieval.kb_dir)


def test_calibration_summary_has_every_metric():
    summary = calibration_summary([0.2, 0.8, 0.9], [0, 1, 1])
    assert {"ece", "mce", "brier", "nll", "auroc", "aurc", "accuracy"} <= set(summary)


def test_temperature_pinned_at_the_bound_is_flagged():
    """Scores below 0.5 for mostly-correct answers: no single T can fix them."""
    raw = np.full(40, 0.42)
    correct = np.array([1] * 34 + [0] * 6)
    scaler = TemperatureScaler().fit(raw, correct)
    assert scaler.at_bound is True
    assert scaler.transform(0.42) < 0.5  # cannot cross the 0.5 fixed point
    assert json.dumps(scaler.to_dict())  # plain JSON types only
