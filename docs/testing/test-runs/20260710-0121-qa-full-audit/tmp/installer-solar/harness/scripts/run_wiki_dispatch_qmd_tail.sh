#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-${HOME}/Solar/harness}"
cd "$HARNESS_DIR"

LIMIT="${WIKI_DISPATCH_LIMIT:-2}"

exec ./solar-harness.sh wiki knowledge-ingest run-pipeline \
  --discover \
  --discover-raw-limit "$LIMIT" \
  --discover-vault-limit "$LIMIT" \
  --json
