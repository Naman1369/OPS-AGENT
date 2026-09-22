"""Draw Fig. 1 of the research paper (system architecture). Run from the repo root."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

INK, INK2, MUTED, SURF = "#0b0b0b", "#52514e", "#898781", "#fcfcfb"
ACC, GOOD, BAD, SOFT = "#2a78d6", "#0ca30c", "#d03b3b", "#eef4fc"

fig, ax = plt.subplots(figsize=(10.5, 4.4), dpi=220)
fig.patch.set_facecolor(SURF)
ax.set_facecolor(SURF)
ax.set_xlim(0, 108)
ax.set_ylim(-2, 44)
ax.axis("off")


def box(x, y, w, h, title, sub="", edge=MUTED, fill="#ffffff", tc=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.2", fc=fill, ec=edge, lw=1.2))
    if sub:
        ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center", fontsize=9, weight="bold", color=tc)
        ax.text(x + w / 2, y + h * 0.30, sub, ha="center", va="center", fontsize=6.8, color=INK2)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=8.5, weight="bold", color=tc)


def arrow(x1, y1, x2, y2, color=INK2, ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=9, color=color, lw=1.1,
                                 linestyle=ls, connectionstyle=f"arc3,rad={rad}"))


y, h = 20, 9
box(1, y, 10, h, "Ticket", "raw text")
box(14, y, 13, h, "Intake", "category, priority,\nentities, query")
box(30, y, 13, h, "Retrieval", "MiniLM + Chroma,\nrelevance filter")
box(46, y, 13, h, "Resolution", "cited steps +\nraw confidence")
box(62, y, 12, h, "Calibration", "T-scaled\nconfidence", edge=ACC, fill=SOFT)
box(77, y - 1, 14, h + 2, "Governance", "G1-G7 rule engine\n(no LLM)", edge=ACC, fill=SOFT, tc=ACC)
box(95, 32, 11, 6, "Deliver", edge=GOOD, tc=GOOD)
box(95, 7, 11, 6, "Escalate", edge=BAD, tc=BAD)
for a, b in ((11, 14), (27, 30), (43, 46), (59, 62), (74, 77)):
    arrow(a + 0.6, y + h / 2, b - 0.6, y + h / 2)
arrow(91.4, y + 7.5, 96.5, 31.6, color=GOOD)
arrow(91.4, y + 0.5, 96.5, 13.4, color=BAD)
ax.text(95.2, 25.5, "all pass", fontsize=6.5, color=GOOD)
ax.text(95.2, 15.8, "any fails", fontsize=6.5, color=BAD)
arrow(36.5, y - 0.4, 81, y - 1.4, ls="--", rad=0.2)
ax.text(58, 14.2, "no usable evidence: Resolution is unreachable", fontsize=7, color=INK2, ha="center",
        bbox=dict(fc=SURF, ec="none", pad=1))
arrow(20.5, y + h + 0.4, 82, y + h + 1.4, ls="--", rad=-0.2)
ax.text(51, 36.6, "ticket not understood: skip straight to Governance", fontsize=7, color=INK2, ha="center",
        bbox=dict(fc=SURF, ec="none", pad=1))
box(56, 0, 19, 7.5, "Calibration profile", "T, threshold, alpha, delta,\nconfiguration fingerprint")
arrow(66, 7.9, 67.5, y - 0.5, color=MUTED, ls=":")
arrow(73, 7.9, 81, y - 1.5, color=MUTED, ls=":")
box(24, 0, 24, 7.5, "Audit trail (SQLite)", "every trace event, append-only,\nSHA-256 hash chain")
fig.savefig("docs/research/figures/architecture.png", facecolor=SURF, bbox_inches="tight")
