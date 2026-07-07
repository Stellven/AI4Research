#!/usr/bin/env bash
set -euo pipefail
cd "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/harness"
python3 artifacts/autosci/runs/e2e-doc-literature-20260707/tools/validate_literature_item.py --metadata artifacts/autosci/runs/e2e-doc-literature-20260707/metadata/cu-04.json --source artifacts/autosci/runs/e2e-doc-literature-20260707/sources/cu-04.md --experiment-id exp-idea-cu-04-landscape-driven --claim-id idea-cu-04-landscape-driven
