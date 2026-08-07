# Research Control Plane Known-Issue Repair

Run branch: `codex/known-issues-research-control-plane`
Baseline: `4b5af751956f8ef1d2eb6bbce8baf9088e694d00`

## Root Cause

Solar's production `$research` bridge delegated most request interpretation to
the legacy seed-kind classifier. That preserved the full prompt, but it did not
expose an auditable research-control-plane taxonomy for website, topic, local
PDF, source pack, experiment evidence, and resume inputs. As a result,
upstream-vs-Solar parity evidence could prove only a subset of `/research`
behavior, source-pack and experiment-evidence starts were hard to audit, and
some CLI options appeared in the surface without targeted semantic checks.

Visualize had a separate parity gap: local graph/canvas generation could be
called and did bind focus/filter flags, but empty or damaged graph inputs still
produced a completed evidence payload because zero-node outputs were not treated
as an error boundary. The resulting evidence also did not expose the original
visualization target in a stable output field.

## Changes

- Added deterministic intake classification in
  `harness/plugins/autosci/bin/research_control_plane.py`.
- Wired `autosci_bridge.py research` through that classification layer before
  creating the Solar runtime.
- Added explicit taxonomy and routing metadata to production research results.
- Added fail-closed preflight checks for blank prompts, contradictory language
  constraints, missing source-pack members, and damaged local PDFs.
- Prepared source packs as bounded Markdown manifests and experiment evidence as
  hashed artifact references under the requested artifact root.
- Preserved `--workflow` as an explicit override while defaulting full natural
  language requests to the classified workflow.
- Updated visualize evidence to expose `outputs.source_ref`,
  `outputs.visualize_options`, and `outputs.status_reasons`.
- Changed visualize empty graph/canvas output from completed to inconclusive.
- Added targeted regression tests under
  `tests/repairs/research_control_plane/`.

## Evidence

Targeted tests:

```text
python -m pytest tests/repairs/research_control_plane --basetemp %TEMP%/rcp-pytest-basetemp-5 -o cache_dir=%TEMP%/rcp-pytest-cache-5 -q
8 passed
```

Production entrypoint probes were run through
`harness/plugins/autosci/bin/autosci_bridge.py research`:

- Chinese website prompt: classified as `website`, started `seed_fetch`, and
  stopped at the expected no-network authorization boundary.
- English topic prompt: classified as `topic`, started `source_discovery`, and
  stopped at the expected source-discovery authorization boundary.
- Local source-pack prompt: classified as `source_pack`, started
  `material_ingest`, and completed in a short-path artifact root.
- Local PDF prompt: classified as `local_pdf`, started `paper_ingest`, and failed
  closed at the current PDF parser/runtime boundary.

## Residual Limitations

- No live upstream AutoSci `/research` command was executed in this repair; the
  parity test uses the repository's saved upstream contract fixture.
- Website and topic production runs require network/source-discovery
  authorization before they can complete beyond the first gated node.
- The local PDF path is now classified and preflighted, but the production PDF
  parser path still failed on the minimal local PDF fixture. This repair records
  that as a remaining product/runtime limitation instead of relabeling it as a
  pass.
- Full source-pack completion is sensitive to Windows path length; the passing
  production evidence uses a short `%TEMP%` artifact root.
