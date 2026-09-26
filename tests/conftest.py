import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_series(
    start: date,
    days: int,
    *,
    base: float = 100.0,
    growth_per_day: float = 0.0,
    season_amp: float = 0.0,
    spikes: dict[str, float] | None = None,
    project_daily: int = 10_000_000,
) -> dict:
    """Synthetic series with a known trend, seasonality and spikes."""
    views, project = {}, {}
    for i in range(days):
        day = start + timedelta(days=i)
        value = base + growth_per_day * i
        if season_amp:
            value *= 1 + season_amp * math.sin(2 * math.pi * day.timetuple().tm_yday / 365)
        key = day.isoformat()
        views[key] = int(round(value))
        project[key] = project_daily
    for key, multiplier in (spikes or {}).items():
        views[key] = int(views[key] * multiplier)

    share = {d: views[d] / project[d] * 1_000_000 for d in views}
    return {
        "lang": "pl",
        "title": "Test",
        "redirects": [],
        "views": views,
        "project_views": project,
        "share_per_million": share,
    }


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKITRENDS_CACHE_DIR", str(tmp_path))
    return tmp_path
