"""Fetching page views from the Wikimedia Pageviews API, with caching.

Two metrics:
  * per-article  - views of a specific article (+ its redirects);
  * aggregate    - views of the whole language edition, the normalisation denominator.

agent=user everywhere: bots and spiders are dropped on the API side.
"""

from __future__ import annotations

from datetime import date, timedelta

from . import cache
from .http import ApiError, encode_title, get_json

REST = "https://wikimedia.org/api/rest_v1/metrics/pageviews"
DATA_START = date(2015, 7, 1)  # no per-article data before this


def project_of(lang: str) -> str:
    return f"{lang}.wikipedia"


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _parse_items(items: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        ts = it["timestamp"]  # YYYYMMDD00
        day = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
        out[day] = out.get(day, 0) + int(it["views"])
    return out


def _fetch_start(cached: dict[str, int], start: date, end: date, today: date | None) -> date | None:
    """Date from which the API must be queried (None: everything is cached)."""
    cutoff = cache.stale_from(today)
    cur = start
    while cur < min(end + timedelta(days=1), cutoff):
        if cur.isoformat() not in cached:
            return cur
        cur += timedelta(days=1)
    return cutoff if end >= cutoff else None


def fetch_article_daily(
    lang: str,
    title: str,
    start: date,
    end: date,
    *,
    use_cache: bool = True,
    today: date | None = None,
) -> dict[str, int]:
    """Daily views of one article. Missing days are filled with zeros."""
    project = project_of(lang)
    start = max(start, DATA_START)
    conn = cache.connect() if use_cache else None

    cached = cache.get_range(conn, project, title, start, end) if conn else {}
    need_from = _fetch_start(cached, start, end, today) if conn else start

    if need_from is not None and need_from <= end:
        url = (
            f"{REST}/per-article/{project}.org/all-access/user/"
            f"{encode_title(title)}/daily/{_ymd(need_from)}/{_ymd(end)}"
        )
        try:
            fresh = _parse_items(get_json(url).get("items", []))
        except ApiError as exc:
            if exc.status == 404:
                fresh = {}  # the article exists but has no views in the period
            else:
                raise
        cached.update(fresh)
        if conn:
            cache.put_range(conn, project, title, fresh, today=today)

    if conn:
        conn.close()
    return _fill_zeros(cached, start, end)


def fetch_project_daily(
    lang: str,
    start: date,
    end: date,
    *,
    use_cache: bool = True,
    today: date | None = None,
) -> dict[str, int]:
    """Daily views of the whole language edition: the normalisation denominator."""
    project = project_of(lang)
    start = max(start, DATA_START)
    conn = cache.connect() if use_cache else None

    cached = cache.get_range(conn, project, "*", start, end) if conn else {}
    need_from = _fetch_start(cached, start, end, today) if conn else start

    if need_from is not None and need_from <= end:
        url = (
            f"{REST}/aggregate/{project}.org/all-access/user/daily/"
            f"{_ymd(need_from)}/{_ymd(end)}"
        )
        fresh = _parse_items(get_json(url).get("items", []))
        cached.update(fresh)
        if conn:
            cache.put_range(conn, project, "*", fresh, today=today)

    if conn:
        conn.close()
    return _fill_zeros(cached, start, end)


def fetch_redirects(lang: str, title: str, *, limit: int = 100) -> list[str]:
    """Titles that redirect to the article.

    Views are counted per exact title: without summing redirects, renaming an
    article looks like a collapse in interest.
    """
    data = get_json(
        f"https://{lang}.wikipedia.org/w/api.php",
        {
            "action": "query",
            "prop": "redirects",
            "titles": title,
            "rdlimit": str(limit),
            "rdnamespace": "0",
            "format": "json",
            "formatversion": "2",
        },
    )
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return []
    return [r["title"] for r in pages[0].get("redirects", [])]


def fetch_series(
    lang: str,
    title: str,
    start: date,
    end: date,
    *,
    include_redirects: bool = True,
    use_cache: bool = True,
    today: date | None = None,
) -> dict:
    """Full series for an article: views, edition denominator and share per million."""
    article = fetch_article_daily(lang, title, start, end, use_cache=use_cache, today=today)

    redirects: list[str] = []
    if include_redirects:
        try:
            redirects = fetch_redirects(lang, title)
        except ApiError:
            redirects = []  # redirects are a bonus, not a reason to fail
        for rd in redirects:
            extra = fetch_article_daily(lang, rd, start, end, use_cache=use_cache, today=today)
            for day, v in extra.items():
                article[day] = article.get(day, 0) + v

    project = fetch_project_daily(lang, start, end, use_cache=use_cache, today=today)
    share = {
        day: (article[day] / project[day] * 1_000_000) if project.get(day) else 0.0
        for day in article
    }
    return {
        "lang": lang,
        "title": title,
        "redirects": redirects,
        "views": article,
        "project_views": project,
        "share_per_million": share,
    }


def _fill_zeros(data: dict[str, int], start: date, end: date) -> dict[str, int]:
    out: dict[str, int] = {}
    cur = start
    while cur <= end:
        key = cur.isoformat()
        out[key] = int(data.get(key, 0))
        cur += timedelta(days=1)
    return out
