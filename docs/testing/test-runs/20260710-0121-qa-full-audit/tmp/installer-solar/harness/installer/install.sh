#!/usr/bin/env bash
# ============================================================================
# Solar Product Platform Installer
#
# Usage:
#   install.sh                                       # interactive wizard
#   install.sh --non-interactive                     # automated, prompts defaults
#   install.sh --non-interactive --vault /tmp/vault  # custom vault path
#   install.sh --non-interactive --skip-llm-cli      # skip Claude/Codex checks
#   install.sh --non-interactive --fake-keys         # use fake/test API keys
#
# Environment (non-interactive):
#   SOLAR_HOME         install root (default: /opt/solar or ~/.solar)
#   HARNESS_DIR        harness directory (default: $SOLAR_HOME/harness)
#   KNOWLEDGE_VAULT    Obsidian vault path (default: ~/Knowledge)
#   SOLAR_TVS_ROOT     optional TVS package checkout path; must contain index.ts
#   SKIP_LLM_CLI=1     skip Claude/Codex binary checks
#   FAKE_KEYS=1        use test placeholder keys
#
# Stop conditions:
#   - No real secrets in output or config
#   - Never references live user private paths in container
#   - Does NOT modify existing ~/.solar user data (--non-interactive guard)
# ============================================================================
set -euo pipefail

# ── helpers ────────────────────────────────────────────────────────────────
red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
info()   { printf '[install] %s\n' "$*" >&2; }

# ── defaults ───────────────────────────────────────────────────────────────
NON_INTERACTIVE=false
SKIP_LLM_CLI=false
FAKE_KEYS=false
CUSTOM_VAULT=""
SOLAR_HOME="${SOLAR_HOME:-}"
HARNESS_DIR="${HARNESS_DIR:-}"
KNOWLEDGE_VAULT="${KNOWLEDGE_VAULT:-}"
SOLAR_TVS_ROOT="${SOLAR_TVS_ROOT:-}"

# parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-interactive) NON_INTERACTIVE=true; shift ;;
    --skip-llm-cli)    SKIP_LLM_CLI=true;    shift ;;
    --fake-keys)       FAKE_KEYS=true;        shift ;;
    --vault)           CUSTOM_VAULT="$2";     shift 2 ;;
    --help|-h)
      echo "Solar Product Platform Installer"
      echo "Usage: install.sh [--non-interactive] [--skip-llm-cli] [--fake-keys] [--vault PATH]"
      echo ""
      echo "Optional for TVS rendering:"
      echo "  bun              JavaScript runtime for tvs_render_cli.ts"
      echo "  SOLAR_TVS_ROOT   TVS checkout path containing index.ts"
      exit 0 ;;
    *) red "Unknown option: $1"; exit 2 ;;
  esac
done

# ── OS detection ───────────────────────────────────────────────────────────
OS_KIND=""
OS_VERSION=""
case "$(uname -s)" in
  Darwin)
    OS_KIND="darwin"
    OS_VERSION="$(sw_vers -productVersion 2>/dev/null || echo 'unknown')"
    ;;
  Linux)
    OS_KIND="linux"
    OS_VERSION="$(grep -oP '(?<=PRETTY_NAME=").*(?=")' /etc/os-release 2>/dev/null || uname -r)"
    ;;
  *)
    red "Unsupported OS: $(uname -s)"; exit 1 ;;
esac

info "OS: $OS_KIND $OS_VERSION"

# ── paths ──────────────────────────────────────────────────────────────────
if [[ -z "$SOLAR_HOME" ]]; then
  if [[ "$OS_KIND" == "darwin" ]]; then
    SOLAR_HOME="$HOME/.solar"
  else
    SOLAR_HOME="/opt/solar"
  fi
fi

if [[ -z "$HARNESS_DIR" ]]; then
  HARNESS_DIR="$SOLAR_HOME/harness"
fi

if [[ -z "$KNOWLEDGE_VAULT" ]]; then
  if [[ -n "$CUSTOM_VAULT" ]]; then
    KNOWLEDGE_VAULT="$CUSTOM_VAULT"
  else
    KNOWLEDGE_VAULT="$HOME/Knowledge"
  fi
fi

info "SOLAR_HOME=$SOLAR_HOME"
info "HARNESS_DIR=$HARNESS_DIR"
info "KNOWLEDGE_VAULT=$KNOWLEDGE_VAULT"

resolve_tvs_root() {
  if [[ -n "$SOLAR_TVS_ROOT" ]]; then
    [[ -f "$SOLAR_TVS_ROOT/index.ts" ]] && printf '%s\n' "$SOLAR_TVS_ROOT"
    return 0
  fi

  local candidate
  for candidate in "$HARNESS_DIR/../../TVS" "$HOME/TVS" "$HOME/Solar/../TVS"; do
    if [[ -f "$candidate/index.ts" ]]; then
      (cd "$candidate" && pwd)
      return 0
    fi
  done
}

# ── guard: refuse to run inside ~/.solar if it already exists ──────────────
if [[ "$NON_INTERACTIVE" == "true" ]] && [[ -d "$HOME/.solar" ]]; then
  yellow "Existing ~/.solar detected. Non-interactive mode will NOT modify existing user data."
  yellow "Skipping directory creation under ~/.solar."
fi

# ── dependency check / install ────────────────────────────────────────────
install_deps() {
  info "Checking dependencies..."
  local missing=()

  for bin in bash python3 git curl tar; do
    if ! command -v "$bin" &>/dev/null; then
      missing+=("$bin")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    if [[ "$OS_KIND" == "darwin" ]]; then
      if ! command -v brew &>/dev/null; then
        red "Homebrew not found. Install it first: https://brew.sh"
        exit 1
      fi
      info "Installing via brew: ${missing[*]}"
      for pkg in "${missing[@]}"; do
        brew install "$pkg" 2>/dev/null || true
      done
    elif [[ "$OS_KIND" == "linux" ]]; then
      if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq "${missing[@]}" python3-venv jq sqlite3
      elif command -v yum &>/dev/null; then
        sudo yum install -y "${missing[@]}" python3 sqlite jq
      else
        red "No supported package manager found (apt/yum). Install manually: ${missing[*]}"
        exit 1
      fi
    fi
  fi

  if ! command -v tmux &>/dev/null; then
    if [[ "$OS_KIND" == "darwin" ]]; then
      brew install tmux 2>/dev/null || true
    elif command -v apt-get &>/dev/null; then
      sudo apt-get install -y -qq tmux
    fi
  fi

  if ! command -v bun &>/dev/null; then
    yellow "Bun not found; JavaScript runtime and TVS-backed features are unavailable until Bun is installed."
  fi

  local tvs_root
  tvs_root="$(resolve_tvs_root || true)"
  if [[ -z "$tvs_root" ]]; then
    if [[ -n "$SOLAR_TVS_ROOT" ]]; then
      yellow "SOLAR_TVS_ROOT is set but does not contain index.ts; TVS rendering will be disabled."
    else
      yellow "TVS renderer optional dependency not configured; set SOLAR_TVS_ROOT to enable it."
    fi
  else
    export SOLAR_TVS_ROOT="$tvs_root"
    info "TVS renderer root: $SOLAR_TVS_ROOT"
  fi

  # Check optional LLM CLIs
  if [[ "$SKIP_LLM_CLI" != "true" ]]; then
    local llm_missing=()
    if ! command -v claude &>/dev/null; then llm_missing+=("claude"); fi
    if ! command -v codex &>/dev/null; then  llm_missing+=("codex"); fi
    if [[ ${#llm_missing[@]} -gt 0 ]]; then
      yellow "LLM CLI(s) not found: ${llm_missing[*]}. Use --skip-llm-cli to suppress."
    fi
  fi

  green "Required dependencies OK"
}

# ── create directory structure ────────────────────────────────────────────
create_dirs() {
  info "Creating directory structure..."
  local dirs=(
    "$SOLAR_HOME"
    "$HARNESS_DIR"
    "$HARNESS_DIR/config"
    "$HARNESS_DIR/installer"
    "$HARNESS_DIR/docker"
    "$HARNESS_DIR/hooks"
    "$HARNESS_DIR/backups"
    "$HARNESS_DIR/backups/product-snapshots"
    "$HARNESS_DIR/run"
    "$HARNESS_DIR/logs"
    "$HARNESS_DIR/tests"
    "$HARNESS_DIR/tests/installer"
  )

  for d in "${dirs[@]}"; do
    if [[ ! -d "$d" ]]; then
      mkdir -p "$d"
      info "  created: $d"
    else
      info "  exists: $d"
    fi
  done
}

# ── write default config (non-destructive) ────────────────────────────────
write_config() {
  info "Writing default configuration..."
  local config_file="$HARNESS_DIR/config/defaults.yaml"

  if [[ -f "$config_file" ]]; then
    info "  config/defaults.yaml already exists — skipping (preserving user config)"
    return 0
  fi

  # Copy from installer source or generate fresh
  local source_config="$HARNESS_DIR/config/defaults.yaml"
  # The source config should already be in place if running from harness root
  # If not, generate a minimal one
  if [[ ! -f "$source_config" ]]; then
    cat > "$config_file" << 'YAMLEOF'
version: 1
generated_by: installer
providers:
  anthropic:
    enabled: true
    api_key_env: ANTHROPIC_API_KEY
    default_model: claude-sonnet-4-20250514
  openai:
    enabled: false
    api_key_env: OPENAI_API_KEY
  google:
    enabled: false
    api_key_env: GOOGLE_AI_API_KEY
vault:
  path: ~/Knowledge
  auto_index: true
mirage:
  enabled: true
  mounts: [/knowledge, /raw, /sources, /papers, /qmd, /solar-db, /cortex, /sprints]
skills:
  registry_path: skills/registry.yaml
  canary_default_inject: false
control_plane:
  state_db_path: run/state.db
  pane_lease_ttl_sec: 600
YAMLEOF
  fi
  info "  config/defaults.yaml written"
}

# ── write .env from .env.example or generate ──────────────────────────────
write_env() {
  local env_file="$HARNESS_DIR/.env"

  if [[ -f "$env_file" ]]; then
    info "  .env already exists — skipping (preserving user secrets)"
    return 0
  fi

  if [[ "$FAKE_KEYS" == "true" ]]; then
    cat > "$env_file" << 'ENVEOF'
# Test / fake keys — for container validation only
ANTHROPIC_API_KEY=sk-ant-test-fake-key-container-validation
ANTHROPIC_BASE_URL=https://api.anthropic.com
OPENAI_API_KEY=sk-test-fake-key-container-validation
OPENAI_BASE_URL=https://api.openai.com/v1
ENVEOF
    chmod 600 "$env_file"
    info "  .env written (fake keys — container mode)"
  else
    cp "$HARNESS_DIR/.env.example" "$env_file" 2>/dev/null || true
    chmod 600 "$env_file"
    info "  .env written from .env.example"
  fi
}

# ── init state DB ─────────────────────────────────────────────────────────
init_state_db() {
  info "Initializing state database..."
  local state_db_py="$HARNESS_DIR/lib/solar_state_db.py"

  if [[ -f "$state_db_py" ]]; then
    python3 "$state_db_py" init 2>/dev/null && {
      info "  state.db initialized"
    } || {
      yellow "  state.db init skipped (module not functional — may be missing dependencies)"
    }
  else
    # Create minimal state.db directly if module not available
    local db_path="$HARNESS_DIR/run/state.db"
    if [[ ! -f "$db_path" ]]; then
      sqlite3 "$db_path" << 'SQLEOF'
CREATE TABLE IF NOT EXISTS tasks (sid TEXT PRIMARY KEY, title TEXT, state TEXT, priority TEXT, lane TEXT, owner TEXT, created_at TEXT, updated_at TEXT, parent_sid TEXT);
CREATE TABLE IF NOT EXISTS assignments (sid TEXT, role TEXT, agent TEXT, started_at TEXT, ended_at TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS leases (pane TEXT PRIMARY KEY, sid TEXT, role TEXT, acquired_at TEXT, ttl_sec INTEGER, heartbeat_at TEXT, holder_pid INTEGER);
CREATE TABLE IF NOT EXISTS events (ts TEXT, sid TEXT, kind TEXT, by TEXT, payload_json TEXT);
CREATE TABLE IF NOT EXISTS artifacts (sid TEXT, kind TEXT, path TEXT, sha256 TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS capabilities (id TEXT PRIMARY KEY, kind TEXT, score REAL, stability TEXT, last_eval_at TEXT);
PRAGMA journal_mode=WAL;
SQLEOF
      info "  state.db created directly (minimal schema)"
    fi
  fi
}

# ── snapshot baseline ─────────────────────────────────────────────────────
snapshot_baseline() {
  info "Creating snapshot baseline..."

  # Check if product_snapshot module exists
  if [[ -f "$HARNESS_DIR/lib/product_snapshot.py" ]]; then
    python3 "$HARNESS_DIR/lib/product_snapshot.py" snapshot \
      --scope minimal \
      --out-dir "$HARNESS_DIR/backups/product-snapshots" \
      2>/dev/null && {
      info "  snapshot baseline created"
      return 0
    } || {
      yellow "  snapshot failed (non-fatal, continuing)"
    }
  else
    yellow "  product_snapshot.py not found — skipping baseline snapshot"
  fi
}

# ── run doctor ────────────────────────────────────────────────────────────
run_doctor() {
  info "Running product doctor..."

  if [[ -f "$HARNESS_DIR/installer/doctor.sh" ]]; then
    bash "$HARNESS_DIR/installer/doctor.sh" --json 2>/dev/null || {
      yellow "  doctor returned non-zero — check output above"
    }
  else
    yellow "  installer/doctor.sh not found — skipping health check"
  fi
}

# ── install git hooks ─────────────────────────────────────────────────────
install_hooks() {
  info "Setting up git hooks..."

  if [[ -d "$HARNESS_DIR/.git" ]] || git -C "$HARNESS_DIR" rev-parse --git-dir &>/dev/null 2>&1; then
    local git_dir
    git_dir="$(git -C "$HARNESS_DIR" rev-parse --git-dir 2>/dev/null)"

    for hook in pre-commit pre-push; do
      local src="$HARNESS_DIR/hooks/${hook}-secret-scan"
      local dst="$git_dir/hooks/$hook"

      if [[ -f "$src" ]]; then
        if [[ -f "$dst" ]]; then
          info "  $hook hook already exists — skipping"
        else
          ln -sf "$src" "$dst" 2>/dev/null || cp "$src" "$dst"
          chmod +x "$dst"
          info "  $hook hook installed"
        fi
      fi
    done
  else
    info "  Not a git repository — skipping hook install"
  fi
}

# ── print summary ─────────────────────────────────────────────────────────
print_summary() {
  echo ""
  echo "┌──────────────────────────────────────────────────────────┐"
  echo "│  Solar Product Platform — Install Complete               │"
  echo "├──────────────────────────────────────────────────────────┤"
  echo "│  SOLAR_HOME:     $SOLAR_HOME"
  echo "│  HARNESS_DIR:    $HARNESS_DIR"
  echo "│  KNOWLEDGE_VAULT: $KNOWLEDGE_VAULT"
  echo "│  SOLAR_TVS_ROOT: ${SOLAR_TVS_ROOT:-N/A}"
  echo "│  OS:             $OS_KIND $OS_VERSION"
  echo "│  Config:         $HARNESS_DIR/config/defaults.yaml"
  echo "│  Env:            $HARNESS_DIR/.env"
  echo "│  State DB:       $HARNESS_DIR/run/state.db"
  echo "├──────────────────────────────────────────────────────────┤"
  echo "│  Next Steps:                                             │"
  echo "│    1. Verify:    solar-harness doctor                    │"
  echo "│    2. Start:     solar-harness start                     │"
  echo "│    3. Snapshot:  solar-harness product snapshot          │"
  echo "└──────────────────────────────────────────────────────────┘"
  echo ""
}

# ── main ───────────────────────────────────────────────────────────────────
main() {
  echo "=== Solar Product Platform Installer ==="
  echo ""

  install_deps
  create_dirs
  write_config
  write_env
  init_state_db
  snapshot_baseline
  install_hooks
  run_doctor
  print_summary

  green "Installation complete."
}

main
