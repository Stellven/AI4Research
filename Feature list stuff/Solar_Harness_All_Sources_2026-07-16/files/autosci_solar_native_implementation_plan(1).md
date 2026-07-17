# AutoSci → Solar-Native Scientific Research Runtime Implementation Plan

**Audience:** coding agent working in `Stellven/OpenSolar` with optional access to a local checkout of `skyllwt/AutoSci`.

**Goal:** integrate *all* AutoSci capabilities into Solar as native scientific research capabilities while keeping a clean capsule structure. AutoSci-specific code should remain in an implementation/backend package that is governed by Solar-native capability capsules, operators, TaskGraphs, evidence schemas, and gates.

---

## 0. Non-negotiable architecture model

Use this model for every capability:

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

### Meaning of each layer

| Layer | Role | Where it should live |
|---|---|---|
| TaskGraph node | Schedules a specific unit of scientific work | `harness/workflows/` or existing TaskGraph template location |
| Logical operator | Describes semantic work, for example `ScientificClaimExtractor` | `harness/config/logical-operators.json` |
| Capability capsule | Declares capability contract, inputs, outputs, effects, bindings, verification | `harness/capability-capsules/*.yaml` and `harness/config/capability-capsules.registry.yaml` |
| Physical operator | Concrete execution surface, for example AutoSci-backed local worker, Claude/Codex worker, deterministic runner | `harness/config/physical-operators.json` |
| Implementation package | AutoSci-specific bridge code, parsers, shims, fixtures | `harness/plugins/autosci/` |
| Command | Concrete command run by a physical operator | Usually invokes `harness/plugins/autosci/bin/autosci_bridge.py` or a non-AutoSci backend |
| Evidence ABI | Typed output contract for every node | `harness/schemas/evidence/*.schema.json` |
| Gate | Deterministic or bounded evaluator that accepts/rejects/inconclusive | `harness/evaluators/scientific/` or existing evaluator location |

### Critical design rules

1. **Do not create a black-box `AutoSciRunner` that owns the workflow.**
2. **Do not move AutoSci-specific implementation details into Solar control-plane core.**
3. **Do move AutoSci workflow semantics into Solar-native operators, capsules, TaskGraphs, manuals, Evidence ABI schemas, and gates.**
4. **Capsules should mostly use generic research capability names**, such as `cap.research-claim-extract`, not `cap.autosci-claim-extract`.
5. **The AutoSci plugin/package is a backend implementation package**, not the owner of the scientific workflow.
6. **Every phase must leave a human-testable artifact or command.**
7. **If a node cannot be verified with evidence, it is not complete.**

---

## 1. Required repository orientation commands

The coding agent should run these before modifying files. Replace paths as needed.

```bash
# Set local repository paths. Adjust if the checkouts already exist elsewhere.
export SOLAR_REPO="/path/to/OpenSolar"
export AUTOSCI_REPO="/path/to/AutoSci"

# Optional: clone if missing.
# git clone https://github.com/Stellven/OpenSolar.git "$SOLAR_REPO"
# git clone https://github.com/skyllwt/AutoSci.git "$AUTOSCI_REPO"

cd "$SOLAR_REPO"
pwd
git status --short

# Read Solar's top-level architecture/context.
sed -n '1,240p' README.md
sed -n '1,260p' docs/solar-architecture-code-map.md

# Inspect Solar Harness extension/control surfaces.
cd "$SOLAR_REPO/harness"
sed -n '1,240p' schemas/plugin.schema.json
sed -n '1,300p' lib/plugin_loader.py
sed -n '1,360p' config/logical-operators.json
sed -n '1,360p' config/physical-operators.json
sed -n '1,260p' config/capability-capsules.registry.yaml
sed -n '1,260p' schemas/draft/capability-capsule.v1.draft.json

# Inspect existing harness layout before adding directories.
find . -maxdepth 3 -type d | sort | sed -n '1,240p'
find . -maxdepth 3 -type f | sort | sed -n '1,240p'

# Inspect AutoSci source/workflows.
cd "$AUTOSCI_REPO"
pwd
git status --short
sed -n '1,260p' README.md
find . -maxdepth 4 -type f | sort | grep -E '(README|\.md$|\.py$|\.ya?ml$|\.json$)' | sed -n '1,360p'
```

---

## 2. Target native capability coverage

After all phases, Solar should natively cover these AutoSci-derived capability groups:

| AutoSci-derived capability group | Solar-native capability | Main logical operator |
|---|---|---|
| Paper ingestion | `cap.research-paper-ingest` | `ScientificPaperIngestor` |
| Literature discovery | `cap.research-literature-discover` | `ScientificLiteratureDiscoverer` |
| Research memory/wiki update | `cap.research-memory-update` | `ScientificMemoryUpdater` |
| Citation/relationship graph update | `cap.research-graph-update` | `ScientificGraphUpdater` |
| Paper analysis | `cap.research-paper-analyze` | `ScientificPaperAnalyzer` |
| Claim/hypothesis extraction | `cap.research-claim-extract` | `ScientificClaimExtractor` |
| Method extraction | `cap.research-method-extract` | `ScientificMethodExtractor` |
| Code evidence mapping | `cap.research-code-evidence-map` | `ScientificCodeEvidenceMapper` |
| Idea generation | `cap.research-idea-generate` | `ScientificIdeaGenerator` |
| Novelty/feasibility evaluation | `cap.research-idea-evaluate` | `ScientificIdeaEvaluator` |
| Experiment design | `cap.research-experiment-design` | `ScientificExperimentDesigner` |
| Experiment run/deploy/collect | `cap.research-experiment-run` | `ScientificExperimentRunner` |
| Experiment monitoring/resume | `cap.research-experiment-monitor` | `ScientificExperimentMonitor` |
| Claim verification/verdict | `cap.research-claim-verify` | `ScientificClaimVerifier` |
| Report planning | `cap.research-report-plan` | `ScientificReportPlanner` |
| Report drafting | `cap.research-report-draft` | `ScientificReportDrafter` |
| Publication/poster/rebuttal production | `cap.research-publication-produce` | `ScientificPublicationProducer` |
| Workflow evolution / self-improvement | `cap.research-workflow-evolve` | `ScientificWorkflowEvolver` |

---

# Phase 0 — Workflow inventory and decomposition

## Goal

Understand AutoSci deeply enough to decompose it into native Solar stages. This phase is documentation-first and should not implement runtime behavior yet.

## Directory/context commands

```bash
cd "$AUTOSCI_REPO"
sed -n '1,260p' README.md
find . -maxdepth 4 -type f | sort | grep -E '(README|\.md$|\.py$|\.ya?ml$|\.json$)' | sed -n '1,500p'

cd "$SOLAR_REPO"
mkdir -p docs/integrations/autosci
```

## Deliverables

Create:

```text
docs/integrations/autosci/autosci-workflow-map.md
docs/integrations/autosci/autosci-to-solar-capability-map.yaml
docs/integrations/autosci/autosci-artifact-map.yaml
```

## Required content

Each AutoSci workflow step must be mapped as:

```yaml
autosci_step: <command/skill/module>
purpose: <what this step does>
inputs: []
outputs: []
internal_mechanism: <brief but concrete>
state_or_memory_touched: []
failure_modes: []
solar_logical_operator: <Scientific...>
solar_capsule: <cap.research-...>
solar_evidence_abi: <schema.v1>
human_test: <how to manually verify>
```

## Human test

A reviewer checks:

```text
[ ] Every known AutoSci workflow is represented.
[ ] Every workflow maps to a native Solar logical operator.
[ ] Every workflow maps to a native Solar capability capsule.
[ ] Every workflow maps to a typed output artifact.
[ ] There is no proposed giant AutoSciRunner workflow owner.
[ ] AutoSci-specific mechanics are separated from Solar-native semantics.
```

## Done when

The human reviewer can explain AutoSci's workflow as a Solar-native TaskGraph without saying “just call AutoSci.”

---

# Phase 1 — Canonical Scientific Evidence ABI schemas

## Goal

Create stable artifact contracts before implementing the runtime. Operators, capsules, TaskGraphs, and gates will depend on these schemas.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
mkdir -p schemas/evidence schemas/evidence/fixtures
sed -n '1,260p' schemas/draft/capability-capsule.v1.draft.json
find schemas -maxdepth 3 -type f | sort | sed -n '1,240p'
```

## Deliverables

Create:

```text
harness/schemas/evidence/research_paper.v1.schema.json
harness/schemas/evidence/literature_discovery.v1.schema.json
harness/schemas/evidence/research_memory_update.v1.schema.json
harness/schemas/evidence/research_graph_update.v1.schema.json
harness/schemas/evidence/research_claims.v1.schema.json
harness/schemas/evidence/research_method.v1.schema.json
harness/schemas/evidence/code_evidence_map.v1.schema.json
harness/schemas/evidence/idea_candidate.v1.schema.json
harness/schemas/evidence/idea_evaluation.v1.schema.json
harness/schemas/evidence/experiment_plan.v1.schema.json
harness/schemas/evidence/experiment_status.v1.schema.json
harness/schemas/evidence/experiment_result.v1.schema.json
harness/schemas/evidence/claim_verdict.v1.schema.json
harness/schemas/evidence/scientific_report.v1.schema.json
harness/schemas/evidence/publication_bundle.v1.schema.json
harness/schemas/evidence/workflow_evolution.v1.schema.json
```

Create fixtures for at least:

```text
harness/schemas/evidence/fixtures/sample_research_paper.v1.json
harness/schemas/evidence/fixtures/sample_research_claims.v1.json
harness/schemas/evidence/fixtures/sample_experiment_plan.v1.json
harness/schemas/evidence/fixtures/sample_experiment_result.v1.json
harness/schemas/evidence/fixtures/sample_claim_verdict.v1.json
harness/schemas/evidence/fixtures/sample_scientific_report.v1.json
```

## Common schema requirements

Each schema should include:

```text
schema
task_id
sprint_id
node_id
status: completed | failed | inconclusive
inputs
outputs
artifacts[]
provenance.operator_id
provenance.implementation_package
provenance.timestamp
limitations[]
```

Each artifact entry should include:

```text
type
path
sha256 optional at first, required once artifact hashing exists
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 -m json.tool schemas/evidence/fixtures/sample_research_claims.v1.json >/tmp/sample_research_claims.pretty.json
python3 -m json.tool schemas/evidence/fixtures/sample_claim_verdict.v1.json >/tmp/sample_claim_verdict.pretty.json

# If jsonschema CLI is installed:
python3 -m jsonschema schemas/evidence/research_claims.v1.schema.json -i schemas/evidence/fixtures/sample_research_claims.v1.json
python3 -m jsonschema schemas/evidence/claim_verdict.v1.schema.json -i schemas/evidence/fixtures/sample_claim_verdict.v1.json
```

Manual checklist:

```text
[ ] Schemas are generic scientific schemas, not AutoSci-only schemas.
[ ] Each schema records task/sprint/node provenance.
[ ] Each schema can represent failure/inconclusive status.
[ ] Core fixtures validate or at least parse cleanly.
```

## Done when

At minimum, these four schemas and fixtures exist and validate/parse:

```text
research_paper.v1
research_claims.v1
experiment_plan.v1
claim_verdict.v1
```

---

# Phase 2 — Clean scientific capability capsule structure

## Goal

Create declarative capsules for each scientific capability. Capsules govern the implementation packages; they are not implementation packages themselves.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' config/capability-capsules.registry.yaml
sed -n '1,260p' schemas/draft/capability-capsule.v1.draft.json
mkdir -p capability-capsules
ls -la capability-capsules || true
```

## Deliverables

Create capsule files:

```text
harness/capability-capsules/cap.research-paper-ingest.yaml
harness/capability-capsules/cap.research-literature-discover.yaml
harness/capability-capsules/cap.research-memory-update.yaml
harness/capability-capsules/cap.research-graph-update.yaml
harness/capability-capsules/cap.research-paper-analyze.yaml
harness/capability-capsules/cap.research-claim-extract.yaml
harness/capability-capsules/cap.research-method-extract.yaml
harness/capability-capsules/cap.research-code-evidence-map.yaml
harness/capability-capsules/cap.research-idea-generate.yaml
harness/capability-capsules/cap.research-idea-evaluate.yaml
harness/capability-capsules/cap.research-experiment-design.yaml
harness/capability-capsules/cap.research-experiment-run.yaml
harness/capability-capsules/cap.research-experiment-monitor.yaml
harness/capability-capsules/cap.research-claim-verify.yaml
harness/capability-capsules/cap.research-report-plan.yaml
harness/capability-capsules/cap.research-report-draft.yaml
harness/capability-capsules/cap.research-publication-produce.yaml
harness/capability-capsules/cap.research-workflow-evolve.yaml
```

Update:

```text
harness/config/capability-capsules.registry.yaml
```

## Required capsule sections

Every capsule should contain at least:

```text
capability_capsule_id
capsule_kind
metadata
applicability
contract
composition
effects
bindings
verification
operator_compatibility
provenance
```

## Binding rule

A capsule may reference AutoSci implementation resources, but should not be named as AutoSci unless the capability is truly AutoSci-specific.

Good:

```yaml
capability_capsule_id: cap.research-claim-extract
bindings:
  skills:
    optional:
      - autosci.claim_extract
  data_refs:
    - schemas/evidence/research_claims.v1.schema.json
effects:
  execute:
    - plugins/autosci/bin/autosci_bridge.py
```

Avoid:

```yaml
capability_capsule_id: cap.autosci-run-everything
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 - <<'PY'
from pathlib import Path
import yaml
reg = yaml.safe_load(Path('config/capability-capsules.registry.yaml').read_text())
ids = []
for group, items in reg.get('capsules', {}).items():
    for item in items:
        ids.append(item['capability_capsule_id'])
required = [
    'cap.research-paper-ingest',
    'cap.research-claim-extract',
    'cap.research-experiment-design',
    'cap.research-claim-verify',
    'cap.research-report-draft',
]
missing = [x for x in required if x not in ids]
print('\n'.join(ids))
assert not missing, f'Missing capsules: {missing}'
PY
```

Manual checklist:

```text
[ ] Capsules are declarative and contract-focused.
[ ] Inputs/outputs reference Evidence ABI schemas.
[ ] Effects declare read/write/execute/network boundaries.
[ ] Verification has concrete pass conditions.
[ ] AutoSci is a backend binding, not the capability meaning.
```

## Done when

All 18 capsule files exist, are registered, and a human agrees the naming is clean and Solar-native.

---

# Phase 3 — Solar-native logical operators

## Goal

Make AutoSci-derived scientific work visible as native Solar logical operators.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,420p' config/logical-operators.json
python3 -m json.tool config/logical-operators.json >/tmp/logical-operators.before.json
```

## Deliverables

Add these logical operators to `harness/config/logical-operators.json`:

```text
ScientificPaperIngestor
ScientificLiteratureDiscoverer
ScientificMemoryUpdater
ScientificGraphUpdater
ScientificPaperAnalyzer
ScientificClaimExtractor
ScientificMethodExtractor
ScientificCodeEvidenceMapper
ScientificIdeaGenerator
ScientificIdeaEvaluator
ScientificExperimentDesigner
ScientificExperimentRunner
ScientificExperimentMonitor
ScientificClaimVerifier
ScientificReportPlanner
ScientificReportDrafter
ScientificPublicationProducer
ScientificWorkflowEvolver
```

## Operator style

Each operator must include:

```text
operator_type
description
primary_role
required_capabilities
cost_hint
concurrency
```

For experiment-running operators, use conservative concurrency:

```json
"concurrency": { "max_parallel": 1, "singleton": false }
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 -m json.tool config/logical-operators.json >/tmp/logical-operators.after.json
python3 - <<'PY'
import json
ops = json.load(open('config/logical-operators.json'))['logical_operators']
required = [
  'ScientificPaperIngestor',
  'ScientificClaimExtractor',
  'ScientificExperimentDesigner',
  'ScientificExperimentRunner',
  'ScientificClaimVerifier',
  'ScientificReportDrafter',
]
missing = [x for x in required if x not in ops]
assert not missing, f'Missing logical operators: {missing}'
for name in required:
    print(name, '->', ops[name].get('primary_role'), ops[name].get('required_capabilities'))
PY
```

Manual checklist:

```text
[ ] There is no giant AutoSciRunner logical operator.
[ ] Operator names describe scientific work, not backend implementation.
[ ] Required capability tokens match the capsule family.
[ ] Existing operators such as ResearchSynthesizer, BenchmarkRunner, Verifier, and ArtifactCurator are reused where appropriate.
```

## Done when

A human can identify which logical operators Solar will schedule for paper ingestion, claim extraction, experiment design, experiment run, verdict, and report generation.

---

# Phase 4 — AutoSci backend implementation package

## Goal

Create `harness/plugins/autosci/` as an implementation/backend adapter package. It should not own the workflow.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' schemas/plugin.schema.json
sed -n '1,340p' lib/plugin_loader.py
mkdir -p plugins/autosci/{bin,adapters,schemas/raw,tests/fixtures,eval_packs}
cd plugins/autosci
pwd
```

## Deliverables

Create:

```text
harness/plugins/autosci/manifest.yaml
harness/plugins/autosci/README.md
harness/plugins/autosci/bin/autosci_bridge.py
harness/plugins/autosci/adapters/solar_envelope_to_autosci.py
harness/plugins/autosci/adapters/autosci_to_research_paper.py
harness/plugins/autosci/adapters/autosci_to_research_claims.py
harness/plugins/autosci/adapters/autosci_to_research_method.py
harness/plugins/autosci/adapters/autosci_to_code_evidence_map.py
harness/plugins/autosci/adapters/autosci_to_idea_candidate.py
harness/plugins/autosci/adapters/autosci_to_experiment_plan.py
harness/plugins/autosci/adapters/autosci_to_experiment_result.py
harness/plugins/autosci/adapters/autosci_to_claim_verdict.py
harness/plugins/autosci/adapters/autosci_to_scientific_report.py
harness/plugins/autosci/schemas/raw/autosci_raw_paper.schema.json
harness/plugins/autosci/schemas/raw/autosci_raw_claims.schema.json
harness/plugins/autosci/schemas/raw/autosci_raw_experiment.schema.json
harness/plugins/autosci/tests/fixtures/sample_paper.md
harness/plugins/autosci/tests/fixtures/sample_autosci_raw_claims.json
harness/plugins/autosci/tests/fixtures/sample_autosci_raw_experiment_result.json
harness/plugins/autosci/tests/test_bridge_smoke.py
harness/plugins/autosci/tests/test_conversion_to_solar_evidence.py
harness/plugins/autosci/eval_packs/autosci_adapter_smoke.yaml
```

## Bridge actions

`autosci_bridge.py` should expose at least:

```bash
python3 plugins/autosci/bin/autosci_bridge.py --help
python3 plugins/autosci/bin/autosci_bridge.py smoke
python3 plugins/autosci/bin/autosci_bridge.py validate --result <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action ingest_paper --envelope <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action extract_claims --envelope <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action design_experiment --envelope <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action run_experiment --envelope <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action verify_claim --envelope <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action write_report --envelope <path>
```

At first, actions may operate on fixtures, but must produce Solar Evidence ABI output.

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 lib/plugin_loader.py validate --id autosci
python3 lib/plugin_loader.py check-scope --plugin autosci --path artifacts/autosci/demo/result.json
python3 lib/plugin_loader.py check-scope --plugin autosci --path ../../README.md || true
python3 plugins/autosci/bin/autosci_bridge.py --help
python3 plugins/autosci/bin/autosci_bridge.py smoke
```

Expected:

```text
[ ] Manifest validates.
[ ] Allowed artifact path passes scope check.
[ ] Illegal path fails scope check.
[ ] Bridge help lists actions.
[ ] Smoke writes result.json and evidence.jsonl under an allowed path.
```

## Done when

AutoSci can be used as a backend adapter package without owning the global research workflow.

---

# Phase 5 — Physical operators and logical bindings

## Goal

Make AutoSci-backed execution surfaces schedulable through Solar's operator runtime.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,420p' config/physical-operators.json
sed -n '1,420p' config/logical-operators.json
sed -n '1,360p' lib/operator_runtime.py
sed -n '1,360p' tools/operatord.py
```

## Deliverables

Add physical operators to `harness/config/physical-operators.json`:

```text
autosci-paper-ingest-worker
autosci-claim-extract-worker
autosci-memory-update-worker
autosci-idea-worker
autosci-experiment-design-worker
autosci-experiment-run-worker
autosci-claim-verify-worker
autosci-report-worker
```

Add logical operator bindings in `harness/config/logical-operators.json`, mapping native logical operators to these physical operators as candidate backends.

## Physical operator command pattern

Use commands like:

```bash
python3 plugins/autosci/bin/autosci_bridge.py run --action extract_claims --envelope "$SOLAR_OPERATOR_ENVELOPE_JSON"
```

## Human test

Create:

```text
harness/artifacts/autosci/smoke/envelope.claim_extract.json
```

Then run:

```bash
cd "$SOLAR_REPO/harness"
python3 -m json.tool config/physical-operators.json >/tmp/physical-operators.valid.json
python3 -m json.tool config/logical-operators.json >/tmp/logical-operators.valid.json

python3 - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, 'lib')
import operator_runtime

env_path = Path('artifacts/autosci/smoke/envelope.claim_extract.json')
print(env_path)
env = json.loads(env_path.read_text())
print(operator_runtime.submit(env))
PY
```

Manual checklist:

```text
[ ] Operator exists in physical-operators.json.
[ ] operator_runtime.submit does not reject unknown operator.
[ ] Lease is acquired.
[ ] Inbox task is written.
[ ] Result directory contains envelope/result/log artifacts.
[ ] No hidden AutoSci full workflow is invoked.
```

## Done when

At least one native logical operator, `ScientificClaimExtractor`, dispatches to an AutoSci-backed physical operator and produces Solar Evidence ABI output.

---

# Phase 6 — Manuals, personas, and dispatch templates

## Goal

Give scientific operators procedural guidance while keeping hard contracts in capsules, schemas, and gates.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
find personas -maxdepth 2 -type f | sort | sed -n '1,240p' || true
find templates -maxdepth 3 -type f | sort | sed -n '1,240p' || true
mkdir -p personas templates/dispatch
```

## Deliverables

Create personas/manuals:

```text
harness/personas/scientific-paper-ingestor.md
harness/personas/scientific-literature-discoverer.md
harness/personas/scientific-memory-updater.md
harness/personas/scientific-claim-extractor.md
harness/personas/scientific-code-evidence-mapper.md
harness/personas/scientific-experiment-designer.md
harness/personas/scientific-experiment-runner.md
harness/personas/scientific-claim-verifier.md
harness/personas/scientific-report-writer.md
```

Create dispatch templates:

```text
harness/templates/dispatch/scientific-paper-ingest.dispatch.md
harness/templates/dispatch/scientific-claim-extract.dispatch.md
harness/templates/dispatch/scientific-code-evidence-map.dispatch.md
harness/templates/dispatch/scientific-experiment-design.dispatch.md
harness/templates/dispatch/scientific-experiment-run.dispatch.md
harness/templates/dispatch/scientific-claim-verify.dispatch.md
harness/templates/dispatch/scientific-report-write.dispatch.md
```

## Manual pattern

Every manual should include:

```text
Role
Inputs
Outputs
Allowed actions
Forbidden actions
Required evidence
Failure handling
When to ask for human approval
Completion checklist
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
grep -R "research_claims.v1\|experiment_plan.v1\|claim_verdict.v1" personas templates/dispatch | sed -n '1,240p'
grep -R "Do not\|must not\|forbidden\|Forbidden" personas templates/dispatch | sed -n '1,240p'
```

Manual checklist:

```text
[ ] Every native scientific operator has a persona/manual.
[ ] Manuals refer to Evidence ABI outputs.
[ ] Manuals forbid overclaiming and hidden verification.
[ ] Manuals describe failure/inconclusive behavior.
[ ] Manuals do not hardcode AutoSci-only assumptions.
```

## Done when

A coding agent or worker can read the manual and know what artifacts to produce, what not to do, and what counts as completion.

---

# Phase 7 — Research TaskGraph templates

## Goal

Encode AutoSci's workflow as native Solar TaskGraphs.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
mkdir -p workflows
find workflows -maxdepth 2 -type f | sort | sed -n '1,240p' || true
sed -n '1,240p' lib/architecture_guard.py
sed -n '1,320p' lib/graph_scheduler.py || true
```

## Deliverables

Create:

```text
harness/workflows/scientific_paper_ingestion_v1.json
harness/workflows/scientific_claim_extraction_v1.json
harness/workflows/scientific_claim_verification_v1.json
harness/workflows/scientific_experiment_lifecycle_v1.json
harness/workflows/scientific_publication_lifecycle_v1.json
harness/workflows/scientific_research_lifecycle_full_v1.json
harness/workflows/scientific_research_resume_v1.json
```

## Minimum workflow shapes

### `scientific_claim_extraction_v1`

```text
ScientificPaperIngestor
  -> ScientificClaimExtractor
  -> VerifierLite
```

### `scientific_claim_verification_v1`

```text
ScientificPaperIngestor
  -> ScientificClaimExtractor
  -> ScientificMethodExtractor
  -> ScientificCodeEvidenceMapper
  -> ScientificExperimentDesigner
  -> ScientificExperimentRunner
  -> ScientificClaimVerifier
  -> ScientificReportDrafter
```

### `scientific_research_lifecycle_full_v1`

```text
ScientificLiteratureDiscoverer
  -> ScientificPaperIngestor
  -> ScientificPaperAnalyzer
  -> ScientificMemoryUpdater
  -> ScientificGraphUpdater
  -> ScientificClaimExtractor
  -> ScientificMethodExtractor
  -> ScientificCodeEvidenceMapper
  -> ScientificIdeaGenerator
  -> ScientificIdeaEvaluator
  -> ScientificExperimentDesigner
  -> ScientificExperimentRunner
  -> ScientificExperimentMonitor
  -> ScientificClaimVerifier
  -> ScientificReportPlanner
  -> ScientificReportDrafter
  -> ScientificPublicationProducer
  -> ScientificMemoryUpdater
  -> ScientificWorkflowEvolver
```

## Node requirements

Every node should include:

```text
id
logical_operator
required_capabilities
read_scope
write_scope
gate
acceptance or pass_conditions
depends_on where applicable
architecture_policy with package/plugin boundary where applicable
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 -m json.tool workflows/scientific_claim_verification_v1.json >/tmp/scientific_claim_verification_v1.valid.json
python3 lib/architecture_guard.py validate --graph workflows/scientific_claim_verification_v1.json --strict
python3 lib/architecture_guard.py validate --graph workflows/scientific_research_lifecycle_full_v1.json --strict
```

Manual checklist:

```text
[ ] Every node has logical_operator.
[ ] Every node has required_capabilities.
[ ] Every node has read_scope/write_scope.
[ ] Every node has a gate.
[ ] Dependencies are explicit.
[ ] No node calls a full AutoSci black-box workflow.
[ ] Experiment-running nodes require bounded mode or human approval.
```

## Done when

A human can read the TaskGraph and see the scientific workflow without reading AutoSci internals.

---

# Phase 8 — Deterministic evaluator gates

## Goal

Completion should be decided by Solar gates, not AutoSci self-report.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
find lib/research evaluators -maxdepth 4 -type f | sort | sed -n '1,240p' || true
mkdir -p evaluators/scientific tests/evaluators/scientific/fixtures/pass tests/evaluators/scientific/fixtures/fail
```

## Deliverables

Create:

```text
harness/evaluators/scientific/__init__.py
harness/evaluators/scientific/paper_gate.py
harness/evaluators/scientific/claims_gate.py
harness/evaluators/scientific/method_gate.py
harness/evaluators/scientific/code_evidence_gate.py
harness/evaluators/scientific/idea_gate.py
harness/evaluators/scientific/experiment_plan_gate.py
harness/evaluators/scientific/experiment_result_gate.py
harness/evaluators/scientific/claim_verdict_gate.py
harness/evaluators/scientific/report_gate.py
harness/evaluators/scientific/memory_update_gate.py
harness/evaluators/scientific/lifecycle_gate.py
harness/evaluators/scientific/workflow_evolution_gate.py
```

Create tests:

```text
tests/evaluators/scientific/test_claims_gate.py
tests/evaluators/scientific/test_experiment_plan_gate.py
tests/evaluators/scientific/test_experiment_result_gate.py
tests/evaluators/scientific/test_claim_verdict_gate.py
tests/evaluators/scientific/test_report_gate.py
```

## Gate examples

`claims_gate.py` should check:

```text
research_claims.v1 schema validates
claims array exists
claim_id exists
claim_type exists
each testable claim has source anchor
non-testable claims are explicitly marked
no claim is marked verified at extraction stage
```

`claim_verdict_gate.py` should check:

```text
claim_verdict.v1 schema validates
verdict is supported / partially_supported / not_supported / inconclusive
verdict links to evidence
limitations are present when confidence is not high
artifact paths exist or are declared unavailable with reason
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 -m pytest tests/evaluators/scientific
```

Manual checklist:

```text
[ ] Each evaluator has at least one pass fixture.
[ ] Each evaluator has at least one fail fixture.
[ ] Evaluators can return failure reasons.
[ ] Evaluators do not call an LLM for pass/fail.
[ ] Evaluators reject unsupported or source-free claims.
```

## Done when

Each major scientific artifact can be accepted/rejected/inconclusive by a deterministic gate.

---

# Phase 9 — Knowledge foundation: discovery, ingestion, memory, graph

## Goal

Implement native Solar support for AutoSci's research memory foundation.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
ls -la plugins/autosci
find plugins/autosci -maxdepth 4 -type f | sort | sed -n '1,260p'
find artifacts knowledge run -maxdepth 3 -type d | sort | sed -n '1,200p' || true
```

## Operators/capsules used

```text
ScientificLiteratureDiscoverer
ScientificPaperIngestor
ScientificPaperAnalyzer
ScientificMemoryUpdater
ScientificGraphUpdater

cap.research-literature-discover
cap.research-paper-ingest
cap.research-paper-analyze
cap.research-memory-update
cap.research-graph-update
```

## Evidence produced

```text
literature_discovery.v1
research_paper.v1
research_memory_update.v1
research_graph_update.v1
```

## Deliverables

Implement backend bridge actions or non-AutoSci backend actions for:

```text
ingest_paper
analyze_paper
update_memory
update_graph
discover_literature optional in first pass
```

## Human test

Run a fixture-mode paper ingestion flow:

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action ingest_paper \
  --envelope plugins/autosci/tests/fixtures/envelope.ingest_paper.json

python3 evaluators/scientific/paper_gate.py artifacts/scientific/smoke/research_paper.json
python3 evaluators/scientific/memory_update_gate.py artifacts/scientific/smoke/research_memory_update.json
```

Manual checklist:

```text
[ ] Paper metadata is extracted.
[ ] Source URL or local file is preserved.
[ ] Memory update is an explicit Solar artifact.
[ ] Graph edges are explicit Solar artifacts.
[ ] No hidden AutoSci full workflow was invoked.
[ ] Gates reject malformed metadata.
```

## Done when

Solar can ingest a paper and update research memory/graph through native nodes and evidence artifacts.

---

# Phase 10 — Claim, method, and code evidence extraction

## Goal

Implement native Solar support for paper → claim → method → code evidence mapping.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-claim-extract.yaml
sed -n '1,260p' capability-capsules/cap.research-method-extract.yaml
sed -n '1,260p' capability-capsules/cap.research-code-evidence-map.yaml
find plugins/autosci/adapters -maxdepth 1 -type f | sort
```

## Operators/capsules used

```text
ScientificClaimExtractor
ScientificMethodExtractor
ScientificCodeEvidenceMapper

cap.research-claim-extract
cap.research-method-extract
cap.research-code-evidence-map
```

## Evidence produced

```text
research_claims.v1
research_method.v1
code_evidence_map.v1
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action extract_claims \
  --envelope plugins/autosci/tests/fixtures/envelope.extract_claims.json

python3 plugins/autosci/bin/autosci_bridge.py run \
  --action map_code_evidence \
  --envelope plugins/autosci/tests/fixtures/envelope.map_code_evidence.json

python3 evaluators/scientific/claims_gate.py artifacts/scientific/smoke/research_claims.json
python3 evaluators/scientific/code_evidence_gate.py artifacts/scientific/smoke/code_evidence_map.json
```

Manual checklist:

```text
[ ] Claims are source-grounded.
[ ] Claims are testable or explicitly marked non-testable.
[ ] Methods are separated from claims.
[ ] Code evidence includes file paths/symbols where available.
[ ] Unknown mappings are marked unknown rather than fabricated.
[ ] Gates catch missing source anchors and unsupported code mappings.
```

## Done when

Solar can represent paper → claim → method → code mapping natively.

---

# Phase 11 — Idea generation and evaluation

## Goal

Implement native Solar support for AutoSci-style ideation and novelty/feasibility filtering.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-idea-generate.yaml
sed -n '1,260p' capability-capsules/cap.research-idea-evaluate.yaml
find schemas/evidence -maxdepth 1 -type f | grep idea | sort
```

## Operators/capsules used

```text
ScientificIdeaGenerator
ScientificIdeaEvaluator

cap.research-idea-generate
cap.research-idea-evaluate
```

## Evidence produced

```text
idea_candidate.v1
idea_evaluation.v1
research_memory_update.v1
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action generate_ideas \
  --envelope plugins/autosci/tests/fixtures/envelope.generate_ideas.json

python3 plugins/autosci/bin/autosci_bridge.py run \
  --action evaluate_ideas \
  --envelope plugins/autosci/tests/fixtures/envelope.evaluate_ideas.json

python3 evaluators/scientific/idea_gate.py artifacts/scientific/smoke/idea_evaluation.json
```

Manual checklist:

```text
[ ] Ideas are grounded in paper/memory context.
[ ] Each idea has novelty rationale.
[ ] Each idea has feasibility estimate.
[ ] Duplicate/failed ideas are filtered or marked.
[ ] Idea status is not updated without evidence.
```

## Done when

Solar can generate, evaluate, and record research ideas as native artifacts.

---

# Phase 12 — Experiment design, run, monitor, collect

## Goal

Implement native Solar support for experiment lifecycle while preserving bounded execution and human approval requirements.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-experiment-design.yaml
sed -n '1,260p' capability-capsules/cap.research-experiment-run.yaml
sed -n '1,260p' capability-capsules/cap.research-experiment-monitor.yaml
sed -n '1,260p' personas/scientific-experiment-runner.md
```

## Operators/capsules used

```text
ScientificExperimentDesigner
ScientificExperimentRunner
ScientificExperimentMonitor

cap.research-experiment-design
cap.research-experiment-run
cap.research-experiment-monitor
```

## Evidence produced

```text
experiment_plan.v1
experiment_status.v1
experiment_result.v1
```

## Safety rule

Experiment execution must require at least one of:

```text
fixture mode
dry-run mode
bounded local sandbox
known safe benchmark
explicit human approval for external commands
```

## Human test

Start with fixture mode:

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action design_experiment \
  --envelope plugins/autosci/tests/fixtures/envelope.design_experiment.json

python3 plugins/autosci/bin/autosci_bridge.py run \
  --action run_experiment \
  --envelope plugins/autosci/tests/fixtures/envelope.run_experiment.fixture.json

python3 evaluators/scientific/experiment_plan_gate.py artifacts/scientific/smoke/experiment_plan.json
python3 evaluators/scientific/experiment_result_gate.py artifacts/scientific/smoke/experiment_result.json
```

Manual checklist:

```text
[ ] Experiment plan has metric.
[ ] Experiment plan has baseline or justified absence.
[ ] Experiment plan has success criterion.
[ ] Run command is recorded.
[ ] Logs and metrics are captured.
[ ] Failure is classified as failed/inconclusive, not silently passed.
[ ] Non-fixture external commands require human approval.
```

## Done when

Solar can design and run a bounded experiment as a native DAG segment.

---

# Phase 13 — Claim verification and verdict

## Goal

Implement native claim verdict production and deterministic verdict gating.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-claim-verify.yaml
sed -n '1,260p' schemas/evidence/claim_verdict.v1.schema.json
sed -n '1,260p' evaluators/scientific/claim_verdict_gate.py
```

## Operators/capsules used

```text
ScientificClaimVerifier
cap.research-claim-verify
```

## Evidence produced

```text
claim_verdict.v1
```

## Human test

Prepare four fixtures:

```text
supported_experiment_result.json
partially_supported_experiment_result.json
not_supported_experiment_result.json
inconclusive_experiment_result.json
```

Run:

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action verify_claim \
  --envelope plugins/autosci/tests/fixtures/envelope.verify_claim.supported.json

python3 evaluators/scientific/claim_verdict_gate.py artifacts/scientific/smoke/claim_verdict.json
```

Manual checklist:

```text
[ ] Verdict is one of supported / partially_supported / not_supported / inconclusive.
[ ] Verdict cites claim artifact.
[ ] Verdict cites experiment/static/code evidence.
[ ] Verdict includes limitations.
[ ] Gate catches verdicts with missing evidence references.
[ ] Inconclusive evidence is not upgraded to supported.
```

## Done when

Solar can produce a claim verdict without trusting AutoSci self-report as final acceptance.

---

# Phase 14 — Report, paper, poster, rebuttal, publication bundle

## Goal

Implement native Solar support for evidence-linked report and publication artifact generation.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-report-plan.yaml
sed -n '1,260p' capability-capsules/cap.research-report-draft.yaml
sed -n '1,260p' capability-capsules/cap.research-publication-produce.yaml
find templates/dispatch -maxdepth 1 -type f | grep scientific-report | sort || true
```

## Operators/capsules used

```text
ScientificReportPlanner
ScientificReportDrafter
ScientificPublicationProducer

cap.research-report-plan
cap.research-report-draft
cap.research-publication-produce
```

## Evidence produced

```text
scientific_report.v1
publication_bundle.v1
report.md
optional poster.html
optional rebuttal.md
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action write_report \
  --envelope plugins/autosci/tests/fixtures/envelope.write_report.json

python3 evaluators/scientific/report_gate.py artifacts/scientific/smoke/scientific_report.json
```

Manual checklist:

```text
[ ] Report sections map to evidence artifacts.
[ ] Unsupported claims are not presented as successful.
[ ] Figures/tables link to artifacts.
[ ] Report has limitations section.
[ ] Publication bundle lists generated files.
[ ] Gate rejects report sections with no evidence references.
```

## Done when

Solar can produce an evidence-linked scientific report and publication bundle natively.

---

# Phase 15 — Full lifecycle workflow and resume/recovery

## Goal

Implement the native equivalent of AutoSci's full research lifecycle.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,360p' workflows/scientific_research_lifecycle_full_v1.json
sed -n '1,360p' workflows/scientific_research_resume_v1.json
sed -n '1,320p' lib/graph_scheduler.py || true
sed -n '1,320p' lib/projection_engine.py || true
sed -n '1,320p' lib/session_log.py || true
```

## Deliverables

Finalize:

```text
harness/workflows/scientific_research_lifecycle_full_v1.json
harness/workflows/scientific_research_resume_v1.json
harness/evaluators/scientific/lifecycle_gate.py
```

## Full workflow shape

```text
ScientificLiteratureDiscoverer
  -> ScientificPaperIngestor
  -> ScientificPaperAnalyzer
  -> ScientificMemoryUpdater
  -> ScientificGraphUpdater
  -> ScientificClaimExtractor
  -> ScientificMethodExtractor
  -> ScientificCodeEvidenceMapper
  -> ScientificIdeaGenerator
  -> ScientificIdeaEvaluator
  -> ScientificExperimentDesigner
  -> ScientificExperimentRunner
  -> ScientificExperimentMonitor
  -> ScientificClaimVerifier
  -> ScientificReportPlanner
  -> ScientificReportDrafter
  -> ScientificPublicationProducer
  -> ScientificMemoryUpdater
  -> ScientificWorkflowEvolver
```

## Human test

Use a tiny paper and fixture repo. If no `solar run-workflow` CLI exists, submit nodes manually through the scheduler/dispatcher path already available in the repo.

Expected final artifact tree:

```text
artifacts/scientific/<job_id>/
  01_paper/
  02_claims/
  03_methods/
  04_code_evidence/
  05_ideas/
  06_experiment_plan/
  07_experiment_result/
  08_verdict/
  09_report/
  10_memory_update/
  lifecycle_summary.json
  evidence.jsonl
```

Manual checklist:

```text
[ ] Failed node can be resumed without rerunning completed nodes.
[ ] Each node has result.json or typed evidence artifact.
[ ] Each node has evidence.jsonl or equivalent evidence entry.
[ ] Parent lifecycle gate summarizes pass/fail/inconclusive.
[ ] Human can inspect intermediate artifacts.
[ ] No hidden AutoSci end-to-end workflow owns the graph.
```

## Done when

Solar can run an end-to-end scientific research lifecycle as a native TaskGraph.

---

# Phase 16 — Workflow evolution / SciEvolve-like feedback

## Goal

Implement native Solar support for learning from scientific workflow outcomes.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-workflow-evolve.yaml
sed -n '1,260p' schemas/evidence/workflow_evolution.v1.schema.json
find evaluators/scientific -maxdepth 1 -type f | sort
```

## Operators/capsules used

```text
ScientificWorkflowEvolver
cap.research-workflow-evolve
```

## Evidence produced

```text
workflow_evolution.v1
recommended_changes.md
optional patch_candidates/
```

## Evolver must collect

```text
failed nodes
gate rejection reasons
ambiguous manuals/prompts
insufficient schemas
poor operator bindings
human intervention points
runtime errors
```

## Evolver may propose

```text
capsule edits
manual edits
routing edits
gate improvements
workflow template changes
```

It must not silently promote changes without review.

## Human test

Use one intentionally failed workflow run.

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action evolve_workflow \
  --envelope plugins/autosci/tests/fixtures/envelope.evolve_workflow.failed_run.json

python3 evaluators/scientific/workflow_evolution_gate.py artifacts/scientific/smoke/workflow_evolution.json
```

Manual checklist:

```text
[ ] Evolution report cites concrete failed nodes.
[ ] It proposes bounded changes.
[ ] It separates manual changes from schema/gate changes.
[ ] It does not silently edit protected core runtime.
[ ] Human can accept/reject each proposed change.
```

## Done when

Solar can learn from AutoSci-style research runs without losing governance.

---

# Phase 17 — Naming and architecture cleanup

## Goal

Ensure the final architecture reads as a Solar-native scientific research runtime, not a wrapper around AutoSci.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
grep -R "AutoSci\|autosci" capability-capsules workflows schemas/evidence evaluators/scientific config/logical-operators.json config/physical-operators.json personas templates/dispatch | sed -n '1,400p' || true
```

## Cleanup rule

AutoSci names are allowed in:

```text
plugins/autosci/**
physical operator vendor/backend descriptions
capsule bindings/provenance
implementation_package metadata
```

AutoSci names should not dominate:

```text
capability IDs
logical operator names
Evidence ABI schema names
workflow template names
gate names
manual role names
```

## Human test

Checklist:

```text
[ ] Capabilities are named `cap.research-*`, not `cap.autosci-*`, except where explicitly backend-specific.
[ ] Logical operators are `Scientific*`, not `AutoSci*`.
[ ] Evidence schemas are generic scientific schemas.
[ ] Workflows are scientific lifecycle workflows, not AutoSci lifecycle wrappers.
[ ] Plugin package remains as backend implementation only.
```

## Done when

The architecture reads as:

```text
Solar scientific research runtime using AutoSci as one backend implementation package.
```

---

# Phase 18 — End-to-end human acceptance test

## Goal

Prove that Solar has all AutoSci capabilities native.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
find workflows -maxdepth 1 -type f | sort | grep scientific
find capability-capsules -maxdepth 1 -type f | sort | grep scientific
find schemas/evidence -maxdepth 1 -type f | sort
find evaluators/scientific -maxdepth 1 -type f | sort
find plugins/autosci -maxdepth 3 -type f | sort | sed -n '1,400p'
```

## Acceptance Test A — Paper ingestion and memory

```bash
cd "$SOLAR_REPO/harness"
# Use actual workflow CLI if available; otherwise submit the template nodes manually.
solar run-workflow scientific_paper_ingestion_v1 \
  --paper plugins/autosci/tests/fixtures/sample_paper.md \
  --mode fixture
```

Pass if:

```text
[ ] research_paper.v1 exists.
[ ] research_memory_update.v1 exists.
[ ] graph update exists if graph update node is enabled.
[ ] Gates accept valid artifacts.
```

## Acceptance Test B — Claim extraction and code mapping

```bash
cd "$SOLAR_REPO/harness"
solar run-workflow scientific_claim_extraction_v1 \
  --paper plugins/autosci/tests/fixtures/sample_paper.md \
  --repo plugins/autosci/tests/fixtures/sample_repo \
  --mode fixture
```

Pass if:

```text
[ ] research_claims.v1 exists.
[ ] research_method.v1 exists.
[ ] code_evidence_map.v1 exists.
[ ] Claims are source-grounded.
[ ] Unknown mappings are marked unknown.
```

## Acceptance Test C — Experiment lifecycle

```bash
cd "$SOLAR_REPO/harness"
solar run-workflow scientific_experiment_lifecycle_v1 \
  --claim artifacts/scientific/demo/research_claims.json \
  --repo plugins/autosci/tests/fixtures/sample_repo \
  --mode fixture
```

Pass if:

```text
[ ] experiment_plan.v1 exists.
[ ] experiment_status.v1 exists.
[ ] experiment_result.v1 exists.
[ ] Logs and metrics exist.
[ ] Failure is classified correctly.
```

## Acceptance Test D — Claim verdict

```bash
cd "$SOLAR_REPO/harness"
solar run-workflow scientific_claim_verification_v1 \
  --claim artifacts/scientific/demo/research_claims.json \
  --experiment-result artifacts/scientific/demo/experiment_result.json \
  --mode fixture
```

Pass if:

```text
[ ] claim_verdict.v1 exists.
[ ] Verdict is supported / partially_supported / not_supported / inconclusive.
[ ] Verdict cites evidence.
[ ] Gate rejects unsupported verdicts.
```

## Acceptance Test E — Report and publication

```bash
cd "$SOLAR_REPO/harness"
solar run-workflow scientific_publication_lifecycle_v1 \
  --verdict artifacts/scientific/demo/claim_verdict.json \
  --mode fixture
```

Pass if:

```text
[ ] scientific_report.v1 exists.
[ ] report.md exists.
[ ] publication_bundle.v1 exists.
[ ] Report is evidence-linked.
[ ] Limitations are explicit.
```

## Acceptance Test F — Full lifecycle

```bash
cd "$SOLAR_REPO/harness"
solar run-workflow scientific_research_lifecycle_full_v1 \
  --input plugins/autosci/tests/fixtures/full_lifecycle_task.json \
  --mode fixture
```

Pass if:

```text
[ ] Every major AutoSci capability appears as a Solar-native node.
[ ] Every node has a logical operator.
[ ] Every node has a capability capsule.
[ ] Every node emits Evidence ABI artifacts.
[ ] Gates decide pass/fail/inconclusive.
[ ] AutoSci package is used only as backend implementation where appropriate.
[ ] Human can inspect intermediate artifacts without reading AutoSci internals.
```

## Final completion definition

The implementation is complete only when:

```text
[ ] AutoSci workflow is decomposed into Solar-native stages.
[ ] All major AutoSci capabilities have native Solar logical operators.
[ ] All major capabilities have clean declarative capsules.
[ ] Capsules bind to implementation packages without becoming implementation packages.
[ ] AutoSci code lives under plugins/autosci as backend adapter code.
[ ] Evidence ABI schemas exist for every major artifact.
[ ] Evaluator gates exist for every major artifact.
[ ] Research TaskGraph templates exist for minimal, verification, experiment, publication, and full lifecycle flows.
[ ] Human can run fixture-mode smoke tests for each capability group.
[ ] Human can inspect intermediate artifacts without reading AutoSci internals.
[ ] No single AutoSciRunner black box owns the workflow.
```

---

# Appendix A — Directory lookup commands for agents

These are the main commands agents should use to locate relevant context:

```bash
cd "$SOLAR_REPO"
sed -n '1,240p' README.md
sed -n '1,260p' docs/solar-architecture-code-map.md

cd "$SOLAR_REPO/harness"
sed -n '1,240p' schemas/plugin.schema.json
sed -n '1,300p' lib/plugin_loader.py
sed -n '1,360p' lib/operator_runtime.py
sed -n '1,360p' tools/operatord.py
sed -n '1,360p' config/logical-operators.json
sed -n '1,360p' config/physical-operators.json
sed -n '1,260p' config/capability-capsules.registry.yaml
sed -n '1,260p' schemas/draft/capability-capsule.v1.draft.json
find . -maxdepth 3 -type d | sort | sed -n '1,240p'
find . -maxdepth 3 -type f | sort | sed -n '1,240p'

cd "$SOLAR_REPO/harness/plugins/autosci"
pwd
find . -maxdepth 4 -type f | sort | sed -n '1,260p'

cd "$SOLAR_REPO/harness/capability-capsules"
pwd
find . -maxdepth 1 -type f | sort | grep scientific

cd "$SOLAR_REPO/harness/workflows"
pwd
find . -maxdepth 1 -type f | sort | grep scientific

cd "$SOLAR_REPO/harness/schemas/evidence"
pwd
find . -maxdepth 1 -type f | sort

cd "$SOLAR_REPO/harness/evaluators/scientific"
pwd
find . -maxdepth 1 -type f | sort

cd "$SOLAR_REPO/harness/personas"
pwd
find . -maxdepth 1 -type f | sort | grep scientific

cd "$SOLAR_REPO/harness/templates/dispatch"
pwd
find . -maxdepth 1 -type f | sort | grep scientific

cd "$AUTOSCI_REPO"
sed -n '1,260p' README.md
find . -maxdepth 4 -type f | sort | grep -E '(README|\.md$|\.py$|\.ya?ml$|\.json$)' | sed -n '1,360p'
```

---

# Appendix B — Minimal PR slicing recommendation

Implement in PRs that match the phases, but allow these combined PRs if needed:

```text
PR 1: Phase 0 docs only
PR 2: Phase 1 schemas + fixtures
PR 3: Phase 2 capsules + registry
PR 4: Phase 3 logical operators
PR 5: Phase 4 AutoSci implementation package skeleton + smoke
PR 6: Phase 5 physical operators + one working dispatch
PR 7: Phase 6 manuals/templates
PR 8: Phase 7 workflows
PR 9: Phase 8 evaluator gates
PR 10: Phase 9-10 paper/claim/code foundation
PR 11: Phase 11-13 idea/experiment/verdict
PR 12: Phase 14-16 report/lifecycle/evolution
PR 13: Phase 17-18 cleanup + acceptance
```

Each PR must include either:

```text
1. a human-readable artifact, or
2. a passing smoke command, or
3. a deterministic gate/test.
```
