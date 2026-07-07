#!/usr/bin/env bash
set -euo pipefail
cd "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/harness"
python3 artifacts/autosci/runs/e2e-doc-literature-20260707/tools/validate_literature_item.py --metadata artifacts/autosci/runs/e2e-doc-literature-20260707/metadata/ghc-01.json --source artifacts/autosci/runs/e2e-doc-literature-20260707/sources/ghc-01.md --experiment-id exp-idea-ghc-01-landscape-driven --claim-id idea-ghc-01-landscape-driven
