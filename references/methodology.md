# Methodology

Read this file only when asked "how is this computed".

## Data source

Wikimedia Pageviews REST API:

| Endpoint | What it gives | Available since |
|---|---|---|
| `per-article` | daily views of one article | 2015-07-01 |
| `aggregate` | views of the whole language edition | 2015-07-01 |

All requests use `access=all-access`, `agent=user` (bots and spiders that
Wikimedia recognised are dropped) and a mandatory `User-Agent` header.

Responses are cached in SQLite keyed by `(project, article, day)`. The last 3 days are not
cached: Wikimedia finalises them with a delay, and a stored zero would stay
zero forever.

## Finding the article

The topic is resolved through Wikidata, not by searching each language separately:

1. Search in the query language's edition (`list=search`, disambiguation pages dropped).
2. `wikibase_item` of the found pages → QID.
3. `wbgetentities` + sitelinks → article titles in every requested language.

This compares translations of the same entity, not similarly named
articles about different things. If nothing matches the query exactly, `ambiguous: true`, and
a human makes the choice.

## Redirects

Views are counted per exact title. If an article is renamed, the old
title keeps part of the traffic and the new one starts from zero, which on a chart
looks like a collapse. So the views of all the article's redirects are added to its views
(`prop=redirects`, up to 100, main namespace).

## Normalisation

Absolute views in the Polish and Czech editions are not comparable: the editions differ
in size and reader activity. The main metric:

```
share_per_million = article views / views of the whole edition × 1,000,000
```

over the same period. This also removes overall shifts in Wikipedia traffic: seasonality
of the whole project, changes in bot classification, the decline in human views
due to AI answers in search.

The `views` metric (absolute views) should only be looked at within one language.

## Monthly aggregation

Days are rolled up into full calendar months; partial months at the edges of the period
are dropped, otherwise the current month always looks like a dip simply because
it has not ended yet.

## Trend

- **Theil–Sen slope**: the median of pairwise slopes `(y_j − y_i)/(j − i)`.
  Unlike OLS, it is not dragged by one day on the main page.
- **Computed on log values.** "−50% per year" must mean multiplying
  by 0.5 each year. A linear slope divided by the median gives numbers like
  −76%/yr on a steep decline: they disagree with year-over-year and within two years push
  the series into negative views. Zeros are replaced with half of the smallest
  positive value in the series.
- `change_pct_per_year = (exp(slope × 12) − 1) × 100`: an annual rate,
  bounded below by −100%.
- **Mann–Kendall test**: statistic `S` (sum of signs of pairwise differences),
  tie-corrected variance, normal approximation `Z`, two-sided `p`.
  The test is rank-based, so taking logs does not change it. The trend is significant when
  `p < 0.05`; otherwise `direction: flat`, whatever the slope.

## Year over year

Sum of the last 12 full months vs the previous 12. The same set of months
is in both windows, so a January spike of interest in diets falls into both halves and does not
turn into "growth". Requires at least 24 full months.

## Seasonality

Month-of-year index = median of that month's values / median of the whole series.
Amplitude = max(index) − min(index); seasonality counts as strong when the
amplitude ≥ 0.3. Peak months are those with index ≥ 1.2.

## Outliers

On the daily series: median `m` and MAD; robust sigma = `1.4826 × MAD`.
A day counts as a spike when `value > m + 5σ` and also `value > 2m`.

Separately, the share of growth explained by these days is computed:

```
share_of_growth = Σ(spike value − m) over the last 365 days
                / (sum of the last 365 days − sum of the previous 365)
```

If this share is ≥ 0.5, the "growth" is really a few days in the news or on the main
page, and confidence drops to `low`.

## Confidence assessment

The level is set by code according to rules (see `wikitrends/confidence.py`):

| Signal | Effect |
|---|---|
| < 12 full months | critical → `low` |
| < 100 views/month | critical → `low` |
| ≥ 50% of growth from spikes | critical → `low` |
| 12–23 months | warning |
| 100–500 views/month | warning |
| trend not significant (p ≥ 0.05) | warning |
| 25–50% of growth from spikes | warning |
| seasonality on a short series | warning |
| months with zero views | warning |

One critical condition → `low`. Two or more warnings → `medium`.
None → `high`.

## Ranking languages

```
score = (w_volume × share_of_max + w_growth × (growth + 100)/200) × confidence_penalty
```

Growth is clipped to ±100%/yr; for an insignificant trend growth counts as zero.
Confidence penalty: `high` = 1.0, `medium` = 0.85, `low` = 0.6.
Weights are set with `--weights volume=0.4,growth=0.6` and printed in the report.
