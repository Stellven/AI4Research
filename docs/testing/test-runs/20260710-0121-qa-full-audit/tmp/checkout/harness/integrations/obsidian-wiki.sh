#!/usr/bin/env bash
# Solar Harness — Obsidian Wiki integration
# Subcommands: install, status, export-sprint, update, query
# Safety: never overwrites real directories; HARNESS_TEST=1 uses temp/test paths.
# Version: 1.0.0  Slice: S1 (installer/status/safe-symlink)

set -euo pipefail

WIKI_INTEGRATION_VERSION="1.0.0"

# ─── path defaults ────────────────────────────────────────────────────────────
DEFAULT_REPO_PATH="${HOME}/.solar/harness/vendor/obsidian-wiki"
DEFAULT_CONFIG_DIR="${HOME}/.obsidian-wiki"
HARNESS_DIR="${HARNESS_DIR:-${HOME}/.solar/harness}"
WIKI_STATE_FILE="${HARNESS_DIR}/integrations/obsidian-wiki-state.json"

# HARNESS_TEST=1 → use .test suffix config to avoid touching real ~/.obsidian-wiki/config
if [[ "${HARNESS_TEST:-}" == "1" ]]; then
  WIKI_CONFIG_FILE="${OBSIDIAN_WIKI_CONFIG:-${HOME}/.obsidian-wiki/config.test}"
else
  WIKI_CONFIG_FILE="${DEFAULT_CONFIG_DIR}/config"
fi

# Vault skeleton: directories to create under vault root
VAULT_SKELETON_DIRS=("_raw" "_raw/solar-harness" "_raw/solar-harness/.dispatch"
                     "projects" "concepts" "entities" "skills"
                     "references" "synthesis" "journal")

# ─── logging helpers ──────────────────────────────────────────────────────────
log_info()  { printf '[wiki] INFO:  %s\n'  "$*" >&2; }
log_warn()  { printf '[wiki] WARN:  %s\n'  "$*" >&2; }
log_error() { printf '[wiki] ERROR: %s\n'  "$*" >&2; }
die()       { log_error "$*"; exit 1; }

iso8601()   { date -u "+%Y-%m-%dT%H:%M:%SZ"; }

# ─── safe_symlink <src> <dst> ─────────────────────────────────────────────────
# Creates dst → src.
#   • If dst is already a symlink   → update (ln -sfn).
#   • If dst is a real dir/file     → REFUSE, return 1.
#   • Otherwise                     → create symlink.
safe_symlink() {
  local src="$1" dst="$2"
  if [[ -L "$dst" ]]; then
    ln -sfn "$src" "$dst"
    log_info "Updated symlink: $dst -> $src"
    return 0
  fi
  if [[ -e "$dst" ]]; then
    log_warn "REFUSE: $dst exists as real dir/file — skipping symlink install"
    return 1
  fi
  mkdir -p "$(dirname "$dst")"
  ln -s "$src" "$dst"
  log_info "Created symlink: $dst -> $src"
  return 0
}

install_skill_tree() {
  local skills_src="$1" target_dir="$2"
  local errors=0 installed=0 skipped=0
  mkdir -p "$target_dir"

  local skill src dst name
  for skill in "$skills_src"/*; do
    [[ -d "$skill" ]] || continue
    name="$(basename "$skill")"
    src="$skill"
    dst="$target_dir/$name"
    if safe_symlink "$src" "$dst"; then
      installed=$((installed + 1))
    else
      skipped=$((skipped + 1))
      errors=$((errors + 1))
    fi
  done

  log_info "Skill install summary for $target_dir: installed/updated=$installed skipped=$skipped"
  if skill_tree_ready "$target_dir"; then
    return 0
  fi
  return "$errors"
}

skill_tree_ready() {
  local target_dir="$1"
  [[ -L "$target_dir/wiki-update" && -L "$target_dir/wiki-query" && -L "$target_dir/wiki-ingest" ]]
}

# ─── load_config ──────────────────────────────────────────────────────────────
# Reads OBSIDIAN_VAULT_PATH and OBSIDIAN_WIKI_REPO from config file into env
# (only if they are not already set by caller).
load_config() {
  local cfg="${WIKI_CONFIG_FILE}"
  [[ ! -f "$cfg" ]] && return 0
  local v r
  v=$(grep -E '^OBSIDIAN_VAULT_PATH=' "$cfg" 2>/dev/null | head -1 | cut -d= -f2- \
      | sed "s/^['\"]//;s/['\"]$//" || true)
  r=$(grep -E '^OBSIDIAN_WIKI_REPO='  "$cfg" 2>/dev/null | head -1 | cut -d= -f2- \
      | sed "s/^['\"]//;s/['\"]$//" || true)
  [[ -n "$v" ]] && OBSIDIAN_VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$v}"
  [[ -n "$r" ]] && OBSIDIAN_WIKI_REPO="${OBSIDIAN_WIKI_REPO:-$r}"
}

# ─── write_config <vault> <repo> ─────────────────────────────────────────────
write_config() {
  local vault="$1" repo="$2"
  mkdir -p "$(dirname "${WIKI_CONFIG_FILE}")"
  printf 'OBSIDIAN_VAULT_PATH=%s\nOBSIDIAN_WIKI_REPO=%s\n' "$vault" "$repo" \
    > "${WIKI_CONFIG_FILE}"
  log_info "Wrote config: ${WIKI_CONFIG_FILE}"
}

# ─── update_state_field <field> <value> ──────────────────────────────────────
# Persists a single string field into the integration state JSON.
update_state_field() {
  local field="$1" value="$2"
  local tmp
  tmp=$(mktemp)
  if [[ -f "$WIKI_STATE_FILE" ]]; then
    python3 - "$WIKI_STATE_FILE" "$field" "$value" "$tmp" <<'PYEOF'
import json, sys
src, field, val, dst = sys.argv[1:]
try:
    d = json.load(open(src))
except Exception:
    d = {}
d[field] = val
json.dump(d, open(dst, 'w'), indent=2)
PYEOF
  else
    python3 - "$field" "$value" "$tmp" <<'PYEOF'
import json, sys
field, val, dst = sys.argv[1:]
json.dump({field: val}, open(dst, 'w'), indent=2)
PYEOF
  fi
  mkdir -p "$(dirname "$WIKI_STATE_FILE")"
  mv "$tmp" "$WIKI_STATE_FILE"
}

# ─── read_state_field <field> ─────────────────────────────────────────────────
read_state_field() {
  local field="$1"
  [[ ! -f "$WIKI_STATE_FILE" ]] && echo "" && return 0
  python3 - "$WIKI_STATE_FILE" "$field" <<'PYEOF'
import json, sys
src, field = sys.argv[1:]
try:
    d = json.load(open(src))
    v = d.get(field, "")
    print(v if v is not None else "")
except Exception:
    print("")
PYEOF
}

# ─── skill target resolution ─────────────────────────────────────────────────
# Returns the effective skill target path for each agent runtime.
# HARNESS_TEST=1 uses SKILL_TARGETS_OVERRIDE_* env vars when set.
skill_target_codex()  {
  echo "${SKILL_TARGETS_OVERRIDE_CODEX:-${HOME}/.codex/skills}"
}
skill_target_claude() {
  echo "${SKILL_TARGETS_OVERRIDE_CLAUDE:-${HOME}/.claude/skills}"
}
skill_target_agents() {
  echo "${SKILL_TARGETS_OVERRIDE_AGENTS:-${HOME}/.agents/skills}"
}

# ─── cmd_install ─────────────────────────────────────────────────────────────
cmd_install() {
  local vault="" repo="" refresh=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --vault)   shift; vault="$1" ;;
      --repo)    shift; repo="$1"  ;;
      --refresh) refresh=1 ;;
      *)         die "Unknown install arg: $1" ;;
    esac
    shift
  done

  [[ -z "$vault" ]] && die "install requires --vault <path>"
  vault="${vault/#\~/$HOME}"
  repo="${repo:-$DEFAULT_REPO_PATH}"
  repo="${repo/#\~/$HOME}"

  # 1. Ensure upstream repo clone ─────────────────────────────────────────────
  if [[ ! -d "$repo" ]]; then
    log_info "Cloning upstream repo to $repo …"
    if ! git clone https://github.com/Ar9av/obsidian-wiki "$repo" 2>&1; then
      log_warn "Clone failed — continuing without upstream repo (offline mode)"
    fi
  elif [[ "$refresh" == "1" ]]; then
    log_info "Refreshing upstream repo at $repo …"
    git -C "$repo" pull --ff-only 2>&1 \
      || log_warn "git pull failed — continuing with existing clone"
  else
    log_info "Upstream repo already present at $repo"
  fi

  # 2. Write config ────────────────────────────────────────────────────────────
  write_config "$vault" "$repo"

  # 3. Create vault skeleton ───────────────────────────────────────────────────
  mkdir -p "$vault"
  local d
  for d in "${VAULT_SKELETON_DIRS[@]}"; do
    mkdir -p "$vault/$d"
  done

  # Seed stub files only if not present (idempotent)
  local ts
  ts="$(iso8601)"
  [[ ! -f "$vault/index.md" ]]        && printf '# Solar Wiki\n' > "$vault/index.md"
  [[ ! -f "$vault/log.md" ]]          && printf '# Log\n' > "$vault/log.md"
  [[ ! -f "$vault/hot.md" ]]          && printf '# Hot Topics\n' > "$vault/hot.md"
  [[ ! -f "$vault/.manifest.json" ]]  && printf '{"version":"1","created":"%s"}\n' "$ts" \
                                            > "$vault/.manifest.json"

  log_info "Vault skeleton ready at $vault"

  # 4. Install skill symlinks ──────────────────────────────────────────────────
  # Skills source: prefer upstream repo's .skills/ dir
  local skills_src=""
  if [[ -d "$repo/.skills" ]]; then
    skills_src="$repo/.skills"
  elif [[ -d "$repo/skills" ]]; then
    skills_src="$repo/skills"
  fi

  local install_errors=0

  if [[ -n "$skills_src" ]]; then
    install_skill_tree "$skills_src" "$(skill_target_codex)"  || install_errors=$((install_errors + 1))
    install_skill_tree "$skills_src" "$(skill_target_claude)" || install_errors=$((install_errors + 1))
    install_skill_tree "$skills_src" "$(skill_target_agents)" || install_errors=$((install_errors + 1))
  else
    log_warn "No .skills/ or skills/ directory found in repo — skipping skill symlinks"
    log_warn "  (repo may not be cloned yet; re-run with --refresh after clone succeeds)"
  fi

  if [[ $install_errors -gt 0 ]]; then
    log_warn "$install_errors skill symlink(s) refused (target exists as real dir) — vault install otherwise complete"
    return 2
  fi

  log_info "Install complete."
}

# ─── cmd_status ──────────────────────────────────────────────────────────────
cmd_status() {
  local json_mode=0
  [[ "${1:-}" == "--json" ]] && json_mode=1

  load_config

  local vault="${OBSIDIAN_VAULT_PATH:-}"
  local repo="${OBSIDIAN_WIKI_REPO:-}"
  local cfg="${WIKI_CONFIG_FILE}"
  local ts
  ts="$(iso8601)"

  # configured = config file present AND vault path is non-empty
  local configured="false"
  [[ -f "$cfg" && -n "$vault" ]] && configured="true"

  # skill symlink checks: target dirs may be real dirs; required wiki skills
  # should be symlinks inside them.
  local codex_ok="false" claude_ok="false" agents_ok="false"
  skill_tree_ready "$(skill_target_codex)"  && codex_ok="true"
  skill_tree_ready "$(skill_target_claude)" && claude_ok="true"
  skill_tree_ready "$(skill_target_agents)" && agents_ok="true"

  # last exported sprint from state file
  local last_exp
  last_exp="$(read_state_field last_exported_sprint)"

  if [[ "$json_mode" == "1" ]]; then
    # Build JSON via Python to handle path escaping safely
    python3 - \
      "$configured" "$repo" "$vault" "$cfg" \
      "$codex_ok" "$claude_ok" "$agents_ok" \
      "$last_exp" "$ts" \
      <<'PYEOF'
import json, sys
args = sys.argv[1:]
configured, repo, vault, cfg, codex_ok, claude_ok, agents_ok, last_exp, ts = args
d = {
    "configured": configured == "true",
    "repo_path": repo,
    "vault_path": vault,
    "config_path": cfg,
    "skills_installed": {
        "codex":  codex_ok  == "true",
        "claude": claude_ok == "true",
        "agents": agents_ok == "true",
    },
    "last_exported_sprint": last_exp if last_exp else None,
    "last_checked_at": ts,
}
print(json.dumps(d, indent=2))
PYEOF
  else
    local cflag="✓" rflag="✓"
    [[ "$configured" != "true" ]] && cflag="✗"
    [[ ! -d "$repo" ]] && rflag="✗"
    printf 'Solar Harness — Obsidian Wiki Status\n'
    printf '  Configured : %s  (%s)\n'     "$cflag" "$cfg"
    printf '  Vault      : %s\n'           "${vault:-(not set)}"
    printf '  Repo       : %s  %s\n'       "$rflag" "${repo:-(not set)}"
    printf '  Skills     : codex=%s  claude=%s  agents=%s\n' \
           "$codex_ok" "$claude_ok" "$agents_ok"
    printf '  Last export: %s\n'           "${last_exp:-(none)}"
    printf '  Checked at : %s\n'           "$ts"
  fi
}

# ─── cmd_export_sprint ────────────────────────────────────────────────────────
# S2 — export sprint artifacts to vault/_raw/solar-harness/<sid>.md
cmd_export_sprint() {
  local sid="" redact_mode="redact"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --redact) redact_mode="redact" ;;
      --full)   redact_mode="full"   ;;
      -*)       die "Unknown export-sprint arg: $1" ;;
      *)        sid="$1" ;;
    esac
    shift
  done

  [[ -z "$sid" ]] && die "export-sprint requires <sid>"

  load_config
  local vault="${OBSIDIAN_VAULT_PATH:-}"
  [[ -z "$vault" ]] && die "Vault not configured. Run: solar-harness wiki install --vault <path>"

  local sprint_dir="${HARNESS_DIR}/sprints"
  local out_dir="${vault}/_raw/solar-harness"
  local out_file="${out_dir}/${sid}.md"
  local ts
  ts="$(iso8601)"

  mkdir -p "$out_dir"

  # Collect sprint source files (best-effort, missing files are skipped)
  local contract_f="${sprint_dir}/${sid}.contract.md"
  local plan_f="${sprint_dir}/${sid}.plan.md"
  local status_f="${sprint_dir}/${sid}.status.json"
  local events_f="${sprint_dir}/${sid}.events.jsonl"

  # Find handoff files: <sid>.handoff.md or handoffs/*.handoff.md
  local handoff_files=()
  [[ -f "${sprint_dir}/${sid}.handoff.md" ]] && handoff_files+=("${sprint_dir}/${sid}.handoff.md")
  local h
  for h in "${sprint_dir}/${sid}"*.handoff.md; do
    [[ -f "$h" ]] && handoff_files+=("$h")
  done

  local redacted_flag="true"
  [[ "$redact_mode" == "full" ]] && redacted_flag="false"

  # Build the export file
  {
    printf -- '---\n'
    printf 'source: solar-harness\n'
    printf 'sprint_id: %s\n' "$sid"
    printf 'exported_at: %s\n' "$ts"
    printf 'redacted: %s\n' "$redacted_flag"
    printf 'visibility: internal\n'
    printf -- '---\n\n'
    printf '# Sprint Export: %s\n\n' "$sid"

    # Contract summary
    if [[ -f "$contract_f" ]]; then
      printf '## Contract Summary\n\n'
      head -60 "$contract_f" | grep -v '^<!--' || true
      printf '\n'
    fi

    # Plan summary
    if [[ -f "$plan_f" ]]; then
      printf '## Plan Summary\n\n'
      head -80 "$plan_f" | grep -v '^<!--' || true
      printf '\n'
    fi

    # Handoff summary (first 40 lines each, up to 2 files)
    local hcount=0
    local hf
    for hf in "${handoff_files[@]}"; do
      [[ $hcount -ge 2 ]] && break
      printf '## Handoff: %s\n\n' "$(basename "$hf")"
      head -40 "$hf" || true
      printf '\n'
      hcount=$((hcount + 1))
    done

    # Status
    if [[ -f "$status_f" ]]; then
      printf '## Status\n\n```json\n'
      cat "$status_f"
      printf '\n```\n\n'
    fi

    # Events summary
    if [[ -f "$events_f" ]]; then
      local event_count
      event_count=$(wc -l < "$events_f" | tr -d ' ')
      printf '## Events (%s total)\n\n' "$event_count"

      # Emit up to 20 structured events (type+summary only, not full payload)
      python3 - "$events_f" "$redact_mode" <<'PYEOF'
import json, sys, re
events_f, mode = sys.argv[1:]
REDACT_PATTERNS = [
    (re.compile(r'(token|key|secret|password|api[_\-]?key)\s*[=:]\s*\S+', re.I), '<REDACTED>'),
    (re.compile(r'Bearer\s+\S+', re.I), 'Bearer <REDACTED>'),
    (re.compile(r'Basic\s+[A-Za-z0-9+/=]{20,}', re.I), 'Basic <REDACTED>'),
    (re.compile(r'\b[0-9a-fA-F]{32,}\b'), '<REDACTED>'),
    (re.compile(r'\b[A-Za-z0-9+/]{43,}={0,2}\b'), '<REDACTED>'),
]

def redact(text):
    if not isinstance(text, str):
        return text
    for pat, repl in REDACT_PATTERNS:
        text = pat.sub(repl, text)
    return text

lines = []
try:
    with open(events_f) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except Exception:
                pass
except Exception:
    pass

shown = 0
for ev in lines[-20:]:
    ev_type = ev.get('type') or ev.get('event', 'unknown')
    ts_val  = ev.get('ts') or ev.get('timestamp', '')
    summary = str(ev.get('summary') or ev.get('message') or ev.get('data', ''))
    if mode == 'redact':
        summary = redact(summary)
    # Truncate long stdout/stderr
    if len(summary) > 200:
        summary = summary[:200] + ' [...truncated, see live log]'
    print(f'- `{ts_val}` [{ev_type}] {summary}')
    shown += 1

if not shown:
    print('(no structured events)')
PYEOF
      printf '\n'
    fi

  } > "$out_file"

  # Redact credential patterns in the full output file
  if [[ "$redact_mode" == "redact" ]]; then
    python3 - "$out_file" <<'PYEOF'
import re, sys
f = sys.argv[1]
with open(f) as fh:
    text = fh.read()
patterns = [
    (re.compile(r'(token|key|secret|password|api[_\-]?key)\s*[=:]\s*\S+', re.I), r'\1=<REDACTED>'),
    (re.compile(r'Authorization:\s*Bearer\s+\S+', re.I), 'Authorization: Bearer <REDACTED>'),
    (re.compile(r'Authorization:\s*Basic\s+\S+', re.I), 'Authorization: Basic <REDACTED>'),
]
for pat, repl in patterns:
    text = pat.sub(repl, text)
with open(f, 'w') as fh:
    fh.write(text)
PYEOF
  fi

  # Update state
  update_state_field "last_exported_sprint" "$sid"

  log_info "Exported sprint $sid → $out_file"
  printf '%s\n' "$out_file"
}

# ─── cmd_update ──────────────────────────────────────────────────────────────
# S3 — generate agent-readable wiki-update instruction file
cmd_update() {
  local project_path="" mode="append"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --project) shift; project_path="$1" ;;
      --mode)    shift; mode="$1" ;;
      *)         die "Unknown update arg: $1" ;;
    esac
    shift
  done

  load_config
  local vault="${OBSIDIAN_VAULT_PATH:-}"
  [[ -z "$vault" ]] && die "Vault not configured. Run: solar-harness wiki install --vault <path>"

  local ts dispatch_dir="${vault}/_raw/solar-harness/.dispatch"
  ts="$(iso8601)"
  mkdir -p "$dispatch_dir"
  local out_file="${dispatch_dir}/wiki-update-${ts}.md"

  {
    printf -- '---\n'
    printf 'type: wiki-update\n'
    printf 'generated_at: %s\n' "$ts"
    printf 'mode: %s\n' "$mode"
    printf 'project: %s\n' "${project_path:-(default vault)}"
    printf -- '---\n\n'
    printf '# Wiki Update Instruction\n\n'
    printf 'Run the wiki-update skill with the following parameters:\n\n'
    printf '```\nskill: wiki-update\n'
    printf 'vault: %s\n' "$vault"
    printf 'mode: %s\n' "$mode"
    [[ -n "$project_path" ]] && printf 'project: %s\n' "$project_path"
    printf '```\n\n'
    printf 'Invoke via:\n\n'
    printf '```bash\nclaude --skill wiki-update < %s\n```\n' "$out_file"
  } > "$out_file"

  log_info "Wiki update instruction written: $out_file"
  printf '%s\n' "$out_file"
}

# ─── cmd_query ───────────────────────────────────────────────────────────────
# S3 — generate agent-readable wiki-query instruction file; refuses empty query
cmd_query() {
  local question="" quick=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --quick) quick=1 ;;
      -*)      die "Unknown query arg: $1" ;;
      *)       question="$1" ;;
    esac
    shift
  done

  if [[ -z "$question" ]]; then
    log_error "REFUSE: empty query string"
    exit 2
  fi

  load_config
  local vault="${OBSIDIAN_VAULT_PATH:-}"
  [[ -z "$vault" ]] && die "Vault not configured. Run: solar-harness wiki install --vault <path>"

  if [[ "$quick" == "1" ]]; then
    local bridge="${HARNESS_DIR}/integrations/obsidian-wiki-bridge.sh"
    if [[ -f "$bridge" ]]; then
      OBSIDIAN_VAULT_PATH="$vault" /bin/bash "$bridge" query "$question" --quick
      return $?
    fi
  fi

  local ts dispatch_dir="${vault}/_raw/solar-harness/.dispatch"
  ts="$(iso8601)"
  mkdir -p "$dispatch_dir"
  local out_file="${dispatch_dir}/wiki-query-${ts}.md"

  {
    printf -- '---\n'
    printf 'type: wiki-query\n'
    printf 'generated_at: %s\n' "$ts"
    [[ "$quick" == "1" ]] && printf 'mode: quick\n' || printf 'mode: full\n'
    printf -- '---\n\n'
    printf '# Wiki Query Instruction\n\n'
    printf 'Question:\n\n> %s\n\n' "$question"
    printf 'Run the wiki-query skill:\n\n'
    printf '```\nskill: wiki-query\n'
    printf 'vault: %s\n' "$vault"
    [[ "$quick" == "1" ]] && printf 'mode: quick\n'
    printf 'question: %s\n' "$question"
    printf '```\n\n'
    printf 'Invoke via:\n\n'
    printf '```bash\nclaude --skill wiki-query < %s\n```\n' "$out_file"
  } > "$out_file"

  log_info "Wiki query instruction written: $out_file"
  printf '%s\n' "$out_file"
}

# ─── main dispatcher ─────────────────────────────────────────────────────────
wiki_main() {
  local subcmd="${1:-help}"
  shift || true
  case "$subcmd" in
    install)       cmd_install       "$@" ;;
    status)        cmd_status        "$@" ;;
    export-sprint) cmd_export_sprint "$@" ;;
    update)        cmd_update        "$@" ;;
    query)         cmd_query         "$@" ;;
    help|--help|-h)
      printf 'Usage: solar-harness wiki <subcommand> [args]\n'
      printf 'Subcommands:\n'
      printf '  install --vault <path> [--repo <path>] [--refresh]\n'
      printf '  status [--json]\n'
      printf '  export-sprint <sid> [--redact|--full]\n'
      printf '  update [--project <path>] [--mode append|full]\n'
      printf '  query "<question>" [--quick]\n'
      ;;
    *)
      die "Unknown wiki subcommand: $subcmd (run 'solar-harness wiki help')"
      ;;
  esac
}

# ── cmd_wiki_* aliases (solar-harness.sh router compatibility) ───────────────
cmd_wiki_install()       { cmd_install       "$@"; }
cmd_wiki_status()        { cmd_status        "$@"; }
cmd_wiki_export_sprint() { cmd_export_sprint "$@"; }

# Allow direct invocation: bash obsidian-wiki.sh <subcmd> [args]
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  wiki_main "$@"
fi
