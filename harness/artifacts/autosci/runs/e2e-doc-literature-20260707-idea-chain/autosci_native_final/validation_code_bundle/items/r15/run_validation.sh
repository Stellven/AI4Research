#!/usr/bin/env bash
set -euo pipefail
cd "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/harness"
python3 artifacts/autosci/runs/e2e-doc-literature-20260707/tools/validate_literature_item.py --metadata artifacts/autosci/runs/e2e-doc-literature-20260707/metadata/r15.json --source artifacts/autosci/runs/e2e-doc-literature-20260707/sources/r15.md --experiment-id exp-idea-r15-landscape-driven-1 --claim-id idea-r15-landscape-driven-1
