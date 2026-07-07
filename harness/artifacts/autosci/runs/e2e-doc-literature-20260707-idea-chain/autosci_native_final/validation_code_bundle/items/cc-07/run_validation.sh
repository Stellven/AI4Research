#!/usr/bin/env bash
set -euo pipefail
cd "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/harness"
python3 artifacts/autosci/runs/e2e-doc-literature-20260707/tools/validate_literature_item.py --metadata artifacts/autosci/runs/e2e-doc-literature-20260707/metadata/cc-07.json --source artifacts/autosci/runs/e2e-doc-literature-20260707/sources/cc-07.md --experiment-id exp-idea-cc-07-landscape-driven --claim-id idea-cc-07-landscape-driven
