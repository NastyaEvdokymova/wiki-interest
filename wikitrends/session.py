"""State of the last run.

Lets "now add Czech" or "make a report" pick up where the last run left off.
"""

from __future__ import annotations

import json
from pathlib import Path

from .cache import cache_path


def _path() -> Path:
    return cache_path().parent / "session.json"


def save(kind: str, payload: dict) -> None:
    _path().write_text(
        json.dumps({"kind": kind, **payload}, ensure_ascii=False), encoding="utf-8"
    )


def load() -> dict | None:
    p = _path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def summary() -> dict:
    state = load()
    if not state:
        return {"empty": True, "hint": "Session is empty: start with the resolve command."}
    return {
        "kind": state.get("kind"),
        "qid": state.get("qid"),
        "label": state.get("label"),
        "langs": [r["lang"] for r in state.get("results", [])],
        "period": state.get("period"),
        "metric": state.get("metric"),
    }


def clear() -> None:
    p = _path()
    if p.exists():
        p.unlink()
