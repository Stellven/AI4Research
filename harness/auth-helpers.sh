#!/usr/bin/env bash
# Solar auth helpers — subscription-first auth for the dashboard.
#
#   auth-helpers.sh status                      -> JSON: {codex,claude,glm} auth state (no token values)
#   auth-helpers.sh reuse-host-creds <provider> -> on WSL, copy existing Windows-side creds in (zero-step)
#   auth-helpers.sh open-url <url>              -> open a URL on the host (cmd.exe / open / xdg-open)
#   auth-helpers.sh login <provider>           -> codex login --device-auth | claude setup-token
#
# Detection is file-presence based (the CLIs own their creds). This NEVER prints or logs a
# token value; secrets stay in their CLI-native files / ~/.solar/secrets (0600).
set -u

_is_wsl() { grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; }
_os() {
  case "$(uname -s)" in
    Darwin) echo macos ;;
    Linux)  _is_wsl && echo wsl || echo linux ;;
    *)      echo other ;;
  esac
}

HOME_DIR="${HOME}"
SECRETS_ENV="${SOLAR_SECRETS_ENV:-$HOME_DIR/.solar/secrets/solar-user-secrets.env}"

_codex_state() {
  if [ -s "$HOME_DIR/.codex/auth.json" ]; then echo ok
  elif command -v codex >/dev/null 2>&1; then echo unauth
  else echo missing-cli; fi
}
_claude_state() {
  if [ -s "$HOME_DIR/.claude/.credentials.json" ] || [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then echo ok
  elif command -v claude >/dev/null 2>&1; then echo unauth
  else echo missing-cli; fi
}
_glm_state() {
  if [ -f "$SECRETS_ENV" ] && grep -q '^ZHIPU_AUTH_TOKEN=' "$SECRETS_ENV" 2>/dev/null; then echo ok
  else echo missing-key; fi
}
_b() { [ "$1" ] && echo true || echo false; }

cmd_status() {
  local codex claude glm
  codex="$(_codex_state)"; claude="$(_claude_state)"; glm="$(_glm_state)"
  printf '{"ok":true,"codex":"%s","claude":"%s","glm":"%s","detail":{"codex_auth_json":%s,"claude_credentials":%s,"claude_oauth_env":%s},"source":"auth-helpers"}\n' \
    "$codex" "$claude" "$glm" \
    "$(_b "$([ -s "$HOME_DIR/.codex/auth.json" ] && echo x)")" \
    "$(_b "$([ -s "$HOME_DIR/.claude/.credentials.json" ] && echo x)")" \
    "$(_b "${CLAUDE_CODE_OAUTH_TOKEN:-}")"
}

cmd_open_url() {
  local url="${1:-}"
  [ -n "$url" ] || { echo '{"ok":false,"error":"no url"}'; return 64; }
  case "$(_os)" in
    macos) open "$url" >/dev/null 2>&1 & ;;
    wsl)   cmd.exe /c start "" "$url" >/dev/null 2>&1 & ;;
    *)     xdg-open "$url" >/dev/null 2>&1 & ;;
  esac
  echo '{"ok":true,"opened":true}'
}

# Zero-step path: on WSL, reuse creds the user already has on the Windows side. Consent is the
# UI's job; this only copies when the runtime-home target is ABSENT (never overwrites).
cmd_reuse_host_creds() {
  local provider="${1:-}" copied=false wu base
  if [ "$(_os)" = "wsl" ]; then
    for wu in /mnt/c/Users/*/; do
      base="$(basename "$wu")"
      case "$base" in Public|Default|"Default User"|All*) continue ;; esac
      if [ "$provider" = "codex" ] && [ -s "${wu}.codex/auth.json" ] && [ ! -s "$HOME_DIR/.codex/auth.json" ]; then
        mkdir -p "$HOME_DIR/.codex"; cp "${wu}.codex/auth.json" "$HOME_DIR/.codex/auth.json"
        chmod 600 "$HOME_DIR/.codex/auth.json"; copied=true; break
      fi
      if [ "$provider" = "claude" ] && [ -s "${wu}.claude/.credentials.json" ] && [ ! -s "$HOME_DIR/.claude/.credentials.json" ]; then
        mkdir -p "$HOME_DIR/.claude"; cp "${wu}.claude/.credentials.json" "$HOME_DIR/.claude/.credentials.json"
        chmod 600 "$HOME_DIR/.claude/.credentials.json"; copied=true; break
      fi
    done
  fi
  printf '{"ok":true,"provider":"%s","reused":%s}\n' "$provider" "$copied"
}

cmd_login() {
  case "${1:-}" in
    codex)  exec codex login --device-auth ;;
    claude) exec claude setup-token ;;
    *) echo "unknown provider: ${1:-}" >&2; return 64 ;;
  esac
}

case "${1:-}" in
  status)           cmd_status ;;
  open-url)         shift; cmd_open_url "$@" ;;
  reuse-host-creds) shift; cmd_reuse_host_creds "$@" ;;
  login)            shift; cmd_login "$@" ;;
  *) echo "usage: auth-helpers.sh {status|open-url <url>|reuse-host-creds <provider>|login <provider>}" >&2; exit 64 ;;
esac
