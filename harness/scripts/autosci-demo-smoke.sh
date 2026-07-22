#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_HARNESS_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
SMOKE_HARNESS="${SMOKE_HARNESS:-/tmp/bettersolar_autosci_smoke_$(date -u +%Y%m%dT%H%M%SZ)}"

mkdir -p "$SMOKE_HARNESS"

for name in bin config personas tools plugins evaluators schemas lib templates workflows; do
  if [[ -e "$SOURCE_HARNESS_DIR/$name" && ! -e "$SMOKE_HARNESS/$name" ]]; then
    ln -s "$SOURCE_HARNESS_DIR/$name" "$SMOKE_HARNESS/$name"
  fi
done

mkdir -p "$SMOKE_HARNESS/run" "$SMOKE_HARNESS/artifacts" "$SMOKE_HARNESS/raw"

DEMO_PAPER="$SMOKE_HARNESS/raw/demo-paper.md"
cat >"$DEMO_PAPER" <<'EOF'
# Demo Paper

## Abstract
This paper checks product-level AutoSci dispatch in unified Solar.

## Method
The test should produce typed evidence under the active HARNESS_DIR.

## Results
The test should write research_paper.v1 and scientific_lifecycle.v1 artifacts.
EOF

SKILLS_OUT="$SMOKE_HARNESS/artifacts/autosci-demo-skills.json"
INGEST_OUT="$SMOKE_HARNESS/artifacts/autosci-demo-ingest.json"
RESEARCH_OUT="$SMOKE_HARNESS/artifacts/autosci-demo-research.json"

HARNESS_DIR="$SMOKE_HARNESS" bash "$SOURCE_HARNESS_DIR/solar-harness.sh" autosci '$skills' >"$SKILLS_OUT"
grep -q '"count": 28' "$SKILLS_OUT"

HARNESS_DIR="$SMOKE_HARNESS" bash "$SOURCE_HARNESS_DIR/solar-harness.sh" autosci '$review --help' >/dev/null

HARNESS_DIR="$SMOKE_HARNESS" bash "$SOURCE_HARNESS_DIR/solar-harness.sh" autosci \
  "\$ingest --paper $DEMO_PAPER --run-id unified-demo-ingest" >"$INGEST_OUT"

HARNESS_DIR="$SMOKE_HARNESS" bash "$SOURCE_HARNESS_DIR/solar-harness.sh" autosci \
  "\$research unified demo --paper $DEMO_PAPER --scheduler-run --scheduler-timeout 20 --run-id unified-demo-research" >"$RESEARCH_OUT"

grep -R -q '"schema": "research_paper.v1"' "$SMOKE_HARNESS/artifacts"
grep -R -q '"schema": "scientific_lifecycle.v1"' "$SMOKE_HARNESS/artifacts"

printf 'AutoSci demo smoke passed\n'
printf 'SMOKE_HARNESS=%s\n' "$SMOKE_HARNESS"
find "$SMOKE_HARNESS/artifacts" -maxdepth 5 -type f | sort | sed -n '1,160p'
