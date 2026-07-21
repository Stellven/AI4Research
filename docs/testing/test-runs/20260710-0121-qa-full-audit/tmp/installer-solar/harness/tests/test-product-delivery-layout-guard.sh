#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SOLAR_HARNESS="$HARNESS_DIR/solar-harness.sh"

fail() {
  echo "FAIL $*" >&2
  exit 1
}

grep -q 'EXPECTED_PRODUCT_DELIVERY_PANES=4' "$SOLAR_HARNESS" \
  || fail "missing Product Delivery expected pane count"

grep -q 'product_delivery_pane_count()' "$SOLAR_HARNESS" \
  || fail "missing Product Delivery pane count helper"

grep -q 'warn_if_product_delivery_layout_incomplete' "$SOLAR_HARNESS" \
  || fail "missing Product Delivery layout warning helper"

grep -q 'layout: error expected=${EXPECTED_PRODUCT_DELIVERY_PANES} actual=${physical_panes}' "$SOLAR_HARNESS" \
  || fail "main-status does not expose physical layout errors"

grep -q 'Solar Harness 已在运行，但 Product Delivery layout 异常' "$SOLAR_HARNESS" \
  || fail "start path still accepts incomplete Product Delivery layout silently"

echo "PASS Product Delivery layout guard is present"
