#!/usr/bin/env bash
# lib/prompt-quarantine.sh — Prompt Quarantine Lifecycle (S4, Coordinator Control Plane v2)
#
# Exports:
#   prompt_quarantine_check <pane> <sid> <dispatch_id>
#     → 0: pane clean, safe to dispatch
#     → 1: residue detected, fix-keys sent, caller should retry
#     → 2: quarantined after _QUARANTINE_MAX_FIXKEYS failed attempts
#     → 3: pane in quarantine cooldown, skip dispatch
#   prompt_quarantine_send_fixkeys <pane>
#     → sends Escape Escape C-u sequence; the ONLY place in the codebase that sends
#       these keys; exposed for tests
#   prompt_quarantine_resolve <pane> <dispatch_id> <resolution>
#     → clears markers/cooldown, writes resolved entry to inbox, restores pane
#
# State files (all under run/quarantine/):
#   inbox.jsonl                          — append-only {dispatch_id,sid,pane,
#                                          captured_excerpt,marker_count,action}
#   <pane_safe>.<dispatch_id>.cnt        — fix-key attempt counter for (pane,dispatch)
#   <pane_safe>.cooldown                 — ISO8601 expiry of quarantine cooldown
#
# Test hooks:
#   _QUARANTINE_CAPTURE_OVERRIDE (env)   — set to snapshot string to bypass tmux
#   _QUARANTINE_DIR (env)                — override base dir (for temp-dir tests)

HARNESS_DIR="${HARNESS_DIR:-${SOLAR_HARNESS_DIR:-$HOME/.solar/harness}}"
_QUARANTINE_DIR="${HARNESS_DIR}/run/quarantine"
_QUARANTINE_MAX_FIXKEYS=3       # on the 4th attempt → quarantine
_QUARANTINE_COOLDOWN_SEC=600    # quarantined pane cannot receive dispatches for 600s

_pane_safe_q() { echo "${1//:/_}" | tr '.' '_'; }

# ── _quarantine_capture ───────────────────────────────────────────────────────
# Returns snapshot of pane content. Overridable via _QUARANTINE_CAPTURE_OVERRIDE.
_quarantine_capture() {
    local pane="$1"
    if [[ -n "${_QUARANTINE_CAPTURE_OVERRIDE+x}" ]]; then
        printf '%s' "$_QUARANTINE_CAPTURE_OVERRIDE"
        return 0
    fi
    tmux capture-pane -t "$pane" -p 2>/dev/null || echo ""
}

# ── _quarantine_has_residue ───────────────────────────────────────────────────
_quarantine_prompt_input() {
    python3 -c '
import re
import sys

lines = sys.stdin.read().splitlines()
prompt_indexes = [i for i, line in enumerate(lines) if "❯" in line]
if not prompt_indexes:
    sys.exit(0)

footer_re = re.compile(r"⏵.*(auto|accept edits|edit|bypass permissions).*mode on|shift\\+tab|esc to interrupt", re.I)
footer_indexes = [i for i, line in enumerate(lines) if footer_re.search(line)]
footer_at = footer_indexes[-1] if footer_indexes else len(lines)

# Claude Code keeps historical submitted prompts above the divider. The current
# editable prompt is the last prompt close to the mode/footer region.
eligible = []
for i in prompt_indexes:
    if i > footer_at or footer_at - i > 6:
        continue
    next_nonempty = ""
    for line in lines[i + 1:footer_at + 1]:
        if line.strip():
            next_nonempty = line.strip()
            break
    if next_nonempty.startswith("─"):
        continue
    eligible.append(i)
if not eligible:
    sys.exit(0)

line = lines[eligible[-1]]
text = line.split("❯", 1)[1].replace("\u00a0", " ").strip()
if text in {"Try \"fix lint errors\"", "Try \"summarize this codebase\""}:
    text = ""
print(text)
'
}

# Residue = current Claude Code prompt has non-whitespace text after it.
# Clean  = no current prompt found, current prompt blank, or only historical prompts.
_quarantine_has_residue() {
    local snapshot="$1"
    local input
    input="$(printf '%s\n' "$snapshot" | _quarantine_prompt_input 2>/dev/null || true)"
    [[ -n "$input" ]]
}

# ── _quarantine_inbox_append ──────────────────────────────────────────────────
_quarantine_inbox_append() {
    local dispatch_id="$1" sid="$2" pane="$3" excerpt="$4" cnt="$5" action="$6"
    python3 -c "
import json, datetime, fcntl, os, sys
d = {
    'ts': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'dispatch_id': sys.argv[1], 'sid': sys.argv[2], 'pane': sys.argv[3],
    'captured_excerpt': sys.argv[4], 'marker_count': int(sys.argv[5]),
    'action': sys.argv[6]
}
lf = sys.argv[7]
os.makedirs(os.path.dirname(lf), exist_ok=True)
with open(lf, 'a') as f:
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(d) + '\n')
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
" "$dispatch_id" "$sid" "$pane" "$excerpt" "$cnt" "$action" \
  "${_QUARANTINE_DIR}/inbox.jsonl" 2>/dev/null || true
}

# ── prompt_quarantine_send_fixkeys ────────────────────────────────────────────
# The ONLY function in the codebase that sends Escape/C-u fix keys to a pane.
# coordinator.sh must NOT call tmux send-keys Escape/C-u directly.
prompt_quarantine_send_fixkeys() {
    local pane="${1:?prompt_quarantine_send_fixkeys: pane required}"
    tmux send-keys -t "$pane" Escape 2>/dev/null || true
    sleep 0.15
    tmux send-keys -t "$pane" Escape 2>/dev/null || true
    sleep 0.15
    tmux send-keys -t "$pane" C-u 2>/dev/null || true
    sleep 0.3
}

# ── prompt_quarantine_check ───────────────────────────────────────────────────
prompt_quarantine_check() {
    local pane="${1:?prompt_quarantine_check: pane required}"
    local sid="${2:?prompt_quarantine_check: sid required}"
    local dispatch_id="${3:?prompt_quarantine_check: dispatch_id required}"

    local pane_safe
    pane_safe=$(_pane_safe_q "$pane")
    local cooldown_file="${_QUARANTINE_DIR}/${pane_safe}.cooldown"
    local cnt_file="${_QUARANTINE_DIR}/${pane_safe}.${dispatch_id}.cnt"
    mkdir -p "$_QUARANTINE_DIR" 2>/dev/null || true

    # Step 1: check if pane is in quarantine cooldown
    if [[ -f "$cooldown_file" ]]; then
        local expires_at now_str
        expires_at=$(cat "$cooldown_file" 2>/dev/null || echo "")
        now_str=$(python3 -c "
import datetime; print(datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))
" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ")
        if [[ -n "$expires_at" && "$expires_at" > "$now_str" ]]; then
            return 3  # still in cooldown
        fi
        rm -f "$cooldown_file"  # expired, clear
    fi

    # Step 2: capture pane snapshot
    local snapshot
    snapshot=$(_quarantine_capture "$pane")

    # Step 3: check for residue
    if ! _quarantine_has_residue "$snapshot"; then
        [[ -f "$cnt_file" ]] && rm -f "$cnt_file"
        return 0  # clean
    fi

    # Step 4: has residue — check how many fix attempts already made
    local cnt=0
    [[ -f "$cnt_file" ]] && cnt=$(cat "$cnt_file" 2>/dev/null || echo 0)

    if (( cnt >= _QUARANTINE_MAX_FIXKEYS )); then
        # 4th+ attempt: quarantine the pane
        local excerpt
        excerpt=$(printf '%s\n' "$snapshot" | tail -3 | head -c 200)

        _quarantine_inbox_append \
            "$dispatch_id" "$sid" "$pane" "$excerpt" "$cnt" "quarantined"

        # Set cooldown expiry
        python3 -c "
import datetime, sys
expires = (datetime.datetime.utcnow() +
           datetime.timedelta(seconds=int(sys.argv[1]))).strftime('%Y-%m-%dT%H:%M:%SZ')
print(expires)
" "$_QUARANTINE_COOLDOWN_SEC" > "$cooldown_file" 2>/dev/null || true

        # Release pane lease (best-effort; it may not exist)
        type release_pane_lease &>/dev/null && \
            release_pane_lease "$pane" "$dispatch_id" "quarantined" &>/dev/null || true

        # Write quarantined event to dispatch ledger
        type dispatch_ledger_append &>/dev/null && \
            dispatch_ledger_append "quarantined" "$sid" "$pane" "$dispatch_id" \
                "{\"marker_count\":${cnt},\"cooldown_sec\":${_QUARANTINE_COOLDOWN_SEC}}" || true

        rm -f "$cnt_file"
        return 2  # quarantined
    fi

    # Step 5: send fix keys, increment counter, log attempt
    prompt_quarantine_send_fixkeys "$pane"
    local new_cnt=$(( cnt + 1 ))
    echo "$new_cnt" > "$cnt_file"
    _quarantine_inbox_append \
        "$dispatch_id" "$sid" "$pane" "" "$new_cnt" "fixkeys_sent"

    return 1  # residue found, fix keys sent, caller should retry
}

# ── prompt_quarantine_resolve ─────────────────────────────────────────────────
prompt_quarantine_resolve() {
    local pane="${1:?prompt_quarantine_resolve: pane required}"
    local dispatch_id="${2:?prompt_quarantine_resolve: dispatch_id required}"
    local resolution="${3:-manual}"

    local pane_safe
    pane_safe=$(_pane_safe_q "$pane")

    rm -f "${_QUARANTINE_DIR}/${pane_safe}.cooldown" 2>/dev/null || true
    rm -f "${_QUARANTINE_DIR}/${pane_safe}.${dispatch_id}.cnt" 2>/dev/null || true

    _quarantine_inbox_append \
        "$dispatch_id" "" "$pane" "" "0" "resolved_${resolution}"
}
