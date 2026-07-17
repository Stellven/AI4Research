# Parallel Work Coordination — AutoSci-on-Solar

## Folder assignments

### Agent A — Solar unification

Primary working folder:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar
```

Branch to create/use:

```bash
integration/autosci-on-openjiuwen-solar
```

Read-only source folder:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar
```

Agent A must not work directly inside native AutoSci except read-only reference:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci
```

### Agent B — AutoSci full parity

Primary working folder:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar
```

Recommended safer worktree:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar-autosci-parity
```

Branch to create/use:

```bash
feature/autosci-full-parity-continuation
```

Read-only native reference:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci
```

Agent B must not edit BetterSolar.

---

## Coordination model

```text
Agent A owns product runtime integration.
Agent B owns deep AutoSci parity.
```

### Agent A owns

```text
BetterSolar integration branch
bin/solar
harness/solar-harness.sh
core/daemon/skill-dispatcher.ts
harness/config/logical-operators.json
harness/config/physical-operators.json
harness/config/capability-capsules.registry.yaml
.gitignore
harness/plugins/autosci import
harness/tools scientific runner import
harness/workflows import
harness/evaluators/scientific import
harness/schemas/evidence import
harness/tests/integration/test_autosci_*.py import
.agents/skills import
```

### Agent B owns

```text
OpenSolar AutoSci module
harness/plugins/autosci/**
harness/tools/research_wiki.py
harness/tools/fetch_*.py
harness/tools/remote.py
harness/evaluators/scientific/**
harness/schemas/evidence/**
harness/workflows/scientific_*.json
harness/capability-capsules/cap.research-*.yaml
harness/plugins/autosci/config/feature_parity_routes.v1.json
harness/plugins/autosci/tests/**
harness/tests/evaluators/scientific/**
docs/integrations/autosci parity docs
```

---

## Shared contract that neither agent should break

```text
AutoSci must remain a Solar-governed backend module.
No black-box AutoSciRunner.
No native AutoSci repo mutation.
Typed Evidence ABI decides completion.
Product-level AutoSci dispatch must continue to work.
All AutoSci runtime outputs must stay under active HARNESS_DIR.
Partial/gated routes must not be promoted to full without proof.
```

---

## Required sync protocol

When Agent B changes any of these, it must write a clear handoff note because Agent A may need to port the change later:

```text
harness/plugins/autosci/config/feature_parity_routes.v1.json
harness/schemas/evidence/*.schema.json
harness/evaluators/scientific/*.py
harness/workflows/scientific_*.json
harness/config/logical-operators.json
harness/config/physical-operators.json
harness/config/capability-capsules.registry.yaml
```

Agent B handoff note path:

```text
docs/integrations/autosci/parity-to-unification-handoff.md
```

Agent A should only import Agent B changes after Agent B reports passing product-level tests.

---

## Immediate sequencing

1. Agent A starts now in BetterSolar and creates `integration/autosci-on-openjiuwen-solar`.
2. Agent B starts now in OpenSolar or a new worktree and creates `feature/autosci-full-parity-continuation`.
3. Agent A does not wait for Agent B to finish full parity.
4. Agent B does not wait for Agent A to finish unification.
5. Agent A imports current AutoSci module first.
6. Agent B improves AutoSci module behind the same interface.
7. Later, Agent A cherry-picks or rsyncs selected Agent B module changes into BetterSolar integration branch.
