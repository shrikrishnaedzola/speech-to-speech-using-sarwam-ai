"""matplotlib charts for the PDF (the on-screen report uses Recharts instead).

Same colours as the screen version (validated light-mode palette).
"""

import io

import matplotlib

matplotlib.use("Agg")  # no window, works on servers
import matplotlib.pyplot as plt  # noqa: E402

from report_module.schema import Report  # noqa: E402

STEPS = [
    ("stt_ms", "STT", "#2a78d6"),
    ("turn_wait_ms", "Turn wait", "#a8a7a1"),
    ("llm_ttft_ms", "LLM first token", "#eb6834"),
    ("tts_ttfb_ms", "TTS first audio", "#1baf7a"),
    ("other_ms", "Other", "#d6d5cf"),
]
TEXT, GRID = "#52514e", "#e5e4df"


def _style(ax):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=TEXT, labelsize=8, length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def latency_chart(report: Report) -> bytes | None:
    """Reply time per turn; stacked by step when the provider reports a split (Sarvam)."""
    turns = [t for t in report.latency.per_turn if t.turn_index > 0 and t.total_ms is not None]
    if not turns:
        return None
    x = [str(t.turn_index) for t in turns]
    fig, ax = plt.subplots(figsize=(7.2, 2.8), dpi=160)
    if report.latency.has_step_split:
        bottom = [0.0] * len(turns)
        for key, label, color in STEPS:
            values = [getattr(t, key) or 0 for t in turns]
            ax.bar(x, values, bottom=bottom, color=color, label=label, width=0.7, edgecolor="white", linewidth=0.8)
            bottom = [b + v for b, v in zip(bottom, values)]
    else:
        ax.bar(x, [t.total_ms for t in turns], color=STEPS[0][2], width=0.7, label="Reply time")
    # Rating limits as dashed lines, named in the legend (labels on the plot would cover bars).
    ax.axhline(1000, color=TEXT, linestyle="--", linewidth=0.8, label="1 s: Good below")
    ax.axhline(1500, color=TEXT, linestyle=":", linewidth=1.0, label="1.5 s: Poor above")
    ax.legend(fontsize=7, frameon=False, ncol=7, loc="upper center", bbox_to_anchor=(0.5, 1.2), labelcolor=TEXT)
    ax.set_xlabel("Turn", fontsize=8, color=TEXT)
    ax.set_ylabel("ms", fontsize=8, color=TEXT)
    _style(ax)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def section_scores_chart(report: Report) -> bytes:
    """Horizontal bars, one per section, value printed at the end of each bar."""
    labels = {"accuracy": "Accuracy", "mishearings": "Mishearings", "latency": "Latency",
              "voice_quality": "Voice quality", "language": "Language", "cost": "Cost"}
    items = list(report.summary.section_scores.items())
    fig, ax = plt.subplots(figsize=(7.2, 2.2), dpi=160)
    names = [labels[k] for k, _ in items][::-1]
    values = [v or 0 for _, v in items][::-1]
    ax.barh(names, values, color=STEPS[0][2], height=0.55)
    for i, (_, v) in enumerate(items[::-1]):
        ax.text((v or 0) + 1, i, "no data" if v is None else f"{v:.0f}", va="center", fontsize=7, color=TEXT)
    ax.set_xlim(0, 110)
    _style(ax)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
