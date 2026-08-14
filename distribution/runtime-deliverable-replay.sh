#!/usr/bin/env bash
set -euo pipefail

bundle_root="$(cd "$(dirname "$0")" && pwd)"
replay_root="${1:?usage: bash replay.sh <new-empty-sandbox>}"

if [ -e "$replay_root" ] && [ -n "$(find "$replay_root" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    echo "replay sandbox must be new or empty: $replay_root" >&2
    exit 1
fi
mkdir -p "$replay_root"

manifest="$bundle_root/runtime-deliverable-manifest.json"
source_archive="$bundle_root/$(python3 - "$manifest" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["source"]["archive_path"])
PY
)"
wrapper_wheel="$(find "$bundle_root/artifacts" -maxdepth 1 -type f -name 'openjiuwen_solar-*.whl' -print -quit)"
[ -f "$source_archive" ] || { echo "bundled source archive missing" >&2; exit 1; }
[ -f "$wrapper_wheel" ] || { echo "bundled wrapper wheel missing" >&2; exit 1; }

python3 -m venv "$replay_root/runtime-python"
runtime_python="$replay_root/runtime-python/bin/python"
"$runtime_python" -m pip install \
    --disable-pip-version-check \
    --no-index \
    --find-links "$bundle_root/wheelhouse" \
    jsonschema pydantic pypdf PyYAML rich
"$runtime_python" "$bundle_root/verify.py" verify --bundle "$bundle_root"

export OPENJIUWEN_SOLAR_INSTALL_TARGET="$wrapper_wheel"
export OPENJIUWEN_SOLAR_SMOKE_ROOT="$replay_root/product"
export OPENJIUWEN_SOLAR_GET_SOLAR_URL="$bundle_root/bundled-get-solar.sh"
export OPENJIUWEN_SOLAR_RUNTIME_SOURCE_ARCHIVE="$source_archive"
export OPENJIUWEN_SOLAR_SKIP_UPDATE=1
export SOLAR_PYTHON="$runtime_python"
export PATH="$bundle_root/tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export SOLAR_CHANNEL="runtime-deliverable/$(python3 - "$manifest" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["source"]["git_commit"][:12])
PY
)"

exec bash "$bundle_root/smoke.sh"
