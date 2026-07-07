#!/usr/bin/env bash
set -euo pipefail
cd "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/harness"
python3 artifacts/autosci/runs/e2e-doc-literature-20260707/tools/validate_literature_item.py --metadata artifacts/autosci/runs/e2e-doc-literature-20260707/metadata/cu-02.json --source artifacts/autosci/runs/e2e-doc-literature-20260707/sources/cu-02.md --experiment-id exp-idea-cu-02-landscape-driven --claim-id idea-cu-02-landscape-driven
