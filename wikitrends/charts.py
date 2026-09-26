"""Chart of normalised series. matplotlib is imported lazily."""

from __future__ import annotations

from pathlib import Path


def _smooth(values: list[float], window: int = 3) -> list[float]:
    """Rolling median: removes one-off spikes without shifting the level."""
    if len(values) < window:
        return values
    half = window // 2
    out = []
    for i in range(len(values)):
        chunk = sorted(values[max(0, i - half) : i + half + 1])
        out.append(chunk[len(chunk) // 2])
    return out


def monthly_chart(results: list[dict], out_path: str | Path, *, metric: str = "share") -> Path:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "Charts need matplotlib: install the report extra "
            "(`uv sync --extra report`)."
        ) from exc

    # Shared month axis: series may start at different times (article created later).
    axis = sorted({m["month"] for r in results for m in (r.get("months") or [])})
    positions = {month: i for i, month in enumerate(axis)}

    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=150)
    for res in results:
        months = res.get("months") or []
        if not months:
            continue
        smoothed = _smooth([m["value"] for m in months])
        xs = [positions[m["month"]] for m in months]
        ax.plot(xs, smoothed, linewidth=1.8, label=f"{res['lang']} — {res['title']}")

    label = "views per million views of the edition" if metric == "share" else "views per month"
    ax.set_ylabel(label, fontsize=8)
    ax.grid(True, alpha=0.25, linewidth=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=8, frameon=False)
    ax.tick_params(labelsize=7)

    step = max(1, len(axis) // 12)
    ax.set_xticks(list(range(0, len(axis), step)))
    ax.set_xticklabels(axis[::step], rotation=45, ha="right")

    fig.tight_layout()
    out = Path(out_path)
    fig.savefig(out)
    plt.close(fig)
    return out
