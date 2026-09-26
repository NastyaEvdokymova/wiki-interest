# Testing the skill

Three levels, from cheap and deterministic to expensive and approximate.

## 1. Unit tests on recorded API responses

```bash
uv run --with pytest python -m pytest -q
```

They run offline: all Wikidata, MediaWiki and Pageviews responses are recorded in
`tests/fixtures/`. There are no network calls and results are reproducible.
Covered: response parsing, filling missing days with zeros, the cache (including
not caching the recent tail), redirect summing, normalisation,
topic resolution and the ambiguity flag.

## 2. Synthetic series with known answers

`tests/test_analyze.py` builds series where the correct answer is known in advance:

| Series | Expected result |
|---|---|
| strictly linear growth | Theil–Sen = the given slope, Mann–Kendall significant |
| linear growth + one ×500 day | the slope barely changes |
| pure seasonal sine wave | seasonality found, no trend |
| seasonality + year over year | year-over-year change ≈ 0 |
| three spikes in a row | days found, share_of_growth > 0.9, confidence `low` |
| noise on a small base | seasonality **not** declared |
| base of ~60 views/month | confidence `low`, reason "small base" |

This guards against the main class of error: "the metric computes, but computes the wrong thing".

## 3. Eval run on a weak model

`cases.json` holds 15 queries: three typical scenarios, follow-up turns and
awkward cases (ambiguous topic, missing article in a language, a revenue question,
a period before 2015, language confused with country).

The run uses a cheap model (Haiku 4.5 or OpenRouter) with the skill
enabled. What is checked is behaviour, not verbatim text:

- which commands were called (`expect_commands`);
- whether the `checks` pass, above all "does not raise confidence
  above what the tool reported" and "does not turn views into money";
- number of tool calls and tokens per query (`metrics_per_run`).

The run needs an API key and is not automated here: results depend on the
model and should be re-recorded on every SKILL.md change.
A growing number of tool calls per query is a sign that the wording in
SKILL.md has become ambiguous.
