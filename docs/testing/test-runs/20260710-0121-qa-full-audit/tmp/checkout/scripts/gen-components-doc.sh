#!/usr/bin/env bash
# gen-components-doc.sh — generate docs/COMPONENTS.md from the component
# manifests (components.d/<name>/component.sh).
#
# Idempotent: identical manifests produce byte-identical output (stable order
# from COMPONENT_ORDER, no timestamps). Run with --check to verify the
# committed doc is in sync with the manifests (regenerate to a temp file and
# diff); used by CI to catch drift when a manifest changes.
# Vars assigned for the benefit of the sourced manifests (so their field
# values can reference SOLAR_HOME/SOURCE_DIR/CLAUDE_DIR under `set -u`) read as
# "unused" to shellcheck — a false positive for this generator.
# shellcheck disable=SC2034
set -eu

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
out="$repo_dir/docs/COMPONENTS.md"

# Stable component order = the installer's COMPONENT_ORDER.
# shellcheck source=/dev/null
order="$(. "$repo_dir/lib/installer/components.sh" >/dev/null 2>&1 && printf '%s' "$COMPONENT_ORDER")"

# Extract one manifest's display fields as a single tab-separated record.
# Sourced in a subshell with all fields pre-initialised; manifests only assign
# COMPONENT_* and define functions at top level, so sourcing has no effect
# beyond setting those fields.
extract() {
    name="$1"
    (
        COMPONENT_NAME="" COMPONENT_DESC="" COMPONENT_DEFAULT="" COMPONENT_PLATFORMS=""
        COMPONENT_REQUIRES_BINS="" COMPONENT_REQUIRES_COMPONENTS="" COMPONENT_CONFIG_VARS=""
        COMPONENT_MCP_SERVERS=""
        SOURCE_DIR="$repo_dir" SOLAR_HOME="$HOME/.solar" CLAUDE_DIR="$HOME/.claude"
        # shellcheck source=/dev/null
        . "$repo_dir/components.d/$name/component.sh" >/dev/null 2>&1 || true
        mcp="no"; [ -n "$COMPONENT_MCP_SERVERS" ] && mcp="yes"
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$COMPONENT_NAME" \
            "$COMPONENT_DEFAULT" \
            "${COMPONENT_PLATFORMS:-all}" \
            "${COMPONENT_REQUIRES_BINS:-—}" \
            "${COMPONENT_REQUIRES_COMPONENTS:-—}" \
            "$mcp" \
            "${COMPONENT_CONFIG_VARS:-—}" \
            "$COMPONENT_DESC"
    )
}

generate() {
    cat <<'HEADER'
<!-- GENERATED FILE — do not edit by hand.
     Regenerate with: ./scripts/gen-components-doc.sh
     Source of truth: components.d/<name>/component.sh -->

# Solar Components

Solar installs as selectable components. The default selection is `kernel` +
`harness` + `autosci`, plus `core-runtime` when `bun` is available; everything
else is opt-in. Select components with `./install.sh --components <list>` (see
[`INSTALL.md`](../INSTALL.md)).

`Default` is `on` (always selected), `auto` (selected when its required
binaries are present), or `off` (opt-in). `Platforms` of `all` means macOS,
Linux, and WSL2.

| Component | Default | Platforms | Requires (bins) | Requires (components) | MCP | Description |
|---|---|---|---|---|---|---|
HEADER

    for name in $order; do
        [ -f "$repo_dir/components.d/$name/component.sh" ] || continue
        IFS="$(printf '\t')" read -r c_name c_default c_platforms c_bins c_comps c_mcp c_cfg c_desc <<EOF
$(extract "$name")
EOF
        printf '| `%s` | %s | %s | %s | %s | %s | %s |\n' \
            "$c_name" "$c_default" "$c_platforms" \
            "$([ "$c_bins" = "—" ] && echo "—" || echo "\`$c_bins\`")" \
            "$([ "$c_comps" = "—" ] && echo "—" || echo "\`$c_comps\`")" \
            "$c_mcp" "$c_desc"
    done

    # Config-var detail for components that require values at install time.
    printf '\n## Required configuration\n\n'
    printf 'Some components need a value supplied with `--set KEY=VALUE` (or the\n'
    printf '`SOLAR_<KEY>` environment twin). In non-interactive mode a missing\n'
    printf 'required value fails with the exact `--set` remedy.\n\n'
    found_cfg=0
    for name in $order; do
        [ -f "$repo_dir/components.d/$name/component.sh" ] || continue
        IFS="$(printf '\t')" read -r c_name _ _ _ _ _ c_cfg _ <<EOF
$(extract "$name")
EOF
        [ "$c_cfg" = "—" ] && continue
        found_cfg=1
        # COMPONENT_CONFIG_VARS = "KEY:required|optional:Description"
        IFS=':' read -r v_key v_req v_desc <<EOF
$c_cfg
EOF
        printf -- '- `%s` requires `%s` (%s) — %s\n' \
            "$c_name" "$v_key" "$v_req" "$v_desc"
    done
    if [ "$found_cfg" -eq 0 ]; then
        printf 'No selected component currently requires a config value.\n'
    fi
}

if [ "${1:-}" = "--check" ]; then
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    generate >"$tmp"
    if ! diff -u "$out" "$tmp"; then
        echo "docs/COMPONENTS.md is out of sync with the manifests." >&2
        echo "Regenerate with: ./scripts/gen-components-doc.sh" >&2
        exit 1
    fi
    echo "docs/COMPONENTS.md is in sync with the component manifests"
    exit 0
fi

generate >"$out"
echo "wrote $out"
