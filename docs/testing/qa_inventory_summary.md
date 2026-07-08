# QA Inventory Summary

## Scope

- Source: tracked files from `git ls-files`.
- Included: package scripts/bins, shell scripts, Python CLIs, HTTP routes, workflows, SKILL.md files, static surfaces, module summary rows, and existing tests.
- Excluded from required execution by default: vendor content, local caches, runtime logs, venvs, and generated artifacts not tracked as source.

## Counts

- Tracked files scanned: 4371
- Test files detected: 929
- Feature rows generated: 1722

## Feature Rows by L1

- AutoSci: 36
- Benchmarks: 8
- Browser: 2
- CI: 22
- CLI: 11
- Components: 16
- Core: 3
- Dashboard: 3
- Desktop: 16
- Harness: 1109
- Hooks: 89
- Ingestion: 39
- Installer: 17
- Packaging: 14
- QA Gates: 28
- Reports: 13
- Repository: 90
- Research: 44
- Runtime: 3
- Skills: 88
- Status Server: 66
- TVS: 5

## Feature Rows by Source Type

- domain-module: 8
- manifest: 3
- module: 14
- package-bin: 2
- package-script: 25
- python-cli: 1109
- route: 121
- shell-cli: 11
- shell-script: 334
- skill: 73
- workflow: 22

## Coverage Status

- covered: 1549
- missing-or-indirect: 132
- partial-or-unmapped: 20
- static-validation-required: 21

## Rows Needing Explicit Test Mapping

- `components.component_manifests.component`: components.d/autosci/component.sh (component)
- `components.component_manifests.component.4`: components.d/daemons/component.sh (component)
- `components.component_manifests.component.5`: components.d/harness/component.sh (component)
- `components.component_manifests.component.6`: components.d/kernel/component.sh (component)
- `components.component_manifests.component.7`: components.d/mempalace/component.sh (component)
- `components.component_manifests.component.10`: components.d/skills-md/component.sh (component)
- `components.component_manifests.component.11`: components.d/skills-obsidian/component.sh (component)
- `components.component_manifests.component.12`: components.d/skills-office/component.sh (component)
- `components.component_manifests.component.13`: components.d/solar-max/component.sh (component)
- `components.component_manifests.component.14`: components.d/status-daemon/component.sh (component)
- `desktop.solar_desktop.script.build_linux`: desktop/package.json (package script: build:linux)
- `desktop.solar_desktop.script.build_mac`: desktop/package.json (package script: build:mac)
- `desktop.solar_desktop.script.build_renderer`: desktop/package.json (package script: build:renderer)
- `desktop.solar_desktop.script.build_win`: desktop/package.json (package script: build:win)
- `desktop.solar_desktop.script.prepackage_check`: desktop/package.json (package script: prepackage-check)
- `desktop.solar_desktop.script.selftest`: desktop/package.json (package script: selftest)
- `desktop.solar_desktop.script.start`: desktop/package.json (package script: start)
- `desktop.electron_shell.verify_macos_package`: desktop/verify-macos-package.sh (verify-macos-package)
- `hooks.runtime_hooks.asset_reminder`: hooks/asset-reminder.sh (asset-reminder)
- `hooks.runtime_hooks.auto_checkpoint`: hooks/auto-checkpoint.sh (auto-checkpoint)
- `hooks.runtime_hooks.auto_favorites_extract`: hooks/auto-favorites-extract.sh (auto-favorites-extract)
- `hooks.runtime_hooks.cortex_hook`: hooks/cortex-hook.sh (cortex-hook)
- `hooks.runtime_hooks.design_cortex_reminder`: hooks/design-cortex-reminder.sh (design-cortex-reminder)
- `hooks.runtime_hooks.enhanced_memory_writer`: hooks/enhanced-memory-writer.sh (enhanced-memory-writer)
- `hooks.runtime_hooks.evolve_auto_record`: hooks/evolve-auto-record.sh (evolve-auto-record)
- `hooks.runtime_hooks.evolve_pre_tool_advisor`: hooks/evolve-pre-tool-advisor.sh (evolve-pre-tool-advisor)
- `hooks.runtime_hooks.evolve_subagent_tracker`: hooks/evolve-subagent-tracker.sh (evolve-subagent-tracker)
- `hooks.runtime_hooks.executor_reminder`: hooks/executor-reminder.sh (executor-reminder)
- `hooks.runtime_hooks.experience_reminder`: hooks/experience-reminder.sh (experience-reminder)
- `hooks.runtime_hooks.hook_logger`: hooks/hook-logger.sh (hook-logger)
- `hooks.runtime_hooks.identity_reminder`: hooks/identity-reminder.sh (identity-reminder)
- `hooks.runtime_hooks.learning_capture`: hooks/learning-capture.sh (learning-capture)
- `hooks.runtime_hooks.memory_auto_updater`: hooks/memory-auto-updater.sh (memory-auto-updater)
- `hooks.runtime_hooks.memory_consolidate_hook`: hooks/memory-consolidate-hook.sh (memory-consolidate-hook)
- `hooks.runtime_hooks.memory_extract_hook`: hooks/memory-extract-hook.sh (memory-extract-hook)
- `hooks.runtime_hooks.memory_recall_hook`: hooks/memory-recall-hook.sh (memory-recall-hook)
- `hooks.runtime_hooks.mempal_precompact_hook`: hooks/mempal_precompact_hook.sh (mempal_precompact_hook)
- `hooks.runtime_hooks.mempal_save_hook`: hooks/mempal_save_hook.sh (mempal_save_hook)
- `hooks.runtime_hooks.mid_refresh`: hooks/mid-refresh.sh (mid-refresh)
- `hooks.runtime_hooks.perf_auto_refresh`: hooks/perf-auto-refresh.sh (perf-auto-refresh)
- `hooks.runtime_hooks.permission_auto_approve`: hooks/permission-auto-approve.sh (permission-auto-approve)
- `hooks.runtime_hooks.personality_anchor_hook`: hooks/personality-anchor-hook.sh (personality-anchor-hook)
- `hooks.runtime_hooks.personality_injector`: hooks/personality-injector.sh (personality-injector)
- `hooks.runtime_hooks.portable`: hooks/lib/portable.sh (portable)
- `hooks.runtime_hooks.post_edit`: hooks/post-edit.sh (post-edit)
- `hooks.runtime_hooks.post_tool_dispatcher`: hooks/post-tool-dispatcher.sh (post-tool-dispatcher)
- `hooks.runtime_hooks.post_tool_failure_recorder`: hooks/post-tool-failure-recorder.sh (post-tool-failure-recorder)
- `hooks.runtime_hooks.pre_bash`: hooks/pre-bash.sh (pre-bash)
- `hooks.runtime_hooks.pre_compact_anchor`: hooks/pre-compact-anchor.sh (pre-compact-anchor)
- `hooks.runtime_hooks.pre_edit`: hooks/pre-edit.sh (pre-edit)
- `hooks.runtime_hooks.ree_first_hook`: hooks/ree-first-hook.sh (ree-first-hook)
- `hooks.runtime_hooks.remote_inbox_watcher`: hooks/remote-inbox-watcher.sh (remote-inbox-watcher)
- `hooks.runtime_hooks.scan_low_quality_capabilities`: hooks/scan-low-quality-capabilities.sh (scan-low-quality-capabilities)
- `hooks.runtime_hooks.self_evolve_postmortem`: hooks/self-evolve-postmortem.sh (self-evolve-postmortem)
- `hooks.runtime_hooks.sma_auto_consolidate`: hooks/sma-auto-consolidate.sh (sma-auto-consolidate)
- `hooks.runtime_hooks.solidifier_cron`: hooks/solidifier-cron.sh (solidifier-cron)
- `hooks.runtime_hooks.subagent_start_tracker`: hooks/subagent-start-tracker.sh (subagent-start-tracker)
- `hooks.runtime_hooks.subagent_stop_tracker`: hooks/subagent-stop-tracker.sh (subagent-stop-tracker)
- `hooks.runtime_hooks.subconscious_learn`: hooks/subconscious-learn.sh (subconscious-learn)
- `hooks.runtime_hooks.subconscious_whisper`: hooks/subconscious-whisper.sh (subconscious-whisper)
- `hooks.runtime_hooks.texture_inject`: hooks/texture-inject.sh (texture-inject)
- `hooks.runtime_hooks.user_modeler_update`: hooks/user-modeler-update.sh (user-modeler-update)
- `hooks.runtime_hooks.user_profile_inject`: hooks/user-profile-inject.sh (user-profile-inject)
- `hooks.runtime_hooks.whisper_hook_v2`: hooks/whisper-hook-v2.sh (whisper-hook-v2)
- `ingestion.daily_arxiv_discovery.daily_arxiv.config`: tools/daily_arxiv.py (daily_arxiv: config)
- `ingestion.daily_arxiv_discovery.daily_arxiv.digest`: tools/daily_arxiv.py (daily_arxiv: digest)
- `ingestion.daily_arxiv_discovery.daily_arxiv.finalize`: tools/daily_arxiv.py (daily_arxiv: finalize)
- `ingestion.daily_arxiv_discovery.daily_arxiv.prepare`: tools/daily_arxiv.py (daily_arxiv: prepare)
- `ingestion.daily_arxiv_discovery.daily_arxiv.recommend_llm`: tools/daily_arxiv.py (daily_arxiv: recommend-llm)
- `ingestion.deepxiv_fetch.fetch_deepxiv.search`: tools/fetch_deepxiv.py (fetch_deepxiv: search)
- `ingestion.latex_math_rendering.rasterize_latex`: tools/rasterize_latex.py (rasterize_latex)
- `ingestion.semantic_scholar_fetch.fetch_s2.citations`: tools/fetch_s2.py (fetch_s2: citations)
- `ingestion.semantic_scholar_fetch.fetch_s2.references`: tools/fetch_s2.py (fetch_s2: references)
- `ingestion.semantic_scholar_fetch.fetch_s2.search`: tools/fetch_s2.py (fetch_s2: search)
- `ingestion.wikipedia_url_fetch.fetch_wikipedia.section`: tools/fetch_wikipedia.py (fetch_wikipedia: section)
- `ingestion.arxiv_fetch.fetch_arxiv`: tools/fetch_arxiv.py (fetch_arxiv)
- `installer.installer_library.common`: lib/installer/common.sh (common)
- `installer.installer_library.components`: lib/installer/components.sh (components)
- `installer.installer_library.config_vars`: lib/installer/config-vars.sh (config-vars)
- `installer.installer_library.copy_engine`: lib/installer/copy-engine.sh (copy-engine)
- ... 52 more rows in CSV

## Static Validation Rows

- `ci.desktop_build.build`: .github/workflows/desktop-build.yml (build)
- `ci.desktop_build.gate`: .github/workflows/desktop-build.yml (gate)
- `ci.install_matrix.core_static`: .github/workflows/install-matrix.yml (core-static)
- `ci.install_matrix.daemons_lifecycle`: .github/workflows/install-matrix.yml (daemons-lifecycle)
- `ci.install_matrix.docs_links`: .github/workflows/install-matrix.yml (docs-links)
- `ci.install_matrix.dry_run_check`: .github/workflows/install-matrix.yml (dry-run-check)
- `ci.install_matrix.install`: .github/workflows/install-matrix.yml (install)
- `ci.install_matrix.installed_clean`: .github/workflows/install-matrix.yml (installed-clean)
- `ci.install_matrix.installer_contract`: .github/workflows/install-matrix.yml (installer-contract)
- `ci.install_matrix.kernel_gen`: .github/workflows/install-matrix.yml (kernel-gen)
- `ci.install_matrix.mempalace_check`: .github/workflows/install-matrix.yml (mempalace-check)
- `ci.install_matrix.privacy_gate`: .github/workflows/install-matrix.yml (privacy-gate)
- `ci.install_matrix.ps1_lint`: .github/workflows/install-matrix.yml (ps1-lint)
- `ci.install_matrix.ps1_pester`: .github/workflows/install-matrix.yml (ps1-pester)
- `ci.install_matrix.shellcheck`: .github/workflows/install-matrix.yml (shellcheck)
- `ci.solar_ci.hf_ai_influence_smoke`: .github/workflows/solar-ci.yml (hf-ai-influence-smoke)
- `ci.solar_ci.python_smoke`: .github/workflows/solar-ci.yml (python-smoke)
- `ci.solar_ci.release_packaging_smoke`: .github/workflows/solar-ci.yml (release-packaging-smoke)
- `ci.windows_wsl2_install.windows_wsl2`: .github/workflows/windows-wsl2-install.yml (windows-wsl2)
- `components.components_d.component_manifests`: components.d (component manifests)
- `runtime.schema.runtime_schemas`: runtime/schema (runtime schemas)

## Interpretation

A `covered` row means a repo test file appears to target the feature by path/name heuristics. It still requires execution before claiming PASS.
A `missing-or-indirect` row is testable but lacks an obvious direct test mapping; it may be covered through a broader smoke gate, but that must be confirmed before final sign-off.
