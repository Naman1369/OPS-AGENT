"""Static figures for the evaluation report and the research paper.

Colour follows the entity, in a fixed order: the four pipeline variants take
categorical slots 1-4 of a validated colour-vision-deficiency-safe palette;
outcome classes use the reserved status colours. Every bar carries a direct
value label, so identity and value never depend on colour alone, and every
figure's numbers are also in the report's tables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..calibration.metrics import reliability_bins  # noqa: E402

VARIANT_COLORS = {
    "single_agent": "#2a78d6",
    "ungoverned": "#eb6834",
    "naive_governed": "#1baf7a",
    "calibration_governed": "#eda100",
}
OUTCOME_COLORS = {
    "correct_resolution": "#0ca30c",
    "unsafe_resolution": "#d03b3b",
    "necessary_escalation": "#c3c2b7",
    "unnecessary_escalation": "#fab219",
}
OUTCOME_LABELS = {
    "correct_resolution": "Correct autonomous resolution",
    "unsafe_resolution": "Unsafe autonomous resolution",
    "necessary_escalation": "Necessary escalation",
    "unnecessary_escalation": "Unnecessary escalation",
}
INK, INK_2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(1)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(True, color=GRID, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)


def _figure(width: float, height: float, ncols: int = 1):
    fig, axes = plt.subplots(1, ncols, figsize=(width, height), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    return fig, axes


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return path


def reliability_diagram(
    before: tuple[Sequence[float], Sequence[int]],
    after: tuple[Sequence[float], Sequence[int]],
    title_before: str,
    title_after: str,
    path: Path,
    n_bins: int = 10,
) -> Path:
    """Two panels: accuracy per confidence bin, raw vs temperature-scaled."""
    fig, axes = _figure(8.4, 3.8, 2)
    for ax, (conf, correct), title in zip(axes, (before, after), (title_before, title_after)):
        _style(ax)
        bins = reliability_bins(conf, correct, n_bins)
        centres = [(b["lower"] + b["upper"]) / 2 for b in bins]
        width = 1.0 / n_bins - 0.012
        heights = [b["accuracy"] if b["count"] else 0.0 for b in bins]
        ax.plot([0, 1], [0, 1], color=MUTED, linewidth=1, label="Perfect calibration")
        ax.bar(centres, heights, width=width, color="#2a78d6", label="Observed accuracy")
        for x, b in zip(centres, bins):
            if b["count"]:
                ax.text(x, (b["accuracy"] or 0) + 0.02, f"n={b['count']}", ha="center", fontsize=6.5, color=INK_2)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.08)
        ax.set_xlabel("Confidence", color=INK_2, fontsize=9)
        ax.set_ylabel("Accuracy of answer", color=INK_2, fontsize=9)
        ax.set_title(title, color=INK, fontsize=10, loc="left")
        ax.legend(frameon=False, fontsize=7.5, loc="upper left", labelcolor=INK_2)
    return _save(fig, path)


def outcome_composition(summaries: dict[str, dict[str, Any]], labels: dict[str, str], path: Path) -> Path:
    """100% stacked horizontal bars of the four outcome classes per variant."""
    variants = list(summaries)
    fig, ax = _figure(8.4, 0.62 * len(variants) + 1.3)
    _style(ax)
    ax.grid(axis="y", visible=False)
    y = np.arange(len(variants))[::-1]
    left = np.zeros(len(variants))
    for cls in OUTCOME_COLORS:
        values = np.array([summaries[v]["outcomes"][cls] / summaries[v]["n"] for v in variants])
        ax.barh(y, values, left=left, height=0.5, color=OUTCOME_COLORS[cls], label=OUTCOME_LABELS[cls],
                edgecolor=SURFACE, linewidth=2)
        for yi, li, vi in zip(y, left, values):
            if vi >= 0.07:
                ink = "#ffffff" if cls in ("correct_resolution", "unsafe_resolution") else INK
                ax.text(li + vi / 2, yi, f"{vi:.0%}", ha="center", va="center", fontsize=8, color=ink)
        left = left + values
    ax.set_yticks(y)
    ax.set_yticklabels([labels[v] for v in variants], color=INK, fontsize=9)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.12), labelcolor=INK_2)
    return _save(fig, path)


def metric_bars(
    values: dict[str, float],
    intervals: dict[str, tuple[float, float]] | None,
    labels: dict[str, str],
    title: str,
    path: Path,
    percent: bool = True,
    reference: float | None = None,
    reference_label: str = "",
) -> Path:
    """One metric per variant as vertical bars with value labels (and CIs)."""
    variants = list(values)
    fig, ax = _figure(5.6, 3.4)
    _style(ax)
    ax.grid(axis="x", visible=False)
    x = np.arange(len(variants))
    heights = [values[v] for v in variants]
    ax.bar(x, heights, width=0.5, color=[VARIANT_COLORS[v] for v in variants])
    if intervals:
        low = [heights[i] - intervals[v][0] for i, v in enumerate(variants)]
        high = [intervals[v][1] - heights[i] for i, v in enumerate(variants)]
        ax.errorbar(x, heights, yerr=[low, high], fmt="none", ecolor=INK_2, elinewidth=1, capsize=3)
    top = max([intervals[v][1] for v in variants] if intervals else heights + [0.01])
    for xi, h in zip(x, heights):
        ax.text(xi - 0.3, h + top * 0.03, f"{h:.1%}" if percent else f"{h:.3f}", ha="center",
                fontsize=8.5, color=INK)
    if reference is not None:
        ax.axhline(reference, color=MUTED, linewidth=1)
        ax.text(len(variants) - 0.5, reference, f" {reference_label}", va="bottom", ha="right", fontsize=7.5, color=INK_2)
    ax.set_xticks(x)
    ax.set_xticklabels([labels[v].replace(" ", "\n", 1) for v in variants], fontsize=8, color=INK)
    ax.set_ylim(0, top * 1.18 + 1e-9)
    if percent:
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_title(title, color=INK, fontsize=10, loc="left")
    return _save(fig, path)


def risk_coverage(
    curves: dict[str, tuple[Sequence[float], Sequence[float]]],
    points: dict[str, tuple[float, float, str]],
    labels: dict[str, str],
    path: Path,
    alpha: float | None = None,
) -> Path:
    """Unsafe Resolution Rate against automation rate as the threshold sweeps."""
    fig, ax = _figure(6.4, 4.0)
    _style(ax)
    for key, (automation, urr) in curves.items():
        ax.plot(automation, urr, color=VARIANT_COLORS[key], linewidth=2, solid_capstyle="round", label=labels[key])
    for key, (automation, urr, text) in points.items():
        ax.scatter([automation], [urr], s=64, color=VARIANT_COLORS[key], edgecolor=SURFACE, linewidth=2, zorder=3)
        left_side = automation > 0.3
        ax.annotate(text, (automation, urr), textcoords="offset points", xytext=(-6 if left_side else 6, 12),
                    fontsize=7.5, color=INK, ha="right" if left_side else "left",
                    bbox={"boxstyle": "round,pad=0.2", "fc": SURFACE, "ec": "none", "alpha": 0.9})
    if alpha is not None:
        ax.axhline(alpha, color=MUTED, linewidth=1)
        ax.text(0.01, alpha, f"target URR alpha = {alpha:.0%}", va="bottom", fontsize=7.5, color=INK_2)
    ax.set_xlabel("Automation rate (share of tickets resolved without a human)", color=INK_2, fontsize=9)
    ax.set_ylabel("Unsafe Resolution Rate (share of all tickets)", color=INK_2, fontsize=9)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK_2)
    return _save(fig, path)


def mast_heatmap(rates: dict[str, dict[str, float | None]], codes: Sequence[str], names: dict[str, str],
                 labels: dict[str, str], title: str, path: Path) -> Path:
    """Failure-mode rate (rows) by variant (columns), one-hue sequential ramp."""
    variants = list(rates)
    matrix = np.array([[rates[v].get(c) if rates[v].get(c) is not None else np.nan for v in variants] for c in codes],
                      dtype=float)
    fig, ax = _figure(7.6, 0.36 * len(codes) + 1.4)
    ax.set_facecolor(SURFACE)
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("blue", ["#f4f8fd", "#86b6ef", "#2a78d6", "#0d366b"])
    cmap.set_bad("#f0efec")
    vmax = max(0.05, np.nanmax(matrix) if np.isfinite(matrix).any() else 0.05)
    ax.imshow(matrix, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)
    for i in range(len(codes)):
        for j in range(len(variants)):
            value = matrix[i, j]
            if np.isnan(value):
                text = "n/a"
            elif value == 0:
                text = "0%"
            else:
                text = f"{value:.1%}" if value < 0.1 else f"{value:.0%}"
            ink = "#ffffff" if (not np.isnan(value) and value > vmax * 0.55) else INK
            ax.text(j, i, text, ha="center", va="center", fontsize=7.5, color=ink)
    ax.set_xticks(range(len(variants)))
    ax.set_xticklabels([labels[v].replace(" ", "\n", 1) for v in variants], fontsize=8, color=INK)
    ax.set_yticks(range(len(codes)))
    ax.set_yticklabels([f"{c} {names[c]}" for c in codes], fontsize=7.5, color=INK)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(title, color=INK, fontsize=10, loc="left")
    return _save(fig, path)


def sensitivity(alphas: Sequence[float], automation: Sequence[float], urr: Sequence[float], path: Path) -> Path:
    """Two small panels: what the risk target alpha buys and costs."""
    fig, axes = _figure(8.4, 3.2, 2)
    for ax, values, title in zip(axes, (automation, urr), ("Automation rate", "Unsafe Resolution Rate")):
        _style(ax)
        ax.plot(alphas, values, color="#eda100", linewidth=2, marker="o", markersize=5,
                markeredgecolor=SURFACE, markeredgewidth=2)
        for a, v in zip(alphas, values):
            ax.annotate(f"{v:.1%}", (a, v), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=7.5, color=INK)
        ax.set_xlabel("Target alpha", color=INK_2, fontsize=9)
        ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        ax.set_ylim(bottom=0, top=max(max(values) * 1.3, 0.02))
        ax.set_title(f"{title} vs risk target (V4)", color=INK, fontsize=10, loc="left")
    if len(axes) > 1:
        axes[1].plot(alphas, alphas, color=MUTED, linewidth=1)
        axes[1].text(alphas[-1], alphas[-1], " URR = alpha", fontsize=7, color=INK_2, va="bottom", ha="right")
    return _save(fig, path)
