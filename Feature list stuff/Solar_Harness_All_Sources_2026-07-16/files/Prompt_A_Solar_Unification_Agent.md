# Agent A Prompt — Solar Unification / Product Integration

## Working folder

You must work primarily in the Stellven/OpenJiuwen Solar repo:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar
```

Use the current AutoSci integration repo as a **read-only source**:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar
```

Use native AutoSci only as a **read-only reference** if needed:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci
```

Do not implement deep AutoSci parity in this task. Your task is unification only.

---

## Mission

Port the AutoSci scientific-runtime module from:

```text
Coconut-ch1ken/OpenSolar
branch: feature/autosci-solar-native
local path: /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar
```

into the productized Stellven/OpenJiuwen Solar runtime:

```text
Stellven/AI4Research
branch: openJiuwen-Solar
local path: /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar
```

Create an integration branch, wire product-level AutoSci command dispatch, merge registries/configs safely, run product-level integration tests, and produce a concise integration report.

Your goal is:

```text
One Solar runtime with AutoSci capabilities enabled at the product CLI/harness level.
```

Your goal is **not**:

```text
100% native AutoSci parity.
```

That work is assigned to Agent B.

---

## Background

There are three relevant repos:

```text
1. Native AutoSci
   Path: /Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci
   Role: full parity reference only.

2. Current AutoSci-on-Solar integration branch
   Path: /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar
   Branch: feature/autosci-solar-native
   Role: contains the AutoSci module to import.

3. Stellven/OpenJiuwen Solar product runtime
   Path: /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar
   Branch: openJiuwen-Solar
   Role: product/runtime base.
```

The information-gathering report found:

```text
OpenSolar HEAD:
  9d68c5baa feature/autosci-solar-native

BetterSolar HEAD:
  cdc7e903 openJiuwen-Solar

AutoSci route inventory:
  route_count = 28
  partial = 17
  gated = 11
  full = 0

Product-level AutoSci tests in OpenSolar:
  6 passed in 5.29s

BetterSolar currently lacks these AutoSci module paths:
  harness/plugins/autosci
  harness/tools/run_scientific_workflow.py
  harness/tools/run_scientific_node_smoke.py
  harness/tools/run_scientific_lifecycle_smoke.py
  harness/workflows/scientific_research_lifecycle_full_v1.json
  harness/evaluators/scientific
  harness/schemas/evidence
  .agents/skills
  docs/integrations/autosci
```

Shared files requiring manual merge:

```text
README.md
AGENTS.md
CLAUDE.md
bin/solar
harness/solar-harness.sh
core/daemon/skill-dispatcher.ts
harness/config/logical-operators.json
harness/config/physical-operators.json
harness/config/capability-capsules.registry.yaml
.gitignore
```

The AutoSci branch adds:

```text
19 Scientific* logical operators
19 autosci-* physical workers
cap.research-* capability capsules
product-level AutoSci dispatch
product-level AutoSci integration tests
```

---

## Non-negotiable architecture

Preserve this architecture:

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

Rules:

```text
1. Do not create a black-box AutoSciRunner.
2. Do not let native AutoSci own the workflow.
3. AutoSci-specific implementation belongs under harness/plugins/autosci/.
4. Solar owns workflow semantics, TaskGraphs, capsules, Evidence ABI, gates, and lifecycle acceptance.
5. Product CLI must call AutoSci through Solar harness/shim, not by directly mutating native AutoSci paths.
6. Do not promote route coverage_status to full.
7. Do not delete or overwrite Stellven product/runtime/desktop/distribution functionality.
```

---

## Safety constraints

Do not:

```text
- push without user approval;
- merge into openJiuwen-Solar directly;
- overwrite shared JSON/YAML configs wholesale;
- delete user uncommitted files;
- import generated runtime artifacts;
- edit native AutoSci repo;
- implement deep full-parity features;
- run real remote experiments;
- send email;
- write secrets;
- mark partial/gated routes as full.
```

Allowed:

```text
- create an integration branch in BetterSolar;
- import AutoSci module paths selectively;
- manually merge shared configs;
- add product CLI dispatch;
- add/adjust integration tests;
- update .gitignore;
- run local tests and isolated smokes;
- produce an integration report.
```

---

## Step 0 — Confirm current state

```bash
export OPEN_SOLAR_REPO="/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar"
export STELLVEN_SOLAR_REPO="/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar"
export NATIVE_AUTOSCI_REPO="/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci"

cd "$OPEN_SOLAR_REPO"
git status --short
git branch --show-current
git rev-parse HEAD

cd "$STELLVEN_SOLAR_REPO"
git status --short
git branch --show-current
git rev-parse HEAD

cd "$NATIVE_AUTOSCI_REPO"
git status --short
git branch --show-current
git rev-parse HEAD
```

If BetterSolar has uncommitted user changes, stop and report. Do not proceed without confirming whether those changes should be preserved.

OpenSolar may have dirty runtime/local files. Treat it as read-only source; do not clean it.

---

## Step 1 — Create the integration branch in BetterSolar

```bash
cd "$STELLVEN_SOLAR_REPO"
git checkout openJiuwen-Solar
git pull --ff-only || true
git checkout -b integration/autosci-on-openjiuwen-solar
```

If the branch already exists:

```bash
git checkout integration/autosci-on-openjiuwen-solar
```

Record:

```bash
git status --short
git log -1 --oneline --decorate
```

---

## Step 2 — Import AutoSci module paths selectively

Use `rsync` from OpenSolar into BetterSolar. Do not import generated artifacts.

```bash
cd "$STELLVEN_SOLAR_REPO"

rsync -a --delete \
  "$OPEN_SOLAR_REPO/harness/plugins/autosci/" \
  "$STELLVEN_SOLAR_REPO/harness/plugins/autosci/"

rsync -a \
  "$OPEN_SOLAR_REPO/harness/tools/run_scientific_workflow.py" \
  "$OPEN_SOLAR_REPO/harness/tools/run_scientific_node_smoke.py" \
  "$OPEN_SOLAR_REPO/harness/tools/run_scientific_lifecycle_smoke.py" \
  "$STELLVEN_SOLAR_REPO/harness/tools/"

mkdir -p "$STELLVEN_SOLAR_REPO/harness/workflows"
rsync -a \
  "$OPEN_SOLAR_REPO/harness/workflows/scientific_"*.json \
  "$STELLVEN_SOLAR_REPO/harness/workflows/"

mkdir -p "$STELLVEN_SOLAR_REPO/harness/evaluators/scientific"
rsync -a --delete \
  "$OPEN_SOLAR_REPO/harness/evaluators/scientific/" \
  "$STELLVEN_SOLAR_REPO/harness/evaluators/scientific/"

mkdir -p "$STELLVEN_SOLAR_REPO/harness/schemas/evidence"
rsync -a \
  "$OPEN_SOLAR_REPO/harness/schemas/evidence/"*.schema.json \
  "$STELLVEN_SOLAR_REPO/harness/schemas/evidence/"

mkdir -p "$STELLVEN_SOLAR_REPO/harness/capability-capsules"
rsync -a \
  "$OPEN_SOLAR_REPO/harness/capability-capsules/cap.research-"*.yaml \
  "$STELLVEN_SOLAR_REPO/harness/capability-capsules/"

mkdir -p "$STELLVEN_SOLAR_REPO/harness/tests/integration"
rsync -a \
  "$OPEN_SOLAR_REPO/harness/tests/integration/autosci_product_smoke_helpers.py" \
  "$OPEN_SOLAR_REPO/harness/tests/integration/test_autosci_"*.py \
  "$STELLVEN_SOLAR_REPO/harness/tests/integration/"

mkdir -p "$STELLVEN_SOLAR_REPO/.agents"
rsync -a --delete \
  "$OPEN_SOLAR_REPO/.agents/skills/" \
  "$STELLVEN_SOLAR_REPO/.agents/skills/"

mkdir -p "$STELLVEN_SOLAR_REPO/docs/integrations/autosci"
rsync -a \
  --exclude='*/runs/*' \
  --exclude='*/operator-smoke/*' \
  --exclude='current-parity-inventory-*.json' \
  "$OPEN_SOLAR_REPO/docs/integrations/autosci/" \
  "$STELLVEN_SOLAR_REPO/docs/integrations/autosci/"
```

After import:

```bash
git status --short
```

Do not commit yet.

---

## Step 3 — Merge shared configs manually

Do not overwrite BetterSolar’s configs. Merge additions.

### 3.1 Logical operators

Need to add the 19 `Scientific*` logical operators from OpenSolar into:

```text
harness/config/logical-operators.json
```

Required keys:

```text
ScientificArtifactReviewer
ScientificClaimExtractor
ScientificClaimVerifier
ScientificCodeEvidenceMapper
ScientificExperimentDesigner
ScientificExperimentMonitor
ScientificExperimentRunner
ScientificGraphUpdater
ScientificIdeaEvaluator
ScientificIdeaGenerator
ScientificLiteratureDiscoverer
ScientificMemoryUpdater
ScientificMethodExtractor
ScientificPaperAnalyzer
ScientificPaperIngestor
ScientificPublicationProducer
ScientificReportDrafter
ScientificReportPlanner
ScientificWorkflowEvolver
```

Use a script or careful manual merge. Preserve all BetterSolar existing keys.

Suggested safe script:

```bash
cd "$STELLVEN_SOLAR_REPO"

python3 - <<'PY'
import json
from pathlib import Path
import os

src = Path(os.environ["OPEN_SOLAR_REPO"]) / "harness/config/logical-operators.json"
dst = Path("harness/config/logical-operators.json")

a = json.loads(src.read_text())
b = json.loads(dst.read_text())

def get_ops(x):
    return x["logical_operators"] if "logical_operators" in x else x

src_ops = get_ops(a)
dst_ops = get_ops(b)

added = []
for k, v in src_ops.items():
    if k.startswith("Scientific") and k not in dst_ops:
        dst_ops[k] = v
        added.append(k)

dst.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
print("added logical operators:", added)
PY
```

Validate:

```bash
python3 -m json.tool harness/config/logical-operators.json >/tmp/logical.ok.json
```

### 3.2 Physical operators

Need to add the 19 `autosci-*` physical workers into:

```text
harness/config/physical-operators.json
```

Required keys:

```text
autosci-artifact-review-worker
autosci-claim-extract-worker
autosci-claim-verify-worker
autosci-code-evidence-map-worker
autosci-experiment-design-worker
autosci-experiment-monitor-worker
autosci-experiment-run-worker
autosci-graph-update-worker
autosci-idea-evaluate-worker
autosci-idea-worker
autosci-literature-discover-worker
autosci-memory-update-worker
autosci-method-extract-worker
autosci-paper-analyze-worker
autosci-paper-ingest-worker
autosci-publication-compile-worker
autosci-report-plan-worker
autosci-report-worker
autosci-workflow-evolve-worker
```

Preserve BetterSolar-only key:

```text
mini-codex-gpt55-medium-evaluator-1
```

Suggested safe script:

```bash
cd "$STELLVEN_SOLAR_REPO"

python3 - <<'PY'
import json
from pathlib import Path
import os

src = Path(os.environ["OPEN_SOLAR_REPO"]) / "harness/config/physical-operators.json"
dst = Path("harness/config/physical-operators.json")

a = json.loads(src.read_text())
b = json.loads(dst.read_text())

def get_ops(x):
    return x["physical_operators"] if "physical_operators" in x else x

src_ops = get_ops(a)
dst_ops = get_ops(b)

added = []
for k, v in src_ops.items():
    if k.startswith("autosci-") and k not in dst_ops:
        dst_ops[k] = v
        added.append(k)

dst.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
print("added physical operators:", added)
PY
```

Validate:

```bash
python3 -m json.tool harness/config/physical-operators.json >/tmp/physical.ok.json
```

### 3.3 Capability registry

Need to add the `cap.research-*` entries from OpenSolar into:

```text
harness/config/capability-capsules.registry.yaml
```

Required capabilities:

```text
cap.research-literature-discover
cap.research-paper-ingest
cap.research-paper-analyze
cap.research-memory-update
cap.research-graph-update
cap.research-claim-extract
cap.research-method-extract
cap.research-code-evidence-map
cap.research-idea-generate
cap.research-idea-evaluate
cap.research-experiment-design
cap.research-experiment-run
cap.research-experiment-monitor
cap.research-claim-verify
cap.research-report-plan
cap.research-report-draft
cap.research-artifact-review
cap.research-publication-produce
cap.research-workflow-evolve
```

Suggested safe script:

```bash
cd "$STELLVEN_SOLAR_REPO"

python3 - <<'PY'
import os
from pathlib import Path
import yaml

src = Path(os.environ["OPEN_SOLAR_REPO"]) / "harness/config/capability-capsules.registry.yaml"
dst = Path("harness/config/capability-capsules.registry.yaml")

a = yaml.safe_load(src.read_text())
b = yaml.safe_load(dst.read_text())

src_items = (a.get("capsules") or {}).get("capability") or []
dst_capsules = b.setdefault("capsules", {})
dst_items = dst_capsules.setdefault("capability", [])

existing = {
    item.get("capability_capsule_id")
    for item in dst_items
    if isinstance(item, dict)
}

added = []
for item in src_items:
    if not isinstance(item, dict):
        continue
    cap = item.get("capability_capsule_id")
    if not str(cap).startswith("cap.research-"):
        continue
    if cap not in existing:
        dst_items.append(item)
        existing.add(cap)
        added.append(cap)

dst.write_text(yaml.safe_dump(b, sort_keys=False, allow_unicode=True))
print("added capabilities:", added)
PY
```

Validate:

```bash
python3 - <<'PY'
import yaml
from pathlib import Path
yaml.safe_load(Path("harness/config/capability-capsules.registry.yaml").read_text())
print("capability registry yaml ok")
PY
```

Then verify all required capabilities:

```bash
python3 - <<'PY'
import yaml
from pathlib import Path

required = {
"cap.research-literature-discover",
"cap.research-paper-ingest",
"cap.research-paper-analyze",
"cap.research-memory-update",
"cap.research-graph-update",
"cap.research-claim-extract",
"cap.research-method-extract",
"cap.research-code-evidence-map",
"cap.research-idea-generate",
"cap.research-idea-evaluate",
"cap.research-experiment-design",
"cap.research-experiment-run",
"cap.research-experiment-monitor",
"cap.research-claim-verify",
"cap.research-report-plan",
"cap.research-report-draft",
"cap.research-artifact-review",
"cap.research-publication-produce",
"cap.research-workflow-evolve",
}

payload = yaml.safe_load(Path("harness/config/capability-capsules.registry.yaml").read_text())
items = payload.get("capsules", {}).get("capability", [])
have = {i.get("capability_capsule_id") for i in items if isinstance(i, dict)}
missing = sorted(required - have)
print("missing:", missing)
raise SystemExit(1 if missing else 0)
PY
```

---

## Step 4 — Wire product-level AutoSci CLI dispatch

You must port the AutoSci dispatch behavior into BetterSolar’s harness/product CLI.

OpenSolar currently has this behavior in `harness/solar-harness.sh`:

```text
do_autosci_command()
case autosci) do_autosci_command "$@" ;;
case $*)      do_autosci_command "$@" ;;
```

Implement the equivalent in BetterSolar.

Required behavior:

```bash
bash harness/solar-harness.sh autosci '$skills'
bash harness/solar-harness.sh autosci '$review --help'
bash harness/solar-harness.sh autosci '$ingest --help'
bash harness/solar-harness.sh autosci '$research --help'
```

If BetterSolar’s `bin/solar` is the product CLI, then also wire:

```bash
bin/solar harness autosci '$skills'
bin/solar harness autosci '$review --help'
```

Minimum harness implementation:

```bash
do_autosci_command() {
  local script_harness_dir shim py candidate command_text
  script_harness_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  shim="$script_harness_dir/plugins/autosci/bin/autosci_skill_shim.py"
  if [[ ! -f "$shim" ]]; then
    shim="$HARNESS_DIR/plugins/autosci/bin/autosci_skill_shim.py"
  fi
  if [[ ! -f "$shim" ]]; then
    err "AutoSci shim not found: $HARNESS_DIR/plugins/autosci/bin/autosci_skill_shim.py"
    exit 1
  fi

  export HARNESS_DIR
  export SOLAR_AUTOSCI_OUTPUT_HARNESS="${SOLAR_AUTOSCI_OUTPUT_HARNESS:-$HARNESS_DIR}"
  export AUTOSCI_ARTIFACT_ROOT="${AUTOSCI_ARTIFACT_ROOT:-$HARNESS_DIR/artifacts/autosci}"
  export SCIENTIFIC_ARTIFACT_ROOT="${SCIENTIFIC_ARTIFACT_ROOT:-$HARNESS_DIR/artifacts/scientific}"

  py=""
  for candidate in "$HARNESS_DIR/bin/python3" "$script_harness_dir/bin/python3" python3; do
    if [[ "$candidate" == "python3" ]]; then
      command -v python3 >/dev/null 2>&1 || continue
    elif [[ ! -x "$candidate" ]]; then
      continue
    fi
    if "$candidate" -c 'import sys' >/dev/null 2>&1; then
      py="$candidate"
      break
    fi
  done
  if [[ -z "$py" ]]; then
    err "No usable python3 found for AutoSci shim"
    exit 1
  fi

  if [[ "$#" -eq 0 ]]; then
    "$py" "$shim" skills list
    return
  fi

  case "${1:-}" in
    skills|skill)
      "$py" "$shim" "$@"
      ;;
    *)
      command_text="$*"
      "$py" "$shim" text "$command_text"
      ;;
  esac
}
```

Add dispatch cases:

```bash
autosci)
  shift || true
  do_autosci_command "$@"
  ;;

\$*)
  do_autosci_command "$@"
  ;;
```

If BetterSolar’s command dispatcher has a different shape, adapt the same behavior without breaking existing commands.

---

## Step 5 — Keep `.agents/skills` wrappers explicit

Ensure wrappers say to use:

```bash
solar-harness.sh autosci '$review <user args>'
```

or final BetterSolar equivalent:

```bash
solar harness autosci '$review <user args>'
```

Do not leave wrappers that only say:

```bash
solar-harness.sh '$review'
```

unless you have verified direct `$...` dispatch works in the product CLI.

---

## Step 6 — Update `.gitignore`

Add or verify:

```gitignore
harness/artifacts/autosci/runs/
harness/artifacts/autosci/phase19/current-parity-inventory-*.json
harness/artifacts/autosci/operator-smoke/
harness/artifacts/scientific/workflow-runs/
harness/.coordinator*
harness/.watchdog*
harness/.pane-*
harness/PLANNER-INBOX.md
.solar-backups/
.DS_Store
```

Then run:

```bash
git ls-files 'harness/artifacts/autosci/runs/*'
git ls-files 'harness/artifacts/autosci/operator-smoke/*'
git ls-files 'harness/artifacts/autosci/phase19/current-parity-inventory-*.json'
git ls-files 'harness/artifacts/scientific/workflow-runs/*'
git ls-files '*.DS_Store'
git ls-files '.solar-backups/*'
```

Remove tracked generated artifacts from index only if they exist in the BetterSolar integration branch:

```bash
git rm --cached <file>
```

Do not delete user files from disk unless explicitly approved.

---

## Step 7 — Run integration tests

From BetterSolar harness:

```bash
cd "$STELLVEN_SOLAR_REPO/harness"

python3 -m pytest -q \
  tests/integration/test_autosci_routes_list.py \
  tests/integration/test_autosci_cli_dispatch.py \
  tests/integration/test_autosci_ingest_demo.py \
  tests/integration/test_autosci_review_demo.py \
  tests/integration/test_autosci_research_scheduler_demo.py \
  tests/integration/test_autosci_artifact_root.py
```

Expected:

```text
6 passed
```

If a test fails because of BetterSolar path differences, fix the integration layer, not the AutoSci test’s safety intent.

---

## Step 8 — Manual smoke test in BetterSolar

Use an isolated harness root:

```bash
cd "$STELLVEN_SOLAR_REPO/harness"

SMOKE_HARNESS="/tmp/bettersolar_autosci_smoke_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$SMOKE_HARNESS"

for name in bin config personas tools plugins evaluators schemas lib templates workflows; do
  [ -e "$PWD/$name" ] && ln -s "$PWD/$name" "$SMOKE_HARNESS/$name"
done

mkdir -p "$SMOKE_HARNESS/run" "$SMOKE_HARNESS/artifacts" "$SMOKE_HARNESS/raw"

cat > "$SMOKE_HARNESS/raw/demo-paper.md" <<'EOF'
# Demo Paper

## Abstract
This paper checks product-level AutoSci dispatch in unified Solar.

## Method
The test should produce typed evidence under the active HARNESS_DIR.

## Results
The test should write research_paper.v1 and scientific_lifecycle.v1 artifacts.
EOF

HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci '$skills'

HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci \
  '$review --help'

HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci \
  "\$ingest --paper $SMOKE_HARNESS/raw/demo-paper.md --run-id unified-demo-ingest"

HARNESS_DIR="$SMOKE_HARNESS" bash "$PWD/solar-harness.sh" autosci \
  "\$research unified demo --paper $SMOKE_HARNESS/raw/demo-paper.md --scheduler-run --scheduler-timeout 20 --run-id unified-demo-research"

find "$SMOKE_HARNESS/artifacts" -maxdepth 5 -type f | sort | sed -n '1,160p'
```

Success criteria:

```text
- $skills returns 28 routes.
- $review --help reaches shim.
- $ingest writes research_paper.v1.
- $research --scheduler-run writes scientific_lifecycle.v1.
- All outputs remain under $SMOKE_HARNESS.
```

---

## Step 9 — Prepare a short integration report

Create:

```text
docs/integrations/autosci/unification-status.md
```

Include:

```text
- branch name;
- source OpenSolar commit;
- BetterSolar base commit;
- files imported;
- configs manually merged;
- tests run;
- manual smoke commands;
- pass/fail status;
- known limitations;
- routes still partial/gated;
- next handoff to Agent B.
```

Do not claim full parity. Use wording:

```text
AutoSci capabilities are product-callable inside the unified Solar runtime.
Full native AutoSci parity remains in progress.
```

---

## Step 10 — Final output expected from Agent A

Your final response should include:

```text
1. Working folder used.
2. Branch created.
3. Files/directories imported.
4. Shared configs merged.
5. CLI paths verified.
6. Test commands and results.
7. Manual smoke command and result.
8. Remaining blockers, if any.
9. Git status.
10. Whether it is ready for user review / PR.
```

Do not push unless explicitly told.

---

## Agent A definition of done

This task is complete when all are true:

```text
[ ] Work is on BetterSolar integration branch.
[ ] AutoSci module exists under BetterSolar harness/plugins/autosci.
[ ] Scientific schemas/gates/workflows/tools are imported.
[ ] Scientific logical operators are merged.
[ ] autosci-* physical workers are merged.
[ ] cap.research-* capsules are merged.
[ ] Product CLI or harness supports `autosci '$cmd'`.
[ ] Product-level AutoSci tests pass.
[ ] Manual isolated smoke passes.
[ ] Generated artifacts are not tracked.
[ ] Integration report exists.
[ ] Full parity is not falsely claimed.
```
