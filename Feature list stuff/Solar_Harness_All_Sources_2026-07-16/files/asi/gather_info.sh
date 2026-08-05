#!/usr/bin/env bash
set -u

INFO_OUT="$(cat /tmp/autosci_solar_info_latest_path.txt)"
mkdir -p "$INFO_OUT"

OPEN_SOLAR_REPO="${OPEN_SOLAR_REPO:-/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar}"
STELLVEN_SOLAR_REPO="${STELLVEN_SOLAR_REPO:-/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar}"
NATIVE_AUTOSCI_REPO="${NATIVE_AUTOSCI_REPO:-}"

{
  echo "OPEN_SOLAR_REPO_ENV=${OPEN_SOLAR_REPO:-}"
  echo "STELLVEN_SOLAR_REPO_ENV=${STELLVEN_SOLAR_REPO:-}"
  echo "NATIVE_AUTOSCI_REPO_ENV=${NATIVE_AUTOSCI_REPO:-}"
  echo
  echo "## Candidate repos"
  find "$HOME" -maxdepth 5 -type d \( -name OpenSolar -o -name AI4Research -o -name BetterSolar -o -name AutoSci \) 2>/dev/null | sort
} > "$INFO_OUT/repo_candidates.txt"

if [[ -z "$NATIVE_AUTOSCI_REPO" ]]; then
  first_native="$(find "$HOME" -maxdepth 5 -type d -name AutoSci 2>/dev/null | sort | head -1 || true)"
  if [[ -n "$first_native" && -d "$first_native/.git" ]]; then
    NATIVE_AUTOSCI_REPO="$first_native"
  fi
fi

{
  echo "OPEN_SOLAR_REPO=$OPEN_SOLAR_REPO"
  echo "STELLVEN_SOLAR_REPO=$STELLVEN_SOLAR_REPO"
  echo "NATIVE_AUTOSCI_REPO=${NATIVE_AUTOSCI_REPO:-missing}"
} > "$INFO_OUT/repo_paths.env"

{
  echo "# System Info"
  date -u
  uname -a || true
  sw_vers 2>/dev/null || true
  lsb_release -a 2>/dev/null || true
  echo
  echo "# Tool Versions"
  git --version || true
  python3 --version || true
  node --version || true
  npm --version || true
  bun --version || true
  jq --version || true
  tmux -V || true
  pytest --version || true
  latexmk -v 2>/dev/null | head -20 || true
  pdflatex --version 2>/dev/null | head -5 || true
  xelatex --version 2>/dev/null | head -5 || true
  lualatex --version 2>/dev/null | head -5 || true
  rsync --version 2>/dev/null | head -5 || true
  ssh -V 2>&1 || true
  screen --version 2>/dev/null || true
  echo
  echo "# Tool Paths"
  for cmd in git python3 node npm bun jq tmux pytest latexmk pdflatex xelatex lualatex rsync ssh screen; do
    printf "%-12s " "$cmd"
    command -v "$cmd" || true
  done
  echo
  echo "# Important Environment Variables, values redacted when sensitive"
  python3 - <<'PY'
import os
names = [
  "HARNESS_DIR", "SOLAR_HARNESS_DIR", "SOLAR_AUTOSCI_OUTPUT_HARNESS",
  "AUTOSCI_ARTIFACT_ROOT", "SCIENTIFIC_ARTIFACT_ROOT",
  "OPEN_SOLAR_REPO", "STELLVEN_SOLAR_REPO", "NATIVE_AUTOSCI_REPO",
  "SEMANTIC_SCHOLAR_API_KEY", "DEEPXIV_TOKEN", "LLM_API_KEY",
  "LLM_BASE_URL", "LLM_MODEL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
  "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
  "SOLAR_PANE_RUNTIME", "SOLAR_CODEX_BIN", "SOLAR_CLAUDE_BIN",
]
for name in names:
    val = os.environ.get(name)
    if val is None:
        print(f"{name}=<unset>")
    elif "KEY" in name or "TOKEN" in name or "AUTH" in name:
        print(f"{name}=<set redacted len={len(val)}>")
    else:
        print(f"{name}={val}")
PY
} > "$INFO_OUT/system_info.txt" 2>&1

: > "$INFO_OUT/git_state.txt"
for repo_var in OPEN_SOLAR_REPO STELLVEN_SOLAR_REPO NATIVE_AUTOSCI_REPO; do
  repo="${!repo_var:-}"
  [[ -n "$repo" ]] || continue
  if [[ ! -d "$repo/.git" ]]; then
    echo "$repo_var not a git repo: $repo" >> "$INFO_OUT/git_state.txt"
    continue
  fi
  {
    echo "============================================================"
    echo "$repo_var=$repo"
    cd "$repo" || exit
    pwd
    git remote -v
    git branch --show-current
    git rev-parse HEAD
    git log -1 --oneline --decorate
    git status --short
    git worktree list || true
    git submodule status || true
    echo
  } >> "$INFO_OUT/git_state.txt" 2>&1
  {
    echo "============================================================"
    echo "$repo_var=$repo"
    cd "$repo" || exit
    git status --short
  } >> "$INFO_OUT/initial_git_status.txt" 2>&1
done

{
  echo "# OpenSolar branches"
  if [[ -d "$OPEN_SOLAR_REPO/.git" ]]; then cd "$OPEN_SOLAR_REPO" && git branch -a | sed -n '1,200p'; fi
  echo
  echo "# Stellven branches"
  if [[ -d "$STELLVEN_SOLAR_REPO/.git" ]]; then cd "$STELLVEN_SOLAR_REPO" && git branch -a | sed -n '1,200p'; fi
  echo
  echo "# Native AutoSci branches"
  if [[ -n "${NATIVE_AUTOSCI_REPO:-}" && -d "$NATIVE_AUTOSCI_REPO/.git" ]]; then cd "$NATIVE_AUTOSCI_REPO" && git branch -a | sed -n '1,120p'; else echo "missing"; fi
} > "$INFO_OUT/git_branches.txt" 2>&1

if [[ -d "$OPEN_SOLAR_REPO/.git" ]]; then
  cd "$OPEN_SOLAR_REPO" || exit
  {
    echo "# Top-level structure"
    find . -maxdepth 2 -type d | sort | sed -n '1,240p'
    echo
    find . -maxdepth 2 -type f | sort | sed -n '1,240p'
  } > "$INFO_OUT/open_solar_top_tree.txt" 2>&1
  {
    echo "# AutoSci plugin files"
    find harness/plugins/autosci -maxdepth 5 -type f | sort | sed -n '1,500p'
    echo
    echo "# AutoSci/scientific harness tools"
    find harness/tools -maxdepth 1 -type f | sort | grep -E 'autosci|scientific|research_wiki|remote|fetch_|review_model|wiki_mutation' || true
    echo
    echo "# Scientific workflows"
    find harness/workflows -maxdepth 1 -type f | sort | grep -E 'scientific|research' || true
    echo
    echo "# Scientific evaluators"
    find harness/evaluators/scientific -maxdepth 2 -type f | sort || true
    echo
    echo "# Evidence schemas"
    find harness/schemas/evidence -maxdepth 1 -type f | sort || true
    echo
    echo "# Research capability capsules"
    find harness/capability-capsules -maxdepth 1 -type f | sort | grep 'cap.research' || true
    echo
    echo "# Product-level AutoSci tests"
    find harness/tests/integration -maxdepth 1 -type f | sort | grep 'autosci' || true
    echo
    echo "# Plugin AutoSci tests"
    find harness/plugins/autosci/tests -maxdepth 2 -type f | sort | sed -n '1,260p' || true
    echo
    echo "# AutoSci skill wrappers"
    find .agents/skills -maxdepth 2 -type f | sort | sed -n '1,360p' || true
    echo
    echo "# AutoSci docs"
    find docs/integrations/autosci -maxdepth 3 -type f | sort | sed -n '1,360p' || true
  } > "$INFO_OUT/open_solar_autosci_tree.txt" 2>&1
fi

if [[ -d "$STELLVEN_SOLAR_REPO/.git" ]]; then
  cd "$STELLVEN_SOLAR_REPO" || exit
  {
    echo "# Stellven top-level structure"
    find . -maxdepth 2 -type d | sort | sed -n '1,260p'
    echo
    find . -maxdepth 2 -type f | sort | sed -n '1,260p'
  } > "$INFO_OUT/stellven_top_tree.txt" 2>&1
  {
    echo "# Stellven harness structure"
    find harness -maxdepth 3 -type d | sort | sed -n '1,300p' || true
    echo
    find harness -maxdepth 3 -type f | sort | sed -n '1,400p' || true
    echo
    echo "# Important dirs"
    for d in bin harness harness/config harness/plugins harness/tools harness/evaluators harness/schemas .agents/skills core/daemon desktop distribution components.d; do
      echo "===== $d ====="
      ls -la "$d" 2>/dev/null || true
    done
  } > "$INFO_OUT/stellven_runtime_tree.txt" 2>&1
  for file in README.md AGENTS.md CLAUDE.md bin/solar harness/solar-harness.sh core/daemon/skill-dispatcher.ts harness/config/logical-operators.json harness/config/physical-operators.json harness/config/capability-capsules.registry.yaml harness/lib/plugin_loader.py harness/schemas/plugin.schema.json desktop/package.json; do
    if [[ -f "$file" ]]; then
      safe_name="$(echo "$file" | tr '/.' '__')"
      { echo "===== $file ====="; sed -n '1,360p' "$file"; } > "$INFO_OUT/stellven_file_${safe_name}.txt"
    fi
  done
fi

if [[ -n "${NATIVE_AUTOSCI_REPO:-}" && -d "$NATIVE_AUTOSCI_REPO/.git" ]]; then
  cd "$NATIVE_AUTOSCI_REPO" || exit
  {
    echo "# Native AutoSci top-level"
    find . -maxdepth 2 -type d | sort | sed -n '1,260p'
    echo
    find . -maxdepth 3 -type f | sort | sed -n '1,500p'
  } > "$INFO_OUT/native_autosci_tree.txt" 2>&1
  {
    echo "# Native skill files"
    find .claude/skills -maxdepth 2 -type f | sort 2>/dev/null || true
    find i18n/en/skills -maxdepth 2 -type f | sort 2>/dev/null || true
    echo
    echo "# Native Python tools"
    find tools -maxdepth 2 -type f | sort 2>/dev/null || true
    echo
    echo "# Native runtime/config/schema"
    find runtime config mcp-servers -maxdepth 3 -type f | sort 2>/dev/null || true
  } > "$INFO_OUT/native_autosci_important_files.txt" 2>&1
  for file in README.md tools/research_wiki.py tools/remote.py tools/discover.py tools/daily_arxiv.py tools/init_discovery.py .claude/skills/research/SKILL.md .claude/skills/ideate/SKILL.md .claude/skills/exp-run/SKILL.md .claude/skills/exp-status/SKILL.md .claude/skills/exp-eval/SKILL.md .claude/skills/paper-draft/SKILL.md .claude/skills/paper-compile/SKILL.md .claude/skills/review/SKILL.md .claude/skills/novelty/SKILL.md .claude/skills/rebuttal/SKILL.md .claude/skills/poster/SKILL.md; do
    if [[ -f "$file" ]]; then
      safe_name="$(echo "$file" | tr '/.' '__')"
      { echo "===== $file ====="; sed -n '1,520p' "$file"; } > "$INFO_OUT/native_file_${safe_name}.txt"
    fi
  done
else
  echo "Native AutoSci repo not found locally; network clone not attempted in restricted environment." > "$INFO_OUT/native_autosci_missing.txt"
fi

OPEN_PY="python3"
if [[ -x "$OPEN_SOLAR_REPO/harness/bin/python3" ]]; then OPEN_PY="$OPEN_SOLAR_REPO/harness/bin/python3"; fi

if [[ -d "$OPEN_SOLAR_REPO/harness" ]]; then
  cd "$OPEN_SOLAR_REPO/harness" || exit
  "$OPEN_PY" - <<'PY' > "$INFO_OUT/autosci_route_summary.json" 2> "$INFO_OUT/autosci_route_summary.stderr.txt"
import json
from collections import Counter
from pathlib import Path
p = Path("plugins/autosci/config/feature_parity_routes.v1.json")
payload = json.loads(p.read_text())
routes = payload.get("routes", [])
summary = {
    "path": str(p),
    "schema": payload.get("schema"),
    "version": payload.get("version"),
    "route_count": len(routes),
    "coverage_status_counts": dict(Counter(str(r.get("coverage_status")) for r in routes)),
    "backend_mode_counts": dict(Counter(str(r.get("backend_mode")) for r in routes)),
    "side_effect_policy_counts": dict(Counter(str(r.get("side_effect_policy")) for r in routes)),
    "routes": [
        {
            "native_skill": r.get("native_skill"),
            "autosci_command": r.get("autosci_command"),
            "coverage_status": r.get("coverage_status"),
            "semantic_parity": r.get("semantic_parity"),
            "backend_mode": r.get("backend_mode"),
            "side_effect_policy": r.get("side_effect_policy"),
            "solar_capability": r.get("solar_capability"),
            "solar_logical_operator": r.get("solar_logical_operator"),
            "solar_backend_action": r.get("solar_backend_action"),
            "evidence_schema": r.get("evidence_schema"),
        }
        for r in routes
    ],
}
print(json.dumps(summary, indent=2, sort_keys=True))
PY

  TMP_HARNESS="$INFO_OUT/tmp_harness_routes"
  mkdir -p "$TMP_HARNESS"
  for name in bin config personas tools plugins evaluators schemas lib templates workflows; do
    [[ -e "$PWD/$name" && ! -e "$TMP_HARNESS/$name" ]] && ln -s "$PWD/$name" "$TMP_HARNESS/$name"
  done
  mkdir -p "$TMP_HARNESS/run" "$TMP_HARNESS/artifacts"
  HARNESS_DIR="$TMP_HARNESS" bash "$PWD/solar-harness.sh" autosci '$skills' > "$INFO_OUT/product_autosci_skills_stdout.json" 2> "$INFO_OUT/product_autosci_skills_stderr.txt" || true

  "$OPEN_PY" - <<'PY' > "$INFO_OUT/autosci_consistency_inventory.json" 2> "$INFO_OUT/autosci_consistency_inventory.stderr.txt"
import json, re
from pathlib import Path
try:
    import yaml
except Exception as e:
    yaml = None

def load_yaml(path):
    if yaml is None:
        return {"_parse_error": "pyyaml unavailable"}
    return yaml.safe_load(Path(path).read_text())

routes = json.loads(Path("plugins/autosci/config/feature_parity_routes.v1.json").read_text()).get("routes", [])
manifest = load_yaml("plugins/autosci/manifest.yaml")
registry = load_yaml("config/capability-capsules.registry.yaml")
logical = json.loads(Path("config/logical-operators.json").read_text())
physical = json.loads(Path("config/physical-operators.json").read_text())
logical_ops = logical.get("logical_operators", logical)
physical_ops = physical.get("operators", physical.get("physical_operators", physical))
caps_in_manifest = set(manifest.get("capabilities") or []) if isinstance(manifest, dict) else set()
caps_in_routes = {r.get("solar_capability") for r in routes if r.get("solar_capability")}
registry_items = []
if isinstance(registry, dict):
    for group, items in (registry.get("capsules") or {}).items():
        if isinstance(items, list):
            registry_items.extend(items)
caps_in_registry = {item.get("capability_capsule_id") for item in registry_items if isinstance(item, dict)}
capsule_files = {p.stem for p in Path("capability-capsules").glob("cap.research-*.yaml")}
schema_files = {p.name.replace(".schema.json", "") for p in Path("schemas/evidence").glob("*.schema.json")}
bridge_path = Path("plugins/autosci/bin/autosci_bridge.py")
bridge_text = bridge_path.read_text(encoding="utf-8", errors="replace") if bridge_path.exists() else ""
route_actions = {r.get("solar_backend_action") for r in routes if r.get("solar_backend_action")}
summary = {
    "route_count": len(routes),
    "manifest_capabilities_count": len(caps_in_manifest),
    "route_capabilities_count": len(caps_in_routes),
    "registry_research_capabilities_count": len([c for c in caps_in_registry if str(c).startswith("cap.research-")]),
    "caps_in_manifest_missing_from_registry": sorted(caps_in_manifest - caps_in_registry),
    "caps_in_routes_missing_from_registry": sorted(caps_in_routes - caps_in_registry),
    "caps_in_registry_missing_files": sorted(c for c in caps_in_registry if str(c).startswith("cap.research-") and c not in capsule_files),
    "route_logical_operators_missing": sorted({r.get("solar_logical_operator") for r in routes if r.get("solar_logical_operator")} - set(logical_ops.keys())),
    "route_evidence_schemas_missing": sorted({r.get("evidence_schema") for r in routes if r.get("evidence_schema")} - schema_files),
    "route_actions": sorted(route_actions),
    "route_actions_maybe_missing_in_bridge_text": sorted(a for a in route_actions if a and a not in bridge_text),
    "physical_autosci_workers": sorted(k for k in physical_ops if str(k).startswith("autosci-")),
}
print(json.dumps(summary, indent=2, sort_keys=True))
PY

  grep -n "do_autosci_command\|autosci)\|\\\$\*)" solar-harness.sh > "$INFO_OUT/open_solar_autosci_dispatch_grep.txt" 2>&1 || true
  sed -n '3000,3290p' solar-harness.sh > "$INFO_OUT/open_solar_solar_harness_dispatch_excerpt.txt"
  grep -n "def normalize_dollar_argv\|def run_research_scheduler_lifecycle\|def selected_actions\|payload_status\|scheduler_node_id\|SCHEDULER_DEMO" plugins/autosci/bin/autosci_skill_shim.py > "$INFO_OUT/open_solar_shim_grep.txt" 2>&1 || true
  sed -n '1,140p' plugins/autosci/bin/autosci_skill_shim.py > "$INFO_OUT/open_solar_shim_head.txt"
  sed -n '320,540p' plugins/autosci/bin/autosci_skill_shim.py > "$INFO_OUT/open_solar_shim_scheduler_excerpt.txt"
  sed -n '1180,1320p' plugins/autosci/bin/autosci_skill_shim.py > "$INFO_OUT/open_solar_shim_status_excerpt.txt"
  sed -n '1,260p' tools/run_scientific_workflow.py > "$INFO_OUT/open_solar_run_scientific_workflow_head.txt"
  sed -n '260,560p' tools/run_scientific_workflow.py > "$INFO_OUT/open_solar_run_scientific_workflow_body.txt"
  sed -n '560,760p' tools/run_scientific_workflow.py > "$INFO_OUT/open_solar_run_scientific_workflow_tail.txt"
  sed -n '1,280p' evaluators/scientific/lifecycle_runtime_gate.py > "$INFO_OUT/open_solar_lifecycle_runtime_gate.txt"
  cp plugins/autosci/manifest.yaml "$INFO_OUT/open_solar_autosci_manifest.yaml" 2>/dev/null || true
  cp config/capability-capsules.registry.yaml "$INFO_OUT/open_solar_capability_registry.yaml" 2>/dev/null || true
  for skill in review research ingest ideate exp-run paper-draft paper-compile; do
    if [[ -f "$OPEN_SOLAR_REPO/.agents/skills/$skill/SKILL.md" ]]; then
      sed -n '1,120p' "$OPEN_SOLAR_REPO/.agents/skills/$skill/SKILL.md" > "$INFO_OUT/open_solar_wrapper_${skill}.md"
    fi
  done

  {
    echo "# pytest product-level AutoSci tests"
    PYTHONPATH="$OPEN_SOLAR_REPO/harness" "$OPEN_PY" -m pytest -q \
      tests/integration/test_autosci_routes_list.py \
      tests/integration/test_autosci_cli_dispatch.py \
      tests/integration/test_autosci_ingest_demo.py \
      tests/integration/test_autosci_review_demo.py \
      tests/integration/test_autosci_research_scheduler_demo.py \
      tests/integration/test_autosci_artifact_root.py
  } > "$INFO_OUT/open_solar_product_autosci_tests.txt" 2>&1

  {
    echo "# pytest collect AutoSci-related tests"
    PYTHONPATH="$OPEN_SOLAR_REPO/harness" "$OPEN_PY" -m pytest --collect-only \
      tests/integration/test_autosci_*.py \
      plugins/autosci/tests \
      tests/test_autosci_phase_c_premerge_readiness.py \
      tests/test_autosci_phase_c_unification_contracts.py \
      2>&1 || true
  } > "$INFO_OUT/open_solar_autosci_pytest_collect.txt"

  cd "$OPEN_SOLAR_REPO" || exit
  git status --short > "$INFO_OUT/open_solar_git_status_after_tests.txt" 2>&1

  cd "$OPEN_SOLAR_REPO/harness" || exit
  SMOKE_HARNESS="$INFO_OUT/manual_smoke_harness"
  mkdir -p "$SMOKE_HARNESS"
  for name in bin config personas tools plugins evaluators schemas lib templates workflows; do
    [[ -e "$PWD/$name" && ! -e "$SMOKE_HARNESS/$name" ]] && ln -s "$PWD/$name" "$SMOKE_HARNESS/$name"
  done
  mkdir -p "$SMOKE_HARNESS/run" "$SMOKE_HARNESS/artifacts" "$SMOKE_HARNESS/raw"
  DEMO_PAPER="$SMOKE_HARNESS/raw/demo-paper.md"
  printf '%s\n' '# Demo Paper' '' '## Abstract' 'This paper is a tiny fixture for AutoSci-on-Solar information gathering.' '' '## Method' 'It checks product-level command dispatch and typed evidence.' '' '## Results' 'It should produce research_paper.v1 evidence.' > "$DEMO_PAPER"
  {
    echo '## $skills'
    HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci '$skills'
    echo
    echo '## $review --help'
    HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci '$review --help'
    echo
    echo '## $ingest demo'
    HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci "\$ingest --paper $DEMO_PAPER --run-id info-smoke-ingest"
    echo
    echo '## $research scheduler demo'
    HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci "\$research info smoke --paper $DEMO_PAPER --scheduler-run --scheduler-timeout 20 --run-id info-smoke-research"
    echo
    echo '## generated files'
    find "$SMOKE_HARNESS/artifacts" -maxdepth 5 -type f | sort | sed -n '1,160p'
  } > "$INFO_OUT/open_solar_manual_product_smoke.txt" 2>&1

  cd "$OPEN_SOLAR_REPO" || exit
  {
    echo "# Tracked generated artifacts"
    echo "## runs"; git ls-files 'harness/artifacts/autosci/runs/*'
    echo "## operator-smoke"; git ls-files 'harness/artifacts/autosci/operator-smoke/*'
    echo "## current parity inventories"; git ls-files 'harness/artifacts/autosci/phase19/current-parity-inventory-*.json'
    echo "## scientific workflow-runs"; git ls-files 'harness/artifacts/scientific/workflow-runs/*'
    echo "## DS_Store"; git ls-files '*.DS_Store'
    echo "## solar backups"; git ls-files '.solar-backups/*'
    echo
    echo "# Ignored artifact patterns check"
    git check-ignore -v harness/artifacts/autosci/runs/example.json 2>/dev/null || true
    git check-ignore -v harness/artifacts/autosci/operator-smoke/example.json 2>/dev/null || true
    git check-ignore -v harness/artifacts/scientific/workflow-runs/example.json 2>/dev/null || true
    echo
    echo "# Large files under AutoSci artifacts"
    find harness/artifacts -type f -size +1M 2>/dev/null | sort | sed -n '1,200p'
  } > "$INFO_OUT/open_solar_artifact_hygiene.txt" 2>&1
fi

# Local comparison without fetch/merge.
if [[ -d "$OPEN_SOLAR_REPO/.git" && -d "$STELLVEN_SOLAR_REPO/.git" ]]; then
  {
    echo "# Local comparison only"
    echo "No fetch was performed. Comparing current local OpenSolar worktree/index metadata to current local BetterSolar worktree."
    echo
    echo "# OpenSolar HEAD"
    git -C "$OPEN_SOLAR_REPO" log -1 --oneline --decorate
    echo "# BetterSolar HEAD"
    git -C "$STELLVEN_SOLAR_REPO" log -1 --oneline --decorate
    echo
    echo "# Files likely requiring manual merge"
    for file in README.md AGENTS.md CLAUDE.md bin/solar harness/solar-harness.sh core/daemon/skill-dispatcher.ts harness/config/logical-operators.json harness/config/physical-operators.json harness/config/capability-capsules.registry.yaml .gitignore; do
      o="$OPEN_SOLAR_REPO/$file"
      s="$STELLVEN_SOLAR_REPO/$file"
      if [[ -e "$o" && -e "$s" ]]; then
        if cmp -s "$o" "$s"; then status="same"; else status="different"; fi
        echo "$status $file"
      elif [[ -e "$o" ]]; then
        echo "open_only $file"
      elif [[ -e "$s" ]]; then
        echo "stellven_only $file"
      else
        echo "missing_both $file"
      fi
    done
    echo
    echo "# AutoSci module target path presence in BetterSolar"
    for path in harness/plugins/autosci harness/tools/run_scientific_workflow.py harness/tools/run_scientific_node_smoke.py harness/tools/run_scientific_lifecycle_smoke.py harness/workflows/scientific_research_lifecycle_full_v1.json harness/evaluators/scientific harness/schemas/evidence .agents/skills docs/integrations/autosci; do
      [[ -e "$STELLVEN_SOLAR_REPO/$path" ]] && echo "present $path" || echo "absent $path"
    done
  } > "$INFO_OUT/merge_focus_diff.txt" 2>&1

  git -C "$OPEN_SOLAR_REPO" ls-files | sort > "$INFO_OUT/open_solar_ls_files.txt"
  git -C "$STELLVEN_SOLAR_REPO" ls-files | sort > "$INFO_OUT/stellven_ls_files.txt"
  comm -23 "$INFO_OUT/open_solar_ls_files.txt" "$INFO_OUT/stellven_ls_files.txt" | sed -n '1,1000p' > "$INFO_OUT/open_only_files.txt"
  comm -13 "$INFO_OUT/open_solar_ls_files.txt" "$INFO_OUT/stellven_ls_files.txt" | sed -n '1,1000p' > "$INFO_OUT/stellven_only_files.txt"
  comm -12 "$INFO_OUT/open_solar_ls_files.txt" "$INFO_OUT/stellven_ls_files.txt" | sed -n '1,1000p' > "$INFO_OUT/common_files.txt"

  OPEN_SOLAR_REPO="$OPEN_SOLAR_REPO" STELLVEN_SOLAR_REPO="$STELLVEN_SOLAR_REPO" python3 - <<'PY' > "$INFO_OUT/config_key_comparison.json" 2> "$INFO_OUT/config_key_comparison.stderr.txt"
import json, os
from pathlib import Path
open_repo = Path(os.environ["OPEN_SOLAR_REPO"])
stellven = Path(os.environ["STELLVEN_SOLAR_REPO"])
out = {}
def read_json(repo, path):
    p = repo / path
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        return {"_parse_error": str(e)}
def keys(obj):
    if not isinstance(obj, dict):
        return []
    for k in ["logical_operators", "operators", "physical_operators"]:
        if isinstance(obj.get(k), dict):
            return sorted(obj[k])
    return sorted(obj)
for path in ["harness/config/logical-operators.json", "harness/config/physical-operators.json"]:
    a = read_json(stellven, path)
    b = read_json(open_repo, path)
    out[path] = {
        "stellven_count": len(keys(a)),
        "autosci_branch_count": len(keys(b)),
        "autosci_only_keys": sorted(set(keys(b)) - set(keys(a)))[:300],
        "stellven_only_keys": sorted(set(keys(a)) - set(keys(b)))[:300],
    }
print(json.dumps(out, indent=2, sort_keys=True))
PY
fi

{
  echo "# Provider and side-effect readiness"
  python3 - <<'PY'
import os
vars = [
  "SEMANTIC_SCHOLAR_API_KEY", "DEEPXIV_TOKEN",
  "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
  "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
]
for v in vars:
    val = os.environ.get(v)
    print(f"{v}: {'present' if val else 'absent'}")
PY
  echo
  echo "# Tool availability"
  for cmd in latexmk pdflatex xelatex lualatex rsync ssh screen; do
    printf "%-12s " "$cmd"
    command -v "$cmd" || true
  done
  echo
  echo "# Possible config files"
  for f in \
    "$OPEN_SOLAR_REPO/harness/config/remote.yaml" \
    "$OPEN_SOLAR_REPO/harness/config/server.yaml" \
    "$OPEN_SOLAR_REPO/harness/plugins/autosci/config/daily-arxiv.yml" \
    "$OPEN_SOLAR_REPO/harness/plugins/autosci/config/daily-arxiv.yml.example" \
    "${NATIVE_AUTOSCI_REPO:-/missing}/config/daily-arxiv.yml.example" \
    "${NATIVE_AUTOSCI_REPO:-/missing}/.env" \
    "$OPEN_SOLAR_REPO/.env"
  do
    if [[ -e "$f" ]]; then echo "present: $f"; else echo "absent:  $f"; fi
  done
} > "$INFO_OUT/provider_side_effect_readiness.txt" 2>&1

if [[ -n "${NATIVE_AUTOSCI_REPO:-}" && -d "$NATIVE_AUTOSCI_REPO/.git" ]]; then
  cd "$NATIVE_AUTOSCI_REPO" || exit
  python3 - <<'PY' > "$INFO_OUT/native_autosci_command_inventory.json" 2> "$INFO_OUT/native_autosci_command_inventory.stderr.txt"
import json
from pathlib import Path
skill_dirs = []
for root in [Path(".claude/skills"), Path("i18n/en/skills")]:
    if root.exists():
        for p in sorted(root.glob("*/SKILL.md")):
            skill_dirs.append(str(p))
tools = [str(p) for p in sorted(Path("tools").glob("*.py"))] if Path("tools").exists() else []
runtime = [str(p) for p in sorted(Path("runtime").rglob("*")) if p.is_file()] if Path("runtime").exists() else []
print(json.dumps({"skill_files": skill_dirs, "tool_files": tools, "runtime_files": runtime[:300]}, indent=2, sort_keys=True))
PY
  {
    echo "# Native AutoSci keywords"
    for file in .claude/skills/research/SKILL.md .claude/skills/ideate/SKILL.md .claude/skills/exp-run/SKILL.md .claude/skills/paper-draft/SKILL.md .claude/skills/paper-compile/SKILL.md tools/research_wiki.py tools/remote.py; do
      [[ -f "$file" ]] || continue
      echo
      echo "===== $file ====="
      grep -nE "Stage|Phase|Gate|resume|checkpoint|remote|screen|rsync|latex|Review LLM|Semantic Scholar|DeepXiv|citation|maturity|transition|checkpoint|paper/|figures|tables|BibTeX|collect|deploy|monitor" "$file" | sed -n '1,220p' || true
    done
  } > "$INFO_OUT/native_autosci_feature_keywords.txt" 2>&1
fi

: > "$INFO_OUT/final_git_status.txt"
for repo_var in OPEN_SOLAR_REPO STELLVEN_SOLAR_REPO NATIVE_AUTOSCI_REPO; do
  repo="${!repo_var:-}"
  [[ -n "$repo" ]] || continue
  [[ -d "$repo/.git" ]] || continue
  {
    echo "============================================================"
    echo "$repo_var=$repo"
    cd "$repo" || exit
    git status --short
  } >> "$INFO_OUT/final_git_status.txt" 2>&1
done

# Build final report from captured files.
INFO_OUT="$INFO_OUT" OPEN_SOLAR_REPO="$OPEN_SOLAR_REPO" STELLVEN_SOLAR_REPO="$STELLVEN_SOLAR_REPO" NATIVE_AUTOSCI_REPO="${NATIVE_AUTOSCI_REPO:-}" python3 - <<'PY'
import json, os, re
from pathlib import Path
info = Path(os.environ["INFO_OUT"])
open_repo = os.environ.get("OPEN_SOLAR_REPO", "")
stellven_repo = os.environ.get("STELLVEN_SOLAR_REPO", "")
native_repo = os.environ.get("NATIVE_AUTOSCI_REPO", "") or "missing"

def text(name, limit=None):
    p = info / name
    if not p.exists():
        return ""
    s = p.read_text(errors="replace")
    return s if limit is None else s[:limit]

def json_file(name):
    try:
        return json.loads((info / name).read_text())
    except Exception:
        return {}
route = json_file("autosci_route_summary.json")
cons = json_file("autosci_consistency_inventory.json")
config_cmp = json_file("config_key_comparison.json")
prod_tests = text("open_solar_product_autosci_tests.txt")
manual_smoke = text("open_solar_manual_product_smoke.txt")
artifact = text("open_solar_artifact_hygiene.txt")
provider = text("provider_side_effect_readiness.txt")
git_state = text("git_state.txt")
initial = text("initial_git_status.txt")
final = text("final_git_status.txt")
merge_focus = text("merge_focus_diff.txt")
native_missing = (info / "native_autosci_missing.txt").exists()
prod_pass = "6 passed" in prod_tests and "failed" not in prod_tests.lower()
manual_pass = all(x in manual_smoke for x in ["## $skills", "## $review --help", "## $ingest demo", "## $research scheduler demo", "research_paper.v1", "scientific_lifecycle.v1"])
tracked_artifacts_found = bool(re.search(r"## runs\n\S|## operator-smoke\n\S|## current parity inventories\n\S|## scientific workflow-runs\n\S", artifact))
ds_store_tracked = bool(re.search(r"## DS_Store\n\S", artifact))
coverage = route.get("coverage_status_counts", {})
side = route.get("side_effect_policy_counts", {})
route_count = route.get("route_count", "unknown")
missing_caps = cons.get("caps_in_routes_missing_from_registry", [])
missing_schemas = cons.get("route_evidence_schemas_missing", [])
missing_ops = cons.get("route_logical_operators_missing", [])
manual_lines = [ln for ln in merge_focus.splitlines() if ln.startswith(("different", "open_only", "stellven_only", "missing_both"))]
files = sorted(p.name for p in info.iterdir() if p.is_file())
report = f"""# AutoSci-on-Solar Information Report

## 1. Executive Summary
- Can start unification branch? yes, with local/CI gate required first; this run did not start a branch or merge.
- Current AutoSci branch readiness: product dispatch and product-level smoke coverage are present; route inventory still contains partial/gated work.
- Stellven integration risk level: medium. Local BetterSolar differs on shared runtime files and lacks the AutoSci module paths.
- Full parity risk level: high. Native AutoSci reference repo status is {'missing locally' if native_missing else 'available locally'}, and current route statuses are not all full.
- Biggest blockers: run the gate on the eventual integration branch, manually merge shared runtime/config files, preserve artifact hygiene, and avoid claiming full parity.

## 2. Repositories
- OpenSolar path: `{open_repo}`
- Stellven/OpenJiuwen local path: `{stellven_repo}`
- Native AutoSci local path: `{native_repo}`

Initial/final git status was captured in `initial_git_status.txt` and `final_git_status.txt`.

```text
{git_state[:4000]}
```

## 3. System and Tools
See `system_info.txt` and `provider_side_effect_readiness.txt`.

Provider/side-effect summary:

```text
{provider[:2200]}
```

## 4. Current AutoSci Branch Inventory
- Route count: `{route_count}`
- Coverage status counts: `{coverage}`
- Side-effect policy counts: `{side}`
- Missing route capabilities from registry: `{missing_caps}`
- Missing route evidence schemas: `{missing_schemas}`
- Missing route logical operators: `{missing_ops}`

Detailed files: `open_solar_autosci_tree.txt`, `autosci_route_summary.json`, `autosci_consistency_inventory.json`.

## 5. Product-Level Dispatch Status
- `solar-harness.sh autosci` dispatch grep: `open_solar_autosci_dispatch_grep.txt`
- `$skills` product path output: `product_autosci_skills_stdout.json`
- Product-level pytest tests: {'pass' if prod_pass else 'fail or unknown'}
- Manual isolated smoke: {'pass' if manual_pass else 'fail or unknown'}

Product test output:

```text
{prod_tests[:2200]}
```

Manual smoke excerpt:

```text
{manual_smoke[:3000]}
```

## 6. Artifact Root and Hygiene
- Product tests and manual smoke used isolated harness roots under this info bundle.
- Generated AutoSci artifact tracking found: `{tracked_artifacts_found}`
- Tracked `.DS_Store` found: `{ds_store_tracked}`

See `open_solar_artifact_hygiene.txt`.

## 7. Stellven Solar Structure
See `stellven_top_tree.txt`, `stellven_runtime_tree.txt`, and captured `stellven_file_*` files.

Likely integration points from local inspection:
- `bin/solar` if present in product base.
- `harness/solar-harness.sh` or equivalent harness CLI.
- `harness/config/logical-operators.json`.
- `harness/config/physical-operators.json`.
- `harness/config/capability-capsules.registry.yaml`.
- `core/daemon/skill-dispatcher.ts` if present.

## 8. Diff / Merge Risk
No fetch was performed. Comparison is local OpenSolar vs local BetterSolar only.

Manual merge focus:

```text
{merge_focus[:3000]}
```

Config key comparison summary:

```json
{json.dumps(config_cmp, indent=2)[:5000]}
```

Manual merge files needing attention from local comparison: `{len(manual_lines)}`.

## 9. Native AutoSci Reference Inventory
Native AutoSci repo: `{native_repo}`.

Status: {'missing locally; clone not attempted because network is restricted and task is read-only info gathering' if native_missing else 'available locally; see native_autosci_tree.txt, native_autosci_command_inventory.json, native_autosci_feature_keywords.txt'}.

Hard parity areas expected from prompt/current route statuses:
- `/ideate` full five-phase/provider-backed novelty path.
- `/exp-run` deploy/collect/full local+remote gated execution.
- `/paper-draft` full paper tree and evidence-linked citations.
- `/paper-compile` TeX/PDF/submission checks.
- `/poster`, `/rebuttal`, Review LLM, live provider and remote-host proofs.

## 10. Recommended Boundaries for Two Agents
Agent A - Solar unification agent:
- Work in Stellven/BetterSolar integration branch only after explicit approval.
- Import bounded AutoSci module paths: plugin, scientific tools/workflows/evaluators/schemas/capsules/tests/wrappers/docs.
- Manually merge shared product files and run `harness/tests/test-autosci-premerge-gate.sh` equivalent after import.

Agent B - AutoSci full-parity agent:
- Continue inside AutoSci module boundaries.
- Do not promote any route to `full` without typed evidence and gate proof.
- Preserve product dispatch, artifact roots, Evidence ABI, and non-black-box workflow ownership.

## 11. Open Questions for User
- Should Native AutoSci be cloned locally for future parity inspection, and where?
- What exact integration branch name should Agent A use?
- Should final product command be `solar harness autosci` only, or also direct `solar harness '$review'`?
- Which provider credentials are allowed for demo vs CI?
- Should demo include only local evidence-safe paths or approved remote experiment paths?

## 12. Attachments
Information bundle directory: `{info}`

Files in bundle:

```text
{chr(10).join(files[:240])}
```
"""
(info / "AUTOSCI_SOLAR_INFO_REPORT.md").write_text(report, encoding="utf-8")
PY

tar -czf "${INFO_OUT}.tgz" -C "$(dirname "$INFO_OUT")" "$(basename "$INFO_OUT")"
{
  echo "REPORT=$INFO_OUT/AUTOSCI_SOLAR_INFO_REPORT.md"
  echo "BUNDLE=${INFO_OUT}.tgz"
} > "$INFO_OUT/final_paths.txt"
cat "$INFO_OUT/final_paths.txt"
