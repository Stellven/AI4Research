#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"

paths=(
  "$HARNESS_DIR/lib"
  "$HARNESS_DIR/scripts"
  "$HARNESS_DIR/tools"
  "$HARNESS_DIR/autopilot"
)

patterns=(
  '^[[:space:]]*import[[:space:]]+omlx([[:space:]]|$)'
  '^[[:space:]]*from[[:space:]]+omlx[[:space:].]'
  '^[[:space:]]*import[[:space:]]+mlx_lm([[:space:]]|$)'
  '^[[:space:]]*from[[:space:]]+mlx_lm[[:space:].]'
)

fail=0
for p in "${paths[@]}"; do
  [[ -e "$p" ]] || continue
  for pat in "${patterns[@]}"; do
    if rg -n --glob '*.py' --glob '!vendor/**' --glob '!**/__pycache__/**' "$pat" "$p"; then
      fail=1
    fi
  done
done

if [[ "$fail" == "1" ]]; then
  cat >&2 <<'EOF'
ERROR: unsafe ThunderOMLX package-root import detected.

Why this is blocked:
  omlx / mlx_lm imports can transitively load transformers -> torch. If numpy
  or OpenBLAS has already loaded Homebrew libomp in the same long-running
  Python process, torch's bundled libomp can trigger OpenMP Error #15 and abort.

Required pattern:
  - For read-only reports, direct-load the specific stdlib-only module by file
    path with importlib.util.spec_from_file_location().
  - For torch/transformers work, run it in an isolated venv/process and do not
    mix it with numpy-heavy long-running harness monitors.
EOF
  exit 1
fi

echo "libomp import guard: PASS"
