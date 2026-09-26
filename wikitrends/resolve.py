"""Topic → the same article in every requested language, via Wikidata.

The classic mistake is comparing "Intermittent fasting" in one language with
"Fasting (religion)" in another. So the query language is used only for search,
and article titles come from the sitelinks of a single Wikidata entity.
"""

from __future__ import annotations

import re

from .http import ApiError, get_json

WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def guess_search_lang(query: str) -> str:
    """Search language from the query's alphabet, used only to find the entity."""
    if re.search(r"[іїєґ]", query, re.IGNORECASE):
        return "uk"
    if re.search(r"[а-яё]", query, re.IGNORECASE):
        return "ru"
    if re.search(r"[ąćęłńóśźż]", query, re.IGNORECASE):
        return "pl"
    if re.search(r"[ěščřžýáíé]", query, re.IGNORECASE):
        return "cs"
    return "en"


def _search_wiki(query: str, lang: str, limit: int = 5) -> list[dict]:
    """Search a language edition + the QID of each article found."""
    data = get_json(
        f"https://{lang}.wikipedia.org/w/api.php",
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": str(limit),
            "gsrnamespace": "0",
            "prop": "pageprops|description",
            "ppprop": "wikibase_item|disambiguation",
            "format": "json",
            "formatversion": "2",
        },
    )
    pages = data.get("query", {}).get("pages", [])
    pages.sort(key=lambda p: p.get("index", 99))
    out = []
    for p in pages:
        props = p.get("pageprops", {})
        if "disambiguation" in props:
            continue  # a disambiguation page is a list of topics, not a topic
        qid = props.get("wikibase_item")
        if qid:
            out.append({"qid": qid, "source_title": p["title"], "description": p.get("description", "")})
    return out


def _entities(qids: list[str], langs: list[str]) -> dict[str, dict]:
    if not qids:
        return {}
    sites = "|".join(f"{lang}wiki" for lang in langs)
    data = get_json(
        WIKIDATA_API,
        {
            "action": "wbgetentities",
            "ids": "|".join(qids[:50]),
            "props": "sitelinks|labels|descriptions",
            "sitefilter": sites,
            "languages": "|".join(dict.fromkeys(langs + ["en", "ru"])),
            "format": "json",
        },
    )
    return data.get("entities", {})


def _label(entity: dict, langs: list[str]) -> str:
    # The label is for a human reader, so English first, not the target languages.
    labels = entity.get("labels", {})
    for lang in ["en", "ru"] + langs:
        if lang in labels:
            return labels[lang]["value"]
    return entity.get("id", "")


def _description(entity: dict, langs: list[str]) -> str:
    descs = entity.get("descriptions", {})
    for lang in ["en", "ru"] + langs:
        if lang in descs:
            return descs[lang]["value"]
    return ""


def resolve_topic(query: str, langs: list[str], *, search_lang: str | None = None, limit: int = 5) -> dict:
    """Returns candidates with article titles per language.

    `ambiguous` = True when the automatic choice is unreliable: the agent must
    ask the user before computing anything.
    """
    search_lang = search_lang or guess_search_lang(query)
    hits = _search_wiki(query, search_lang, limit=limit)
    if not hits:
        raise ApiError(
            f"Nothing found for \"{query}\" in {search_lang}.wikipedia",
            hint="Try different wording or pass --search-lang with the query language.",
        )

    entities = _entities([h["qid"] for h in hits], langs)
    candidates = []
    for hit in hits:
        entity = entities.get(hit["qid"], {})
        sitelinks = entity.get("sitelinks", {})
        titles = {
            lang: sitelinks[f"{lang}wiki"]["title"]
            for lang in langs
            if f"{lang}wiki" in sitelinks
        }
        candidates.append(
            {
                "qid": hit["qid"],
                "source_title": hit["source_title"],
                "label": _label(entity, langs) or hit["source_title"],
                "description": _description(entity, langs) or hit["description"],
                "titles": titles,
                "missing_langs": [lang for lang in langs if lang not in titles],
            }
        )

    best = candidates[0]
    if best["missing_langs"]:
        best["near_matches"] = _near_matches(entities.get(best["qid"], {}), best["missing_langs"])
    needle = query.casefold()
    exact = best["source_title"].casefold() == needle or best["label"].casefold() == needle
    ambiguous = not exact and len(candidates) > 1

    result = {
        "query": query,
        "search_lang": search_lang,
        "selected": best,
        "ambiguous": ambiguous,
        "alternatives": candidates[1:4],
    }
    if ambiguous:
        result["hint"] = "No exact match: ask the user which article they mean."
    if best["missing_langs"]:
        result["warning"] = (
            f"No article in languages: {', '.join(best['missing_langs'])}. "
            "These languages will be skipped. Do not end the answer with \"no data\": "
            "show near_matches, offer to compute for the languages that have the article, "
            "and say that the missing article is itself a signal: the topic is not "
            "covered in that edition."
        )
    return result


def _near_matches(entity: dict, missing: list[str], *, limit: int = 2) -> dict[str, list[str]]:
    """Related articles in the languages that lack the target article.

    A Wikidata entity has a label even without an article, so we can search in the
    target language. This is NOT the same entity, only material for asking the user.
    """
    labels = entity.get("labels", {})
    out: dict[str, list[str]] = {}
    for lang in missing:
        # There may be no label in the target language; fall back to the English one.
        label = labels.get(lang, {}).get("value") or labels.get("en", {}).get("value")
        if not label:
            continue
        try:
            hits = _search_wiki(label, lang, limit=limit)
        except ApiError:
            continue
        if hits:
            out[lang] = [h["source_title"] for h in hits]
    return out


def titles_for(qid: str, langs: list[str]) -> dict[str, str]:
    """Article titles by QID, for analyze/compare without searching again."""
    entity = _entities([qid], langs).get(qid, {})
    sitelinks = entity.get("sitelinks", {})
    if not entity:
        raise ApiError(
            f"Entity {qid} not found in Wikidata",
            hint="Check the QID or start with the resolve command.",
        )
    return {lang: sitelinks[f"{lang}wiki"]["title"] for lang in langs if f"{lang}wiki" in sitelinks}


def label_for(qid: str, langs: list[str]) -> str:
    entity = _entities([qid], langs).get(qid, {})
    return _label(entity, langs) if entity else qid
