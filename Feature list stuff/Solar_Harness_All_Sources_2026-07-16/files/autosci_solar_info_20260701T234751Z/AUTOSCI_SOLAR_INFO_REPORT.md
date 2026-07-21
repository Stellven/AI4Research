# AutoSci-on-Solar Information Report

## 1. Executive Summary
- Can start unification branch? yes, with local/CI gate required first; this run did not start a branch or merge.
- Current AutoSci branch readiness: product dispatch and product-level smoke coverage are present; route inventory still contains partial/gated work.
- Stellven integration risk level: medium. Local BetterSolar differs on shared runtime files and lacks the AutoSci module paths.
- Full parity risk level: high. Native AutoSci reference repo status is available locally, and current route statuses are not all full.
- Biggest blockers: run the gate on the eventual integration branch, manually merge shared runtime/config files, preserve artifact hygiene, and avoid claiming full parity.

## 2. Repositories
- OpenSolar path: `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar`
- Stellven/OpenJiuwen local path: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar`
- Native AutoSci local path: `/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci`

Initial/final git status was captured in `initial_git_status.txt` and `final_git_status.txt`.

```text
============================================================
OPEN_SOLAR_REPO=/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar
/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar
origin	git@github.com:Coconut-ch1ken/OpenSolar.git (fetch)
origin	git@github.com:Coconut-ch1ken/OpenSolar.git (push)
upstream	https://github.com/Stellven/OpenSolar.git (fetch)
upstream	https://github.com/Stellven/OpenSolar.git (push)
feature/autosci-solar-native
9d68c5baa9b814c086ae87f9c26f6ad0ae62ecd7
9d68c5baa (HEAD -> feature/autosci-solar-native, origin/feature/autosci-solar-native) progress
 M .DS_Store
 M harness/.pane-restart-state
 M harness/PLANNER-INBOX.md
 M harness/config/physical-operators.json
 M harness/logs/pane-exit.jsonl
/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar                    9d68c5baa [feature/autosci-solar-native]
/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.worktrees/builder e611942c0 [harness-builder-20260630-104210]
fatal: no submodule mapping found in .gitmodules for path 'harness/vendor/obsidian-wiki'

============================================================
STELLVEN_SOLAR_REPO=/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar
/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar
origin	https://github.com/Stellven/AI4Research.git (fetch)
origin	https://github.com/Stellven/AI4Research.git (push)
upstream	https://github.com/lisihao/Solar.git (fetch)
upstream	https://github.com/lisihao/Solar.git (push)
openJiuwen-Solar
cdc7e90334437796232e019a0dd689d33e53e7f2
cdc7e903 (HEAD -> openJiuwen-Solar, origin/pkg/migration, origin/openJiuwen-Solar, origin/HEAD) chore(dashboard): rebuild static bundle after rc8 integration
/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar cdc7e903 [openJiuwen-Solar]

============================================================
NATIVE_AUTOSCI_REPO=/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci
/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci
origin	https://github.com/Coconut-ch1ken/AutoSci.git (fetch)
origin	https://github.com/Coconut-ch1ken/AutoSci.git (push)
upstream	https://github.com/skyllwt/AutoSci.git (fetch)
upstream	https://github.com/skyllwt/AutoSci.git (push)
main
71469e89eb1381e557661da0b90c0585c48288d7
71469e8 (HEAD -> main, upstream/main, upstream/HEAD, origin/main, origin/HEAD) Update WeChat group QR code (group 3, valid through Jun 21)
 M .claude/skills/discover/SKILL.md
 M .claude/skills/discover/references/ranking-signals.md
 M .claude/skills/discover/references/seed-modes.md
 M .claude/skills/ideate/SKILL.md
 M .github/ISSUE_TEMPLATE/bug_report.md
 M .github/PULL_REQUEST_TEMPLATE.md
 M .github/workflows/daily-arxiv.yml
 M README.md
 M config/README.md
 M config/daily-arxiv.yml.example
 M config/setup-guide.md
 M docs/daily-arxiv-deployment.md
 M docs/runtime-directory-structure.en.md
 M docs/runtime-directory-structure.zh.md
 M i18n/en/CLAUDE.md
 M i18n/en/shared-references/cross-model-review.md
 M i18n/en/skills/ask/SKILL.md
 M i18n/en/skills/daily-arxiv/SKILL.md
 M i18n/en/skills/daily-arxiv/references/automation-scaffold.md
 M i18n/en/skills/exp-design/SKILL.md
 M i18n/en/skills/exp-eval/SKILL.md
 M i18n/en/skills/exp-pilot-eval/SKILL.md
 M i18n/en/skills/exp-pilot-run/SKILL.md
 M i18n/en/skills/exp-run/SKILL.md
 M i18n/en/skills/exp-status/SKILL.md
 M i18n/en/skills/ideate/SKILL.md
 M i18n/en/skills/ingest/SKILL.md
 M i18n/en/skills/ingest/references/cross-references.md
 M i18n/en/skills/novelty/SKILL.md
 M i18n/en/skills/paper-compile/SKILL.md
 M i18n/en/skills/paper-draft/SKILL.md
 M i18n/en/skills/paper-plan/SKILL.md
 M i18n/en/skills/poster/SKILL.md
 M i18n/en/skills/prefill/SKILL.md
 M i18n/en/skills/rebuttal/SKILL.md
 M i18n/en/skills/refine/SKILL.md
 M i18n/en/skills/research/SKILL.md
 M i18n/en/skills/reset/SKILL.md
 M i18n/en/skills/review/SKILL.md
 M i18n/en/skills/setup/SKILL.md
 M i18n/en/skills/survey/SKILL.md
 M i18n/en/skills/visualize/SKILL.md
 M runtime/CLAUDE.md
 M
```

## 3. System and Tools
See `system_info.txt` and `provider_side_effect_readiness.txt`.

Provider/side-effect summary:

```text
# Provider and side-effect readiness
SEMANTIC_SCHOLAR_API_KEY: absent
DEEPXIV_TOKEN: absent
LLM_API_KEY: absent
LLM_BASE_URL: absent
LLM_MODEL: absent
OPENAI_API_KEY: present
ANTHROPIC_API_KEY: absent
ANTHROPIC_AUTH_TOKEN: absent

# Tool availability
latexmk      pdflatex     /Library/TeX/texbin/pdflatex
xelatex      /Library/TeX/texbin/xelatex
lualatex     /Library/TeX/texbin/lualatex
rsync        /usr/bin/rsync
ssh          /usr/bin/ssh
screen       /usr/bin/screen

# Possible config files
absent:  /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/harness/config/remote.yaml
absent:  /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/harness/config/server.yaml
absent:  /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/harness/plugins/autosci/config/daily-arxiv.yml
absent:  /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/harness/plugins/autosci/config/daily-arxiv.yml.example
present: /Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci/config/daily-arxiv.yml.example
present: /Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci/.env
absent:  /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.env

```

## 4. Current AutoSci Branch Inventory
- Route count: `28`
- Coverage status counts: `{'gated': 11, 'partial': 17}`
- Side-effect policy counts: `{'approval_required': 15, 'dry_run_only': 9, 'none': 4}`
- Missing route capabilities from registry: `[]`
- Missing route evidence schemas: `[]`
- Missing route logical operators: `[]`

Detailed files: `open_solar_autosci_tree.txt`, `autosci_route_summary.json`, `autosci_consistency_inventory.json`.

## 5. Product-Level Dispatch Status
- `solar-harness.sh autosci` dispatch grep: `open_solar_autosci_dispatch_grep.txt`
- `$skills` product path output: `product_autosci_skills_stdout.json`
- Product-level pytest tests: pass
- Manual isolated smoke: pass

Product test output:

```text
# pytest product-level AutoSci tests
......                                                                   [100%]
6 passed in 5.29s

```

Manual smoke excerpt:

```text
## $skills
{
  "count": 28,
  "ok": true,
  "skills": [
    {
      "autosci_command": "/ask",
      "coverage_status": "partial",
      "physical_operator": "SkillgenResearchWikiQueryOperator",
      "side_effect_policy": "none",
      "skill": "ask",
      "solar_backend_action": "ask_wiki"
    },
    {
      "autosci_command": "/check",
      "coverage_status": "partial",
      "physical_operator": "SkillgenWikiHealthOperator",
      "side_effect_policy": "none",
      "skill": "check",
      "solar_backend_action": "check_wiki_health"
    },
    {
      "autosci_command": "/daily-arxiv",
      "coverage_status": "gated",
      "physical_operator": "ApprovalGatedDailyArxivOperator",
      "side_effect_policy": "approval_required",
      "skill": "daily-arxiv",
      "solar_backend_action": "daily_arxiv_prepare_finalize"
    },
    {
      "autosci_command": "/discover",
      "coverage_status": "partial",
      "physical_operator": "AutoSciBridgeLiteratureOperator",
      "side_effect_policy": "none",
      "skill": "discover",
      "solar_backend_action": "discover_literature"
    },
    {
      "autosci_command": "/edit",
      "coverage_status": "gated",
      "physical_operator": "ApprovalGatedWikiEditOperator",
      "side_effect_policy": "approval_required",
      "skill": "edit",
      "solar_backend_action": "edit_wiki_plan"
    },
    {
      "autosci_command": "/exp-design",
      "coverage_status": "partial",
      "physical_operator": "AutoSciBridgeExperimentDesigner",
      "side_effect_policy": "dry_run_only",
      "skill": "exp-design",
      "solar_backend_action": "design_experiment"
    },
    {
      "autosci_command": "/exp-eval",
      "coverage_status": "partial",
      "physical_operator": "AutoSciBridgeClaimVerifier",
      "side_effect_policy": "approval_required",
      "skill": "exp-eval",
      "solar_backend_action": "verify_claim"
    },
    {
      "autosci_command": "/exp-pilot-eval",
      "coverage_status": "partial",
      "physical_operator": "AutoSciBridgePilotVerifier",
      "side_effect_policy": "approval_required",
      "skill": "exp-pilot-eval",
      "solar_backend_action": "evaluate_pilot_result"
    },
    {
      "autosci_command": "/exp-pilot-run",
      "coverage_status": "gated",
      "physical_operator": "ApprovalGatedPilotExperimentRunner",
      "side_effect_policy": "approval_required",
      "skill": "exp-pilot-run",
      "solar_backend_action": "run_pilot_experiment"
    },
    {
      "autosci_command": "/exp-run",
      "coverage_status": "gated",
      "physical_operator": "ApprovalGatedExperimentRunner",
      "side_effect_policy": "approval_required",
      "skill": "exp-run",
      "solar_backend_action": "run_experiment"
    },
    {
      "autosci_command": "/exp-status",
      "coverage_status": "partial",
      "physical_operator": "AutoSciBridgeExperimentMonitor",
      "side_effect_policy": "none",
      "skill": "exp-status",
      "solar_backend_action": "monitor_experim
```

## 6. Artifact Root and Hygiene
- Product tests and manual smoke used isolated harness roots under this info bundle.
- Generated AutoSci run/operator/workflow artifact tracking found: `False`
- Tracked `.DS_Store` found: `True`
- Tracked `.solar-backups` found: `True`

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
# Local comparison only
No fetch was performed. Comparing current local OpenSolar worktree/index metadata to current local BetterSolar worktree.

# OpenSolar HEAD
9d68c5baa (HEAD -> feature/autosci-solar-native, origin/feature/autosci-solar-native) progress
# BetterSolar HEAD
cdc7e903 (HEAD -> openJiuwen-Solar, origin/pkg/migration, origin/openJiuwen-Solar, origin/HEAD) chore(dashboard): rebuild static bundle after rc8 integration

# Files likely requiring manual merge
different README.md
different AGENTS.md
different CLAUDE.md
stellven_only bin/solar
different harness/solar-harness.sh
stellven_only core/daemon/skill-dispatcher.ts
different harness/config/logical-operators.json
different harness/config/physical-operators.json
different harness/config/capability-capsules.registry.yaml
different .gitignore

# AutoSci module target path presence in BetterSolar
absent harness/plugins/autosci
absent harness/tools/run_scientific_workflow.py
absent harness/tools/run_scientific_node_smoke.py
absent harness/tools/run_scientific_lifecycle_smoke.py
absent harness/workflows/scientific_research_lifecycle_full_v1.json
absent harness/evaluators/scientific
absent harness/schemas/evidence
absent .agents/skills
absent docs/integrations/autosci

```

Config key comparison summary:

```json
{
  "harness/config/logical-operators.json": {
    "autosci_branch_count": 43,
    "autosci_only_keys": [
      "ScientificArtifactReviewer",
      "ScientificClaimExtractor",
      "ScientificClaimVerifier",
      "ScientificCodeEvidenceMapper",
      "ScientificExperimentDesigner",
      "ScientificExperimentMonitor",
      "ScientificExperimentRunner",
      "ScientificGraphUpdater",
      "ScientificIdeaEvaluator",
      "ScientificIdeaGenerator",
      "ScientificLiteratureDiscoverer",
      "ScientificMemoryUpdater",
      "ScientificMethodExtractor",
      "ScientificPaperAnalyzer",
      "ScientificPaperIngestor",
      "ScientificPublicationProducer",
      "ScientificReportDrafter",
      "ScientificReportPlanner",
      "ScientificWorkflowEvolver"
    ],
    "stellven_count": 24,
    "stellven_only_keys": []
  },
  "harness/config/physical-operators.json": {
    "autosci_branch_count": 65,
    "autosci_only_keys": [
      "autosci-artifact-review-worker",
      "autosci-claim-extract-worker",
      "autosci-claim-verify-worker",
      "autosci-code-evidence-map-worker",
      "autosci-experiment-design-worker",
      "autosci-experiment-monitor-worker",
      "autosci-experiment-run-worker",
      "autosci-graph-update-worker",
      "autosci-idea-evaluate-worker",
      "autosci-idea-worker",
      "autosci-literature-discover-worker",
      "autosci-memory-update-worker",
      "autosci-method-extract-worker",
      "autosci-paper-analyze-worker",
      "autosci-paper-ingest-worker",
      "autosci-publication-compile-worker",
      "autosci-report-plan-worker",
      "autosci-report-worker",
      "autosci-workflow-evolve-worker"
    ],
    "stellven_count": 47,
    "stellven_only_keys": [
      "mini-codex-gpt55-medium-evaluator-1"
    ]
  }
}
```

Manual merge files needing attention from local comparison: `10`.

## 9. Native AutoSci Reference Inventory
Native AutoSci repo: `/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci`.

Status: available locally; see native_autosci_tree.txt, native_autosci_command_inventory.json, native_autosci_feature_keywords.txt.

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
Information bundle directory: `/tmp/autosci_solar_info_20260701T234751Z`

Files in bundle:

```text
autosci_consistency_inventory.json
autosci_consistency_inventory.stderr.txt
autosci_route_summary.json
autosci_route_summary.stderr.txt
common_files.txt
config_key_comparison.json
config_key_comparison.stderr.txt
final_git_status.txt
gather_info.sh
git_branches.txt
git_state.txt
initial_git_status.txt
merge_focus_diff.txt
native_autosci_command_inventory.json
native_autosci_command_inventory.stderr.txt
native_autosci_feature_keywords.txt
native_autosci_important_files.txt
native_autosci_tree.txt
native_file_README_md.txt
native_file__claude_skills_exp-eval_SKILL_md.txt
native_file__claude_skills_exp-run_SKILL_md.txt
native_file__claude_skills_exp-status_SKILL_md.txt
native_file__claude_skills_ideate_SKILL_md.txt
native_file__claude_skills_novelty_SKILL_md.txt
native_file__claude_skills_paper-compile_SKILL_md.txt
native_file__claude_skills_paper-draft_SKILL_md.txt
native_file__claude_skills_poster_SKILL_md.txt
native_file__claude_skills_rebuttal_SKILL_md.txt
native_file__claude_skills_research_SKILL_md.txt
native_file__claude_skills_review_SKILL_md.txt
native_file_tools_daily_arxiv_py.txt
native_file_tools_discover_py.txt
native_file_tools_init_discovery_py.txt
native_file_tools_remote_py.txt
native_file_tools_research_wiki_py.txt
open_only_files.txt
open_solar_artifact_hygiene.txt
open_solar_autosci_dispatch_grep.txt
open_solar_autosci_manifest.yaml
open_solar_autosci_pytest_collect.txt
open_solar_autosci_tree.txt
open_solar_capability_registry.yaml
open_solar_git_status_after_tests.txt
open_solar_lifecycle_runtime_gate.txt
open_solar_ls_files.txt
open_solar_manual_product_smoke.txt
open_solar_product_autosci_tests.txt
open_solar_run_scientific_workflow_body.txt
open_solar_run_scientific_workflow_head.txt
open_solar_run_scientific_workflow_tail.txt
open_solar_shim_grep.txt
open_solar_shim_head.txt
open_solar_shim_scheduler_excerpt.txt
open_solar_shim_status_excerpt.txt
open_solar_solar_harness_dispatch_excerpt.txt
open_solar_top_tree.txt
open_solar_wrapper_exp-run.md
open_solar_wrapper_ideate.md
open_solar_wrapper_ingest.md
open_solar_wrapper_paper-compile.md
open_solar_wrapper_paper-draft.md
open_solar_wrapper_research.md
open_solar_wrapper_review.md
product_autosci_skills_stderr.txt
product_autosci_skills_stdout.json
provider_side_effect_readiness.txt
repo_candidates.txt
repo_paths.env
stellven_file_AGENTS_md.txt
stellven_file_CLAUDE_md.txt
stellven_file_README_md.txt
stellven_file_bin_solar.txt
stellven_file_core_daemon_skill-dispatcher_ts.txt
stellven_file_desktop_package_json.txt
stellven_file_harness_config_capability-capsules_registry_yaml.txt
stellven_file_harness_config_logical-operators_json.txt
stellven_file_harness_config_physical-operators_json.txt
stellven_file_harness_lib_plugin_loader_py.txt
stellven_file_harness_schemas_plugin_schema_json.txt
stellven_file_harness_solar-harness_sh.txt
stellven_ls_files.txt
stellven_only_files.txt
stellven_runtime_tree.txt
stellven_top_tree.txt
system_info.txt
```
