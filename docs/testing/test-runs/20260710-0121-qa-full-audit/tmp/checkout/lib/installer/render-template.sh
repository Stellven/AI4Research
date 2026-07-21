#!/usr/bin/env bash

# render-template.sh — flat {{VAR}} template rendering (no template logic;
# conditionality lives at the component level). Resolution precedence:
#   --set KEY=VALUE  >  SOLAR_<KEY> env  >  installer-derived defaults
# Rendering fails loudly listing every unresolved {{VAR}} (chezmoi pattern).

render_template() {
    template="$1"
    output="$2"
    [ -f "$template" ] || die "template missing: $template"
    SOLAR_SET_VARS="${SOLAR_SET_VARS:-}" \
    SOLAR_HOME="$SOLAR_HOME" CLAUDE_DIR="$CLAUDE_DIR" OS_KIND="$OS_KIND" \
    SELECTED_COMPONENTS="$SELECTED_COMPONENTS" SOLAR_DB="$SOLAR_DB" \
    python3 - "$template" "$output" <<'PY'
import os
import re
import sys

template, output = sys.argv[1], sys.argv[2]
with open(template, encoding="utf-8") as f:
    text = f.read()

mapping = {
    "SOLAR_HOME": os.environ.get("SOLAR_HOME", ""),
    "CLAUDE_DIR": os.environ.get("CLAUDE_DIR", ""),
    "OS_KIND": os.environ.get("OS_KIND", ""),
    "SELECTED_COMPONENTS": os.environ.get("SELECTED_COMPONENTS", ""),
    "SOLAR_DB": os.environ.get("SOLAR_DB", ""),
}
# SOLAR_<KEY> env vars (do not clobber the explicit defaults above).
for key, value in os.environ.items():
    if key.startswith("SOLAR_") and key not in ("SOLAR_SET_VARS",):
        mapping.setdefault(key, value)
# --set KEY=VALUE overrides win (highest precedence).
for line in os.environ.get("SOLAR_SET_VARS", "").splitlines():
    if "=" in line:
        key, value = line.split("=", 1)
        mapping[key.strip()] = value

pattern = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
text = pattern.sub(lambda m: mapping.get(m.group(1).strip(), m.group(0)), text)
leftover = sorted(set(pattern.findall(text)))
if leftover:
    sys.stderr.write(
        "unresolved template vars in %s: %s\n" % (template, ", ".join(leftover))
    )
    raise SystemExit(1)

tmp = output + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write(text)
os.replace(tmp, output)
PY
}

# config_init — generate ~/.solar/config.env once (machine data). Never
# overwrites an existing file (preserves user edits across re-run/upgrade).
config_init() {
    template="$SOURCE_DIR/templates/config/config.env.template"
    output="$SOLAR_HOME/config.env"
    [ -f "$template" ] || return 0
    dry_run_note "generate $output from config template (once)" && return 0
    if [ -f "$output" ]; then
        info "config.env exists; preserving user edits"
        return 0
    fi
    mkdir -p "$SOLAR_HOME"
    render_template "$template" "$output"
    info "wrote $output"
}
