#!/usr/bin/env bash

COMPONENT_NAME="mempalace"
COMPONENT_DESC="Semantic memory MCP server (off by default)"
COMPONENT_DEFAULT="off"
COMPONENT_PLATFORMS="darwin linux wsl"
COMPONENT_REQUIRES_BINS="python3"
COMPONENT_REQUIRES_COMPONENTS="kernel"
COMPONENT_PYTHON_REQS="requirements/mempalace.txt"
COMPONENT_CONFIG_VARS="VAULT_PATH:required:Path to knowledge vault"
# First REAL (non-synthetic) use of mcp-register: the MCP entrypoint is
# mempalace_mcp_server.py (NOT server.py).
COMPONENT_MCP_SERVERS="mempalace:$SOLAR_HOME/venv/bin/python $SOLAR_HOME/mempalace/mempalace_mcp_server.py"

component_install() {
    copy_payload "$SOURCE_DIR/mempalace" "$SOLAR_HOME/mempalace"
    dry_run_note "render mempalace config.yaml, create venv, install python requirements" && return 0
    # config.yaml is read by mempalace_init.py (CONFIG_FILE); VAULT_PATH is
    # templated here, resolved by the required-config-var mechanism.
    render_template "$SOURCE_DIR/templates/config/mempalace.config.yaml.template" \
        "$SOLAR_HOME/mempalace/config.yaml"
    if [ ! -d "$SOLAR_HOME/venv" ]; then
        python3 -m venv "$SOLAR_HOME/venv" || die "mempalace: failed to create venv at $SOLAR_HOME/venv"
    fi
    pip_install_reqs "$SOLAR_HOME/venv" "$SOURCE_DIR/$COMPONENT_PYTHON_REQS"
    return 0
}

component_verify() {
    [ -f "$SOLAR_HOME/mempalace/mempalace_mcp_server.py" ] \
        || die "mempalace verify failed: mempalace_mcp_server.py missing"
    [ -f "$SOLAR_HOME/mempalace/config.yaml" ] \
        || die "mempalace verify failed: config.yaml missing"
    if grep -q '{{' "$SOLAR_HOME/mempalace/config.yaml"; then
        die "mempalace verify failed: config.yaml has unresolved template vars"
    fi
    [ -x "$SOLAR_HOME/venv/bin/python" ] \
        || die "mempalace verify failed: venv python missing"
}
