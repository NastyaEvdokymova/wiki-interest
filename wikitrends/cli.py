"""CLI: the skill's only interface.

Output is always compact JSON: the heavy monthly series stay in the session and go
into the report, not into the model's context.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta

from . import analyze as an
from . import cache, charts, fetch, report, resolve, session
from .confidence import LIMITATIONS, assess, verdict
from .http import ApiError

QID_RE = re.compile(r"^Q\d+$")
CONF_LABEL = {"high": "high", "medium": "medium", "low": "low"}


# ------------------------------------------------------------- utilities


def parse_period(period: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    end = today - timedelta(days=1)
    m = re.fullmatch(r"(\d+)([my])", period.strip().lower())
    if not m:
        raise ValueError("Period must look like 24m or 5y")
    n, unit = int(m.group(1)), m.group(2)
    months = n if unit == "m" else n * 12
    year, month = end.year, end.month - months
    while month <= 0:
        month += 12
        year -= 1
    start = date(year, month, 1)
    return max(start, fetch.DATA_START), end


def parse_weights(raw: str | None) -> dict[str, float] | None:
    if not raw:
        return None
    weights = {}
    for part in raw.split(","):
        key, _, value = part.partition("=")
        weights[key.strip()] = float(value)
    return weights


def emit(payload: dict, *, code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return code


def compact(result: dict) -> dict:
    """Result without heavy details: they stay in the session and go into the report."""
    out = {k: v for k, v in result.items() if k not in ("months", "metric")}
    if isinstance(out.get("seasonality"), dict):
        out["seasonality"] = {k: v for k, v in out["seasonality"].items() if k != "index"}
    if isinstance(out.get("spikes"), dict):
        out["spikes"] = {**out["spikes"], "days": out["spikes"]["days"][:3]}
    return out


# ------------------------------------------------------------- commands


def cmd_resolve(args) -> int:
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    return emit(resolve.resolve_topic(args.query, langs, search_lang=args.search_lang))


def _resolve_target(topic: str, langs: list[str], search_lang: str | None):
    """Topic or QID → (qid, label, titles). None if a human needs to confirm."""
    if QID_RE.match(topic):
        return topic, resolve.label_for(topic, langs), resolve.titles_for(topic, langs), None

    res = resolve.resolve_topic(topic, langs, search_lang=search_lang)
    if res["ambiguous"]:
        return None, None, None, {
            "needs_confirmation": True,
            "reason": "The topic resolved ambiguously: ask the user and rerun with a QID.",
            **res,
        }
    sel = res["selected"]
    return sel["qid"], sel["label"], sel["titles"], None


def _run_analysis(args) -> dict | None:
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    qid, label, titles, pending = _resolve_target(args.topic, langs, args.search_lang)
    if pending:
        emit(pending)
        return None

    start, end = parse_period(args.period)
    results = []
    for lang in langs:
        title = titles.get(lang)
        if not title:
            results.append(
                {"lang": lang, "title": None, "error": "no article in this language edition"}
            )
            continue
        res = an.analyze_lang(lang, title, start, end, metric=args.metric, use_cache=not args.no_cache)
        res["confidence"] = assess(res)
        results.append(res)

    verdicts = [verdict(r, r.get("confidence", {"level": "low"})) for r in results]
    return {
        "qid": qid,
        "label": label,
        "period": args.period,
        "metric": args.metric,
        "results": results,
        "verdicts": verdicts,
    }


def cmd_analyze(args) -> int:
    state = _run_analysis(args)
    if state is None:
        return 0
    session.save("analyze", state)
    return emit(
        {
            "qid": state["qid"],
            "label": state["label"],
            "period": state["period"],
            "metric": state["metric"],
            "verdicts": state["verdicts"],
            "results": [compact(r) for r in state["results"]],
            "limitations": LIMITATIONS,
        }
    )


def cmd_compare(args) -> int:
    state = _run_analysis(args)
    if state is None:
        return 0

    weights = parse_weights(args.weights) or {"volume": 0.5, "growth": 0.5}
    kept, excluded = an.screen_langs(
        state["results"], min_confidence=args.min_confidence, min_views=args.min_views
    )
    ranking = an.rank_langs(kept, weights)
    state["ranking"] = ranking
    state["excluded"] = excluded
    thresholds = {"min_confidence": args.min_confidence, "min_views": args.min_views}
    state["recommendation"] = _recommendation(ranking, weights, thresholds)
    session.save("compare", state)

    return emit(
        {
            "qid": state["qid"],
            "label": state["label"],
            "period": state["period"],
            "metric": state["metric"],
            "ranking": ranking,
            "excluded": excluded,
            "recommendation": state["recommendation"],
            "verdicts": state["verdicts"],
            "confidence_by_lang": {
                r["lang"]: r.get("confidence", {"level": "low", "reasons": [r.get("error", "")]})
                for r in state["results"]
            },
            "limitations": LIMITATIONS,
        }
    )


def _why(entry: dict, leader_share: float, weights: dict[str, float]) -> str:
    """Why a language sits where it does: the same three inputs the score formula uses."""
    pct_of_leader = round(entry["share_per_million"] / leader_share * 100) if leader_share else 0
    if entry["significant"]:
        growth = f"trend {entry['change_pct_per_year']:+.1f}% per year counts toward the score"
    elif weights.get("growth", 0):
        growth = "trend not significant, so it adds nothing for growth"
    else:
        growth = "trend not used (growth weight 0)"
    return (
        f"{entry['lang']}: score {entry['score']}; volume {entry['share_per_million']} per million "
        f"({pct_of_leader}% of the leader); {growth}; "
        f"confidence {CONF_LABEL.get(entry['confidence'], '—')}"
    )


def _recommendation(
    ranking: list[dict], weights: dict[str, float], thresholds: dict | None = None
) -> dict:
    thresholds = thresholds or {"min_confidence": "low", "min_views": 0}
    criteria = ", ".join(f"{k}={v}" for k, v in {**weights, **thresholds}.items())
    if not ranking:
        return {
            "text": "Nothing to compare: no language has usable data above the thresholds.",
            "criteria": criteria,
            "why": [],
            "research_next": [],
        }

    top = ranking[0]
    parts = [
        f"Top candidate: {top['lang']} (score {top['score']}): "
        f"{top['share_per_million']} views per million, "
        f"trend {top['change_pct_per_year']:+.1f}% per year"
        f"{'' if top['significant'] else ' (not significant)'}, "
        f"confidence {CONF_LABEL.get(top['confidence'], '—')}."
    ]
    if len(ranking) > 1:
        second = ranking[1]
        gap = top["score"] - second["score"]
        if gap < 0.05:
            parts.append(
                f"The lead over {second['lang']} is small ({gap:.3f}): on this data the "
                "languages are practically equivalent, so choose on other grounds."
            )
        else:
            parts.append(f"Next: {second['lang']} (score {second['score']}).")
    if top["confidence"] == "low":
        parts.append("The leader's confidence is low: too early to decide on this data.")

    # Audiences worth validating next: the best-ranked ones the data can actually vouch for.
    research_next = [r["lang"] for r in ranking if r["confidence"] != "low"][:3]
    if research_next:
        parts.append(f"Research next: {', '.join(research_next)}.")
    else:
        parts.append("No language has enough confidence to research next on this data.")

    leader_share = max(r["share_per_million"] for r in ranking)
    return {
        "text": " ".join(parts),
        "criteria": criteria,
        "why": [_why(r, leader_share, weights) for r in ranking],
        "research_next": research_next,
    }


def cmd_chart(args) -> int:
    state = session.load()
    if not state:
        return emit(
            {"error": "Session is empty", "hint": "Run analyze or compare first."}, code=1
        )
    try:
        out = charts.monthly_chart(
            state.get("results", []), args.out, metric=state.get("metric", "share")
        )
    except RuntimeError as exc:
        return emit({"error": str(exc)}, code=1)
    return emit(
        {
            "chart": str(out),
            "label": state.get("label"),
            "langs": [r["lang"] for r in state.get("results", [])],
            "note": "Y axis: views per million views of the edition, smoothed with a rolling median.",
        }
    )


def cmd_report(args) -> int:
    state = session.load()
    if not state:
        return emit(
            {"error": "Session is empty", "hint": "Run analyze or compare first."}, code=1
        )
    try:
        out = report.build_report(state, args.out)
    except RuntimeError as exc:
        return emit({"error": str(exc)}, code=1)
    return emit({"report": str(out), "langs": [r["lang"] for r in state.get("results", [])]})


def cmd_session(args) -> int:
    if args.action == "clear":
        session.clear()
        return emit({"cleared": True})
    return emit(session.summary())


def cmd_cache(args) -> int:
    if args.action == "clear":
        cache.clear()
        return emit({"cleared": True, "path": str(cache.cache_path())})
    return emit({"path": str(cache.cache_path())})


# ------------------------------------------------------------- argument parsing


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wikitrends", description="Topic interest from Wikipedia page views")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("resolve", help="topic → articles in every language")
    r.add_argument("query")
    r.add_argument("--langs", required=True, help="pl,cs,uk")
    r.add_argument("--search-lang", default=None, help="search language (default: from the query's alphabet)")
    r.set_defaults(func=cmd_resolve)

    def add_analysis_args(sp):
        sp.add_argument("topic", help="QID (Q1188781) or topic")
        sp.add_argument("--langs", required=True, help="pl,cs,uk")
        sp.add_argument("--period", default="24m", help="24m, 36m, 5y")
        sp.add_argument("--metric", default="share", choices=["share", "views"])
        sp.add_argument("--search-lang", default=None)
        sp.add_argument("--no-cache", action="store_true")

    a = sub.add_parser("analyze", help="per-language analysis")
    add_analysis_args(a)
    a.set_defaults(func=cmd_analyze)

    c = sub.add_parser("compare", help="compare and rank languages")
    add_analysis_args(c)
    c.add_argument("--weights", default=None, help="volume=0.4,growth=0.6")
    c.add_argument(
        "--min-confidence", default="low", choices=["low", "medium", "high"],
        help="languages below this confidence are excluded from the ranking",
    )
    c.add_argument(
        "--min-views", type=int, default=0,
        help="languages with fewer monthly views are excluded from the ranking",
    )
    c.set_defaults(func=cmd_compare)

    ch = sub.add_parser("chart", help="PNG chart from the last result")
    ch.add_argument("--from-last", action="store_true", default=True)
    ch.add_argument("--out", default="chart.png", help="absolute path to the PNG")
    ch.set_defaults(func=cmd_chart)

    rep = sub.add_parser("report", help="PDF from the last result")
    rep.add_argument("--from-last", action="store_true", default=True)
    rep.add_argument("--out", default="report.pdf")
    rep.set_defaults(func=cmd_report)

    s = sub.add_parser("session", help="session state")
    s.add_argument("action", nargs="?", default="show", choices=["show", "clear"])
    s.set_defaults(func=cmd_session)

    ca = sub.add_parser("cache", help="page view cache")
    ca.add_argument("action", nargs="?", default="show", choices=["show", "clear"])
    ca.set_defaults(func=cmd_cache)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ApiError as exc:
        return emit({"error": str(exc), "hint": exc.hint}, code=1)
    except ValueError as exc:
        return emit({"error": str(exc)}, code=1)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
