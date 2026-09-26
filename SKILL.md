---
name: wiki-interest
description: Estimates interest in a topic from Wikipedia page views across language editions: compares languages, determines the trend and how reliable it is, builds a PDF report. Use for questions like "is interest in X growing", "in which language/country is the topic more popular", "should we enter market Y with topic X", "how far can we trust this data".
---

# Wiki Interest

Topic interest analysis from Wikipedia article page views.

## When to use

- "Is interest in <topic> growing in <language>?"
- "Where is the topic more popular: Polish or Czech Wikipedia?"
- "How far can we trust this growth?"
- "Make a report on <X> for languages <...>"

## The main rule

**Do not write your own analysis code.** All the analytics are already in the CLI. Your job is
to call the right command and relay its output. The tool itself computes the trend, seasonality,
outliers and confidence level.

## Workflow (do not skip steps)

1. **resolve**: find the article and its titles in every language.
2. **Confirm with the user** if `ambiguous: true` or there are `missing_langs`.
3. **analyze** (one language) or **compare** (several languages).
4. **chart** if asked for a chart/image; **report** if asked for a report, PDF
   or document. Do not write your own chart code, not even one line of matplotlib.

## Commands

Run from the skill directory, the one containing this SKILL.md (`<skill>` below):

```bash
cd <skill> && uv run wikitrends <command>
```

Without `uv` the core works too: `python3 <skill>/scripts/wikitrends.py <command>`
(only `report` needs matplotlib and reportlab).

**Always pass `--out` as an absolute path in the user's working directory.**
Commands run after `cd` into the skill directory, so a relative path would
save the report inside the skill, where the user will not find it.

```bash
# topic → QID + article titles per language
uv run wikitrends resolve "intermittent fasting" --langs cs,uk

# per-language analysis over a period
uv run wikitrends analyze Q1666254 --langs cs,uk --period 24m

# compare languages on the normalised metric
uv run wikitrends compare Q1666254 --langs cs,uk,de --metric share

# chart only (PNG) from the last result
uv run wikitrends chart --from-last --out /absolute/path/chart.png

# PDF from the last result
uv run wikitrends report --from-last --out /absolute/path/report.pdf

# what is in the session
uv run wikitrends session show
```

Useful flags: `--period 24m|5y`, `--metric share|views`, `--no-cache`,
`--weights growth=0.6,volume=0.4` (custom recommendation criteria in the report),
`--min-confidence medium` and `--min-views 300` for compare (languages below the
thresholds are excluded from the ranking).

The compare output has `recommendation.why` (one line per ranked language),
`recommendation.research_next` (which audiences to look at next) and `excluded`
(languages left out, with the reason). For "which audiences next and why", relay these
fields; do not build your own ranking. If the user states a criterion ("growth matters
more", "only big audiences", "only reliable data"), rerun compare with the matching
`--weights` / `--min-views` / `--min-confidence` instead of reinterpreting the old result.

## Typical requests

**"Is interest in meditation growing on Polish Wikipedia?"**
```bash
uv run wikitrends resolve "meditation" --langs pl
uv run wikitrends analyze Q108458 --langs pl --period 36m
```

**"Where is the topic more promising: pl, cs, uk?"**
```bash
uv run wikitrends resolve "intermittent fasting" --langs pl,cs,uk
uv run wikitrends compare Q1666254 --langs cs,uk --period 24m  # pl dropped: no article
```

**"Make a report"** after analyze/compare: `uv run wikitrends report --from-last --out /absolute/path/report.pdf`

## Hard output rules

- **Do not raise confidence above what the tool reported.** Relay the `confidence` field
  (`high`/`medium`/`low`) and the `reasons` list as they are; do not soften them.
- **Always mention the limitations** from the `limitations` field of the response.
- **Page views ≠ willingness to pay.** Do not turn interest into demand, revenue or
  market size. It is a signal of attention, nothing more.
- Do not compare absolute views across languages, only `share`
  (views per million views of the edition).
- If `ambiguous: true`, first ask which article is meant. Do not rephrase the query
  until the ambiguity goes away: that is choosing the article yourself.
- **Name the article you measured.** If it is a proxy for the user's topic (for example
  the "English language" article for "learning English"), say so in the answer.
- **If a language has no article, do not stop at "no data".** Say that the topic is not
  covered in that edition (that is a signal in itself), show `near_matches`
  as replacement candidates, warning that they are **different** articles, and
  compute for the languages that have the article.

## Details

Read only when asked "how is this computed":
- `references/methodology.md`: metric formulas, trend, seasonality, outliers.
- `references/limitations.md`: typical distortions in Wikipedia data.
