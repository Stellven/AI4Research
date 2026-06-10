#!/usr/bin/env bash
set -e

SOLAR_SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
export SOLAR_SOURCE_DIR

. "$SOLAR_SOURCE_DIR/lib/installer/main.sh"

main "$@"
