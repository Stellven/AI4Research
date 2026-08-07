#!/usr/bin/env bash

COMPONENT_NAME="harness"
COMPONENT_DESC="Python harness runtime payload"
COMPONENT_DEFAULT="on"
COMPONENT_REQUIRES_BINS="python3"
COMPONENT_REQUIRES_COMPONENTS="kernel"
COMPONENT_PYTHON_REQS="requirements/harness.txt"

component_install() {
    copy_payload "$SOURCE_DIR/harness" "$SOLAR_HOME/harness"
    dry_run_note "prepare harness runtime helpers" && return 0
    chmod +x "$SOLAR_HOME/harness/"*.sh 2>/dev/null || true
    chmod +x "$SOLAR_HOME/harness/lib/"*.sh 2>/dev/null || true
    chmod +x "$SOLAR_HOME/tests/harness/"*.sh 2>/dev/null || true
    chmod +x "$SOLAR_HOME/harness/tools/"*.sh 2>/dev/null || true
    chmod +x "$SOLAR_HOME/harness/tools/"*.py 2>/dev/null || true
    if [ -f "$SOLAR_HOME/harness/solar-harness.sh" ]; then
        ln -sf "$SOLAR_HOME/harness/solar-harness.sh" "$SOLAR_HOME/bin/solar-harness"
    fi
    pip_install_reqs "$SOLAR_PYTHON" "$SOURCE_DIR/$COMPONENT_PYTHON_REQS"
    {
        printf 'source=%s\n' "$SOURCE_DIR/harness"
        printf 'destination=%s\n' "$SOLAR_HOME/harness"
        printf 'synced_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'repo=%s\n' "$SOURCE_DIR"
    } > "$SOLAR_HOME/harness/.runtime-source"
    if [ "$FAKE_KEYS" = "true" ]; then
        dry_run_note "write fake harness env files" && return 0
        for env_file in "$SOLAR_HOME/.env" "$SOLAR_HOME/harness/.env"; do
            if [ ! -f "$env_file" ]; then
                mkdir -p "$(dirname "$env_file")"
                {
                    printf 'OPENAI_API_KEY=fake-key-for-ci\n'
                    printf 'ANTHROPIC_API_KEY=fake-key-for-ci\n'
                    printf 'SOLAR_FAKE_KEYS=1\n'
                } > "$env_file"
                chmod 600 "$env_file"
            fi
        done
    fi
    return 0
}

component_verify() {
    [ -f "$SOLAR_HOME/harness/solar-harness.sh" ] || die "harness verify failed: solar-harness.sh missing"
    if [ "${SKIP_PY_DEPS:-false}" != "true" ]; then
        "$SOLAR_PYTHON" -c 'import yaml, jsonschema, pydantic, rich' \
            || die "harness verify failed: requirements/harness.txt is not importable by $SOLAR_PYTHON"
    fi
}
