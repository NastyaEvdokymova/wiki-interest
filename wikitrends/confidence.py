"""Confidence assessment by transparent rules.

The level is set by code, not by the model: the agent only relays `level` and
`reasons`. SKILL.md explicitly forbids raising confidence above it.
"""

from __future__ import annotations

LIMITATIONS = [
    "Wikipedia page views are a signal of attention, not of willingness to pay.",
    "Share per million compares language editions, not country audiences: "
    "readers of an edition can live anywhere.",
    "Some bot traffic is not caught by the agent=user filter.",
    "Since 2024 overall Wikipedia views have been falling due to AI answers in search; "
    "per-edition normalisation compensates for this only partially.",
]


def assess(analysis: dict) -> dict:
    """Returns {'level': high|medium|low, 'reasons': [...]}."""
    if analysis.get("error"):
        return {"level": "low", "reasons": [analysis["error"]]}

    reasons: list[str] = []
    critical = 0
    warnings = 0

    tr = analysis["trend"]
    months_used = tr["months_used"]
    base_views = analysis["current"]["monthly_views"]
    spike = analysis["spikes"]
    season = analysis["seasonality"]

    # 1. Series length
    if months_used < 12:
        critical += 1
        reasons.append(f"short series: only {months_used} full months")
    elif months_used < 24:
        warnings += 1
        reasons.append(
            f"series of {months_used} months is too short to separate trend from seasonality; "
            "year-over-year is not computed"
        )

    # 2. Base size
    if base_views < 100:
        critical += 1
        reasons.append(f"very small base: ~{base_views} views/month, close to noise")
    elif base_views < 500:
        warnings += 1
        reasons.append(f"small base: ~{base_views} views/month, sensitive to noise")

    # 3. Trend significance
    p_text = "p<0.0001" if tr["mk_p"] == 0 else f"p={tr['mk_p']}"
    if tr["significant"]:
        word = "significant growth" if tr["direction"] == "up" else "significant decline"
        reasons.append(f"{word} ({p_text}), {tr['change_pct_per_year']}% per year")
    else:
        warnings += 1
        reasons.append(
            f"trend not statistically significant ({p_text}): changes are indistinguishable from noise"
        )

    # 4. Contribution of anomalous days
    sog = spike.get("share_of_growth")
    if sog is not None and sog >= 0.5:
        critical += 1
        reasons.append(
            f"{int(sog * 100)}% of the growth comes from {spike['count']} anomalous days: "
            "one-off spikes, not sustained interest"
        )
    elif sog is not None and sog >= 0.25:
        warnings += 1
        reasons.append(
            f"{int(sog * 100)}% of the growth falls on {spike['count']} anomalous days"
        )

    # 5. Seasonality
    if season.get("detected"):
        peaks = ", ".join(str(m) for m in season.get("peak_months", []))
        note = f"strong seasonality (amplitude {season['amplitude']}, peak months {peaks})"
        if months_used < 24:
            warnings += 1
            note += "; on a short series it is easy to mistake for a trend"
        reasons.append(note)

    # 6. Gaps in the data
    zero_months = sum(1 for m in analysis["months"] if m["views"] == 0)
    if zero_months:
        warnings += 1
        reasons.append(f"{zero_months} months with zero views: the article probably did not exist yet")

    if critical:
        level = "low"
    elif warnings >= 2:
        level = "medium"
    elif warnings == 1:
        level = "medium" if not tr["significant"] or base_views < 500 else "high"
    else:
        level = "high"

    return {"level": level, "reasons": reasons}


CONF_LABEL = {"high": "high", "medium": "medium", "low": "low"}


def verdict(analysis: dict, conf: dict) -> str:
    """A one-sentence verdict, so the model does not compose its own."""
    if analysis.get("error"):
        return f"{analysis['lang']}: not enough data ({analysis['error']})"

    tr = analysis["trend"]
    lang = analysis["lang"]
    share = analysis["current"]["share_per_million"]
    level = CONF_LABEL.get(conf["level"], conf["level"])
    if not tr["significant"]:
        return (
            f"{lang}: interest is stable (~{share} views per million), "
            f"no significant trend; confidence {level}"
        )
    word = "growing" if tr["direction"] == "up" else "declining"
    return (
        f"{lang}: interest is {word} by {abs(tr['change_pct_per_year'])}% per year "
        f"(~{share} views per million); confidence {level}"
    )
