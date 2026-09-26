# wiki-interest

An Agent Skills skill: estimates interest in a topic from Wikipedia page views across
language editions. Answers questions like "is interest in the topic growing",
"in which language is the topic more promising", "how far can we trust this data", and
builds a one-page report.

## Install and run

```bash
ln -s "$(pwd)" ~/.claude/skills/wiki-interest    # install the skill
uv sync --extra report                           # environment (report is needed only for the PDF)
uv run --with pytest python -m pytest -q         # 29 tests, all offline
./demo.sh                                        # 5 scenarios in a row, ~15 seconds
```

The core (`resolve`, `analyze`, `compare`) runs on the plain Python standard library,
with no dependencies to install. matplotlib and reportlab are needed only for
`chart` and `report`. The skill ships no compiled files; the environment is reproduced from
`pyproject.toml` + `uv.lock`.

## What is where

| Path | What it is |
|---|---|
| `SKILL.md` | instructions for the agent: workflow, commands, hard output rules |
| `wikitrends/` | all the analytics: topic resolution, fetching, metrics, confidence, report |
| `scripts/wikitrends.py` | single CLI entry point |
| `references/` | methodology and data limitations, read by the agent on request |
| `tests/` | 29 tests: synthetic data with known answers + recorded API responses |
| `evals/` | a set of 15 eval queries and runs on Haiku 4.5 |
| `RUNBOOK.md` | what to run in which order and how to demo it |
| `ROADMAP.md` | how to develop it further |

---

## How the skill helps the agent evaluate results and check conclusions

The starting assumption: a weak model writes analytical code on the fly poorly and
draws wrong conclusions from raw numbers. So all the substantive work is
deterministic code, and the agent is left with three tasks: understand the request, call the
command, relay the ready-made conclusions.

Concretely:

**The code returns not just numbers but their interpretation.** Along with the trend
it returns `confidence` (`high`/`medium`/`low`) and a list of reasons: "small base:
~183 views/month", "40% of the growth comes from 3 anomalous days". SKILL.md explicitly
forbids raising confidence above the reported level. So the model does not invent a level of
trust but relays it: in the baseline run without the skill it wrote
"the data is 90–95% reliable", a number based on nothing.

**The metrics are chosen to be hard to misuse.** The Theil–Sen slope
is robust to outliers; significance is checked with Mann–Kendall, and when
`p ≥ 0.05` the trend direction is forced to `flat`, whatever the slope
comes out as; year-over-year uses matching months, so seasonality is not
passed off as growth; partial months at the edges of the period are dropped.

**Typical traps are closed in code, not in instructions.** Redirects are summed with
the main article, otherwise a rename looks like a collapse. Absolute views
are normalised by the edition's views, otherwise languages cannot be compared. Spikes
are found by median and MAD, and the share of the change that falls on them
is computed separately.

**Ambiguity goes back to the human.** `resolve` finds the article via
Wikidata and, if there is no exact match, returns `ambiguous: true` with a list of
candidates. The agent must ask. This guards against the classic mistake of
comparing articles with different meanings in different languages. In the example 3 run
the safeguard worked: the model asked instead of taking the first
article it found.

## How repeated and related requests work

The state of the last analysis is kept in the session: QID, period, metric, languages,
monthly series. So "now add German", "show 5 years" or
"make a report" do not start from resolving the topic again.

All Pageviews API responses are cached in SQLite keyed by "project, article, day",
so a related request is almost free: changing the period from 24 to 36 months
fetches only the missing months. The last three days are not cached: Wikimedia
finalises them with a delay, and a stored zero would stay forever.

Command output is deliberately compact: monthly series and the seasonality index stay
in the session and go into the report, but not into the model's context. stdout gets a summary.

## Why recommendations rest on data and assumptions are visible

The recommendation is produced by code using an open formula: share of the maximum volume and
annual growth, with a penalty for low confidence. The weights are set by the user
(`--weights growth=0.8,volume=0.2`) and printed next to the conclusion, so the report's
reader sees which criteria produced the language order. An insignificant trend earns
zero points for growth, not whatever number happened to come out.

Every ranked language gets a one-line "why" built from the same inputs as the score
(volume relative to the leader, whether growth counted, confidence), and the
recommendation names up to three languages to research next, skipping any with `low`
confidence. The user can also set hard thresholds (`--min-confidence medium`,
`--min-views 300`): languages below them leave the ranking and are listed as excluded
with the reason, instead of sitting at the bottom where they still look like candidates.

The PDF has a separate "Assumptions and limitations" block: first the confidence
reasons for each language, then the general limitations: views are not
willingness to pay, a language edition is not a country, some bot traffic is not
detected, and since 2024 overall Wikipedia views have been falling due to AI answers in
search. These limitations are returned in every CLI response, and SKILL.md requires
mentioning them.

## How the AI tools' output was checked

**1. Tests (29, offline).** Wikidata, MediaWiki and Pageviews responses are recorded
in `tests/fixtures/`; there are no network calls. Separately, synthetic series with
known answers: a strictly linear increase must give the exact slope;
the same series with one ×500 day gives almost the same slope; a pure seasonal sine wave gives
seasonality with no trend; three spikes in a row give confidence `low`.

**2. Run on live data.** Every command was checked against the real API, and
this produced two findings the tests could not: the seasonality detector picked up
noise on a base of ~175 views/month (a threshold on within-month spread was added), and
the entity label was chosen in the target language instead of the query language.

**3. Full-scenario runs on Haiku 4.5.** Two rounds, all three examples from the task
each time, plus a baseline without the skill for comparison. Round 2 used
`--output-format json`, so every run has turns, tokens and cost (3–7 turns,
$0.03–0.07 per run). Analysis in [`evals/runs/README.md`](evals/runs/README.md).

Round 2 found three more defects, each fixed and rerun:
year-over-year sums read as monthly levels (fields renamed to monthly averages),
ambiguity sidestepped by rephrasing the query (SKILL.md rule; the model now asks), and
raw views compared across languages despite the SKILL.md rule (raw views removed from
the `compare` ranking, so the model no longer gets the number to misuse).

In round 1 the weak model found two defects that neither the tests nor the live runs found:

- **The trend metric lied on steep declines.** The model reported −75.9%/yr with
  year-over-year −45.5%. The numbers did not agree, and formally such a rate would push
  the series into negative views within two years: `change_pct_per_year` was computed as
  a linear slope divided by the median. The trend was moved to log values and
  became −50.0%/yr. Two tests were added.
- **The PDF was saved inside the skill directory.** SKILL.md tells the agent to `cd` into the skill
  directory, and a relative `--out` landed there. A rule about absolute paths was added
  to SKILL.md.

A separate check of facts rather than code: the first example in the task compares
intermittent fasting in the Polish and Czech editions, but **Polish Wikipedia has
no such article**. This was confirmed twice: via Wikidata sitelinks and by searching
plwiki under four different titles. The skill reports this explicitly
(`missing_langs`) instead of returning zeros as a lack of interest.

## Further development

See [`ROADMAP.md`](ROADMAP.md): a topic as a cluster of articles, moving to dumps with
DuckDB for large volumes, clickstream and per-country data, screening dozens of
languages with correction for multiple comparisons.
