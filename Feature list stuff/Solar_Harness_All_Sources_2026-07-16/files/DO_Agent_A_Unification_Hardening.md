# DO — Agent A: Unification Hardening / Product Integration

## Work folder and push target

Work in the Stellven/OpenJiuwen Solar repo:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar
```

Use this branch:

```bash
integration/autosci-unification-hardening
```

Push to:

```bash
origin/integration/autosci-unification-hardening
```

Treat these repos as read-only sources unless explicitly needed:

```bash
# AutoSci-on-Solar source/reference
/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar

# Native AutoSci reference
/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci
```

Do **not** push to `openJiuwen-Solar` directly unless the user explicitly tells you to.

---

## Your mission

Make the AutoSci integration in BetterSolar product-ready.

This means:

```text
BetterSolar's Solar runtime can invoke AutoSci capabilities through the product/harness CLI,
write typed Solar evidence,
keep artifacts under the active HARNESS_DIR,
run the product-level AutoSci smoke tests,
and produce a demo-ready status report.
```

This does **not** mean full native AutoSci parity. Agent B owns full-parity work.

Do not implement deep `/ideate`, `/exp-run`, `/paper-draft`, `/paper-compile`, `/poster`, or `/rebuttal` parity unless it is required to keep product-level smoke tests passing.

---

## Background

We are unifying two Solar branches:

```text
BetterSolar / Stellven Solar
  Product/runtime base with bin/solar, installer, dashboard, desktop, distribution.

OpenSolar feature/autosci-solar-native
  AutoSci scientific-runtime integration work.

Native AutoSci
  Full parity reference.
```

The latest information report found:

```text
OpenSolar branch: feature/autosci-solar-native
BetterSolar branch: openJiuwen-Solar
Native AutoSci branch: main

AutoSci route count: 28
Partial routes: 17
Gated routes: 11
Full routes: 0

OpenSolar product-level AutoSci tests passed:
6 passed in 5.29s
```

Your job is to make sure BetterSolar is the single unified Solar runtime with AutoSci product-level command dispatch.

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
2. AutoSci-specific implementation remains under harness/plugins/autosci/.
3. Solar owns workflow semantics, TaskGraphs, capsules, Evidence ABI, gates, resume, and lifecycle acceptance.
4. Product CLI should call AutoSci through Solar harness/shim, not native AutoSci directly.
5. Do not promote route coverage_status to full.
6. Do not remove or break Stellven product/runtime/desktop/distribution behavior.
```

---

## Step 0 — Start clean and create branch

```bash
export STELLVEN_SOLAR_REPO="/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar"
export OPEN_SOLAR_REPO="/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar"
export NATIVE_AUTOSCI_REPO="/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci"

cd "$STELLVEN_SOLAR_REPO"
git status --short
git branch --show-current
git remote -v
git fetch origin
git checkout openJiuwen-Solar
git pull --ff-only || true

# If the branch already exists, check it out instead.
git checkout -b integration/autosci-unification-hardening || git checkout integration/autosci-unification-hardening
```

If there are uncommitted user changes before you start, stop and report them.

---

## Step 1 — Determine whether AutoSci module already exists in BetterSolar

Run:

```bash
cd "$STELLVEN_SOLAR_REPO"

test -f harness/plugins/autosci/manifest.yaml && echo "autosci manifest present" || echo "autosci manifest missing"
test -f harness/plugins/autosci/bin/autosci_skill_shim.py && echo "autosci shim present" || echo "autosci shim missing"
test -f harness/plugins/autosci/bin/autosci_bridge.py && echo "autosci bridge present" || echo "autosci bridge missing"
test -f harness/tools/run_scientific_workflow.py && echo "scientific workflow runner present" || echo "scientific workflow runner missing"
test -f harness/workflows/scientific_research_lifecycle_full_v1.json && echo "scientific workflow present" || echo "scientific workflow missing"
test -f harness/tests/integration/test_autosci_routes_list.py && echo "product AutoSci tests present" || echo "product AutoSci tests missing"
```

If all are present, do **not** re-import blindly. Proceed to verification/hardening.

If any are missing, selectively import the missing AutoSci module pieces from OpenSolar. Do not import generated artifacts.

---

## Step 2 — If needed, import missing AutoSci module pieces

Only do this if Step 1 found missing files.

```bash
cd "$STELLVEN_SOLAR_REPO"

rsync -a --delete \
  "$OPEN_SOLAR_REPO/harness/plugins/autosci/" \
  "$STELLVEN_SOLAR_REPO/harness/plugins/autosci/"

mkdir -p "$STELLVEN_SOLAR_REPO/harness/tools"
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

---

## Step 3 — Verify shared registries/configs

Run these checks:

```bash
cd "$STELLVEN_SOLAR_REPO"

python3 -m json.tool harness/config/logical-operators.json >/tmp/logical.ok.json
python3 -m json.tool harness/config/physical-operators.json >/tmp/physical.ok.json

python3 - <<'PY'
import yaml
from pathlib import Path
yaml.safe_load(Path("harness/config/capability-capsules.registry.yaml").read_text())
print("capability registry yaml ok")
PY
```

Verify required AutoSci keys:

```bash
grep -q "ScientificExperimentRunner" harness/config/logical-operators.json
grep -q "ScientificPublicationProducer" harness/config/logical-operators.json
grep -q "autosci-experiment-run-worker" harness/config/physical-operators.json
grep -q "autosci-publication-compile-worker" harness/config/physical-operators.json
grep -q "cap.research-experiment-run" harness/config/capability-capsules.registry.yaml
grep -q "cap.research-publication-produce" harness/config/capability-capsules.registry.yaml
```

If a key is missing, import only the missing `Scientific*`, `autosci-*`, or `cap.research-*` entries from OpenSolar. Do not overwrite whole config files.

---

## Step 4 — Verify product-level AutoSci dispatch

Run:

```bash
cd "$STELLVEN_SOLAR_REPO/harness"

bash solar-harness.sh autosci '$skills'
bash solar-harness.sh autosci '$review --help'
bash solar-harness.sh autosci '$ingest --help'
bash solar-harness.sh autosci '$research --help'
```

Also verify direct `$...` convenience dispatch if supported:

```bash
bash solar-harness.sh '$review --help'
```

If direct `$...` fails but explicit `autosci '$cmd'` works, document it. Explicit `autosci` form is required; direct `$...` is optional.

Verify product CLI forwarding if `bin/solar` is usable in this checkout:

```bash
cd "$STELLVEN_SOLAR_REPO"
bin/solar harness autosci '$skills' || true
bin/solar harness autosci '$review --help' || true
```

If `bin/solar` fails because install receipt or SOLAR_HOME is missing, document the reason. Do not rewrite unrelated lifecycle behavior unless the forwarding path itself is wrong.

---

## Step 5 — Run required product-level tests

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

Expected result:

```text
6 passed
```

If tests fail, fix product integration, artifact-root handling, or path assumptions. Do not implement unrelated deep parity.

---

## Step 6 — Run manual isolated smoke

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
- $review --help reaches AutoSci shim.
- $ingest writes research_paper.v1.
- $research --scheduler-run writes scientific_lifecycle.v1.
- All outputs remain under $SMOKE_HARNESS.
```

---

## Step 7 — Artifact hygiene

Check tracked generated files:

```bash
cd "$STELLVEN_SOLAR_REPO"

git ls-files 'harness/artifacts/autosci/runs/*'
git ls-files 'harness/artifacts/autosci/operator-smoke/*'
git ls-files 'harness/artifacts/autosci/phase19/current-parity-inventory-*.json'
git ls-files 'harness/artifacts/scientific/workflow-runs/*'
git ls-files '*.DS_Store'
git ls-files '.solar-backups/*'
```

Update `.gitignore` if needed:

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

If generated artifacts are tracked, remove them from index only:

```bash
git rm --cached <file>
```

Do not delete user data from disk without permission.

---

## Step 8 — Add or update demo/status docs

Create or update:

```text
harness/scripts/autosci-demo-smoke.sh
docs/integrations/autosci/unification-status.md
```

`unification-status.md` must include:

```text
- branch name and HEAD
- AutoSci module present/missing check
- commands tested
- pytest result
- manual smoke result
- artifact-root behavior
- known limitations
- explicit statement: full native AutoSci parity is not complete
```

Allowed boss-facing statement:

```text
Integrated Solar now has product-level AutoSci capabilities enabled.
Full native AutoSci parity continues in parallel.
```

Forbidden statement:

```text
AutoSci full parity is complete.
```

---

## Step 9 — Commit and push

After tests pass or after a clear blocked report is written:

```bash
cd "$STELLVEN_SOLAR_REPO"
git status --short
git add \
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
  harness/solar-harness.sh \
  harness/config/logical-operators.json \
  harness/config/physical-operators.json \
  harness/config/capability-capsules.registry.yaml \
  .gitignore \
  harness/scripts/autosci-demo-smoke.sh

git commit -m "feat(autosci): harden product-level AutoSci integration"

git push -u origin integration/autosci-unification-hardening
```

If a file does not exist, remove it from the `git add` command. Do not add generated runtime artifacts.

---

## Final response required from Agent A

Report:

```text
- working folder
- branch
- push target
- HEAD commit
- whether product tests passed
- whether manual smoke passed
- whether bin/solar path passed or why it did not
- files changed
- remaining blockers
- final git status
```

---

## Agent A definition of done

```text
[ ] Branch integration/autosci-unification-hardening exists in BetterSolar.
[ ] Branch is pushed to origin.
[ ] AutoSci module exists in BetterSolar.
[ ] Product-level tests pass or failures are documented.
[ ] Manual isolated smoke passes or failure is documented.
[ ] `solar-harness.sh autosci '$skills'` works.
[ ] `solar-harness.sh autosci '$research ... --scheduler-run'` works.
[ ] Outputs stay under active HARNESS_DIR.
[ ] Demo/status docs exist.
[ ] Full parity is not falsely claimed.
```
