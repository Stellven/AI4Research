#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

LABEL="${SOLAR_QUOTA_REFRESH_LABEL:-com.solar.harness-quota-refresh}"
INTERVAL="${SOLAR_QUOTA_REFRESH_INTERVAL:-300}"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${HARNESS_DIR}/logs"
STDOUT_LOG="${LOG_DIR}/quota-refresh.out.log"
STDERR_LOG="${LOG_DIR}/quota-refresh.err.log"

launchd_domain() {
  printf 'gui/%s\n' "$(id -u)"
}

usage() {
  cat <<EOF
Solar Harness quota/rate refresh daemon

Usage:
  $0 install [--interval SECONDS]
  $0 uninstall
  $0 status
  $0 run-once
EOF
}

parse_interval_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --interval)
        shift
        INTERVAL="${1:-}"
        ;;
      --interval=*)
        INTERVAL="${1#--interval=}"
        ;;
      *)
        echo "unknown argument: $1" >&2
        return 2
        ;;
    esac
    shift || true
  done
  if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]] || [[ "$INTERVAL" -lt 60 ]]; then
    echo "interval must be an integer >= 60 seconds" >&2
    return 2
  fi
}

write_plist() {
  local bash_path="/bin/bash"
  [[ -x /opt/homebrew/bin/bash ]] && bash_path="/opt/homebrew/bin/bash"
  mkdir -p "$(dirname "$PLIST_PATH")" "$LOG_DIR"
  cat > "$PLIST_PATH" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${bash_path}</string>
    <string>${HARNESS_DIR}/scripts/quota-refresh-daemon.sh</string>
    <string>run-once</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>${INTERVAL}</integer>
  <key>WorkingDirectory</key>
  <string>${HARNESS_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:${HOME}/.solar/bin:${HOME}/n/bin:${HOME}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PYTHONIOENCODING</key>
    <string>utf-8</string>
    <key>HARNESS_DIR</key>
    <string>${HARNESS_DIR}</string>
  </dict>
  <key>StandardOutPath</key>
  <string>${STDOUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${STDERR_LOG}</string>
</dict>
</plist>
PLIST_EOF
}

run_once() {
  mkdir -p "$LOG_DIR"
  printf '[%s] quota-refresh start\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "${HARNESS_DIR}/solar-harness.sh" pm-fleet quota-refresh --json --apply
  printf '[%s] quota-refresh end\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

install_job() {
  parse_interval_args "$@"
  local domain
  domain="$(launchd_domain)"
  write_plist
  if command -v launchctl >/dev/null 2>&1; then
    launchctl bootout "$domain" "$PLIST_PATH" 2>/dev/null || launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl bootstrap "$domain" "$PLIST_PATH" 2>/dev/null || launchctl load "$PLIST_PATH"
    launchctl kickstart -k "${domain}/${LABEL}" 2>/dev/null || true
  fi
  echo "ok installed ${LABEL}"
  echo "plist=${PLIST_PATH}"
  echo "interval=${INTERVAL}s"
  echo "stdout=${STDOUT_LOG}"
  echo "stderr=${STDERR_LOG}"
}

uninstall_job() {
  local domain
  domain="$(launchd_domain)"
  if command -v launchctl >/dev/null 2>&1; then
    launchctl bootout "$domain" "$PLIST_PATH" 2>/dev/null || launchctl unload "$PLIST_PATH" 2>/dev/null || true
  fi
  rm -f "$PLIST_PATH"
  echo "ok uninstalled ${LABEL}"
}

status_job() {
  local domain
  domain="$(launchd_domain)"
  echo "label=${LABEL}"
  echo "plist=${PLIST_PATH}"
  echo "interval=${INTERVAL}s"
  [[ -f "$PLIST_PATH" ]] && echo "plist_state=present" || echo "plist_state=missing"
  if command -v launchctl >/dev/null 2>&1 && launchctl print "${domain}/${LABEL}" >/dev/null 2>&1; then
    echo "launchd_state=loaded"
  else
    echo "launchd_state=not_loaded"
  fi
  echo "stdout=${STDOUT_LOG}"
  echo "stderr=${STDERR_LOG}"
}

case "${1:-help}" in
  install)
    shift
    install_job "$@"
    ;;
  uninstall)
    uninstall_job
    ;;
  status)
    status_job
    ;;
  run-once)
    run_once
    ;;
  help|--help|-h|"")
    usage
    ;;
  *)
    echo "unknown subcommand: $1" >&2
    usage >&2
    exit 2
    ;;
esac
