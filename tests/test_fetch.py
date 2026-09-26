"""Tests on recorded API responses: offline and deterministic."""

import json
from datetime import date

import pytest

from wikitrends import cache, fetch, resolve
from wikitrends.http import ApiError

JAN_START, JAN_END = date(2025, 1, 1), date(2025, 1, 31)
TODAY = date(2025, 3, 1)  # January is long final → cached in full


@pytest.fixture
def router(fixtures_dir, monkeypatch):
    """Stubs the network: URL → recorded response. Counts calls."""
    calls = {"count": 0}

    def load(name):
        return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))

    def fake_get_json(url, params=None, **kwargs):
        calls["count"] += 1
        if "per-article" in url:
            if "Intervallfasten" in url or "Kurzzeitfasten" in url:
                return load("per_article_cs.json")  # any valid series will do for a redirect
            return load("per_article_cs.json")
        if "aggregate" in url:
            return load("aggregate_cs.json")
        if params and params.get("prop") == "redirects":
            return load("redirects_de.json" if "de." in url else "redirects_cs.json")
        if params and params.get("generator") == "search":
            return load("search_ru_fasting.json")
        if params and params.get("action") == "wbgetentities":
            return load("entities_q1666254.json")
        raise AssertionError(f"unexpected request: {url} {params}")

    monkeypatch.setattr("wikitrends.fetch.get_json", fake_get_json)
    monkeypatch.setattr("wikitrends.resolve.get_json", fake_get_json)
    return calls


def test_parse_items_groups_by_day():
    items = [
        {"timestamp": "2025010100", "views": 10},
        {"timestamp": "2025010200", "views": 20},
    ]
    assert fetch._parse_items(items) == {"2025-01-01": 10, "2025-01-02": 20}


def test_article_daily_covers_every_day(router, tmp_cache):
    data = fetch.fetch_article_daily("cs", "Přerušovaný půst", JAN_START, JAN_END, today=TODAY)
    assert len(data) == 31
    assert all(isinstance(v, int) for v in data.values())
    assert sum(data.values()) > 0


def test_second_call_is_served_from_cache(router, tmp_cache):
    fetch.fetch_article_daily("cs", "Přerušovaný půst", JAN_START, JAN_END, today=TODAY)
    before = router["count"]
    fetch.fetch_article_daily("cs", "Přerušovaný půst", JAN_START, JAN_END, today=TODAY)
    assert router["count"] == before  # no new requests


def test_fresh_tail_is_not_cached(tmp_cache):
    conn = cache.connect()
    today = date(2025, 3, 10)
    cache.put_range(
        conn, "cs.wikipedia", "X", {"2025-03-05": 5, "2025-03-09": 9}, today=today
    )
    stored = cache.get_range(conn, "cs.wikipedia", "X", date(2025, 3, 1), today)
    assert "2025-03-05" in stored  # older than the lag: stored
    assert "2025-03-09" not in stored  # recent tail: not stored


def test_missing_article_yields_zeros_not_crash(fixtures_dir, monkeypatch, tmp_cache):
    def missing(url, params=None, **kwargs):
        if "aggregate" in url:
            return json.loads((fixtures_dir / "aggregate_cs.json").read_text(encoding="utf-8"))
        raise ApiError("404", hint="", status=404)

    monkeypatch.setattr("wikitrends.fetch.get_json", missing)
    data = fetch.fetch_article_daily("cs", "No such article", JAN_START, JAN_END, today=TODAY)
    assert set(data.values()) == {0}


def test_series_merges_redirect_views(router, tmp_cache):
    plain = fetch.fetch_series(
        "cs", "Přerušovaný půst", JAN_START, JAN_END, include_redirects=False, today=TODAY
    )
    merged = fetch.fetch_series(
        "de", "Intermittierendes Fasten", JAN_START, JAN_END, today=TODAY
    )
    assert merged["redirects"] == ["Intervallfasten", "Kurzzeitfasten"]
    # three identical series (article + two redirects) vs one
    assert sum(merged["views"].values()) == 3 * sum(plain["views"].values())


def test_share_is_normalised_per_million(router, tmp_cache):
    series = fetch.fetch_series(
        "cs", "Přerušovaný půst", JAN_START, JAN_END, include_redirects=False, today=TODAY
    )
    day = "2025-01-15"
    expected = series["views"][day] / series["project_views"][day] * 1_000_000
    assert series["share_per_million"][day] == pytest.approx(expected)


def test_resolve_returns_titles_per_language(router):
    res = resolve.resolve_topic("Периодическое голодание", ["cs", "uk"], search_lang="ru")
    assert res["selected"]["qid"] == "Q1666254"
    assert res["selected"]["titles"]["cs"] == "Přerušovaný půst"
    assert res["ambiguous"] is False  # exact title match


def test_resolve_flags_ambiguity(router):
    res = resolve.resolve_topic("голодание по часам", ["cs", "uk"], search_lang="ru")
    assert res["ambiguous"] is True
    assert "hint" in res


def test_resolve_reports_missing_languages(router):
    res = resolve.resolve_topic("Периодическое голодание", ["cs", "pl"], search_lang="ru")
    assert res["selected"]["missing_langs"] == ["pl"]
    assert "warning" in res
