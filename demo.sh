#!/usr/bin/env bash
# Skill demo: the scenarios in a row, no model involved, only deterministic code.
# Run: ./demo.sh    (with a warm cache it all takes ~15 seconds)
set -euo pipefail
# Save the report where the skill was run from, not inside its directory.
OUT="${1:-$PWD/demo-report.pdf}"
cd "$(dirname "$0")"

RUN="uv run --extra report python scripts/wikitrends.py"

step() {
  echo
  echo "════════════════════════════════════════════════════════════════"
  echo "  $1"
  echo "════════════════════════════════════════════════════════════════"
  echo "  \$ $2"
  echo
}

step "1. The skill does not guess which article is meant" \
     "wikitrends resolve \"fasting diet\" --langs pl,cs,uk"
$RUN resolve "fasting diet" --langs pl,cs,uk
echo
echo "→ ambiguous: true and a warning about pl. The agent must ask, not compute."

step "2. Comparing languages: normalised metric + confidence" \
     "wikitrends compare Q1666254 --langs cs,uk,de --period 36m"
$RUN compare Q1666254 --langs cs,uk,de --period 36m
echo
echo "→ Ranking, confidence reasons and limitations are computed by code."
echo "  The model only has to relay them."

step "3. The user's own criteria change the recommendation" \
     "wikitrends compare Q1666254 --langs cs,uk,de --period 36m --weights growth=0.8,volume=0.2"
$RUN compare Q1666254 --langs cs,uk,de --period 36m --weights growth=0.8,volume=0.2 \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps({'ranking':d['ranking'],'recommendation':d['recommendation']}, ensure_ascii=False, indent=1))"
echo
echo "→ The criteria are printed next to the conclusion; the formula is transparent."

step "4. Chart only, no report" \
     "wikitrends chart --from-last --out ${OUT%.pdf}.png"
$RUN chart --from-last --out "${OUT%.pdf}.png"
echo
echo "→ The model does not write matplotlib itself: SKILL.md forbids it."

step "5. One-page PDF from the last result" \
     "wikitrends report --from-last --out $OUT"
$RUN report --from-last --out "$OUT"
echo
echo "→ File: $OUT"

step "6. Check: 29 tests, all offline: synthetic data and recorded API responses" \
     "pytest -q"
uv run --with pytest python -m pytest -q

echo
echo "Done. Methodology: references/methodology.md, data distortions: references/limitations.md."
