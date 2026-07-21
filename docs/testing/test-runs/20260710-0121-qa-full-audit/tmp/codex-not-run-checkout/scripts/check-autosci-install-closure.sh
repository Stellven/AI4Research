#!/usr/bin/env bash
# check-autosci-install-closure.sh — prove the installed CLI carries the
# AutoSci runtime closure, not just the repo-local source tree.
set -eu

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-autosci-install.XXXXXX")"
home_dir="$sandbox/home"
skills_json="$sandbox/autosci-skills.json"
ingest_json="$sandbox/autosci-ingest-smoke.json"
test_path="$PATH"

cleanup() {
    rm -rf "$sandbox"
}
trap cleanup EXIT INT TERM

if [ -x "$repo_dir/.venv/bin/python3" ]; then
    test_path="$repo_dir/.venv/bin:$test_path"
fi

python_has_autosci_deps() {
    PATH="$test_path" python3 - <<'PY' >/dev/null 2>&1
import jsonschema
import pydantic
import rich
import yaml
PY
}

assert_file() {
    path="$1"
    [ -f "$path" ] || {
        echo "missing expected AutoSci install file: $path" >&2
        exit 1
    }
}

assert_no_generated_junk() {
    root="$1"
    junk="$sandbox/generated-junk.txt"
    find "$root" \( -name __pycache__ -o -name '*.pyc' -o -name .DS_Store \) -print > "$junk"
    if [ -s "$junk" ]; then
        echo "AutoSci closure copied generated/junk files:" >&2
        cat "$junk" >&2
        exit 1
    fi
}

assert_autosci_receipt() {
    PATH="$test_path" python3 - "$home_dir/.solar/install-receipt.json" <<'PY'
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = ["kernel", "harness", "autosci"]
actual = receipt.get("components")
if actual != expected:
    raise SystemExit(f"components mismatch: expected {expected!r}, got {actual!r}")
roots = receipt.get("component_roots", {}).get("autosci")
if not roots or not any(path.endswith("/tools") for path in roots):
    raise SystemExit(f"autosci tools root missing from receipt: {roots!r}")
if not roots or not any(path.endswith("/.agents/skills") for path in roots):
    raise SystemExit(f"autosci skills root missing from receipt: {roots!r}")
PY
}

assert_autosci_skills_list() {
    PATH="$test_path" python3 - "$skills_json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("ok") is not True:
    raise SystemExit(f"skills list did not report ok: {payload!r}")
skills = payload.get("skills") or []
if payload.get("count", 0) < 20 or len(skills) < 20:
    raise SystemExit(f"expected at least 20 AutoSci skills, got {payload.get('count')} / {len(skills)}")
names = {item.get("skill") for item in skills if isinstance(item, dict)}
for required in ("ingest", "discover", "paper-draft", "visualize"):
    if required not in names:
        raise SystemExit(f"required AutoSci skill missing from installed list: {required}")
PY
}

assert_ingest_smoke() {
    PATH="$test_path" python3 - "$ingest_json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("ok") is not True:
    raise SystemExit(f"ingest smoke failed: {payload!r}")
if payload.get("skill") != "ingest":
    raise SystemExit(f"unexpected smoke skill: {payload!r}")
if payload.get("action_count", 0) < 1:
    raise SystemExit(f"ingest smoke ran no actions: {payload!r}")
if payload.get("failed_count", 0) != 0:
    raise SystemExit(f"ingest smoke reported failed actions: {payload!r}")
PY
}

assert_residue_empty() {
    residue="$sandbox/residue.txt"
    find "$home_dir" -mindepth 1 -print | sort > "$residue"
    if [ -s "$residue" ]; then
        echo "install residue remains after uninstall:" >&2
        cat "$residue" >&2
        exit 1
    fi
}

mkdir -p "$home_dir"

default_home="$sandbox/default-home"
default_out="$sandbox/default-dry-run.out"
mkdir -p "$default_home"
PATH="$test_path" HOME="$default_home" "$repo_dir/install.sh" \
    --yes \
    --dry-run \
    --fake-keys \
    --skip-llm-cli \
    --skip-py-deps \
    > "$default_out" 2>&1
grep -q "OpenSolar dry-run complete: .*autosci" "$default_out" || {
    echo "default installer component set does not include autosci:" >&2
    cat "$default_out" >&2
    exit 1
}
echo "AutoSci default component selection: ok"

PATH="$test_path" HOME="$home_dir" "$repo_dir/install.sh" \
    --yes \
    --components kernel,harness,autosci \
    --fake-keys \
    --skip-llm-cli \
    --skip-py-deps \
    >/dev/null

assert_autosci_receipt
assert_file "$home_dir/.solar/harness/plugins/autosci/bin/autosci_skill_shim.py"
assert_file "$home_dir/.solar/harness/plugins/autosci/bin/autosci_bridge.py"
assert_file "$home_dir/.solar/tools/research_wiki.py"
assert_file "$home_dir/.solar/tools/visualize.py"
assert_file "$home_dir/.solar/tools/serve.py"
assert_file "$home_dir/.solar/.agents/skills/ingest/SKILL.md"
assert_file "$home_dir/.solar/.agents/skills/prefill/foundations-catalog.yaml"
assert_no_generated_junk "$home_dir/.solar/tools"
assert_no_generated_junk "$home_dir/.solar/.agents/skills"

PATH="$test_path" HOME="$home_dir" "$home_dir/.solar/bin/solar" \
    harness autosci skills list > "$skills_json"
assert_autosci_skills_list
echo "AutoSci installed skills list: ok"

if python_has_autosci_deps; then
    PATH="$test_path" HOME="$home_dir" "$home_dir/.solar/bin/solar" \
        harness autosci "\$ingest --smoke" > "$ingest_json"
    assert_ingest_smoke
    echo "AutoSci installed ingest smoke: ok"
else
    echo "AutoSci installed ingest smoke: skipped (python deps unavailable on PATH)" >&2
fi

PATH="$test_path" HOME="$home_dir" "$home_dir/.solar/bin/solar" \
    repair --fake-keys --skip-llm-cli --skip-py-deps >/dev/null
PATH="$test_path" HOME="$home_dir" "$home_dir/.solar/bin/solar" \
    harness autosci skills list > "$skills_json"
assert_autosci_skills_list
echo "AutoSci repair round-trip: ok"

PATH="$test_path" HOME="$home_dir" "$home_dir/.solar/bin/solar" uninstall --yes >/dev/null
assert_residue_empty
echo "check-autosci-install-closure passed"
