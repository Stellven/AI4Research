#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${EXT_DIR:-}" ]]; then
  if [[ -f "$HOME/Solar/harness/extensions/chatgpt-knowledge-capture/manifest.json" ]]; then
    EXT_DIR="$HOME/Solar/harness/extensions/chatgpt-knowledge-capture"
  else
    EXT_DIR="$HOME/.solar/harness/extensions/chatgpt-knowledge-capture"
  fi
fi
CHROME_APP="${CHROME_APP:-Google Chrome}"

if [[ ! -f "$EXT_DIR/manifest.json" ]]; then
  echo "missing extension manifest: $EXT_DIR/manifest.json" >&2
  exit 2
fi

open -a "$CHROME_APP" --args --load-extension="$EXT_DIR" "$@"
