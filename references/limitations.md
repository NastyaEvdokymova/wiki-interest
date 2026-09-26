# Data limitations

What Wikipedia page views do not show and the most common distortions.

## What this data does not measure

- **Willingness to pay.** An article view is a signal of attention. Growing interest in a
  topic implies neither demand, nor market size, nor conversion. Never turn
  views into money.
- **Audience geography.** The metric is tied to a language edition, not a country.
  The Ukrainian-speaking audience is spread well beyond Ukraine, the English
  edition is read by the whole world, and in Poland some readers use the English
  edition. Language edition ≠ country.
- **Intent.** People open an article out of curiosity, for homework, because of
  the news or via a social media link. "Buyer interest" cannot be told apart.

## Systematic distortions

- **Overall decline in views.** Since 2024 human Wikipedia views have been
  falling: people get some answers directly in search and from assistants. The
  `share_per_million` metric compensates only partially, to the extent that the
  decline is even across topics. "Reference" topics (definitions, dates, formulas)
  drop more than long-read topics.
- **Bot reclassification.** Wikimedia periodically changes the rules for classifying
  traffic as bots. Level jumps in 2021 and 2023 in some editions come
  from this, not from reader behaviour.
- **Undetected bots.** The `agent=user` filter does not catch everything. A flat "shelf"
  of views without daily and weekly waves is a typical sign of scraping.
- **Main page and news.** An article appearing in "Did you know" or in the
  news cycle produces a spike tens of times above the background. The code flags such
  days and computes their contribution to growth.
- **Mobile redirects and apps.** They are counted, but the composition of `all-access`
  has changed over time; compare periods before and after 2016 with care.

## Article-specific issues

- **Renames.** Without summing redirects they look like a collapse in interest.
  The code sums them, but only redirects that exist at query time: if a
  redirect was deleted, part of the history is lost.
- **Article splits and merges.** When a large article is split into several,
  the views are distributed among them: the original article's level falls without
  any drop in interest in the topic.
- **Different article size.** A detailed article in one language and a stub in another
  give different reading depth and different search visibility. Comparing shares
  still makes sense, but a 1.5–2× difference may be explained by article
  quality rather than audience interest.
- **No article in a language.** No article does not mean no interest. It only
  means there is nothing to measure; such languages are explicitly excluded from the comparison.

## Period boundaries

`per-article` data starts on 1 July 2015. The last 1–3 days are
finalised with a delay and may be understated, so the analysis always
ends yesterday, and partial months are dropped.
