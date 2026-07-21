#!/usr/bin/env bash

# mcp-register.sh — register each selected component's MCP servers via the
# sanctioned `claude mcp add ... --scope user` CLI (never hand-edits
# ~/.mcp.json). Registered server names are recorded in
# $SOLAR_HOME/registered-mcp.txt so uninstall can `claude mcp remove` them.
#
# Component manifest declares servers in COMPONENT_MCP_SERVERS, one per line:
#   COMPONENT_MCP_SERVERS="mempalace:$SOLAR_HOME/venv/bin/python $SOLAR_HOME/mempalace/server.py"
# i.e. "<name>:<command with args>".

mcp_register() {
    [ "${NO_MCP:-false}" = "true" ] && { info "skipping MCP registration (--no-mcp)"; return 0; }
    if [ "${SKIP_LLM_CLI:-false}" = "true" ] || ! command -v claude >/dev/null 2>&1; then
        info "claude CLI unavailable; skipping MCP registration"
        return 0
    fi

    record="$SOLAR_HOME/registered-mcp.txt"
    for name in $SELECTED_COMPONENTS; do
        load_component "$name"
        [ -n "${COMPONENT_MCP_SERVERS:-}" ] || continue
        printf '%s\n' "$COMPONENT_MCP_SERVERS" | while IFS= read -r entry; do
            entry="$(printf '%s' "$entry" | awk '{$1=$1; print}')"
            [ -n "$entry" ] || continue
            server_name="${entry%%:*}"
            server_cmd="${entry#*:}"
            [ -n "$server_name" ] && [ -n "$server_cmd" ] || continue
            dry_run_note "claude mcp add $server_name" && continue
            if claude mcp add "$server_name" --scope user -- $server_cmd >/dev/null 2>&1; then
                info "registered MCP server: $server_name"
                printf '%s\n' "$server_name" >> "$record"
            else
                yellow "failed to register MCP server: $server_name"
            fi
        done
    done
}
