#!/usr/bin/env bash
set -euo pipefail
cd "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/harness"
python3 artifacts/autosci/runs/e2e-doc-literature-20260707/tools/validate_literature_item.py --metadata artifacts/autosci/runs/e2e-doc-literature-20260707/metadata/r13.json --source artifacts/autosci/runs/e2e-doc-literature-20260707/sources/r13.md --experiment-id exp-idea-r13-landscape-driven-1 --claim-id idea-r13-landscape-driven-1
