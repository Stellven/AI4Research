#!/usr/bin/env bash
set -euo pipefail
log() { :; }
reset_stale_runtime_state() {
  local why="${1:-fresh-session}"
  local run_dir="$HARNESS_DIR/run"
  local reset_count=0 lease_dir marker

  # 1) Hygiene registry → empty, so freshly-launched panes re-register clean (clears any
  #    stale needs_respawn/needs_recover latch). Recreated on first registry access.
  if [[ -f "$run_dir/pane-hygiene.json" ]]; then
    printf '{}\n' > "$run_dir/pane-hygiene.json"
    reset_count=$((reset_count+1))
  fi

  # 2) Pane/actor leases: on a clean start no pane holds a live lease.
  for lease_dir in "$run_dir/pane-leases" "$run_dir/actor-leases"; do
    if [[ -d "$lease_dir" ]]; then
      find "$lease_dir" -maxdepth 1 -type f \( -name '*.json' -o -name '*.json.lock' \) -delete 2>/dev/null || true
      reset_count=$((reset_count+1))
    fi
  done

  # 3) Stale pane assignments + fire-once dispatch markers (root dotfiles). These reserve
  #    panes / suppress re-dispatch for sprints that may be long gone; rebuilt on demand.
  for marker in .pane-assignments .drafting-flow-dispatched .drafting-flow-retry .builder-flow-dispatched; do
    if [[ -f "$HARNESS_DIR/$marker" ]]; then
      rm -f "$HARNESS_DIR/$marker"
      reset_count=$((reset_count+1))
    fi
  done

  log "${G:-}[clean-start] reset ${reset_count} stale runtime state item(s) (${why})${N:-}"
}
reset_stale_runtime_state audit-approved-clean-start
