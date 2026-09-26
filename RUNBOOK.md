# What to run in which order

A cheat sheet for running and demoing. Everything runs from the skill directory
(`/home/nastya/wiki-interest`) unless stated otherwise.

## 0. Once: installation

```bash
cd /home/nastya/wiki-interest

# environment (matplotlib and reportlab are needed only for chart and report)
uv sync --extra report

# install the skill so Claude can see it
ln -s /home/nastya/wiki-interest ~/.claude/skills/wiki-interest
```

To check the skill is installed: start a new Claude Code session and look at
`/skills`; `wiki-interest` should be there. **A new session is needed
after installation**; the skill will not appear in the current one.

To remove the skill: `rm ~/.claude/skills/wiki-interest`.

## 1. Check that everything works

```bash
uv run --with pytest python -m pytest -q     # 29 tests, all offline, ~0.2 s
```

If the tests are green, the code is fine. They do not need the network.

## 2. Manual run: commands in order

The order is fixed: `resolve` → (confirm the article) → `analyze`/`compare` →
`chart`/`report`. Each next command takes its state from the session.

```bash
# 1. topic → QID and article titles per language
uv run wikitrends resolve "intermittent fasting" --langs cs,uk,de

# 2. analyse one language
uv run wikitrends analyze Q1666254 --langs cs --period 36m

# 2b. or compare several
uv run wikitrends compare Q1666254 --langs cs,uk,de --period 36m

# 2c. with custom criteria (growth matters more than volume)
uv run wikitrends compare Q1666254 --langs cs,uk,de --weights growth=0.8,volume=0.2

# 2d. drop languages the data cannot vouch for
uv run wikitrends compare Q1666254 --langs cs,uk,de --min-confidence medium --min-views 300

# 3. chart or report from the last result: the path MUST be absolute
uv run wikitrends chart  --from-last --out ~/chart.png
uv run wikitrends report --from-last --out ~/report.pdf

# what is in the session now
uv run wikitrends session show
```

A relative `--out` saves the file inside the skill directory, where nobody will
find it. So always use an absolute path.

**Useful:**

```bash
uv run wikitrends cache show     # where the cache lives
uv run wikitrends cache clear    # reset the cache (the first request is slower afterwards)
uv run wikitrends session clear  # forget the last result
```

The cache and session live in `~/.cache/wikitrends/`. The first request on a new topic takes 5–10
seconds; repeated and related ones are almost instant.

---

# How to demo it

Three options, from quick to most convincing. If you have time for one, pick the third.

## Option A: the script, 15 seconds, no model

```bash
cd ~                              # the report will be saved here
/home/nastya/wiki-interest/demo.sh
```

Six steps in a row: ambiguous topic → language comparison → custom criteria →
chart → PDF → tests. Everything is deterministic and the cache is warm, so nothing
breaks in front of an audience.

Shows **what the tool can do**. Does not show the main point: that a weak model
finds it easy to use.

## Option B: a live question to the agent

A new Claude Code session, an ordinary question in plain language:

> Is interest in meditation growing on Polish Wikipedia?

Watch not the answer but **what the agent called**: `resolve`, then
`analyze`. It writes no code of its own. That is the whole point of the skill.

Good follow-up questions, which show the session at work:

> Now add Czech
> Show 5 years
> Make a PDF report

## Option C: with and without the skill, the most convincing

Shows exactly what all this was for: a weak model without the tool
draws wrong conclusions from raw numbers.

```bash
# 1. baseline, WITHOUT the skill
rm ~/.claude/skills/wiki-interest
mkdir -p /tmp/demo-a && cd /tmp/demo-a
claude --model haiku -p "Is interest in intermittent fasting growing on Czech Wikipedia over the last 3 years? How far can this data be trusted? Get the data yourself." \
  --allowedTools Bash Read Write WebFetch WebSearch Skill

# 2. the same question WITH the skill
ln -s /home/nastya/wiki-interest ~/.claude/skills/wiki-interest
mkdir -p /tmp/demo-b && cd /tmp/demo-b
claude --model haiku -p "<the same question>" \
  --allowedTools Bash Read Write WebFetch WebSearch Skill
```

Each run takes about a minute. What to point at:

| Without the skill | With the skill |
|---|---|
| "The data is **90–95%** reliable": a number out of thin air | `confidence: medium` + specific reasons |
| Compared September 2023 with the **unfinished** September 2026 → "−87%" | partial months dropped |
| Trend from two points, significance not checked | Theil–Sen + Mann–Kendall, `p<0.0001` |
| Absolute views: the decline of all Wikipedia counted as a decline of the topic | normalisation per million edition views |

If there is no time to run it live, both answers are already saved in
[`evals/runs/`](evals/runs/), together with the analysis.

## What else is worth showing

**The ambiguity safeguard.** Ask the agent about the topic "fasting diet" or
"English": it gets `ambiguous: true` and **asks back**, instead of
taking the first article it finds. This guards against the costliest mistake:
comparing articles with different meanings in different languages.

**Honesty about missing data.** The first example from the task is intermittent
fasting on Polish and Czech Wikipedia. Polish has **no** such article.
The skill says so directly, offers related articles as candidates and computes for
the languages that have the article. It never returns zero in place of "no data".

**Two defects the weak model found.** Analysis in
[`evals/runs/README.md`](evals/runs/README.md). This is a direct answer to the question
"how did you check the AI tools' output".

## If something goes wrong

| Symptom | Cause and what to do |
|---|---|
| The skill is not in `/skills` | a new Claude Code session is needed after installing the symlink |
| `Session is empty` on chart/report | run `analyze` or `compare` first |
| Charts need matplotlib | `uv sync --extra report` |
| Odd numbers after a code change | `uv run wikitrends cache clear` |
| The report "disappeared" | it was saved by relative path inside the skill directory |
