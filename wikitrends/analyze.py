"""All the analytics: monthly aggregation, trend, seasonality, outliers.

The metrics are deliberately robust to outliers: one day on the main page must not
turn into a "growing trend".
"""

from __future__ import annotations

import math
from datetime import date

from . import fetch

# ---------------------------------------------------------------- statistics


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def mad(values: list[float]) -> float:
    """Median absolute deviation: a robust analogue of the standard deviation."""
    if not values:
        return 0.0
    m = median(values)
    return median([abs(v - m) for v in values])


def theil_sen(ys: list[float]) -> float:
    """Theil–Sen slope: median of pairwise slopes, x = point index."""
    n = len(ys)
    if n < 2:
        return 0.0
    slopes = [
        (ys[j] - ys[i]) / (j - i)
        for i in range(n - 1)
        for j in range(i + 1, n)
    ]
    return median(slopes)


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def mann_kendall(ys: list[float]) -> dict:
    """Mann–Kendall test for a monotonic trend (with tie correction)."""
    n = len(ys)
    if n < 4:
        return {"s": 0, "z": 0.0, "p": 1.0, "significant": False}

    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            s += (ys[j] > ys[i]) - (ys[j] < ys[i])

    counts: dict[float, int] = {}
    for y in ys:
        counts[y] = counts.get(y, 0) + 1
    ties = sum(c * (c - 1) * (2 * c + 5) for c in counts.values() if c > 1)
    var = (n * (n - 1) * (2 * n + 5) - ties) / 18.0
    if var <= 0:
        return {"s": s, "z": 0.0, "p": 1.0, "significant": False}

    z = (s - 1) / math.sqrt(var) if s > 0 else ((s + 1) / math.sqrt(var) if s < 0 else 0.0)
    p = 2 * (1 - _phi(abs(z)))
    return {"s": s, "z": round(z, 2), "p": round(p, 4), "significant": p < 0.05}


# ------------------------------------------------------------- aggregation


def to_monthly(series: dict, metric: str = "share") -> list[dict]:
    """Daily series → full calendar months.

    Partial months at the edges are dropped: otherwise the last month always
    looks like a dip simply because it has not ended yet.
    """
    views, project = series["views"], series["project_views"]
    buckets: dict[str, dict] = {}
    for day, v in views.items():
        key = day[:7]
        b = buckets.setdefault(key, {"views": 0, "project": 0, "days": 0})
        b["views"] += v
        b["project"] += project.get(day, 0)
        b["days"] += 1

    out = []
    for month in sorted(buckets):
        b = buckets[month]
        year, mon = int(month[:4]), int(month[5:7])
        if b["days"] < _days_in_month(year, mon):
            continue
        share = (b["views"] / b["project"] * 1_000_000) if b["project"] else 0.0
        out.append(
            {
                "month": month,
                "views": b["views"],
                "share_per_million": round(share, 3),
                "value": round(share, 3) if metric == "share" else b["views"],
            }
        )
    return out


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return (date(year + 1, 1, 1) - date(year, 12, 1)).days
    return (date(year, month + 1, 1) - date(year, month, 1)).days


# ------------------------------------------------------------- metrics


def trend(months: list[dict]) -> dict:
    """Trend as an annual rate of change.

    The slope is computed on log values: "-50% per year" must mean multiplying
    by 0.5 each year, not subtracting half of the starting level. A linear slope
    divided by the median gives numbers like -76%/yr on a steep decline, which
    disagree with year-over-year and push the series below zero within two years.
    Mann–Kendall is rank-based, so taking logs does not change it.
    """
    ys = [m["value"] for m in months]
    mk = mann_kendall(ys)

    positive = [y for y in ys if y > 0]
    floor = min(positive) / 2 if positive else 1.0
    log_slope = theil_sen([math.log(y if y > 0 else floor) for y in ys])
    pct_year = (math.exp(log_slope * 12) - 1) * 100

    direction = "flat"
    if mk["significant"]:
        direction = "up" if log_slope > 0 else "down"
    return {
        "log_slope_per_month": round(log_slope, 5),
        "change_pct_per_year": round(pct_year, 1),
        "mk_p": mk["p"],
        "significant": mk["significant"],
        "direction": direction,
        "months_used": len(ys),
    }


def year_over_year(months: list[dict]) -> dict:
    """Year over year on matching months, so seasonality is not mistaken for growth."""
    if len(months) < 24:
        return {"available": False, "reason": "needs at least 24 full months"}
    recent, prev = months[-12:], months[-24:-12]
    r = sum(m["value"] for m in recent)
    p = sum(m["value"] for m in prev)
    # Monthly averages, not 12-month sums: a weak model read a sum of shares
    # (116 per million) as the monthly level (actually ~9.7).
    return {
        "available": True,
        "recent_12m_monthly_avg": round(r / 12, 2),
        "previous_12m_monthly_avg": round(p / 12, 2),
        "change_pct": round((r - p) / p * 100, 1) if p else None,
    }


def seasonality(months: list[dict]) -> dict:
    """Month-of-year index relative to the overall level."""
    if len(months) < 24:
        return {"detected": False, "reason": "needs at least 24 full months"}
    overall = median([m["value"] for m in months])
    if overall <= 0:
        return {"detected": False, "reason": "zero baseline level"}

    by_month: dict[int, list[float]] = {}
    for m in months:
        by_month.setdefault(int(m["month"][5:7]), []).append(m["value"])
    index = {mon: round(median(vals) / overall, 2) for mon, vals in sorted(by_month.items())}
    amplitude = max(index.values()) - min(index.values())
    peaks = [mon for mon, v in index.items() if v >= 1.2]

    # Noise threshold: on a small base the spread within one month of the year can exceed
    # the difference between months, and then "seasonality" is just jitter.
    noise = median([mad(vals) / overall for vals in by_month.values() if len(vals) > 1])
    threshold = max(0.3, 2 * noise)
    return {
        "detected": amplitude >= threshold,
        "amplitude": round(amplitude, 2),
        "noise_threshold": round(threshold, 2),
        "peak_months": peaks,
        "index": index,
    }


def spikes(series: dict, metric: str = "share", *, top: int = 5) -> dict:
    """Anomalous days by median and MAD + the share of growth they explain."""
    key = "share_per_million" if metric == "share" else "views"
    daily = series[key]
    days = sorted(daily)
    if len(days) < 30:
        return {"days": [], "share_of_growth": None}

    values = [daily[d] for d in days]
    m = median(values)
    sigma = 1.4826 * mad(values)
    threshold = m + 5 * sigma if sigma > 0 else m * 3

    found = [
        {"date": d, "value": round(daily[d], 2), "x_median": round(daily[d] / m, 1) if m else None}
        for d in days
        if daily[d] > threshold and daily[d] > 2 * m
    ]
    found.sort(key=lambda x: x["value"], reverse=True)

    # How much of the "growth" these days alone produce: last 365 days vs the previous 365.
    share_of_growth = None
    if len(days) >= 730:
        recent, prev = days[-365:], days[-730:-365]
        growth = sum(daily[d] for d in recent) - sum(daily[d] for d in prev)
        recent_set = set(recent)
        excess = sum(daily[f["date"]] - m for f in found if f["date"] in recent_set)
        if growth > 0:
            share_of_growth = round(min(excess / growth, 1.0), 2)

    return {"days": found[:top], "count": len(found), "share_of_growth": share_of_growth}


# ------------------------------------------------------------- entry point


CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


def screen_langs(
    results: list[dict], *, min_confidence: str = "low", min_views: int = 0
) -> tuple[list[dict], list[dict]]:
    """Split results into rankable ones and excluded ones, with a reason for each exclusion.

    The user's thresholds move a language out of the ranking entirely, rather than
    letting a heavy penalty leave it at the bottom where it still looks like a candidate.
    """
    kept, excluded = [], []
    floor = CONF_ORDER[min_confidence]
    for r in results:
        if r.get("error"):
            excluded.append({"lang": r["lang"], "reason": r["error"]})
            continue
        level = r.get("confidence", {}).get("level", "low")
        views = r["current"]["monthly_views"]
        if CONF_ORDER.get(level, 0) < floor:
            excluded.append(
                {"lang": r["lang"], "reason": f"confidence {level} is below the threshold {min_confidence}"}
            )
        elif views < min_views:
            excluded.append(
                {"lang": r["lang"], "reason": f"~{views} views/month is below the threshold {min_views}"}
            )
        else:
            kept.append(r)
    return kept, excluded


def rank_langs(results: list[dict], weights: dict[str, float] | None = None) -> list[dict]:
    """Rank languages by a transparent formula.

    By default volume and growth weigh equally; low confidence penalises the score
    so that "growth from a base of 40 views" does not end up on top.
    """
    weights = weights or {"volume": 0.5, "growth": 0.5}
    total = sum(weights.values()) or 1.0
    w_vol = weights.get("volume", 0.0) / total
    w_growth = weights.get("growth", 0.0) / total

    usable = [r for r in results if not r.get("error")]
    if not usable:
        return []

    max_share = max(r["current"]["share_per_million"] for r in usable) or 1.0
    penalty = {"high": 1.0, "medium": 0.85, "low": 0.6}

    ranked = []
    for r in usable:
        growth = max(-100.0, min(100.0, r["trend"]["change_pct_per_year"]))
        if not r["trend"]["significant"]:
            growth = 0.0  # an insignificant trend earns no points
        score = (
            w_vol * (r["current"]["share_per_million"] / max_share)
            + w_growth * ((growth + 100) / 200)
        ) * penalty.get(r.get("confidence", {}).get("level", "medium"), 0.85)
        ranked.append(
            {
                "lang": r["lang"],
                "title": r["title"],
                "share_per_million": r["current"]["share_per_million"],
                # No monthly_views here: raw views are not comparable across editions, and a
                # weak model given them ranked "largest audience" by them anyway.
                "change_pct_per_year": r["trend"]["change_pct_per_year"],
                "significant": r["trend"]["significant"],
                "confidence": r.get("confidence", {}).get("level"),
                "score": round(score, 3),
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked


def analyze_lang(
    lang: str,
    title: str,
    start: date,
    end: date,
    *,
    metric: str = "share",
    use_cache: bool = True,
) -> dict:
    series = fetch.fetch_series(lang, title, start, end, use_cache=use_cache)
    months = to_monthly(series, metric)
    if not months:
        return {
            "lang": lang,
            "title": title,
            "error": "no full month of data",
            "months": [],
        }

    recent = months[-12:] if len(months) >= 12 else months
    return {
        "lang": lang,
        "title": title,
        "redirects_merged": len(series["redirects"]),
        "period": {"from": months[0]["month"], "to": months[-1]["month"]},
        "metric": metric,
        "current": {
            "monthly_views": round(sum(m["views"] for m in recent) / len(recent)),
            "share_per_million": round(
                sum(m["share_per_million"] for m in recent) / len(recent), 2
            ),
        },
        "trend": trend(months),
        "yoy": year_over_year(months),
        "seasonality": seasonality(months),
        "spikes": spikes(series, metric),
        "months": months,
    }
