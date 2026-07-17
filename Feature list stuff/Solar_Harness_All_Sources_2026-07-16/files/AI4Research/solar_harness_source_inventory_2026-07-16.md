# Solar Harness Source Inventory

**Inventory date:** 2026-07-16  
**Scope:** Sources available from the shared Solar Harness / AI4Research project history, saved files, and referenced public links.

This inventory separates primary source code from historical snapshots, raw evidence, and documents generated from that evidence. A generated analysis is useful context, but it is not a substitute for checking the repository and commit on which it was based.

## 1. Canonical repository sources

These four repositories formed the canonical comparison set in the integration and parity work.

| Role | Repository | Branch/reference used |
| --- | --- | --- |
| Upstream Solar baseline | [lisihao/Solar](https://github.com/lisihao/Solar) | Baseline/default branch as inspected at the time |
| Native AutoSci reference | [skyllwt/AutoSci](https://github.com/skyllwt/AutoSci) | `main`; later upstream also exposed runtime-specific branches |
| AutoSci-on-Solar fusion result (“OpenSolar”) | [Coconut-ch1ken/OpenSolar](https://github.com/Coconut-ch1ken/OpenSolar/tree/feature/autosci-solar-native) | `feature/autosci-solar-native` |
| Productized/downloader Solar (“BetterSolar”) | [Stellven/AI4Research](https://github.com/Stellven/AI4Research/tree/openJiuwen-Solar) | `openJiuwen-Solar` |

### Other repository references mentioned during the project

- [Coconut-ch1ken/OpenSolar — 2026-06-25 snapshot](https://github.com/Coconut-ch1ken/OpenSolar/tree/2026-06-25-1717-snapshot) — historical migration snapshot.
- [Stellven/OpenSolar](https://github.com/Stellven/OpenSolar) — earlier OpenSolar integration reference.
- [Stellven/AutoSci](https://github.com/Stellven/AutoSci) — project fork/reference used in later AutoSci analysis.
- [Coconut-ch1ken/AutoSci](https://github.com/Coconut-ch1ken/AutoSci) — alternate AutoSci working reference mentioned in project history.
- [suraj-subrahmanyan/OpenSolar](https://github.com/suraj-subrahmanyan/OpenSolar/tree/pkg/migration) — `pkg/migration` work mentioned as another migration source.

## 2. Recorded branch and commit checkpoints

These are historical evidence anchors, not claims about the current repository heads.

| Repository/branch | Recorded checkpoint | Context |
| --- | --- | --- |
| OpenSolar `feature/autosci-solar-native` | `c36824b62e620df9f8d1059559c140a2b62be6cc` | Code-first parity audit baseline |
| AI4Research `openJiuwen-Solar` | `9b22ad962d88fa0859a0e35d3fe7e84f3f3ae390` | Code-first parity audit baseline |
| OpenSolar `feature/autosci-solar-native` | `9d68c5baa` | Later checkpoint recorded in handoff/prompt files |
| BetterSolar `openJiuwen-Solar` | `cdc7e903` | Later checkpoint recorded in handoff/prompt files |
| Native AutoSci `main` | `71469e8` | Native-reference checkpoint recorded in parity prompt |
| Setup Wizard `feature/setup-wizard` | `c48507fb` | Based on `origin/pkg/migration`; nearby commits recorded as `446a1c5b`, `a10dfcfe`, `1d9fddf0`, `c710b732` |

Two planned working branches also appear in the agent handoffs:

- `integration/autosci-unification-hardening`
- `feature/autosci-full-parity-continuation`

## 3. Direct research-paper sources

### Direct source

- [AutoSci: A Memory-Centric Agentic System for the Full Scientific Research Lifecycle](https://arxiv.org/abs/2605.31468) — the paper directly associated with the native AutoSci capability target.

### Adjacent AI4Research/Solar design references

- [CORAL: Towards Autonomous Multi-Agent Evolution for Open-Ended Discovery](https://arxiv.org/abs/2604.01658)
- [AI Research Agents Narrow Scientific Exploration](https://arxiv.org/abs/2605.27905)
- [Emergence World: A Platform for Evaluating Long-Horizon Multi-Agent Autonomy](https://arxiv.org/abs/2606.08367)

The last three informed adjacent multi-agent, evaluation, and research-system discussions; they are not the source of Solar Harness itself.

## 4. Repository paths used as technical evidence

The following paths were repeatedly cited or inspected. They belong to different branches/repositories, so their exact existence and contents must be checked against the relevant commit.

### Solar runtime and shared integration surface

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `.gitignore`
- `bin/solar`
- `harness/solar-harness.sh`
- `components.d/harness/component.sh`
- `core/daemon/skill-dispatcher.ts`
- `harness/config/logical-operators.json`
- `harness/config/physical-operators.json`
- `harness/config/capability-capsules.registry.yaml`

### AutoSci integration and parity layer

- `harness/plugins/autosci/`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `harness/plugins/autosci/config/feature_operator_bindings.v1.json`
- `plugins/autosci/bin/autosci_bridge.py`
- `plugins/autosci/bin/autosci_parity_bridge.py`
- `plugins/autosci/bin/autosci_operator_smoke.py`
- `docs/integrations/autosci/`
- `autosci-solar-feature-parity-matrix.md`
- `unification-status.md`

### Scientific lifecycle, evaluators, and evidence

- `harness/tools/run_scientific_workflow.py`
- `harness/tools/run_scientific_node_smoke.py`
- `harness/tools/run_scientific_lifecycle_smoke.py`
- `harness/workflows/scientific_research_lifecycle_full_v1.json`
- `harness/evaluators/scientific/`
- `harness/schemas/evidence/`
- `research_paper.v1`
- `scientific_lifecycle.v1`

### Skills and installed runtime locations

- `.agents/skills/`
- `.agents/skills/ingest/SKILL.md`
- `~/.claude/skills/`
- `~/.solar/harness/`

### Productization, setup, and live E2E

- `desktop/main.js`
- `desktop/preload.js`
- `setup-wizard/render.js`
- `src/setup/`
- `installer.nsh`
- `harness/lib/setup_preflight.py`
- `status-server/routes/setup_routes.py`
- `tests/test_setup_preflight.py`
- `scripts/live-codex-e2e-isolated.sh`

## 5. Saved raw evidence and extraction bundle

These are saved original/uploaded artifacts rather than model-generated summaries. Most were collected together on 2026-07-02.

### Bundle and report

- `autosci_solar_info_20260701T234751Z.tgz`
- `AUTOSCI_SOLAR_INFO_REPORT.md`

### Repository state, paths, and manifests

- `initial_git_status.txt`
- `final_git_status.txt`
- `final_paths.txt`
- `open_solar_artifact_hygiene.txt`
- `open_solar_git_status_after_tests.txt`
- `open_solar_ls_files.txt`
- `open_solar_autosci_manifest.yaml`
- `stellven_only_files.txt`
- `stellven_runtime_tree.txt`

### Runtime and code excerpts

- `open_solar_manual_product_smoke.txt`
- `open_solar_run_scientific_workflow_head.txt`
- `open_solar_shim_head.txt`
- `stellven_file_core_daemon_skill-dispatcher_ts.txt`
- `stellven_file_harness_config_logical-operators_json.txt`
- `native_file__claude_skills_paper-compile_SKILL_md.txt`
- `native_file_tools_init_discovery_py.txt`
- `native_file_tools_research_wiki_py.txt`

## 6. Saved migration, parity, and agent-execution documents

These are derived work products. Their conclusions are tied to the repository state available when each document was made.

### Plans, audits, and status reports

- `autosci_solar_native_implementation_plan.md`
- `autosci_solar_native_implementation_plan(1).md`
- `autosci_solar_native_implementation_plan(1)(1).md`
- `autosci_solar_gap_analysis_2026-06-25.md`
- `AutoSci_Solar_Native_Migration_Master_Handoff_2026-06-26.md`
- `AutoSci_Solar_Native_ChatGPT_Check_Status_Report.md`
- `AutoSci_Solar_Parity_Recheck_and_Coding_Agent_Execution_Plan_2026-06-29.md`
- `AutoSci_Solar_Prioritized_Integration_Plan_2026-06-30.md`
- `autosci_perfect_run_acceptance_manifest.md`
- `autosci_perfect_run_acceptance_manifest.yaml`

### Coding-agent and review prompts

- `solar_autosci_strict_parity_audit_prompt.md`
- `autosci_migration_coding_agent_prompt_2026-06-25.md`
- `AutoSci_Solar_100_Percent_Parity_Fast_Track_Coding_Agent_Prompt.md`
- `AutoSci_Solar_Info_Gathering_Coding_Agent_Prompt.md`
- `Prompt_A_Solar_Unification_Agent.md`
- `Prompt_B_AutoSci_Full_Parity_Agent.md`
- `Parallel_AutoSci_Solar_Agent_Coordination.md`
- `DO_Agent_A_Unification_Hardening.md`
- `DO_Agent_B_Full_Parity.md`

### Example/fixture artifact

- `autosci_example_wiki.zip`

## 7. Architecture and technical-report artifacts

### Direct Solar Harness architecture artifacts

- `Solar_Harness_Architecture_OnePage.pptx`
- `Solar_Harness_Architecture_OnePage(1).pptx`
- `solar-architecture-deck.html`
- `slide-1.png` — saved slide/architecture preview.

### Solar-native AutoSci technical-report lineage

- `Solar_Native_AutoSci_Technical_Report_Draft.docx`
- `Solar_Native_AutoSci_Technical_Report_PD11_Revised.docx`
- `Solar_Native_AutoSci_Technical_Report_PD11_Revised(1).docx`
- `Solar_Native_AutoSci_Technical_Report_PD11_Operator_Assimilation.docx`
- `Second-Draft-of-Technical-Report.docx`
- `Second-Draft-of-Technical-Report_Revised.docx`

### Broader AI4Research/Solar context artifacts

- `5.19 ai4research flow.txt`
- `AI4Research_Planning_Report_Enhanced.docx`
- `AI4Research_Solar_RSI_汇报版_逻辑顺序最终版_深度分析主干重构版.html`
- `AI时代技术创新与技术规划中的AI4Research闭环实践报告.docx`
- `跨领域大颗粒技术规划的机制和方法研究报告_AI4Research增强版.docx`

An unlabeled attachment, `fa921640-d5ea-4446-bbde-aa0020b04136.png`, was retrieved in Solar-related history but cannot be safely classified from its filename alone.

## 8. QA, feature-inventory, and test-guideline artifacts

### Original audit workbook uploads

- `qa_inventory_test_mapping_and_pass_fail_merged.xlsx`
- `qa_inventory_test_mapping_and_pass_fail_merged(1).xlsx`
- `qa_inventory_test_mapping_and_pass_fail_merged(2).xlsx`

### Three-part and recursive feature decomposition

- `ai4research_three_part_level1_features.xlsx`
- `ai4research_recursive_feature_split.xlsx`
- `ai4research_recursive_feature_split_qa_execution.xlsx`

### QA execution package

- `ai4research_coding_agent_qa_control_pack.docx`
- `ai4research_fixture_set_instructions.md`
- `ai4research_test_execution_runbook.md`
- `ai4research_qa_agent_package.zip`

### Restructured feature-workbook lineage

- `ai4research_restructured_feature_workbook.xlsx`
- `ai4research_restructured_feature_workbook(1).xlsx`
- `ai4research_restructured_feature_workbook_updated.xlsx`
- `ai4research_restructured_feature_workbook_workflow_refined.xlsx`
- `ai4research_restructured_feature_workbook_workflow_finer_sorted.xlsx`
- `ai4research_restructured_feature_workbook_workflow_audited_dimensions.xlsx`
- `ai4research_restructured_feature_workbook_annotated_zh.xlsx`
- `ai4research_restructured_feature_workbook_annotated_zh_action.xlsx`
- `ai4research_restructured_feature_workbook_workflow_l2_pipeline.xlsx`
- `ai4research_restructured_feature_workbook_workflow_l2_pipeline_v2.xlsx`
- `ai4research_restructured_feature_workbook_workflow_l2_pipeline_v2_no_chinese_annotations.xlsx`

The last file is the latest named endpoint of the L2 workflow-pipeline reframing visible in the saved set; that statement refers to filename lineage, not a new code audit.

## 9. Known local working-copy references

These paths appeared in prompts and handoffs on the user’s Mac. They are historical references and are not mounted in the current workspace.

- `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar`
- `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar`
- `/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci`
- `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar-autosci-parity`
- `/tmp/solar-setup-wizard`

## 10. Prior Solar/OpenSolar comparison conversations with retrievable links

- [Repo功能融合检查](https://chatgpt.com/c/6a47db66-2cd0-83ea-8cd5-0a1d4db39e86)
- [Repo融合与进度检查](https://chatgpt.com/c/6a47db36-26a0-83ea-aab9-86df2c806d80)
- [Repo功能融合进展](https://chatgpt.com/c/6a4c180b-9238-83ea-9b95-8e4701990ad1)
- [Project Comparison and Guidance](https://chatgpt.com/c/6a3da034-045c-83ea-8283-28932e580831)
- [AutoSci OpenSolar Integration Detail](https://chatgpt.com/c/6a2b2143-1ee8-83ea-981d-c6fa5a8195d4)

Additional project threads covered architecture generation, AutoSci parity, setup/runtime isolation, feature decomposition, and QA workbook auditing, but stable conversation URLs were not exposed in the retrieved source set.

## 11. Related but non-technical source material

The following files supported report formatting or coursework compliance, not Solar Harness architecture or implementation, and therefore are not treated as technical sources above:

- `Section 1: Drafting a Technical Report.pdf`
- `Section 1: The Structure of a Technical Report.pdf`
- `First-Draft-of-Technical-Report-Template(1).docx`

## 12. Reliability hierarchy

For any new architectural or parity conclusion, use the sources in this order:

1. Repository code at an explicitly recorded branch and commit.
2. Executed tests, manifests, and raw evidence captured from that same commit.
3. Architecture/acceptance documents tied to that commit.
4. Generated gap analyses, prompts, and handoffs.
5. Historical conversation summaries.

The four canonical repositories in Section 1 are the source-of-truth set. The saved documents preserve useful project history, but several describe earlier states and should not be read as the current parity status without a fresh code audit.
