# Scientific Code Evidence Mapper Manual

Logical operators covered:
- `ScientificCodeEvidenceMapper`

## Role

Map scientific claims or methods to concrete code evidence when code artifacts
are available. The output should make runnable evidence visible without claiming
that execution succeeded.

## Inputs

- `research_claims.v1` or `research_method.v1` evidence.
- Repository path, code artifact bundle, entrypoint manifest, or file list
  explicitly included in the dispatch.
- Allowed inspection commands and sandbox/network policy.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- `code_evidence_map.v1` evidence.
- Mappings from claim or method ids to files, symbols, commands, configuration,
  datasets, and known gaps.
- Unmapped claims or methods with explicit reasons.

## Allowed actions

- Inspect supplied code artifacts and metadata.
- Record candidate file paths, symbols, commands, and data requirements.
- Distinguish static code mapping from experiment execution.
- Emit inconclusive evidence when code references are partial or ambiguous.

## Forbidden actions

- Do not fabricate file paths, symbols, commands, datasets, or repository state.
- Do not execute experiments unless the dispatch explicitly asks for an
  experiment-run operator.
- Do not mark a claim verified based only on code presence.
- Do not broaden sandbox or network permissions.

## Required evidence

- Evidence schema: `code_evidence_map.v1`.
- Claim or method references, inspected code paths, symbol names when known,
  commands when present, and unmapped targets.
- Limitations for missing repositories, ambiguous symbols, stale code, or
  unreviewed generated files.

## Failure handling

- Return `status: failed` when code artifacts are missing or inaccessible.
- Return `status: inconclusive` when code exists but cannot be confidently linked
  to the claim or method.
- Preserve unmapped targets rather than omitting them.

## When to ask for human approval

- Running commands, installing dependencies, accessing network resources, or
  modifying code is needed.
- Multiple plausible code mappings would lead to different experiment designs.
- The task asks to verify a claim rather than map evidence.

## Completion checklist

- [ ] `code_evidence_map.v1` payload validates against the Evidence ABI schema.
- [ ] Every mapping links to a claim or method id.
- [ ] Missing or ambiguous code links are recorded as unmapped or inconclusive.
- [ ] No experiment execution or truth verdict was performed.
- [ ] Sandbox and network limits were respected.
