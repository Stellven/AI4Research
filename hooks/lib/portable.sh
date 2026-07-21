#!/bin/sh
# Portable helpers for Solar hook scripts.

sed_i() {
    script="$1"
    file="$2"
    tmp="${file}.tmp.$$"
    sed "$script" "$file" > "$tmp" && mv "$tmp" "$file"
}

date_add() {
    amount="$1"
    format="${2:-%Y-%m-%dT%H:%M}"
    os_name="$(uname -s 2>/dev/null || echo unknown)"

    if [ "$os_name" = "Darwin" ]; then
        date -v"$amount" -u +"$format"
        return $?
    fi

    unit="${amount#${amount%?}}"
    number="${amount%?}"
    direction=""
    value="$number"
    if [ "${number#-}" != "$number" ]; then
        direction=" ago"
        value="${number#-}"
    else
        value="${number#+}"
    fi

    case "$unit" in
        M) unit_name="minutes" ;;
        H) unit_name="hours" ;;
        D) unit_name="days" ;;
        *) unit_name="$unit" ;;
    esac

    date -u -d "$value $unit_name$direction" +"$format"
}

solar_python() {
    venv_dir="${1:-}"
    if [ -n "${SOLAR_PYTHON:-}" ] && [ -x "$SOLAR_PYTHON" ]; then
        printf '%s\n' "$SOLAR_PYTHON"
    elif [ -n "$venv_dir" ] && [ -x "$venv_dir/bin/python3" ]; then
        printf '%s\n' "$venv_dir/bin/python3"
    elif [ -n "$venv_dir" ] && [ -x "$venv_dir/bin/python" ]; then
        printf '%s\n' "$venv_dir/bin/python"
    elif [ -x "$HOME/.solar/venv/bin/python3" ]; then
        printf '%s\n' "$HOME/.solar/venv/bin/python3"
    elif command -v python3 >/dev/null 2>&1; then
        command -v python3
    else
        command -v python
    fi
}
