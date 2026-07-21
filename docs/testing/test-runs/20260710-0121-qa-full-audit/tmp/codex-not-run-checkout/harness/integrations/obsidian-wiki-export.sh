#!/usr/bin/env bash
# obsidian-wiki-export.sh — export-sprint logic for Solar Harness x Obsidian Wiki integration
#
# Converts Solar sprint artifacts into Obsidian Wiki raw staging markdown.
# Source this file or call cmd_wiki_export_sprint directly.
#
# Environment:
#   OBSIDIAN_VAULT_PATH      — resolved from ~/.obsidian-wiki/config if not set
#   OBSIDIAN_WIKI_CONFIG     — config file path (default ~/.obsidian-wiki/config)
#   SPRINT_DIR               — sprint artifacts dir (default ~/.solar/harness/sprints)
#   HARNESS_TEST             — if set, relaxes vault path validation
#   OBSIDIAN_WIKI_EXPORT_DRY — if set, print output path but do not write

set -euo pipefail

# ── helpers ──────────────────────────────────────────────────────────────────

_export_log()  { echo "[wiki-export] $*" >&2; }
_export_ok()   { echo "[wiki-export] ✓ $*" >&2; }
_export_warn() { echo "[wiki-export] ⚠ $*" >&2; }
_export_err()  { echo "[wiki-export] ✗ $*" >&2; }

# Load vault path from config file if OBSIDIAN_VAULT_PATH not already set.
_export_load_config() {
  local config="${OBSIDIAN_WIKI_CONFIG:-$HOME/.obsidian-wiki/config}"
  if [[ -z "${OBSIDIAN_VAULT_PATH:-}" ]]; then
    if [[ -f "$config" ]]; then
      # shellcheck disable=SC1090
      source "$config"
    fi
  fi
  if [[ -z "${OBSIDIAN_VAULT_PATH:-}" ]]; then
    _export_err "OBSIDIAN_VAULT_PATH not set. Run: solar-harness wiki install --vault <path>"
    return 1
  fi
}

# Validate vault path is safe to write to.
_export_assert_vault_safe() {
  local vault="$1"
  if [[ -z "${HARNESS_TEST:-}" ]]; then
    # In production, vault must exist and be a directory.
    if [[ ! -d "$vault" ]]; then
      _export_err "Vault directory does not exist: $vault"
      return 1
    fi
  fi
}

# Return the sprint directory (env override or default).
_export_sprint_dir() {
  echo "${SPRINT_DIR:-$HOME/.solar/harness/sprints}"
}

# ISO 8601 timestamp.
_export_iso8601() {
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

# ── redaction ────────────────────────────────────────────────────────────────

# Redact secrets from a string. Reads stdin, writes stdout.
# Applies regex patterns that match common credential leaks.
# Uses python3 -c to keep stdin available for pipeline data.
_redact_stream() {
  python3 -c '
import sys, re

CRED_KV = re.compile(
    r"(?i)(token|key|secret|password|api[_-]?key|apikey|auth|credential|passwd)\s*[=:]\s*\S+"
)
AUTH_HEADER = re.compile(
    r"(?i)(Authorization|Bearer|Basic)\s*[:\s]+[A-Za-z0-9+/=._-]{8,}"
)
LONG_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")
LONG_B64 = re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b")

def redact(line):
    line = CRED_KV.sub(lambda m: m.group(1) + "=<REDACTED>", line)
    line = AUTH_HEADER.sub(lambda m: m.group(1) + ": <REDACTED>", line)
    line = LONG_HEX.sub("<REDACTED>", line)
    line = LONG_B64.sub("<REDACTED>", line)
    return line

for line in sys.stdin:
    sys.stdout.write(redact(line))
'
}

# Redact a file's contents to stdout.
_redact_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then return 0; fi
  _redact_stream < "$path"
}

# Truncate terminal transcript: first 200 chars + notice.
_truncate_transcript() {
  python3 -c "
import sys
data = sys.stdin.read()
if len(data) > 200:
    print(data[:200] + '\n[...truncated, see live log]')
else:
    print(data)
"
}

# ── section builders ─────────────────────────────────────────────────────────

# Extract and summarize a markdown file (first N lines).
_summarize_md() {
  local path="$1"
  local max_lines="${2:-80}"
  local label="${3:-}"
  if [[ ! -f "$path" ]]; then
    echo "_[${label:-$(basename "$path")} not found]_"
    return 0
  fi
  head -"${max_lines}" "$path"
  local total
  total=$(wc -l < "$path")
  if (( total > max_lines )); then
    echo ""
    echo "_[...${total} total lines, truncated to ${max_lines}]_"
  fi
}

# Summarize events.jsonl: count by event type, list up to max_events.
_summarize_events() {
  local path="$1"
  local max_events="${2:-20}"
  if [[ ! -f "$path" ]]; then
    echo "_[events log not found]_"
    return 0
  fi
  local total
  total=$(wc -l < "$path")
  echo "**Total events**: ${total}"
  echo ""
  echo "**Event counts by type**:"
  python3 - "$path" <<'PYEOF'
import sys, json, collections
path = sys.argv[1]
counts = collections.Counter()
with open(path) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
            evt = ev.get('event') or ev.get('type') or 'unknown'
            counts[evt] += 1
        except Exception:
            counts['_parse_error'] += 1
for evt, cnt in counts.most_common():
    print(f'- `{evt}`: {cnt}')
PYEOF
  echo ""
  echo "**Selected events** (up to ${max_events}):"
  python3 - "$path" "$max_events" <<'PYEOF'
import sys, json
path, max_ev = sys.argv[1], int(sys.argv[2])
events = []
with open(path) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
            events.append(ev)
        except Exception:
            pass
# Show first half and last half to capture start and end
half = max_ev // 2
shown = events[:half]
if len(events) > max_ev:
    shown += events[-(max_ev - half):]
else:
    shown = events[:max_ev]
for ev in shown:
    ts = ev.get('ts', '')
    evt = ev.get('event') or ev.get('type') or 'unknown'
    actor = ev.get('actor') or ev.get('by') or ''
    severity = ev.get('severity', '')
    parts = [f'`{ts}`' if ts else '', f'**{evt}**', f'by `{actor}`' if actor else '', f'[{severity}]' if severity else '']
    print('- ' + ' '.join(p for p in parts if p))
PYEOF
}

# Extract eval verdict from eval.json.
_extract_eval_verdict() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "_[eval not found — sprint may not yet be evaluated]_"
    return 0
  fi
  python3 - "$path" <<'PYEOF'
import sys, json
with open(sys.argv[1]) as f:
    d = json.load(f)
verdict = d.get('verdict', 'unknown')
rnd = d.get('round', '?')
passed = d.get('passed_conditions', [])
failed = d.get('failed_conditions', [])
warnings = d.get('warnings', [])
print(f'**Verdict**: `{verdict}` (round {rnd})')
print(f'**Passed**: {", ".join(passed) if passed else "none"}')
print(f'**Failed**: {", ".join(failed) if failed else "none"}')
if warnings:
    print(f'**Warnings** ({len(warnings)}):')
    for w in warnings[:5]:
        cond = w.get('cond', '')
        sev = w.get('severity', '')
        ev = w.get('evidence', '')
        print(f'  - [{cond}] ({sev}): {ev[:120]}')
PYEOF
}

# Extract status summary from status.json.
_extract_status_summary() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "_[status.json not found]_"
    return 0
  fi
  python3 - "$path" <<'PYEOF'
import sys, json
with open(sys.argv[1]) as f:
    d = json.load(f)
fields = ['status', 'phase', 'priority', 'lane', 'round', 'updated_at', 'handoff_to']
for k in fields:
    if k in d:
        print(f'- **{k}**: `{d[k]}`')
PYEOF
}

# ── cmd_wiki_export_sprint ───────────────────────────────────────────────────

# Usage: cmd_wiki_export_sprint <sid> [--redact|--full]
#
# Exports sprint artifacts to $OBSIDIAN_VAULT_PATH/_raw/solar-harness/<sid>.md
# Default mode is --redact.
cmd_wiki_export_sprint() {
  local sid=""
  local mode="redact"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --redact) mode="redact"; shift ;;
      --full)   mode="full";   shift ;;
      -*)
        _export_err "Unknown option: $1"
        _export_err "Usage: export-sprint <sid> [--redact|--full]"
        return 1
        ;;
      *)
        if [[ -z "$sid" ]]; then
          sid="$1"
        else
          _export_err "Unexpected argument: $1"
          return 1
        fi
        shift
        ;;
    esac
  done

  if [[ -z "$sid" ]]; then
    _export_err "Usage: export-sprint <sid> [--redact|--full]"
    return 1
  fi

  # Load vault path.
  _export_load_config

  # Safety check.
  _export_assert_vault_safe "$OBSIDIAN_VAULT_PATH"

  local sprint_dir
  sprint_dir=$(_export_sprint_dir)

  # Locate sprint artifact files.
  local f_contract="${sprint_dir}/${sid}.contract.md"
  local f_plan="${sprint_dir}/${sid}.plan.md"
  local f_handoff="${sprint_dir}/${sid}.handoff.md"
  local f_eval="${sprint_dir}/${sid}.eval.json"
  local f_status="${sprint_dir}/${sid}.status.json"
  local f_events="${sprint_dir}/${sid}.events.jsonl"

  # At minimum the sprint id should have at least one artifact.
  local found=0
  for f in "$f_contract" "$f_plan" "$f_handoff" "$f_eval" "$f_status" "$f_events"; do
    [[ -f "$f" ]] && (( found++ )) || true
  done
  if (( found == 0 )); then
    _export_err "No sprint artifacts found for '$sid' in $sprint_dir"
    return 1
  fi

  # Build output path.
  local out_dir="${OBSIDIAN_VAULT_PATH}/_raw/solar-harness"
  local out_file="${out_dir}/${sid}.md"

  if [[ -n "${OBSIDIAN_WIKI_EXPORT_DRY:-}" ]]; then
    _export_log "DRY RUN: would write to $out_file"
    echo "$out_file"
    return 0
  fi

  mkdir -p "$out_dir"

  local exported_at
  exported_at=$(_export_iso8601)
  local redacted_flag="true"
  [[ "$mode" == "full" ]] && redacted_flag="false"

  _export_log "Exporting sprint '$sid' (mode=$mode) → $out_file"

  # Build the markdown document.
  {
    # YAML frontmatter.
    printf -- '---\n'
    printf 'source: solar-harness\n'
    printf 'sprint_id: %s\n' "$sid"
    printf 'exported_at: %s\n' "$exported_at"
    printf 'redacted: %s\n' "$redacted_flag"
    printf 'visibility: internal\n'
    printf -- '---\n\n'

    # Title.
    printf '# Sprint Export: %s\n\n' "$sid"
    printf '_Exported at %s — mode: `%s`_\n\n' "$exported_at" "$mode"

    # ── Status ──
    printf '## Status\n\n'
    _extract_status_summary "$f_status"
    printf '\n'

    # ── Eval ──
    printf '## Evaluation\n\n'
    _extract_eval_verdict "$f_eval"
    printf '\n'

    # ── Contract ──
    printf '## Contract (summary)\n\n'
    if [[ "$mode" == "redact" ]]; then
      _summarize_md "$f_contract" 80 "contract" | _redact_stream
    else
      _summarize_md "$f_contract" 80 "contract"
    fi
    printf '\n'

    # ── Plan ──
    printf '## Plan (summary)\n\n'
    if [[ "$mode" == "redact" ]]; then
      _summarize_md "$f_plan" 80 "plan" | _redact_stream
    else
      _summarize_md "$f_plan" 80 "plan"
    fi
    printf '\n'

    # ── Handoff ──
    printf '## Handoff (summary)\n\n'
    if [[ -f "$f_handoff" ]]; then
      if [[ "$mode" == "redact" ]]; then
        _summarize_md "$f_handoff" 60 "handoff" | _redact_stream
      else
        _summarize_md "$f_handoff" 60 "handoff"
      fi
    else
      printf '_[handoff not yet written]_\n'
    fi
    printf '\n'

    # ── Events ──
    printf '## Events\n\n'
    if [[ "$mode" == "redact" ]]; then
      _summarize_events "$f_events" 20 | _redact_stream
    else
      _summarize_events "$f_events" 20
    fi
    printf '\n'

    # ── Artifact index ──
    printf '## Source Artifacts\n\n'
    printf '| File | Present |\n'
    printf '|------|--------|\n'
    local _label _fpath _present
    for _art in \
      "contract:$f_contract" \
      "plan:$f_plan" \
      "handoff:$f_handoff" \
      "eval:$f_eval" \
      "status:$f_status" \
      "events:$f_events"; do
      _label="${_art%%:*}"
      _fpath="${_art#*:}"
      _present="no"
      [[ -f "$_fpath" ]] && _present="yes"
      printf '| `%s` | %s |\n' "$_label" "$_present"
    done
    printf '\n'

    printf '_Generated by solar-harness wiki export-sprint — do not edit manually._\n'

  } > "$out_file"

  # Update last_exported_sprint in status.json if writable.
  if [[ -f "$f_status" && -w "$f_status" ]]; then
    python3 - "$f_status" "$sid" "$exported_at" <<'PYEOF' || true
import sys, json
path, sid, ts = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    d = json.load(f)
d['last_exported_sprint'] = sid
d['last_exported_at'] = ts
with open(path, 'w') as f:
    json.dump(d, f, indent=2)
    f.write('\n')
PYEOF
    _export_ok "Updated last_exported_sprint in status.json"
  fi

  _export_ok "Written: $out_file"
  echo "$out_file"
}

# ── CLI entrypoint ────────────────────────────────────────────────────────────
# Allow direct invocation: obsidian-wiki-export.sh export-sprint <sid> [opts]

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
  cmd="${1:-}"
  shift || true
  case "$cmd" in
    export-sprint)
      cmd_wiki_export_sprint "$@"
      ;;
    *)
      echo "Usage: $(basename "$0") export-sprint <sid> [--redact|--full]" >&2
      exit 1
      ;;
  esac
fi
