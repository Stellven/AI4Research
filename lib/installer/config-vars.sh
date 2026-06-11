#!/usr/bin/env bash

# config-vars.sh — required/optional config-var resolution for the selected
# components. mempalace is its first consumer.
#
# A component manifest may declare (one entry per line):
#   COMPONENT_CONFIG_VARS="KEY:required:Human description"
#                          "KEY2:optional:..."
# Resolution precedence (highest first):
#   --set KEY=VALUE  >  SOLAR_<KEY> env  >  components.d/<name>/defaults.env
# A required var still unresolved:
#   - interactive TTY (not --yes): prompt for it on /dev/tty
#   - otherwise: FAIL LOUD with the exact --set remedy
# Every resolved value is fed to render-template by appending KEY=VALUE to
# SOLAR_SET_VARS, so {{KEY}} placeholders render regardless of the source.

# Last-match lookup of KEY in the current SOLAR_SET_VARS (KEY=VALUE lines).
set_vars_lookup() {
    _k="$1"
    _result=""
    while IFS= read -r _line; do
        case "$_line" in
            "$_k="*) _result="${_line#*=}" ;;
        esac
    done <<EOF
$SOLAR_SET_VARS
EOF
    printf '%s' "$_result"
}

# Last-match lookup of KEY in a component's defaults.env (KEY=VALUE lines;
# '#' comments and blanks ignored). Missing file => empty.
defaults_lookup() {
    _comp="$1"
    _k="$2"
    _result=""
    _file="$SOURCE_DIR/components.d/$_comp/defaults.env"
    [ -f "$_file" ] || { printf ''; return 0; }
    while IFS= read -r _line; do
        case "$_line" in
            \#*|'') : ;;
            "$_k="*) _result="${_line#*=}" ;;
        esac
    done < "$_file"
    printf '%s' "$_result"
}

resolve_config_vars() {
    # TTY-ness must be sampled before the heredoc redirections below remap
    # stdin; an interactive prompt then reads from /dev/tty explicitly.
    _interactive=false
    if [ "$YES" != "true" ] && [ -t 0 ]; then
        _interactive=true
    fi

    for _comp in $SELECTED_COMPONENTS; do
        load_component "$_comp"
        [ -n "${COMPONENT_CONFIG_VARS:-}" ] || continue
        while IFS= read -r _entry; do
            _entry="$(printf '%s' "$_entry" | awk '{$1=$1; print}')"
            [ -n "$_entry" ] || continue
            _key="${_entry%%:*}"
            _rest="${_entry#*:}"
            _req="${_rest%%:*}"
            _desc="${_rest#*:}"
            [ -n "$_key" ] || continue

            # precedence: --set > SOLAR_<KEY> env > defaults.env
            _val="$(set_vars_lookup "$_key")"
            if [ -z "$_val" ]; then
                eval "_val=\${SOLAR_${_key}:-}"
            fi
            if [ -z "$_val" ]; then
                _val="$(defaults_lookup "$_comp" "$_key")"
            fi
            if [ -z "$_val" ] && [ "$_req" = "required" ] && [ "$_interactive" = "true" ]; then
                printf '%s requires %s (%s): ' "$COMPONENT_NAME" "$_key" "$_desc" >&2
                read -r _val </dev/tty || _val=""
            fi
            if [ -z "$_val" ] && [ "$_req" = "required" ]; then
                die "$COMPONENT_NAME requires $_key; pass --set $_key=/path"
            fi

            # Feed render-template: the resolved value wins (it IS the value).
            if [ -n "$_val" ]; then
                SOLAR_SET_VARS="$SOLAR_SET_VARS$_key=$_val
"
            fi
        done <<EOF
$COMPONENT_CONFIG_VARS
EOF
    done
    export SOLAR_SET_VARS
}
