# How to develop the skill further

Each step below is a separate iteration: what we add, what it breaks and how
we check we have not broken anything. The order is chosen so that each step
builds on the previous, already verified one.

## What the skill can do now

One article per topic, up to ~10 languages, data from the Pageviews API, a trend with a confidence
assessment, a one-page PDF. That is enough for the question "is it worth looking in this
direction", but not for research.

Three limitations that bite first:

1. **Topic ≠ article.** "Astronomy" is not only the article "Astronomy" but also
   planets, telescopes, constellations. One article understates interest and is too
   sensitive to its quality in a particular language.
2. **The API is not for volume.** One request per article per language. Screening 30 languages ×
   50 topics is 1,500 requests, hours of work and hitting rate limits.
3. **Page views are one signal.** You cannot see where the reader came from or where they went.

---

## Step 1. A topic as a cluster of articles

**What we add.** `resolve --expand` collects not one article but a group: walking
categories 1–2 levels down, or Wikidata properties (`part of`, `instance of`,
`subclass of`). The topic metric is the sum of the cluster articles' shares.

**What breaks.** Double counting (an article in two categories), junk in
categories (lists, templates, disambiguation), different category structures in
different languages: a cluster built from the Polish tree is not the cluster from the Czech one.
So the cluster is built **once from Wikidata** and expanded into languages
via sitelinks; otherwise different sets of articles get compared.

**How we check.** The cluster is fixed in the session and printed as a list, so a human
sees what went in. Test: for a topic with a known composition (the planets of the Solar
System) the cluster must contain exactly 8 articles and no lists.
Separate check: the cluster's share sum ≥ the head article's share.

**When.** First: it changes the answers to current questions the most.

## Step 2. Volume: dumps instead of the API

**What we add.** Downloading `pageviews-YYYYMM` from dumps.wikimedia.org and processing
them with DuckDB directly on the compressed files. The API stays for interactive requests on
1–3 topics; dumps kick in for screening.

**What breaks.** Dump rows are article titles without redirect resolution,
and they must be mapped to QIDs in advance. Volume: a month of all projects is tens of
gigabytes, so filtering to the needed languages happens at read time.

**How we check.** The key is agreement with the API: for 20 random articles the monthly
totals from the dump and from the API must agree within 1% (some discrepancy is expected
from different redirect handling). This is a regression test, not a one-off check.

**When.** Only after step 1; otherwise we just compute the wrong thing faster.

## Step 3. Deeper signals

**What we add.**

- **Clickstream** (monthly dumps of transitions): where readers come into
  the article from and where they go. Answers "interest in the topic or random
  traffic from the news" much more precisely than the spike detector.
- **Views by country.** Wikimedia publishes them with differential
  privacy. This removes the main limitation of the current metric, the conflation of
  language and country: you can see what share of Ukrainian-edition readers are abroad.

**What breaks.** Differentially private data is noisy by
construction: small values are suppressed and cannot be summed like ordinary
views. The code must return a confidence interval, not a point, and
`confidence` must account for the value being noisy.

**How we check.** Synthetic data does not help here: we need checks on topics with
known geography (national holidays, local figures), where the country's share
must obviously be high.

## Step 4. Market screening

**What we add.** `wikitrends screen "topic" --top 30`: ranking dozens of
languages by promise with thresholds: languages with `low` confidence do not make it into
the top of the list but are moved to a separate "not enough data" section.

**What breaks.** Multiple comparisons: if 30 languages are tested at
`p < 0.05`, one or two will show a "significant trend" by chance. A correction is needed
(Benjamini–Hochberg); otherwise screening will produce false findings more often
the more widely it is used.

**How we check.** A synthetic run: 30 series without a trend must give zero
"significant" ones after correction. This test must exist before
anyone starts using the command.

---

## What to do in parallel, not later

- **Eval run metrics.** Right now `evals/runs/` holds answer texts.
  We should collect `--output-format json`: number of turns, tokens, cost. A growing
  number of calls per request is the earliest sign that the wording in
  SKILL.md has become ambiguous.
- **Run evals on every SKILL.md change.** Two of the three defects found
  in the first runs (the trend metric and the PDF save path) were found by the weak
  model, not by the tests.

## What not to do

- **Sum languages into "world interest".** Editions overlap in readers:
  a Pole may read both the Polish and the English article. A sum of shares means
  nothing.
- **Turn views into market size.** Any conversion factor would be
  made up, yet would look like a calculation. This is a product limitation, not a
  technical one, and adding data cannot remove it.
- **Leave the choice of article to the model.** The example 3 run showed that even with
  the safeguard the model proposes dubious candidates
  (Simple English Wikipedia instead of the English language). Human confirmation
  must remain a mandatory step.
