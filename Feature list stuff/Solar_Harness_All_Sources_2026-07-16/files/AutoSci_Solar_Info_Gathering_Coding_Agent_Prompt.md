# Information-Gathering Prompt for Coding Agent
## AutoSci-on-Solar Parallel Planning Preparation

You are a coding agent with terminal access. Your task is **only to gather information** needed to plan the next phase of the AutoSci-on-Solar project.

Do **not** continue implementation work. Do **not** fix bugs. Do **not** edit tracked source files. Do **not** commit anything. Do **not** open a PR. Do **not** promote any route to `full`. Do **not** merge anything.

Your output will be sent back to ChatGPT. ChatGPT will use your collected data to generate two later execution prompts:

```text
Agent A — Solar unification agent:
  Port the AutoSci module into Stellven/OpenJiuwen Solar and prove product-level AutoSci command dispatch.

Agent B — AutoSci full-parity agent:
  Continue filling native AutoSci semantic parity inside the AutoSci module while preserving the unified runtime contract.
```

This prompt is for **information gathering only**.

---

# 0. Project background

We are working with three related codebases:

```text
1. Native AutoSci
   Reference repo: https://github.com/skyllwt/AutoSci
   Role: source-of-truth for native AutoSci behavior and full parity target.

2. Current AutoSci-on-Solar integration branch
   Repo: https://github.com/Coconut-ch1ken/OpenSolar
   Branch: feature/autosci-solar-native
   Role: user’s current AutoSci integration work. It contains AutoSci plugin/shim/bridge, scientific operators, evidence schemas, gates, workflows, and product-level harness dispatch.

3. Stellven/OpenJiuwen Solar
   Repo: https://github.com/Stellven/AI4Research
   Likely branch: openJiuwen-Solar
   Role: productized Solar runtime base with installer/product CLI/desktop/distribution infrastructure.
```

Our goal is not to build two Solars that communicate with each other. The intended final architecture is:

```text
One shared Solar runtime
  + AutoSci scientific capability module
```

The current strategy is parallel:

```text
Track A:
  Start Solar unification now by porting the AutoSci module into Stellven/OpenJiuwen Solar on an integration branch.

Track B:
  Continue native AutoSci full-parity work inside the AutoSci module after the integration contract is stable.
```

The non-negotiable architecture model is:

```text
TaskGraph node
  -> Logical operator
  -> Capability capsule
  -> Physical operator
  -> Implementation package
  -> Command
  -> Evidence ABI
  -> Gate / human-verifiable test
```

Critical rules:

```text
- Do not create a black-box AutoSciRunner that owns the whole workflow.
- AutoSci-specific code should remain in a bounded backend/plugin package.
- Solar owns workflow semantics, capability capsules, TaskGraphs, Evidence ABI, gates, resume, and lifecycle acceptance.
- Evidence decides completion. If a node cannot be verified with evidence, it is not complete.
```

---

# 1. Your mission

Gather all information needed to write applicable, concrete instructions for the two agents.

You must produce a final report containing:

```text
1. Exact local repo paths, branches, remotes, and working tree status.
2. Actual file structure of all three repos.
3. Exact AutoSci module structure in the current feature branch.
4. Exact Stellven/OpenJiuwen Solar structure and CLI/runtime layout.
5. Test results for current product-level AutoSci integration tests.
6. Route/capability/operator/schema/gate inventory.
7. Evidence of product-level dispatch behavior.
8. Artifact-root behavior and generated artifact hygiene.
9. Merge/conflict risk between current AutoSci branch and Stellven Solar.
10. Native AutoSci feature inventory needed for full parity.
11. Provider/side-effect environment availability, with secrets redacted.
12. Remaining unknowns and blockers.
```

Do not solve the issues. Only gather data.

---

# 2. Safety rules

Run commands read-only whenever possible.

Allowed:

```text
- git status / diff / log / ls-files / branch / remote
- find / ls / sed / grep / python scripts that read files
- pytest tests that use isolated tmp directories
- cloning into /tmp or another temporary directory if a repo is missing
- creating a report directory under /tmp or a user-specified output path
```

Not allowed:

```text
- editing tracked source files
- applying patches
- committing
- pushing
- merging
- rebasing
- deleting tracked files
- changing route coverage_status
- running destructive reset commands
- running real remote experiments
- sending emails
- uploading anything
- printing secrets
```

If a command would write artifacts, make sure it writes only under a temporary isolated `HARNESS_DIR`, not into the production repo unless the test already guarantees isolation.

At the beginning and end of the task, record:

```bash
git status --short
```

for each local repo.

If any repo status changes, report exactly what changed and why.

---

# 3. Create an output bundle

Create a timestamped output directory outside the repos:

```bash
export INFO_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export INFO_OUT="/tmp/autosci_solar_info_${INFO_TS}"
mkdir -p "$INFO_OUT"
```

Capture command outputs into files under this directory. Also create one final Markdown summary:

```text
$INFO_OUT/AUTOSCI_SOLAR_INFO_REPORT.md
```

At the end, create a tarball:

```bash
tar -czf "${INFO_OUT}.tgz" -C "$(dirname "$INFO_OUT")" "$(basename "$INFO_OUT")"
```

Your final answer to the user should include:

```text
- path to AUTOSCI_SOLAR_INFO_REPORT.md
- path to .tgz bundle
- short summary of pass/fail/unknown
```

---

# 4. Locate the three repos

First, try environment variables if already set:

```bash
echo "OPEN_SOLAR_REPO=${OPEN_SOLAR_REPO:-}"
echo "STELLVEN_SOLAR_REPO=${STELLVEN_SOLAR_REPO:-}"
echo "NATIVE_AUTOSCI_REPO=${NATIVE_AUTOSCI_REPO:-}"
```

If not set, search likely paths:

```bash
{
  echo "## Candidate repos"
  find "$HOME" -maxdepth 5 -type d \( -name OpenSolar -o -name AI4Research -o -name AutoSci \) 2>/dev/null | sort
} | tee "$INFO_OUT/repo_candidates.txt"
```

Set these variables based on actual local paths:

```bash
export OPEN_SOLAR_REPO="<path-to-Coconut/OpenSolar-local-checkout>"
export STELLVEN_SOLAR_REPO="<path-to-Stellven/AI4Research-local-checkout>"
export NATIVE_AUTOSCI_REPO="<path-to-skylwt/AutoSci-local-checkout>"
```

If a repo is missing and internet is available, you may clone into `/tmp/autosci_solar_info_repos` for inspection only:

```bash
mkdir -p /tmp/autosci_solar_info_repos

# Only if missing:
git clone https://github.com/Coconut-ch1ken/OpenSolar.git /tmp/autosci_solar_info_repos/OpenSolar
git clone https://github.com/Stellven/AI4Research.git /tmp/autosci_solar_info_repos/AI4Research
git clone https://github.com/skyllwt/AutoSci.git /tmp/autosci_solar_info_repos/AutoSci
```

Do not overwrite existing local repos.

---

# 5. Record system environment

Run:

```bash
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
} | tee "$INFO_OUT/system_info.txt"
```

---

# 6. Record Git identity and state for each repo

For each repo, run:

```bash
for repo_var in OPEN_SOLAR_REPO STELLVEN_SOLAR_REPO NATIVE_AUTOSCI_REPO; do
  repo="${!repo_var:-}"
  [ -n "$repo" ] || continue
  [ -d "$repo/.git" ] || { echo "$repo_var not a git repo: $repo" | tee -a "$INFO_OUT/git_state.txt"; continue; }

  {
    echo "============================================================"
    echo "$repo_var=$repo"
    cd "$repo"
    pwd
    git remote -v
    git branch --show-current
    git rev-parse HEAD
    git log -1 --oneline --decorate
    git status --short
    git worktree list || true
    git submodule status || true
    echo
  } | tee -a "$INFO_OUT/git_state.txt"
done
```

Also collect branches:

```bash
{
  echo "# OpenSolar branches"
  cd "$OPEN_SOLAR_REPO" && git branch -a | sed -n '1,200p'

  echo
  echo "# Stellven branches"
  cd "$STELLVEN_SOLAR_REPO" && git branch -a | sed -n '1,200p'

  echo
  echo "# Native AutoSci branches"
  cd "$NATIVE_AUTOSCI_REPO" && git branch -a | sed -n '1,120p'
} | tee "$INFO_OUT/git_branches.txt"
```

---

# 7. Inspect current AutoSci integration branch structure

In `Coconut-ch1ken/OpenSolar/tree/feature/autosci-solar-native`, gather structure:

```bash
cd "$OPEN_SOLAR_REPO"
git checkout feature/autosci-solar-native 2>/dev/null || true

{
  echo "# Top-level structure"
  find . -maxdepth 2 -type d | sort | sed -n '1,240p'
  echo
  find . -maxdepth 2 -type f | sort | sed -n '1,240p'
} | tee "$INFO_OUT/open_solar_top_tree.txt"

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
} | tee "$INFO_OUT/open_solar_autosci_tree.txt"
```

---

# 8. Inspect Stellven/OpenJiuwen Solar structure

In Stellven Solar, gather structure:

```bash
cd "$STELLVEN_SOLAR_REPO"

{
  echo "# Stellven top-level structure"
  find . -maxdepth 2 -type d | sort | sed -n '1,260p'
  echo
  find . -maxdepth 2 -type f | sort | sed -n '1,260p'
} | tee "$INFO_OUT/stellven_top_tree.txt"

{
  echo "# Stellven harness structure"
  find harness -maxdepth 3 -type d | sort | sed -n '1,300p' || true
  echo
  find harness -maxdepth 3 -type f | sort | sed -n '1,400p' || true
  echo
  echo "# Important dirs"
  ls -la bin 2>/dev/null || true
  ls -la harness 2>/dev/null || true
  ls -la harness/config 2>/dev/null || true
  ls -la harness/plugins 2>/dev/null || true
  ls -la harness/tools 2>/dev/null || true
  ls -la harness/evaluators 2>/dev/null || true
  ls -la harness/schemas 2>/dev/null || true
  ls -la .agents/skills 2>/dev/null || true
  ls -la core/daemon 2>/dev/null || true
  ls -la desktop 2>/dev/null || true
  ls -la distribution 2>/dev/null || true
  ls -la components.d 2>/dev/null || true
} | tee "$INFO_OUT/stellven_runtime_tree.txt"
```

Capture important files:

```bash
cd "$STELLVEN_SOLAR_REPO"

for file in \
  README.md \
  AGENTS.md \
  CLAUDE.md \
  bin/solar \
  harness/solar-harness.sh \
  core/daemon/skill-dispatcher.ts \
  harness/config/logical-operators.json \
  harness/config/physical-operators.json \
  harness/config/capability-capsules.registry.yaml \
  harness/lib/plugin_loader.py \
  harness/schemas/plugin.schema.json \
  desktop/package.json
do
  if [ -f "$file" ]; then
    safe_name="$(echo "$file" | tr '/.' '__')"
    {
      echo "===== $file ====="
      sed -n '1,360p' "$file"
    } > "$INFO_OUT/stellven_file_${safe_name}.txt"
  fi
done
```

---

# 9. Inspect native AutoSci reference structure

Native AutoSci is the full parity reference.

```bash
cd "$NATIVE_AUTOSCI_REPO"

{
  echo "# Native AutoSci top-level"
  find . -maxdepth 2 -type d | sort | sed -n '1,260p'
  echo
  find . -maxdepth 3 -type f | sort | sed -n '1,500p'
} | tee "$INFO_OUT/native_autosci_tree.txt"

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
} | tee "$INFO_OUT/native_autosci_important_files.txt"
```

Capture key native docs and skills:

```bash
cd "$NATIVE_AUTOSCI_REPO"

for file in \
  README.md \
  tools/research_wiki.py \
  tools/remote.py \
  tools/discover.py \
  tools/daily_arxiv.py \
  tools/init_discovery.py \
  .claude/skills/research/SKILL.md \
  .claude/skills/ideate/SKILL.md \
  .claude/skills/exp-run/SKILL.md \
  .claude/skills/exp-status/SKILL.md \
  .claude/skills/exp-eval/SKILL.md \
  .claude/skills/paper-draft/SKILL.md \
  .claude/skills/paper-compile/SKILL.md \
  .claude/skills/review/SKILL.md \
  .claude/skills/novelty/SKILL.md \
  .claude/skills/rebuttal/SKILL.md \
  .claude/skills/poster/SKILL.md
do
  if [ -f "$file" ]; then
    safe_name="$(echo "$file" | tr '/.' '__')"
    {
      echo "===== $file ====="
      sed -n '1,520p' "$file"
    } > "$INFO_OUT/native_file_${safe_name}.txt"
  fi
done
```

---

# 10. Generate current AutoSci route inventory

Run in the current AutoSci integration branch:

```bash
cd "$OPEN_SOLAR_REPO/harness"

python3 - <<'PY' | tee "$INFO_OUT/autosci_route_summary.json"
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
    "coverage_status_counts": Counter(str(r.get("coverage_status")) for r in routes),
    "backend_mode_counts": Counter(str(r.get("backend_mode")) for r in routes),
    "side_effect_policy_counts": Counter(str(r.get("side_effect_policy")) for r in routes),
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
print(json.dumps(summary, indent=2, sort_keys=True, default=dict))
PY
```

Also run the product-level command path if available:

```bash
cd "$OPEN_SOLAR_REPO/harness"

TMP_HARNESS="$INFO_OUT/tmp_harness_routes"
mkdir -p "$TMP_HARNESS"
for name in bin config personas tools plugins evaluators schemas lib templates workflows; do
  [ -e "$PWD/$name" ] && ln -s "$PWD/$name" "$TMP_HARNESS/$name"
done
mkdir -p "$TMP_HARNESS/run" "$TMP_HARNESS/artifacts"

HARNESS_DIR="$TMP_HARNESS" bash "$PWD/solar-harness.sh" autosci '$skills' \
  > "$INFO_OUT/product_autosci_skills_stdout.json" \
  2> "$INFO_OUT/product_autosci_skills_stderr.txt" || true
```

---

# 11. Generate capability/operator/schema/gate consistency inventory

Run in current AutoSci integration branch:

```bash
cd "$OPEN_SOLAR_REPO/harness"

python3 - <<'PY' | tee "$INFO_OUT/autosci_consistency_inventory.json"
import json
import yaml
import re
from pathlib import Path

routes = json.loads(Path("plugins/autosci/config/feature_parity_routes.v1.json").read_text()).get("routes", [])
manifest = yaml.safe_load(Path("plugins/autosci/manifest.yaml").read_text())
registry = yaml.safe_load(Path("config/capability-capsules.registry.yaml").read_text())

logical = json.loads(Path("config/logical-operators.json").read_text())
physical = json.loads(Path("config/physical-operators.json").read_text())

# Be tolerant to different JSON shapes.
logical_ops = logical.get("logical_operators", logical)
physical_ops = physical.get("physical_operators", physical)

caps_in_manifest = set(manifest.get("capabilities") or [])
caps_in_routes = {r.get("solar_capability") for r in routes if r.get("solar_capability")}

registry_items = []
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
    "caps_in_registry_missing_files": sorted(
        c for c in caps_in_registry
        if str(c).startswith("cap.research-") and c not in capsule_files
    ),
    "route_logical_operators_missing": sorted(
        {r.get("solar_logical_operator") for r in routes if r.get("solar_logical_operator")}
        - set(logical_ops.keys())
    ),
    "route_evidence_schemas_missing": sorted(
        {r.get("evidence_schema") for r in routes if r.get("evidence_schema")}
        - schema_files
    ),
    "route_actions": sorted(route_actions),
    "route_actions_maybe_missing_in_bridge_text": sorted(
        a for a in route_actions
        if a and a not in bridge_text
    ),
    "physical_autosci_workers": sorted(k for k in physical_ops if str(k).startswith("autosci-")),
}
print(json.dumps(summary, indent=2, sort_keys=True))
PY
```

---

# 12. Inspect critical current AutoSci files

Capture relevant snippets from the current branch.

```bash
cd "$OPEN_SOLAR_REPO/harness"

# solar-harness AutoSci dispatch
grep -n "do_autosci_command\|autosci)\|\\\\\\$\\*)" solar-harness.sh | tee "$INFO_OUT/open_solar_autosci_dispatch_grep.txt" || true
sed -n '3000,3260p' solar-harness.sh > "$INFO_OUT/open_solar_solar_harness_dispatch_excerpt.txt"

# shim critical functions
grep -n "def normalize_dollar_argv\|def run_research_scheduler_lifecycle\|def selected_actions\|payload_status\|scheduler_node_id" plugins/autosci/bin/autosci_skill_shim.py \
  | tee "$INFO_OUT/open_solar_shim_grep.txt" || true
sed -n '1,120p' plugins/autosci/bin/autosci_skill_shim.py > "$INFO_OUT/open_solar_shim_head.txt"
sed -n '320,520p' plugins/autosci/bin/autosci_skill_shim.py > "$INFO_OUT/open_solar_shim_scheduler_excerpt.txt"
sed -n '1180,1320p' plugins/autosci/bin/autosci_skill_shim.py > "$INFO_OUT/open_solar_shim_status_excerpt.txt"

# generic workflow runner
sed -n '1,220p' tools/run_scientific_workflow.py > "$INFO_OUT/open_solar_run_scientific_workflow_head.txt"
sed -n '220,520p' tools/run_scientific_workflow.py > "$INFO_OUT/open_solar_run_scientific_workflow_body.txt"
sed -n '520,700p' tools/run_scientific_workflow.py > "$INFO_OUT/open_solar_run_scientific_workflow_tail.txt"

# lifecycle gate
sed -n '1,260p' evaluators/scientific/lifecycle_runtime_gate.py > "$INFO_OUT/open_solar_lifecycle_runtime_gate.txt"

# manifest and registries
cat plugins/autosci/manifest.yaml > "$INFO_OUT/open_solar_autosci_manifest.yaml"
cat config/capability-capsules.registry.yaml > "$INFO_OUT/open_solar_capability_registry.yaml"

# wrappers most relevant to demo / full parity
for skill in review research ingest ideate exp-run paper-draft paper-compile; do
  if [ -f ".agents/skills/$skill/SKILL.md" ]; then
    sed -n '1,120p' ".agents/skills/$skill/SKILL.md" > "$INFO_OUT/open_solar_wrapper_${skill}.md"
  fi
done
```

---

# 13. Run current product-level tests in the AutoSci integration branch

Run only the product-level tests needed for unification readiness:

```bash
cd "$OPEN_SOLAR_REPO/harness"

{
  echo "# pytest product-level AutoSci tests"
  python3 -m pytest -q \
    tests/integration/test_autosci_routes_list.py \
    tests/integration/test_autosci_cli_dispatch.py \
    tests/integration/test_autosci_ingest_demo.py \
    tests/integration/test_autosci_review_demo.py \
    tests/integration/test_autosci_research_scheduler_demo.py \
    tests/integration/test_autosci_artifact_root.py
} 2>&1 | tee "$INFO_OUT/open_solar_product_autosci_tests.txt"
```

Also collect tests without running all heavy tests:

```bash
cd "$OPEN_SOLAR_REPO/harness"

{
  echo "# pytest collect AutoSci-related tests"
  python3 -m pytest --collect-only \
    tests/integration/test_autosci_*.py \
    plugins/autosci/tests \
    tests/evaluators/scientific \
    2>&1 || true
} | tee "$INFO_OUT/open_solar_autosci_pytest_collect.txt"
```

Record whether test artifacts changed tracked files:

```bash
cd "$OPEN_SOLAR_REPO"
git status --short | tee "$INFO_OUT/open_solar_git_status_after_tests.txt"
```

---

# 14. Manual product-level smoke in isolated harness

Run a manual smoke using isolated harness. This is separate from pytest.

```bash
cd "$OPEN_SOLAR_REPO/harness"

SMOKE_HARNESS="$INFO_OUT/manual_smoke_harness"
mkdir -p "$SMOKE_HARNESS"
for name in bin config personas tools plugins evaluators schemas lib templates workflows; do
  [ -e "$PWD/$name" ] && ln -s "$PWD/$name" "$SMOKE_HARNESS/$name"
done
mkdir -p "$SMOKE_HARNESS/run" "$SMOKE_HARNESS/artifacts"

{
  echo "## $skills"
  HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci '$skills'

  echo
  echo "## $review --help"
  HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci '$review --help'

  echo
  echo "## $ingest demo"
  DEMO_PAPER="$SMOKE_HARNESS/raw/demo-paper.md"
  mkdir -p "$(dirname "$DEMO_PAPER")"
  cat > "$DEMO_PAPER" <<'EOF'
# Demo Paper

## Abstract
This paper is a tiny fixture for AutoSci-on-Solar information gathering.

## Method
It checks product-level command dispatch and typed evidence.

## Results
It should produce research_paper.v1 evidence.
EOF
  HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci "\$ingest --paper $DEMO_PAPER --run-id info-smoke-ingest"

  echo
  echo "## $research scheduler demo"
  HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci "\$research info smoke --paper $DEMO_PAPER --scheduler-run --scheduler-timeout 20 --run-id info-smoke-research"

  echo
  echo "## generated files"
  find "$SMOKE_HARNESS/artifacts" -maxdepth 5 -type f | sort | sed -n '1,160p'
} 2>&1 | tee "$INFO_OUT/open_solar_manual_product_smoke.txt"
```

If any command fails, do not fix it. Capture the failure output.

---

# 15. Artifact hygiene checks

Run in the current AutoSci branch:

```bash
cd "$OPEN_SOLAR_REPO"

{
  echo "# Tracked generated artifacts"
  echo "## runs"
  git ls-files 'harness/artifacts/autosci/runs/*'
  echo "## operator-smoke"
  git ls-files 'harness/artifacts/autosci/operator-smoke/*'
  echo "## current parity inventories"
  git ls-files 'harness/artifacts/autosci/phase19/current-parity-inventory-*.json'
  echo "## scientific workflow-runs"
  git ls-files 'harness/artifacts/scientific/workflow-runs/*'
  echo "## DS_Store"
  git ls-files '*.DS_Store'
  echo "## solar backups"
  git ls-files '.solar-backups/*'

  echo
  echo "# Ignored artifact patterns check"
  git check-ignore -v harness/artifacts/autosci/runs/example.json 2>/dev/null || true
  git check-ignore -v harness/artifacts/autosci/operator-smoke/example.json 2>/dev/null || true
  git check-ignore -v harness/artifacts/scientific/workflow-runs/example.json 2>/dev/null || true

  echo
  echo "# Large files under AutoSci artifacts"
  find harness/artifacts -type f -size +1M 2>/dev/null | sort | sed -n '1,200p'
} | tee "$INFO_OUT/open_solar_artifact_hygiene.txt"
```

---

# 16. Compare current AutoSci branch with Stellven Solar

Use a temporary clone/fetch if needed. Do not modify product branches.

```bash
COMPARE_DIR="$INFO_OUT/compare_work"
mkdir -p "$COMPARE_DIR"

# Use existing Stellven repo, but fetch Coconut into it only if acceptable.
# Fetching remote objects does not edit tracked files.
cd "$STELLVEN_SOLAR_REPO"
git fetch https://github.com/Coconut-ch1ken/OpenSolar.git feature/autosci-solar-native

{
  echo "# Merge base"
  git merge-base HEAD FETCH_HEAD || true

  echo
  echo "# Ahead/behind or log comparison"
  git log --oneline --left-right --cherry-pick HEAD...FETCH_HEAD | sed -n '1,240p' || true

  echo
  echo "# Diff stat"
  git diff --stat HEAD...FETCH_HEAD || true

  echo
  echo "# Diff name-status"
  git diff --name-status HEAD...FETCH_HEAD | sed -n '1,800p' || true
} | tee "$INFO_OUT/stellven_vs_autosci_branch_diff.txt"
```

Generate focused overlap reports:

```bash
cd "$STELLVEN_SOLAR_REPO"

{
  echo "# Files likely requiring manual merge"
  git diff --name-status HEAD...FETCH_HEAD -- \
    README.md AGENTS.md CLAUDE.md \
    bin/solar \
    harness/solar-harness.sh \
    core/daemon/skill-dispatcher.ts \
    harness/config/logical-operators.json \
    harness/config/physical-operators.json \
    harness/config/capability-capsules.registry.yaml \
    .gitignore \
    | sed -n '1,200p'

  echo
  echo "# AutoSci module files from Coconut branch"
  git diff --name-status HEAD...FETCH_HEAD -- \
    harness/plugins/autosci \
    harness/tools/run_scientific_workflow.py \
    harness/tools/run_scientific_node_smoke.py \
    harness/tools/run_scientific_lifecycle_smoke.py \
    harness/workflows \
    harness/evaluators/scientific \
    harness/schemas/evidence \
    harness/capability-capsules \
    harness/tests/integration \
    .agents/skills \
    docs/integrations/autosci \
    | sed -n '1,500p'
} | tee "$INFO_OUT/merge_focus_diff.txt"
```

Compare config keys if both files exist:

```bash
python3 - <<'PY' | tee "$INFO_OUT/config_key_comparison.json"
import json
import subprocess
from pathlib import Path
import tempfile
import os

repo = Path(os.environ["STELLVEN_SOLAR_REPO"])
out = {}

def read_worktree(path):
    p = repo / path
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        return {"_parse_error": str(e)}

def read_fetch_head(path):
    try:
        data = subprocess.check_output(["git", "show", f"FETCH_HEAD:{path}"], cwd=repo, text=True)
    except subprocess.CalledProcessError:
        return None
    try:
        return json.loads(data)
    except Exception as e:
        return {"_parse_error": str(e)}

for path in ["harness/config/logical-operators.json", "harness/config/physical-operators.json"]:
    a = read_worktree(path)
    b = read_fetch_head(path)
    def keys(obj):
        if not isinstance(obj, dict):
            return []
        for k in ["logical_operators", "physical_operators"]:
            if isinstance(obj.get(k), dict):
                return sorted(obj[k])
        return sorted(obj)
    out[path] = {
        "stellven_count": len(keys(a)),
        "autosci_branch_count": len(keys(b)),
        "autosci_only_keys": sorted(set(keys(b)) - set(keys(a)))[:300],
        "stellven_only_keys": sorted(set(keys(a)) - set(keys(b)))[:300],
    }

print(json.dumps(out, indent=2, sort_keys=True))
PY
```

---

# 17. Provider and side-effect readiness

Gather only presence/absence. Do not print secret values.

```bash
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
    "$NATIVE_AUTOSCI_REPO/config/daily-arxiv.yml.example" \
    "$NATIVE_AUTOSCI_REPO/.env" \
    "$OPEN_SOLAR_REPO/.env"
  do
    if [ -e "$f" ]; then
      echo "present: $f"
    else
      echo "absent:  $f"
    fi
  done
} | tee "$INFO_OUT/provider_side_effect_readiness.txt"
```

---

# 18. Native AutoSci full-parity gap inventory

Use native AutoSci reference to summarize major command families and implementation files.

```bash
cd "$NATIVE_AUTOSCI_REPO"

python3 - <<'PY' | tee "$INFO_OUT/native_autosci_command_inventory.json"
import json
from pathlib import Path

skill_dirs = []
for root in [Path(".claude/skills"), Path("i18n/en/skills")]:
    if root.exists():
        for p in sorted(root.glob("*/SKILL.md")):
            skill_dirs.append(str(p))

tools = [str(p) for p in sorted(Path("tools").glob("*.py"))] if Path("tools").exists() else []
runtime = [str(p) for p in sorted(Path("runtime").rglob("*")) if p.is_file()] if Path("runtime").exists() else []

print(json.dumps({
    "skill_files": skill_dirs,
    "tool_files": tools,
    "runtime_files": runtime[:300],
}, indent=2, sort_keys=True))
PY
```

Create a human summary of native features by grepping key terms:

```bash
cd "$NATIVE_AUTOSCI_REPO"

{
  echo "# Native AutoSci keywords"
  for file in \
    .claude/skills/research/SKILL.md \
    .claude/skills/ideate/SKILL.md \
    .claude/skills/exp-run/SKILL.md \
    .claude/skills/paper-draft/SKILL.md \
    .claude/skills/paper-compile/SKILL.md \
    tools/research_wiki.py \
    tools/remote.py
  do
    [ -f "$file" ] || continue
    echo
    echo "===== $file ====="
    grep -nE "Stage|Phase|Gate|resume|checkpoint|remote|screen|rsync|latex|Review LLM|Semantic Scholar|DeepXiv|citation|maturity|transition|checkpoint|paper/|figures|tables|BibTeX|collect|deploy|monitor" "$file" | sed -n '1,220p' || true
  done
} | tee "$INFO_OUT/native_autosci_feature_keywords.txt"
```

---

# 19. Create the final report

Now write:

```text
$INFO_OUT/AUTOSCI_SOLAR_INFO_REPORT.md
```

Use this structure:

```markdown
# AutoSci-on-Solar Information Report

## 1. Executive Summary
- Can start unification branch? yes/no/unknown
- Current AutoSci branch readiness
- Stellven integration risk level
- Full parity risk level
- Biggest blockers

## 2. Repositories
- local paths
- remotes
- branches
- HEAD commits
- dirty status

## 3. System and Tools
- OS
- Python
- Node/Bun
- jq/tmux/pytest
- TeX tools
- rsync/ssh/screen
- provider env presence, redacted

## 4. Current AutoSci Branch Inventory
- plugin files
- route count and status counts
- capabilities
- operators
- schemas
- gates
- workflows
- tests

## 5. Product-Level Dispatch Status
- does solar-harness.sh autosci exist?
- does direct $ dispatch exist?
- wrapper status
- test coverage
- manual smoke result

## 6. Artifact Root and Hygiene
- root policy observed
- test result
- generated artifacts tracked?
- .gitignore status

## 7. Stellven Solar Structure
- CLI structure
- harness structure
- desktop/distribution structure
- likely integration points

## 8. Diff / Merge Risk
- merge base
- stat
- manual merge files
- AutoSci module files to import
- files to exclude
- config key differences

## 9. Native AutoSci Reference Inventory
- command list
- key tools
- hard parity areas

## 10. Recommended Boundaries for Two Agents
- Agent A files
- Agent B files
- conflict risks

## 11. Open Questions for User
- CLI final shape
- provider policy
- demo scope
- backup policy
- branch/push policy

## 12. Attachments
- list files in this info bundle
```

Do not invent. If something is unknown, write `unknown` and explain what command failed or what file was missing.

---

# 20. Final check and output

At the end, run:

```bash
for repo_var in OPEN_SOLAR_REPO STELLVEN_SOLAR_REPO NATIVE_AUTOSCI_REPO; do
  repo="${!repo_var:-}"
  [ -n "$repo" ] || continue
  [ -d "$repo/.git" ] || continue
  {
    echo "============================================================"
    echo "$repo_var=$repo"
    cd "$repo"
    git status --short
  } | tee -a "$INFO_OUT/final_git_status.txt"
done

tar -czf "${INFO_OUT}.tgz" -C "$(dirname "$INFO_OUT")" "$(basename "$INFO_OUT")"

echo "REPORT=$INFO_OUT/AUTOSCI_SOLAR_INFO_REPORT.md"
echo "BUNDLE=${INFO_OUT}.tgz"
```

Final response should be short:

```text
Information gathering complete.

Report:
<path>

Bundle:
<path>

Key status:
- product dispatch tests: pass/fail/not run
- manual smoke: pass/fail/not run
- merge blockers found: <count/list>
- repos changed by this task: yes/no
```

Remember: do not implement fixes. Do not continue migration. Only gather information.
