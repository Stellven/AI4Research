#!/usr/bin/env bash
set -euo pipefail
cd "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/harness"
python3 artifacts/autosci/runs/e2e-doc-literature-20260707/tools/validate_literature_item.py --metadata artifacts/autosci/runs/e2e-doc-literature-20260707/metadata/ghc-04.json --source artifacts/autosci/runs/e2e-doc-literature-20260707/sources/ghc-04.md --experiment-id exp-idea-ghc-04-landscape-driven-1 --claim-id idea-ghc-04-landscape-driven-1
