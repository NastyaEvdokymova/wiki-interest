"""SQLite cache of page views keyed by (project, article, day).

Recent days (the last LAG_DAYS) are not cached: Wikimedia finalises them with a
delay, and a stored zero would stay zero forever.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

LAG_DAYS = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS views (
    project TEXT NOT NULL,
    article TEXT NOT NULL,   -- '*' for the whole-edition aggregate
    day     TEXT NOT NULL,   -- YYYY-MM-DD
    views   INTEGER NOT NULL,
    PRIMARY KEY (project, article, day)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def cache_path() -> Path:
    base = os.environ.get("WIKITRENDS_CACHE_DIR")
    if base:
        root = Path(base)
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "wikitrends"
    root.mkdir(parents=True, exist_ok=True)
    return root / "cache.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(cache_path())
    conn.executescript(_SCHEMA)
    return conn


def stale_from(today: date | None = None) -> date:
    """First date that cannot be treated as final."""
    return (today or date.today()) - timedelta(days=LAG_DAYS)


def get_range(
    conn: sqlite3.Connection, project: str, article: str, start: date, end: date
) -> dict[str, int]:
    rows = conn.execute(
        "SELECT day, views FROM views WHERE project=? AND article=? AND day>=? AND day<=?",
        (project, article, start.isoformat(), end.isoformat()),
    ).fetchall()
    return {day: views for day, views in rows}


def put_range(
    conn: sqlite3.Connection,
    project: str,
    article: str,
    data: dict[str, int],
    *,
    today: date | None = None,
) -> None:
    cutoff = stale_from(today).isoformat()
    rows = [(project, article, day, v) for day, v in data.items() if day < cutoff]
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO views (project, article, day, views) VALUES (?,?,?,?)", rows
        )
        conn.commit()


def missing_days(cached: dict[str, int], start: date, end: date, *, today: date | None = None) -> bool:
    """True if the cache does not fully cover the final days of the range."""
    cutoff = stale_from(today)
    cur, last = start, min(end, cutoff - timedelta(days=1))
    while cur <= last:
        if cur.isoformat() not in cached:
            return True
        cur += timedelta(days=1)
    return end >= cutoff  # always refetch the recent tail


def clear() -> None:
    path = cache_path()
    if path.exists():
        path.unlink()
