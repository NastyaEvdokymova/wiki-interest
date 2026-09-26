# Full-scenario runs on a cheap model

## Run 2: English version of the skill (2026-09-26)

Haiku 4.5, `claude --model haiku -p ... --output-format json`, the three examples from the
task in their original wording (in English), a clean working directory per example.
The `--output-format json` output gives turns, tokens and cost for each run.

| File | Example | Turns | Output tokens | Cost |
|---|---|---|---|---|
| [en-example1-fasting-turn1.md](en-example1-fasting-turn1.md) | intermittent fasting, pl vs cs | 4 | 1,229 | $0.041 |
| [en-example1-fasting-turn2.md](en-example1-fasting-turn2.md) | user: "analyze only Czech + PDF" | 3 | 821 | $0.046 |
| [en-example2-astronomy-before-yoy-fix.md](en-example2-astronomy-before-yoy-fix.md) | astronomy in uk, before the fix below | 5 | 995 | $0.044 |
| [en-example2-astronomy.md](en-example2-astronomy.md) | astronomy in uk, after the fix | 6 | 1,546 | $0.056 |
| [en-example3-english-before-fixes.md](en-example3-english-before-fixes.md) | learning English in pl/cs/uk/de, before the fixes below | 7 | 2,735 | $0.068 |
| [en-example3-english-turn1.md](en-example3-english-turn1.md) | the same, after the fixes: asks which article | 4 | 1,480 | $0.043 |
| [en-example3-english-turn2.md](en-example3-english-turn2.md) | user: "Q1860, growth matters more" + report | 3 | 1,249 | $0.025 |

What worked: in example 1 the model reported that Polish Wikipedia has no such
article, showed the near matches as *different* articles and asked before computing;
after the answer it analysed Czech and saved the PDF to the user's directory. The
confidence levels in all answers match the tool's `confidence.level`, and the
limitations are mentioned. In example 3 the model relayed `research_next` (uk, cs, pl)
instead of building its own order, turned "growth matters more" into `--weights growth=0.6,volume=0.4`,
and said that the "English language" article is only a proxy for interest in learning English.

**Defect found and fixed: year-over-year fields read as monthly levels.**
`yoy.recent_12m` was the *sum* of 12 monthly shares. The model wrote "the last 12 months
averaged 116 views per million" while the monthly level was ~9.7. The fields are now
`recent_12m_monthly_avg` / `previous_12m_monthly_avg`; after the fix the model reports
"9.7 per million, down from 17.79 a year ago". Test: `test_yoy_reports_monthly_averages_not_sums`.

**Defect found and fixed: ambiguity sidestepped by rephrasing.** For "learning English"
`resolve` returns `ambiguous: true`; in the first run the model rephrased the query until
it got an exact match ("English", Q1860) and never said which article it measured.
SKILL.md now forbids rephrasing away the ambiguity and requires naming the measured article
when it is a proxy. In the rerun the model asks which article to use, and after the answer
it names the article and calls it a proxy.

**Defect found and fixed: absolute views compared across languages.** Even with the
SKILL.md rule, the model called Polish "the largest absolute audience" by raw monthly views
(wrong, German has more, and the cross-language comparison SKILL.md forbids). The rule alone
did not hold, so `monthly_views` was removed from the `compare` ranking output (it stays in
the report table). In the rerun the answer compares only views per million.

## Run 1: Russian version of the skill (2026-09-22)

Date: 2026-09-22. Model: **Haiku 4.5** (`claude --model haiku -p`).
The skill was installed via a symlink in `~/.claude/skills/`, with a clean working directory.

All three examples from the task were run. Below is what each run checked and what
it turned up.

The runs were done in Russian and Ukrainian; the answer files here are English
translations. The original answers are in the Russian copy of the skill (`../wiki-interest-ru`).

| File | Example from the task |
|---|---|
| [haiku-example1-fasting-without-skill.md](haiku-example1-fasting-without-skill.md) | intermittent fasting, **without the skill**: baseline |
| [haiku-example1-fasting-with-skill.md](haiku-example1-fasting-with-skill.md) | the same with the skill |
| [haiku-example2-astronomy.md](haiku-example2-astronomy.md) | astronomy in uk + a question about trust |
| [haiku-example3-english-turn1.md](haiku-example3-english-turn1.md) | English across four editions: first turn |
| [haiku-example3-english-turn2.md](haiku-example3-english-turn2.md) | user clarification + PDF |

## Example 1: with and without the skill

Same question, same allowed tools, clean directory.

> Is interest in intermittent fasting growing on Czech Wikipedia over the last
> 3 years? How far can this data be trusted?

Both models got the direction of the conclusion right: interest is declining. The difference is
how the conclusion was reached and what was said about trust.

| Mistake without the skill | What the model did | What the skill does |
|---|---|---|
| Invented confidence | "The data is **90–95%** reliable": the number has no basis | `confidence: medium` by rules + reasons |
| Partial month at the edge | Compared September 2023 (592) with September 2026 (79) → "−87%". September 2026 had not ended on the run date | partial months are dropped |
| Two points instead of a series | Trend from the first and last month | Theil–Sen over all months |
| No significance check | "Declining steadily", with no test | Mann–Kendall, `p<0.0001` |
| Absolute views | The overall fall in Wikipedia traffic counted as a fall in interest in the topic | normalisation per million edition views |
| Outliers ignored | The 14 April 2025 peak (×60 the median) silently went into the averages | spikes found, their contribution computed |
| Seasonality as an excuse | Mentioned under "caveats", not taken into account | month-of-year index + year-over-year |

With the skill, the answer contains exactly the values the tool reported, the confidence
level is not raised, and the limitations are listed.

## Example 2: astronomy in uk

The full scenario worked: `resolve` → `analyze` → relaying. The model correctly
reported that interest is **falling** (−50%/yr, `p=0.0001`), even though the question was
phrased as "is it growing": the hint in the question did not shift the conclusion.

**This run found a metric defect.** The first version computed
`change_pct_per_year` as a linear slope divided by the median and reported
−75.9%/yr with year-over-year −45.5%. The numbers did not agree, and formally such a rate
would push the series into negative views within two years. The trend was moved to log
values and became −50.0%/yr, consistent with year-over-year. Tests
`test_trend_is_a_compounding_annual_rate` and
`test_steep_decline_never_exceeds_minus_100_percent` were added. The saved answer is from after
the fix.

## Example 3: English in four editions, two turns

**Turn 1.** The model got `ambiguous: true` and **asked back**, offering
options, instead of taking the first article it found. The safeguard from
SKILL.md worked, but it also means the scenario does not finish in one turn.

**Turn 2.** The user specified the article (Q1860) and the criterion ("growth matters more than
volume"). The model passed `--weights`, built the comparison across four languages and a
PDF. The repeated request did not start from scratch: the QID and period came from the session.

**This run found a usability defect.** The PDF was saved **inside the skill
directory**: SKILL.md tells the agent to `cd` into it, and a relative `--out` landed there
too. A rule was added to SKILL.md: `--out` is always an absolute path in the user's working
directory.

## How to reproduce

```bash
ln -s <path-to-skill> ~/.claude/skills/wiki-interest
claude --model haiku -p "<question>" --allowedTools Bash Read Write WebFetch WebSearch Skill
claude -c --model haiku -p "<clarification>" --allowedTools ...   # second turn
```

For the baseline the skill must be removed (`rm ~/.claude/skills/wiki-interest`); otherwise
the model will find it and the comparison loses its meaning.

Call and token metrics were not collected in these runs: `-p` prints only the
final text. Collecting them needs `--output-format json` (gives `num_turns`,
`usage`, cost).
