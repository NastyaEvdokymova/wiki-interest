"""Synthetic series with known answers: the metrics must catch what they should."""

import random
from datetime import date

from conftest import make_series

from wikitrends import analyze as an
from wikitrends.confidence import assess

START = date(2023, 1, 1)
THREE_YEARS = 1095


def test_theil_sen_matches_known_slope():
    ys = [10 + 2 * i for i in range(20)]
    assert abs(an.theil_sen(ys) - 2.0) < 1e-9


def test_theil_sen_ignores_single_outlier():
    ys = [10 + 2 * i for i in range(20)]
    ys[7] = 5000  # one day on the main page
    assert abs(an.theil_sen(ys) - 2.0) < 0.5


def test_mann_kendall_flags_flat_series_as_insignificant():
    ys = [100, 102, 98, 101, 99, 103, 97, 100, 101, 99, 102, 98]
    assert an.mann_kendall(ys)["significant"] is False


def test_mann_kendall_detects_monotone_growth():
    mk = an.mann_kendall([100 + 5 * i for i in range(24)])
    assert mk["significant"] is True
    assert mk["p"] < 0.01


def test_partial_months_are_dropped():
    series = make_series(date(2023, 1, 15), 120)  # start and end mid-month
    months = an.to_monthly(series)
    assert months[0]["month"] == "2023-02"
    assert months[-1]["month"] == "2023-04"


def test_growth_series_reports_upward_trend():
    series = make_series(START, THREE_YEARS, base=1000, growth_per_day=1.0)
    result = an.to_monthly(series)
    trend = an.trend(result)
    assert trend["direction"] == "up"
    assert trend["significant"] is True
    assert trend["change_pct_per_year"] > 10


def _months(values: list[float]) -> list[dict]:
    return [
        {"month": f"{2020 + i // 12}-{i % 12 + 1:02d}", "value": v, "views": int(v)}
        for i, v in enumerate(values)
    ]


def test_trend_is_a_compounding_annual_rate():
    halving = _months([100 * 0.5 ** (i / 12) for i in range(36)])
    assert abs(an.trend(halving)["change_pct_per_year"] + 50) < 1
    doubling = _months([100 * 2 ** (i / 12) for i in range(36)])
    assert abs(an.trend(doubling)["change_pct_per_year"] - 100) < 1


def test_steep_decline_never_exceeds_minus_100_percent():
    crash = _months([1000 * 0.75**i for i in range(24)])  # −25% every month
    assert -100 < an.trend(crash)["change_pct_per_year"] < -95


def test_seasonality_is_not_mistaken_for_trend():
    series = make_series(START, THREE_YEARS, base=1000, season_amp=0.6)
    months = an.to_monthly(series)
    assert an.seasonality(months)["detected"] is True
    assert an.trend(months)["direction"] == "flat"


def test_noisy_series_is_not_called_seasonal():
    rng = random.Random(42)
    series = make_series(START, THREE_YEARS, base=6)
    for day in series["views"]:
        series["views"][day] = max(0, int(rng.gauss(6, 4)))
    series["share_per_million"] = {
        d: series["views"][d] / series["project_views"][d] * 1_000_000 for d in series["views"]
    }
    season = an.seasonality(an.to_monthly(series))
    assert season["detected"] is False


def test_yoy_ignores_seasonal_swing():
    series = make_series(START, THREE_YEARS, base=1000, season_amp=0.6)
    yoy = an.year_over_year(an.to_monthly(series))
    assert yoy["available"] is True
    assert abs(yoy["change_pct"]) < 5


def test_yoy_reports_monthly_averages_not_sums():
    months = [{"month": f"m{i}", "value": 10.0} for i in range(12)] + [
        {"month": f"n{i}", "value": 5.0} for i in range(12)
    ]
    yoy = an.year_over_year(months)
    assert yoy["previous_12m_monthly_avg"] == 10.0
    assert yoy["recent_12m_monthly_avg"] == 5.0
    assert yoy["change_pct"] == -50.0


def test_spike_days_are_detected_and_attributed():
    series = make_series(
        START,
        THREE_YEARS,
        base=1000,
        spikes={"2025-03-10": 40, "2025-03-11": 30, "2025-03-12": 25},
    )
    spikes = an.spikes(series)
    found = {d["date"] for d in spikes["days"]}
    assert {"2025-03-10", "2025-03-11", "2025-03-12"} <= found
    assert spikes["share_of_growth"] is not None and spikes["share_of_growth"] > 0.9


def test_confidence_drops_when_growth_comes_from_spikes():
    series = make_series(
        START,
        THREE_YEARS,
        base=1000,
        spikes={"2025-03-10": 60, "2025-03-11": 50, "2025-03-12": 40},
    )
    months = an.to_monthly(series)
    analysis = {
        "lang": "pl",
        "title": "Test",
        "current": {"monthly_views": 30000, "share_per_million": 3.0},
        "trend": an.trend(months),
        "yoy": an.year_over_year(months),
        "seasonality": an.seasonality(months),
        "spikes": an.spikes(series),
        "months": months,
    }
    conf = assess(analysis)
    assert conf["level"] == "low"
    assert any("of the growth" in r for r in conf["reasons"])


def test_small_base_lowers_confidence():
    series = make_series(START, THREE_YEARS, base=2)
    months = an.to_monthly(series)
    analysis = {
        "lang": "cs",
        "title": "Test",
        "current": {"monthly_views": 60, "share_per_million": 0.2},
        "trend": an.trend(months),
        "yoy": an.year_over_year(months),
        "seasonality": an.seasonality(months),
        "spikes": an.spikes(series),
        "months": months,
    }
    conf = assess(analysis)
    assert conf["level"] == "low"
    assert any("base" in r for r in conf["reasons"])


def test_ranking_penalises_low_confidence():
    strong = {
        "lang": "pl",
        "title": "A",
        "current": {"monthly_views": 5000, "share_per_million": 10.0},
        "trend": {"change_pct_per_year": 5.0, "significant": True},
        "confidence": {"level": "high"},
    }
    shaky = {
        "lang": "cs",
        "title": "B",
        "current": {"monthly_views": 80, "share_per_million": 9.5},
        "trend": {"change_pct_per_year": 90.0, "significant": True},
        "confidence": {"level": "low"},
    }
    ranking = an.rank_langs([strong, shaky])
    assert ranking[0]["lang"] == "pl"


def test_insignificant_growth_scores_as_zero_growth():
    ranked = an.rank_langs(
        [
            {
                "lang": "pl",
                "title": "A",
                "current": {"monthly_views": 5000, "share_per_million": 10.0},
                "trend": {"change_pct_per_year": 80.0, "significant": False},
                "confidence": {"level": "high"},
            }
        ],
        {"volume": 0.0, "growth": 1.0},
    )
    assert ranked[0]["score"] == 0.5  # (0 + 100) / 200


def _result(lang, share, views, pct, significant, level):
    return {
        "lang": lang,
        "title": lang.upper(),
        "current": {"monthly_views": views, "share_per_million": share},
        "trend": {"change_pct_per_year": pct, "significant": significant},
        "confidence": {"level": level},
    }


def test_thresholds_move_languages_out_of_the_ranking():
    results = [
        _result("pl", 10.0, 5000, 5.0, True, "high"),
        _result("cs", 9.0, 3000, 0.0, False, "low"),
        _result("uk", 8.0, 80, 0.0, False, "medium"),
        {"lang": "sk", "title": None, "error": "no article in this language edition"},
    ]
    kept, excluded = an.screen_langs(results, min_confidence="medium", min_views=100)
    assert [r["lang"] for r in kept] == ["pl"]
    reasons = {e["lang"]: e["reason"] for e in excluded}
    assert "confidence low" in reasons["cs"]
    assert "80 views/month" in reasons["uk"]
    assert reasons["sk"] == "no article in this language edition"


def test_recommendation_explains_every_rank_and_skips_low_confidence_for_next():
    from wikitrends.cli import _recommendation

    ranking = an.rank_langs(
        [
            _result("pl", 10.0, 5000, 20.0, True, "high"),
            _result("cs", 9.0, 3000, 0.0, False, "low"),
            _result("de", 5.0, 2000, 0.0, False, "medium"),
        ]
    )
    rec = _recommendation(ranking, {"volume": 0.5, "growth": 0.5})
    assert len(rec["why"]) == 3
    assert "50% of the leader" in next(w for w in rec["why"] if w.startswith("de"))
    assert rec["research_next"] == ["pl", "de"]
    assert "min_confidence=low" in rec["criteria"]
