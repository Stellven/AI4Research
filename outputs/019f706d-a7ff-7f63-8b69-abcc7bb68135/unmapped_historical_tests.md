# Unmapped historical tests

Source: historical workbook at commit `718aae9a`, path `docs/testing/test-runs/20260710-0121-qa-full-audit/ai4research_recursive_feature_split_qa_execution_colored.xlsx`

Total: 250

## AutoSci route action workflow: reset_plan (4)

- **WF-0264-MISSING-INVALID-SCOPE-REJECTED-E14DB0** — Missing/invalid scope is rejected; dry-run plan lists exact mutations. — `test_missing_invalid_scope_rejected_dry` — FAIL (row 265)
- **WF-0265-PLAN-GENERATED-WITHOUT-MUTATION-38B119** — Plan is generated without mutation and is not research success evidence. — `test_plan_generated_without_mutation_not` — FAIL (row 266)
- **WF-0266-EXECUTION-REQUIRES-EXPLICIT-APPROVAL-9BF203** — Execution requires explicit approval and preserves unscoped data. — `test_execution_requires_explicit_approval_preserves` — PASS (row 267)
- **WF-0267-RESET-RESULT-REPORTS-CHANGED-E66455** — Reset result reports changed paths and residual state. — `test_reset_result_reports_changed_paths` — PASS (row 268)

## AutoSci slash workflow: /reset (4)

- **WF-0127-MISSING-INVALID-SCOPE-REJECTED-4D0810** — Missing/invalid scope is rejected; dry-run plan lists exact mutations. — `test_missing_invalid_scope_rejected_dry` — PASS (row 128)
- **WF-0128-PLAN-GENERATED-WITHOUT-MUTATION-D9591A** — Plan is generated without mutation and is not research success evidence. — `test_plan_generated_without_mutation_not` — PASS (row 129)
- **WF-0129-EXECUTION-REQUIRES-EXPLICIT-APPROVAL-E2A5D6** — Execution requires explicit approval and preserves unscoped data. — `test_execution_requires_explicit_approval_preserves` — PASS (row 130)
- **WF-0130-RESET-RESULT-REPORTS-CHANGED-E820FB** — Reset result reports changed paths and residual state. — `test_reset_result_reports_changed_paths` — PASS (row 131)

## CI workflow: desktop-build (4)

- **WF-0428-TRIGGER-MATRIX-MATCH-EXPECTED-EA10EE** — Workflow trigger and matrix match expected OS/jobs. — `test_trigger_matrix_match_expected_os` — PASS (row 429)
- **WF-0429-SETUP-STEPS-INSTALL-REQUIRED-D04944** — Setup steps install required tools or fail with clear logs. — `test_setup_steps_install_required_tools` — PASS (row 430)
- **WF-0430-JOB-FAILS-FAILING-UNDERLYING-33D5D1** — Job fails on failing underlying command and uploads useful logs/artifacts. — `test_job_fails_failing_underlying_command` — PASS (row 431)
- **WF-0431-EXPECTED-ARTIFACTS-STATUS-SUMMARIES-87AB96** — Expected artifacts or status summaries are produced on success/failure. — `test_expected_artifacts_status_summaries_produced` — PASS (row 432)

## CI workflow: install-matrix (4)

- **WF-0432-TRIGGER-MATRIX-MATCH-EXPECTED-36F461** — Workflow trigger and matrix match expected OS/jobs. — `test_trigger_matrix_match_expected_os` — PASS (row 433)
- **WF-0433-SETUP-STEPS-INSTALL-REQUIRED-2D0B58** — Setup steps install required tools or fail with clear logs. — `test_setup_steps_install_required_tools` — PASS (row 434)
- **WF-0434-JOB-FAILS-FAILING-UNDERLYING-EE12FB** — Job fails on failing underlying command and uploads useful logs/artifacts. — `test_job_fails_failing_underlying_command` — FAIL (row 435)
- **WF-0435-EXPECTED-ARTIFACTS-STATUS-SUMMARIES-B115CE** — Expected artifacts or status summaries are produced on success/failure. — `test_expected_artifacts_status_summaries_produced` — FAIL (row 436)

## CI workflow: solar-ci (4)

- **WF-0436-TRIGGER-MATRIX-MATCH-EXPECTED-567244** — Workflow trigger and matrix match expected OS/jobs. — `test_trigger_matrix_match_expected_os` — PASS (row 437)
- **WF-0437-SETUP-STEPS-INSTALL-REQUIRED-E66300** — Setup steps install required tools or fail with clear logs. — `test_setup_steps_install_required_tools` — PASS (row 438)
- **WF-0438-JOB-FAILS-FAILING-UNDERLYING-DD0F6A** — Job fails on failing underlying command and uploads useful logs/artifacts. — `test_job_fails_failing_underlying_command` — FAIL (row 439)
- **WF-0439-EXPECTED-ARTIFACTS-STATUS-SUMMARIES-0F1251** — Expected artifacts or status summaries are produced on success/failure. — `test_expected_artifacts_status_summaries_produced` — FAIL (row 440)

## Desktop package script: build:linux (4)

- **MISC-0182-UI-LOADS-REAL-STATUS-C494DD** — UI loads real status data and handles empty/missing/error states honestly. — `test_ui_loads_real_status_data` — INCONCLUSIVE_EXPECTED (row 1679)
- **MISC-0183-INTERACTIVE-STATES-ACCESSIBLE-PERSISTENT-E46782** — Interactive states are accessible, persistent where required, and do not trigger hidden work. — `test_interactive_states_accessible_persistent_where` — INCONCLUSIVE_EXPECTED (row 1680)
- **MISC-0184-EXPECTED-BUILD-PACKAGE-TEST-F6FBD3** — Expected build/package/test artifact is produced and verifiable. — `test_expected_build_package_test_artifact` — SKIPPED_ENV (row 1681)
- **MISC-0185-PLATFORM-SPECIFIC-PATH-HEADLESS-9CAFBC** — Platform-specific path or headless failure is explicit. — `test_platform_specific_path_headless_failure` — SKIPPED_ENV (row 1682)

## Desktop package script: gate (4)

- **MISC-0202-UI-LOADS-REAL-STATUS-25446F** — UI loads real status data and handles empty/missing/error states honestly. — `test_ui_loads_real_status_data` — SKIPPED_ENV (row 1699)
- **MISC-0203-INTERACTIVE-STATES-ACCESSIBLE-PERSISTENT-150FBD** — Interactive states are accessible, persistent where required, and do not trigger hidden work. — `test_interactive_states_accessible_persistent_where` — SKIPPED_ENV (row 1700)
- **MISC-0204-EXPECTED-BUILD-PACKAGE-TEST-BD4E9D** — Expected build/package/test artifact is produced and verifiable. — `test_expected_build_package_test_artifact` — SKIPPED_ENV (row 1701)
- **MISC-0205-PLATFORM-SPECIFIC-PATH-HEADLESS-FB00EF** — Platform-specific path or headless failure is explicit. — `test_platform_specific_path_headless_failure` — SKIPPED_ENV (row 1702)

## Desktop package script: prepackage-check (4)

- **MISC-0207-UI-LOADS-REAL-STATUS-231DD6** — UI loads real status data and handles empty/missing/error states honestly. — `test_ui_loads_real_status_data` — PASS (row 1704)
- **MISC-0208-INTERACTIVE-STATES-ACCESSIBLE-PERSISTENT-762312** — Interactive states are accessible, persistent where required, and do not trigger hidden work. — `test_interactive_states_accessible_persistent_where` — INCONCLUSIVE_EXPECTED (row 1705)
- **MISC-0209-EXPECTED-BUILD-PACKAGE-TEST-E868E1** — Expected build/package/test artifact is produced and verifiable. — `test_expected_build_package_test_artifact` — SKIPPED_ENV (row 1706)
- **MISC-0210-PLATFORM-SPECIFIC-PATH-HEADLESS-7ADB08** — Platform-specific path or headless failure is explicit. — `test_platform_specific_path_headless_failure` — SKIPPED_ENV (row 1707)

## Desktop package script: selftest (4)

- **MISC-0212-UI-LOADS-REAL-STATUS-83344E** — UI loads real status data and handles empty/missing/error states honestly. — `test_ui_loads_real_status_data` — INCONCLUSIVE_EXPECTED (row 1709)
- **MISC-0213-INTERACTIVE-STATES-ACCESSIBLE-PERSISTENT-479A6A** — Interactive states are accessible, persistent where required, and do not trigger hidden work. — `test_interactive_states_accessible_persistent_where` — INCONCLUSIVE_EXPECTED (row 1710)
- **MISC-0214-EXPECTED-BUILD-PACKAGE-TEST-E4FF2F** — Expected build/package/test artifact is produced and verifiable. — `test_expected_build_package_test_artifact` — SKIPPED_ENV (row 1711)
- **MISC-0215-PLATFORM-SPECIFIC-PATH-HEADLESS-D68468** — Platform-specific path or headless failure is explicit. — `test_platform_specific_path_headless_failure` — SKIPPED_ENV (row 1712)

## Hook/runtime support surface: asset-reminder (5)

- **MISC-0492-HOOK-FIRES-ONLY-INTENDED-807121** — Hook fires only on intended event and handles missing payload/env. — `test_hook_fires_only_intended_event` — SKIPPED_NA (row 1989)
- **MISC-0493-NO-OP-PATH-EXITS-1B9086** — No-op path exits cleanly without side effects. — `test_no_op_path_exits_cleanly` — INCONCLUSIVE_EXPECTED (row 1990)
- **MISC-0494-ANY-MUTATION-LIMITED-DOCUMENTED-1E7F90** — Any mutation is limited to documented paths and preserves user data. — `test_any_mutation_limited_documented_paths` — SKIPPED_NA (row 1991)
- **MISC-0495-HOOK-RECORDS-USEFUL-LOG-92C320** — Hook records useful log/evidence for success/failure. — `test_hook_records_useful_log_evidence` — SKIPPED_NA (row 1992)
- **MISC-0496-HOOK-FAILURE-DOES-NOT-0B8C7C** — Hook failure does not block unrelated runtime paths unless intended. — `test_hook_failure_does_not_block` — SKIPPED_NA (row 1993)

## Hook/runtime support surface: executor-reminder (5)

- **MISC-0537-HOOK-FIRES-ONLY-INTENDED-6757DF** — Hook fires only on intended event and handles missing payload/env. — `test_hook_fires_only_intended_event` — INCONCLUSIVE_EXPECTED (row 2034)
- **MISC-0538-NO-OP-PATH-EXITS-AA1D21** — No-op path exits cleanly without side effects. — `test_no_op_path_exits_cleanly` — SKIPPED_NA (row 2035)
- **MISC-0539-ANY-MUTATION-LIMITED-DOCUMENTED-7F1D9C** — Any mutation is limited to documented paths and preserves user data. — `test_any_mutation_limited_documented_paths` — SKIPPED_NA (row 2036)
- **MISC-0540-HOOK-RECORDS-USEFUL-LOG-2D6C05** — Hook records useful log/evidence for success/failure. — `test_hook_records_useful_log_evidence` — SKIPPED_NA (row 2037)
- **MISC-0541-HOOK-FAILURE-DOES-NOT-5AAB54** — Hook failure does not block unrelated runtime paths unless intended. — `test_hook_failure_does_not_block` — INCONCLUSIVE_EXPECTED (row 2038)

## Hook/runtime support surface: experience-reminder (5)

- **MISC-0542-HOOK-FIRES-ONLY-INTENDED-255C85** — Hook fires only on intended event and handles missing payload/env. — `test_hook_fires_only_intended_event` — SKIPPED_NA (row 2039)
- **MISC-0543-NO-OP-PATH-EXITS-DF3AF2** — No-op path exits cleanly without side effects. — `test_no_op_path_exits_cleanly` — FAIL (row 2040)
- **MISC-0544-ANY-MUTATION-LIMITED-DOCUMENTED-0C8569** — Any mutation is limited to documented paths and preserves user data. — `test_any_mutation_limited_documented_paths` — SKIPPED_NA (row 2041)
- **MISC-0545-HOOK-RECORDS-USEFUL-LOG-08DEFA** — Hook records useful log/evidence for success/failure. — `test_hook_records_useful_log_evidence` — SKIPPED_NA (row 2042)
- **MISC-0546-HOOK-FAILURE-DOES-NOT-CE6962** — Hook failure does not block unrelated runtime paths unless intended. — `test_hook_failure_does_not_block` — SKIPPED_NA (row 2043)

## Hook/runtime support surface: identity-reminder (5)

- **MISC-0552-HOOK-FIRES-ONLY-INTENDED-54F0C1** — Hook fires only on intended event and handles missing payload/env. — `test_hook_fires_only_intended_event` — SKIPPED_NA (row 2049)
- **MISC-0553-NO-OP-PATH-EXITS-030DCA** — No-op path exits cleanly without side effects. — `test_no_op_path_exits_cleanly` — SKIPPED_NA (row 2050)
- **MISC-0554-ANY-MUTATION-LIMITED-DOCUMENTED-C0E3A4** — Any mutation is limited to documented paths and preserves user data. — `test_any_mutation_limited_documented_paths` — SKIPPED_NA (row 2051)
- **MISC-0555-HOOK-RECORDS-USEFUL-LOG-F4A8D3** — Hook records useful log/evidence for success/failure. — `test_hook_records_useful_log_evidence` — SKIPPED_NA (row 2052)
- **MISC-0556-HOOK-FAILURE-DOES-NOT-6F7BE8** — Hook failure does not block unrelated runtime paths unless intended. — `test_hook_failure_does_not_block` — SKIPPED_NA (row 2053)

## Installable component: autosci (5)

- **MISC-0016-COMPONENT-MANIFEST-DECLARES-DEFAULT-7B74CE** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1513)
- **MISC-0017-COMPONENT-INSTALLS-ONLY-WHEN-950252** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — PASS (row 1514)
- **MISC-0018-INSTALLED-ROOTS-FILES-MATCH-B97074** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — PASS (row 1515)
- **MISC-0019-DOCTOR-DETECTS-MISSING-COMPONENT-24EF05** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1516)
- **MISC-0020-UNINSTALL-REMOVES-COMPONENT-OWNED-DBD142** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — PASS (row 1517)

## Installable component: codex-bridge (5)

- **MISC-0046-COMPONENT-MANIFEST-DECLARES-DEFAULT-0D21B7** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1543)
- **MISC-0047-COMPONENT-INSTALLS-ONLY-WHEN-08535D** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — INCONCLUSIVE_EXPECTED (row 1544)
- **MISC-0048-INSTALLED-ROOTS-FILES-MATCH-86E6FC** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_ENV (row 1545)
- **MISC-0049-DOCTOR-DETECTS-MISSING-COMPONENT-6D441C** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1546)
- **MISC-0050-UNINSTALL-REMOVES-COMPONENT-OWNED-EF240F** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_ENV (row 1547)

## Installable component: core-runtime (5)

- **MISC-0006-COMPONENT-MANIFEST-DECLARES-DEFAULT-F31626** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1503)
- **MISC-0007-COMPONENT-INSTALLS-ONLY-WHEN-387A6B** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — SKIPPED_ENV (row 1504)
- **MISC-0008-INSTALLED-ROOTS-FILES-MATCH-B4E269** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_ENV (row 1505)
- **MISC-0009-DOCTOR-DETECTS-MISSING-COMPONENT-7D4463** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1506)
- **MISC-0010-UNINSTALL-REMOVES-COMPONENT-OWNED-4C9F1B** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_ENV (row 1507)

## Installable component: daemons (5)

- **MISC-0061-COMPONENT-MANIFEST-DECLARES-DEFAULT-00577F** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1558)
- **MISC-0062-COMPONENT-INSTALLS-ONLY-WHEN-C44474** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — SKIPPED_ENV (row 1559)
- **MISC-0063-INSTALLED-ROOTS-FILES-MATCH-06CC29** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_ENV (row 1560)
- **MISC-0064-DOCTOR-DETECTS-MISSING-COMPONENT-9EE132** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1561)
- **MISC-0065-UNINSTALL-REMOVES-COMPONENT-OWNED-5448E8** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_ENV (row 1562)

## Installable component: harness (5)

- **MISC-0011-COMPONENT-MANIFEST-DECLARES-DEFAULT-B35C07** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1508)
- **MISC-0012-COMPONENT-INSTALLS-ONLY-WHEN-DB6B7A** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — PASS (row 1509)
- **MISC-0013-INSTALLED-ROOTS-FILES-MATCH-1629C7** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — PASS (row 1510)
- **MISC-0014-DOCTOR-DETECTS-MISSING-COMPONENT-D3CECF** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1511)
- **MISC-0015-UNINSTALL-REMOVES-COMPONENT-OWNED-7CB9A4** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — PASS (row 1512)

## Installable component: kernel (5)

- **MISC-0001-COMPONENT-MANIFEST-DECLARES-DEFAULT-61F0CF** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — PASS (row 1498)
- **MISC-0002-COMPONENT-INSTALLS-ONLY-WHEN-1FDC60** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — SKIPPED_NA (row 1499)
- **MISC-0003-INSTALLED-ROOTS-FILES-MATCH-92DF3B** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_NA (row 1500)
- **MISC-0004-DOCTOR-DETECTS-MISSING-COMPONENT-9DBF8F** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1501)
- **MISC-0005-UNINSTALL-REMOVES-COMPONENT-OWNED-D1844A** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_NA (row 1502)

## Installable component: mempalace (5)

- **MISC-0056-COMPONENT-MANIFEST-DECLARES-DEFAULT-CA234C** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1553)
- **MISC-0057-COMPONENT-INSTALLS-ONLY-WHEN-197AD2** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — SKIPPED_ENV (row 1554)
- **MISC-0058-INSTALLED-ROOTS-FILES-MATCH-7BC484** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_ENV (row 1555)
- **MISC-0059-DOCTOR-DETECTS-MISSING-COMPONENT-8AC771** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1556)
- **MISC-0060-UNINSTALL-REMOVES-COMPONENT-OWNED-C24EE1** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_ENV (row 1557)

## Installable component: skills-browser (5)

- **MISC-0041-COMPONENT-MANIFEST-DECLARES-DEFAULT-5C6283** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — SKIPPED_NA (row 1538)
- **MISC-0042-COMPONENT-INSTALLS-ONLY-WHEN-DDDFDC** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — SKIPPED_NA (row 1539)
- **MISC-0043-INSTALLED-ROOTS-FILES-MATCH-E8A632** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_NA (row 1540)
- **MISC-0044-DOCTOR-DETECTS-MISSING-COMPONENT-0103F4** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — SKIPPED_NA (row 1541)
- **MISC-0045-UNINSTALL-REMOVES-COMPONENT-OWNED-14670B** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_NA (row 1542)

## Installable component: skills-calendar (5)

- **MISC-0036-COMPONENT-MANIFEST-DECLARES-DEFAULT-8BB14E** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1533)
- **MISC-0037-COMPONENT-INSTALLS-ONLY-WHEN-B6A469** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — SKIPPED_NA (row 1534)
- **MISC-0038-INSTALLED-ROOTS-FILES-MATCH-C5419E** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_NA (row 1535)
- **MISC-0039-DOCTOR-DETECTS-MISSING-COMPONENT-D4FC0A** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1536)
- **MISC-0040-UNINSTALL-REMOVES-COMPONENT-OWNED-4EB840** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_NA (row 1537)

## Installable component: skills-md (5)

- **MISC-0021-COMPONENT-MANIFEST-DECLARES-DEFAULT-F33362** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1518)
- **MISC-0022-COMPONENT-INSTALLS-ONLY-WHEN-E12B22** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — INCONCLUSIVE_EXPECTED (row 1519)
- **MISC-0023-INSTALLED-ROOTS-FILES-MATCH-57270D** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_NA (row 1520)
- **MISC-0024-DOCTOR-DETECTS-MISSING-COMPONENT-4AC051** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1521)
- **MISC-0025-UNINSTALL-REMOVES-COMPONENT-OWNED-C56EB9** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_NA (row 1522)

## Installable component: skills-obsidian (5)

- **MISC-0031-COMPONENT-MANIFEST-DECLARES-DEFAULT-F81AA6** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1528)
- **MISC-0032-COMPONENT-INSTALLS-ONLY-WHEN-35B98A** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — INCONCLUSIVE_EXPECTED (row 1529)
- **MISC-0033-INSTALLED-ROOTS-FILES-MATCH-FF7886** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_NA (row 1530)
- **MISC-0034-DOCTOR-DETECTS-MISSING-COMPONENT-EB812A** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1531)
- **MISC-0035-UNINSTALL-REMOVES-COMPONENT-OWNED-692059** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_NA (row 1532)

## Installable component: skills-office (5)

- **MISC-0026-COMPONENT-MANIFEST-DECLARES-DEFAULT-FB7442** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1523)
- **MISC-0027-COMPONENT-INSTALLS-ONLY-WHEN-7167D7** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — INCONCLUSIVE_EXPECTED (row 1524)
- **MISC-0028-INSTALLED-ROOTS-FILES-MATCH-450AA6** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_NA (row 1525)
- **MISC-0029-DOCTOR-DETECTS-MISSING-COMPONENT-F9513E** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1526)
- **MISC-0030-UNINSTALL-REMOVES-COMPONENT-OWNED-F0D581** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_NA (row 1527)

## Installable component: solar-max (5)

- **MISC-0051-COMPONENT-MANIFEST-DECLARES-DEFAULT-83C262** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1548)
- **MISC-0052-COMPONENT-INSTALLS-ONLY-WHEN-9FA0BC** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — SKIPPED_NA (row 1549)
- **MISC-0053-INSTALLED-ROOTS-FILES-MATCH-3509C7** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_NA (row 1550)
- **MISC-0054-DOCTOR-DETECTS-MISSING-COMPONENT-C60513** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1551)
- **MISC-0055-UNINSTALL-REMOVES-COMPONENT-OWNED-0CF1BA** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_NA (row 1552)

## Installable component: status-daemon (5)

- **MISC-0066-COMPONENT-MANIFEST-DECLARES-DEFAULT-6B9935** — Component manifest declares default state, platforms, requirements, dependencies, and description. — `test_component_manifest_declares_default_state` — INCONCLUSIVE_EXPECTED (row 1563)
- **MISC-0067-COMPONENT-INSTALLS-ONLY-WHEN-F7587E** — Component installs only when selected/default/auto rules are satisfied. — `test_component_installs_only_when_selected` — SKIPPED_ENV (row 1564)
- **MISC-0068-INSTALLED-ROOTS-FILES-MATCH-EFC03B** — Installed roots/files match receipt and do not overwrite user-owned data. — `test_installed_roots_files_match_receipt` — SKIPPED_ENV (row 1565)
- **MISC-0069-DOCTOR-DETECTS-MISSING-COMPONENT-A5AC38** — Doctor detects missing component roots and repair restores them when possible. — `test_doctor_detects_missing_component_roots` — INCONCLUSIVE_EXPECTED (row 1566)
- **MISC-0070-UNINSTALL-REMOVES-COMPONENT-OWNED-C6D3D3** — Uninstall removes component-owned files and preserves requested user data. — `test_uninstall_removes_component_owned_files` — SKIPPED_ENV (row 1567)

## Installer / packaging surface: component selection (5)

- **MISC-0254-ACCEPTED-FLAGS-ENV-CONFIG-62B307** — Accepted flags/env/config are parsed and invalid/missing required values emit exact remedy. — `test_accepted_flags_env_config_parsed` — PASS (row 1751)
- **MISC-0255-PLATFORM-SPECIFIC-PATH-RUNS-9F88CE** — Platform-specific path runs or reports unsupported/experimental status clearly. — `test_platform_specific_path_runs_reports` — PASS (row 1752)
- **MISC-0256-EXPECTED-INSTALLER-PACKAGE-ARTIFACTS-9C0AFD** — Expected installer/package artifacts are produced with version/component metadata. — `test_expected_installer_package_artifacts_produced` — PASS (row 1753)
- **MISC-0257-DRY-RUN-WRITES-NOTHING-DF9732** — Dry-run writes nothing; repeated operations are idempotent or report drift safely. — `test_dry_run_writes_nothing_repeated` — PASS (row 1754)
- **MISC-0258-FAILURES-STOP-CLEANLY-ACTIONABLE-725271** — Failures stop cleanly with actionable remedy and no partial hidden success. — `test_failures_stop_cleanly_actionable_remedy` — PASS (row 1755)

## Installer / packaging surface: generated component docs (5)

- **MISC-0259-ACCEPTED-FLAGS-ENV-CONFIG-C3B545** — Accepted flags/env/config are parsed and invalid/missing required values emit exact remedy. — `test_accepted_flags_env_config_parsed` — PASS (row 1756)
- **MISC-0260-PLATFORM-SPECIFIC-PATH-RUNS-FB9237** — Platform-specific path runs or reports unsupported/experimental status clearly. — `test_platform_specific_path_runs_reports` — PASS (row 1757)
- **MISC-0261-EXPECTED-INSTALLER-PACKAGE-ARTIFACTS-CB4F5A** — Expected installer/package artifacts are produced with version/component metadata. — `test_expected_installer_package_artifacts_produced` — PASS (row 1758)
- **MISC-0262-DRY-RUN-WRITES-NOTHING-782FA0** — Dry-run writes nothing; repeated operations are idempotent or report drift safely. — `test_dry_run_writes_nothing_repeated` — PASS (row 1759)
- **MISC-0263-FAILURES-STOP-CLEANLY-ACTIONABLE-69A166** — Failures stop cleanly with actionable remedy and no partial hidden success. — `test_failures_stop_cleanly_actionable_remedy` — PASS (row 1760)

## Installer / packaging surface: GitHub release preparation (5)

- **MISC-0289-ACCEPTED-FLAGS-ENV-CONFIG-57233D** — Accepted flags/env/config are parsed and invalid/missing required values emit exact remedy. — `test_accepted_flags_env_config_parsed` — SKIPPED_NA (row 1786)
- **MISC-0290-PLATFORM-SPECIFIC-PATH-RUNS-AF1733** — Platform-specific path runs or reports unsupported/experimental status clearly. — `test_platform_specific_path_runs_reports` — SKIPPED_NA (row 1787)
- **MISC-0291-EXPECTED-INSTALLER-PACKAGE-ARTIFACTS-2CAD89** — Expected installer/package artifacts are produced with version/component metadata. — `test_expected_installer_package_artifacts_produced` — SKIPPED_NA (row 1788)
- **MISC-0292-DRY-RUN-WRITES-NOTHING-966C17** — Dry-run writes nothing; repeated operations are idempotent or report drift safely. — `test_dry_run_writes_nothing_repeated` — SKIPPED_NA (row 1789)
- **MISC-0293-FAILURES-STOP-CLEANLY-ACTIONABLE-AECCF8** — Failures stop cleanly with actionable remedy and no partial hidden success. — `test_failures_stop_cleanly_actionable_remedy` — SKIPPED_NA (row 1790)

## Installer / packaging surface: install receipt (5)

- **MISC-0249-ACCEPTED-FLAGS-ENV-CONFIG-81DF5F** — Accepted flags/env/config are parsed and invalid/missing required values emit exact remedy. — `test_accepted_flags_env_config_parsed` — PASS (row 1746)
- **MISC-0250-PLATFORM-SPECIFIC-PATH-RUNS-0939DE** — Platform-specific path runs or reports unsupported/experimental status clearly. — `test_platform_specific_path_runs_reports` — PASS (row 1747)
- **MISC-0251-EXPECTED-INSTALLER-PACKAGE-ARTIFACTS-26C90A** — Expected installer/package artifacts are produced with version/component metadata. — `test_expected_installer_package_artifacts_produced` — PASS (row 1748)
- **MISC-0252-DRY-RUN-WRITES-NOTHING-F5380A** — Dry-run writes nothing; repeated operations are idempotent or report drift safely. — `test_dry_run_writes_nothing_repeated` — PASS (row 1749)
- **MISC-0253-FAILURES-STOP-CLEANLY-ACTIONABLE-357837** — Failures stop cleanly with actionable remedy and no partial hidden success. — `test_failures_stop_cleanly_actionable_remedy` — PASS (row 1750)

## Installer / packaging surface: release checklist (5)

- **MISC-0294-ACCEPTED-FLAGS-ENV-CONFIG-ED0376** — Accepted flags/env/config are parsed and invalid/missing required values emit exact remedy. — `test_accepted_flags_env_config_parsed` — INCONCLUSIVE_EXPECTED (row 1791)
- **MISC-0295-PLATFORM-SPECIFIC-PATH-RUNS-BFAD35** — Platform-specific path runs or reports unsupported/experimental status clearly. — `test_platform_specific_path_runs_reports` — SKIPPED_NA (row 1792)
- **MISC-0296-EXPECTED-INSTALLER-PACKAGE-ARTIFACTS-32EE64** — Expected installer/package artifacts are produced with version/component metadata. — `test_expected_installer_package_artifacts_produced` — SKIPPED_NA (row 1793)
- **MISC-0297-DRY-RUN-WRITES-NOTHING-3B8C15** — Dry-run writes nothing; repeated operations are idempotent or report drift safely. — `test_dry_run_writes_nothing_repeated` — SKIPPED_NA (row 1794)
- **MISC-0298-FAILURES-STOP-CLEANLY-ACTIONABLE-B7B849** — Failures stop cleanly with actionable remedy and no partial hidden success. — `test_failures_stop_cleanly_actionable_remedy` — SKIPPED_NA (row 1795)

## Installer / packaging surface: release packaging (5)

- **MISC-0279-ACCEPTED-FLAGS-ENV-CONFIG-F0A876** — Accepted flags/env/config are parsed and invalid/missing required values emit exact remedy. — `test_accepted_flags_env_config_parsed` — FAIL (row 1776)
- **MISC-0280-PLATFORM-SPECIFIC-PATH-RUNS-AE2BA1** — Platform-specific path runs or reports unsupported/experimental status clearly. — `test_platform_specific_path_runs_reports` — PASS (row 1777)
- **MISC-0281-EXPECTED-INSTALLER-PACKAGE-ARTIFACTS-3EE006** — Expected installer/package artifacts are produced with version/component metadata. — `test_expected_installer_package_artifacts_produced` — PASS (row 1778)
- **MISC-0282-DRY-RUN-WRITES-NOTHING-898484** — Dry-run writes nothing; repeated operations are idempotent or report drift safely. — `test_dry_run_writes_nothing_repeated` — FAIL (row 1779)
- **MISC-0283-FAILURES-STOP-CLEANLY-ACTIONABLE-41DB07** — Failures stop cleanly with actionable remedy and no partial hidden success. — `test_failures_stop_cleanly_actionable_remedy` — PASS (row 1780)

## QA inventory top-level area: AutoSci (4)

- **MISC-0404-AREA-HAS-TRACKED-FILES-9977FD** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1901)
- **MISC-0405-ROWS-MAP-REAL-TESTS-19127B** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1902)
- **MISC-0406-AREA-HAS-EXPLICIT-CRITERIA-4C7FA0** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1903)
- **MISC-0407-COVERAGE-STATUS-JUSTIFIED-NOT-276EC4** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1904)

## QA inventory top-level area: Benchmarks (4)

- **MISC-0408-AREA-HAS-TRACKED-FILES-B72FA6** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1905)
- **MISC-0409-ROWS-MAP-REAL-TESTS-ABD637** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1906)
- **MISC-0410-AREA-HAS-EXPLICIT-CRITERIA-B259D4** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1907)
- **MISC-0411-COVERAGE-STATUS-JUSTIFIED-NOT-869348** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1908)

## QA inventory top-level area: Browser (4)

- **MISC-0412-AREA-HAS-TRACKED-FILES-D7CBE4** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1909)
- **MISC-0413-ROWS-MAP-REAL-TESTS-69E4FD** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1910)
- **MISC-0414-AREA-HAS-EXPLICIT-CRITERIA-92E768** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1911)
- **MISC-0415-COVERAGE-STATUS-JUSTIFIED-NOT-47F17D** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1912)

## QA inventory top-level area: CI (4)

- **MISC-0416-AREA-HAS-TRACKED-FILES-0CFF08** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1913)
- **MISC-0417-ROWS-MAP-REAL-TESTS-A170D1** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1914)
- **MISC-0418-AREA-HAS-EXPLICIT-CRITERIA-002C8A** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1915)
- **MISC-0419-COVERAGE-STATUS-JUSTIFIED-NOT-84F617** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1916)

## QA inventory top-level area: CLI (4)

- **MISC-0420-AREA-HAS-TRACKED-FILES-A76A1C** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1917)
- **MISC-0421-ROWS-MAP-REAL-TESTS-C758D1** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1918)
- **MISC-0422-AREA-HAS-EXPLICIT-CRITERIA-70B84A** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1919)
- **MISC-0423-COVERAGE-STATUS-JUSTIFIED-NOT-8D0299** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1920)

## QA inventory top-level area: Components (4)

- **MISC-0424-AREA-HAS-TRACKED-FILES-306B99** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1921)
- **MISC-0425-ROWS-MAP-REAL-TESTS-C0C681** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1922)
- **MISC-0426-AREA-HAS-EXPLICIT-CRITERIA-73F625** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1923)
- **MISC-0427-COVERAGE-STATUS-JUSTIFIED-NOT-56D831** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1924)

## QA inventory top-level area: Core (4)

- **MISC-0428-AREA-HAS-TRACKED-FILES-9C355B** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1925)
- **MISC-0429-ROWS-MAP-REAL-TESTS-016FB0** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1926)
- **MISC-0430-AREA-HAS-EXPLICIT-CRITERIA-F06934** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1927)
- **MISC-0431-COVERAGE-STATUS-JUSTIFIED-NOT-C6D2B8** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1928)

## QA inventory top-level area: Dashboard (4)

- **MISC-0432-AREA-HAS-TRACKED-FILES-47D90E** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1929)
- **MISC-0433-ROWS-MAP-REAL-TESTS-EC40E5** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1930)
- **MISC-0434-AREA-HAS-EXPLICIT-CRITERIA-0FB267** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — INCONCLUSIVE_EXPECTED (row 1931)
- **MISC-0435-COVERAGE-STATUS-JUSTIFIED-NOT-9A20C1** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1932)

## QA inventory top-level area: Desktop (4)

- **MISC-0436-AREA-HAS-TRACKED-FILES-BBBA95** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1933)
- **MISC-0437-ROWS-MAP-REAL-TESTS-6C3D26** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1934)
- **MISC-0438-AREA-HAS-EXPLICIT-CRITERIA-5629FD** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1935)
- **MISC-0439-COVERAGE-STATUS-JUSTIFIED-NOT-A152CE** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1936)

## QA inventory top-level area: Harness (4)

- **MISC-0440-AREA-HAS-TRACKED-FILES-F1B17E** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1937)
- **MISC-0441-ROWS-MAP-REAL-TESTS-E3A9BA** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1938)
- **MISC-0442-AREA-HAS-EXPLICIT-CRITERIA-410FF7** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1939)
- **MISC-0443-COVERAGE-STATUS-JUSTIFIED-NOT-D75CF2** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1940)

## QA inventory top-level area: Hooks (4)

- **MISC-0444-AREA-HAS-TRACKED-FILES-E10AA5** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1941)
- **MISC-0445-ROWS-MAP-REAL-TESTS-257936** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1942)
- **MISC-0446-AREA-HAS-EXPLICIT-CRITERIA-B39664** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1943)
- **MISC-0447-COVERAGE-STATUS-JUSTIFIED-NOT-0DFEA3** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1944)

## QA inventory top-level area: Ingestion (4)

- **MISC-0448-AREA-HAS-TRACKED-FILES-305403** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1945)
- **MISC-0449-ROWS-MAP-REAL-TESTS-8432BC** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1946)
- **MISC-0450-AREA-HAS-EXPLICIT-CRITERIA-A64109** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1947)
- **MISC-0451-COVERAGE-STATUS-JUSTIFIED-NOT-D88AFA** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1948)

## QA inventory top-level area: Installer (4)

- **MISC-0452-AREA-HAS-TRACKED-FILES-EE6213** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1949)
- **MISC-0453-ROWS-MAP-REAL-TESTS-655FC4** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1950)
- **MISC-0454-AREA-HAS-EXPLICIT-CRITERIA-119188** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1951)
- **MISC-0455-COVERAGE-STATUS-JUSTIFIED-NOT-900BE3** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1952)

## QA inventory top-level area: Packaging (4)

- **MISC-0456-AREA-HAS-TRACKED-FILES-9A28ED** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1953)
- **MISC-0457-ROWS-MAP-REAL-TESTS-62B097** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1954)
- **MISC-0458-AREA-HAS-EXPLICIT-CRITERIA-37C445** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1955)
- **MISC-0459-COVERAGE-STATUS-JUSTIFIED-NOT-0C3B0A** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1956)

## QA inventory top-level area: QA Gates (4)

- **MISC-0460-AREA-HAS-TRACKED-FILES-75AB92** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1957)
- **MISC-0461-ROWS-MAP-REAL-TESTS-BA426F** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1958)
- **MISC-0462-AREA-HAS-EXPLICIT-CRITERIA-54FBF9** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1959)
- **MISC-0463-COVERAGE-STATUS-JUSTIFIED-NOT-F64F2F** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1960)

## QA inventory top-level area: Reports (4)

- **MISC-0464-AREA-HAS-TRACKED-FILES-1BA0DC** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1961)
- **MISC-0465-ROWS-MAP-REAL-TESTS-A5B0C7** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1962)
- **MISC-0466-AREA-HAS-EXPLICIT-CRITERIA-6DFECA** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1963)
- **MISC-0467-COVERAGE-STATUS-JUSTIFIED-NOT-D39B9F** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1964)

## QA inventory top-level area: Repository (4)

- **MISC-0468-AREA-HAS-TRACKED-FILES-54C3BA** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1965)
- **MISC-0469-ROWS-MAP-REAL-TESTS-C1F7E4** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1966)
- **MISC-0470-AREA-HAS-EXPLICIT-CRITERIA-5C94E3** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1967)
- **MISC-0471-COVERAGE-STATUS-JUSTIFIED-NOT-0CB5F6** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1968)

## QA inventory top-level area: Research (4)

- **MISC-0472-AREA-HAS-TRACKED-FILES-25F7F9** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1969)
- **MISC-0473-ROWS-MAP-REAL-TESTS-5CDDB5** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1970)
- **MISC-0474-AREA-HAS-EXPLICIT-CRITERIA-773235** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1971)
- **MISC-0475-COVERAGE-STATUS-JUSTIFIED-NOT-6A38D3** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1972)

## QA inventory top-level area: Runtime (4)

- **MISC-0476-AREA-HAS-TRACKED-FILES-09EA19** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1973)
- **MISC-0477-ROWS-MAP-REAL-TESTS-AC2F94** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1974)
- **MISC-0478-AREA-HAS-EXPLICIT-CRITERIA-14D315** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1975)
- **MISC-0479-COVERAGE-STATUS-JUSTIFIED-NOT-883A52** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1976)

## QA inventory top-level area: Skills (4)

- **MISC-0480-AREA-HAS-TRACKED-FILES-800260** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1977)
- **MISC-0481-ROWS-MAP-REAL-TESTS-79EF8D** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1978)
- **MISC-0482-AREA-HAS-EXPLICIT-CRITERIA-900F0C** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1979)
- **MISC-0483-COVERAGE-STATUS-JUSTIFIED-NOT-755058** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1980)

## QA inventory top-level area: Status Server (4)

- **MISC-0484-AREA-HAS-TRACKED-FILES-00C242** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1981)
- **MISC-0485-ROWS-MAP-REAL-TESTS-53AE21** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1982)
- **MISC-0486-AREA-HAS-EXPLICIT-CRITERIA-A9E519** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1983)
- **MISC-0487-COVERAGE-STATUS-JUSTIFIED-NOT-7E60BA** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1984)

## QA inventory top-level area: TVS (4)

- **MISC-0488-AREA-HAS-TRACKED-FILES-0F076D** — Area has tracked files/features enumerated and exclusions documented. — `test_area_has_tracked_files_features` — PASS (row 1985)
- **MISC-0489-ROWS-MAP-REAL-TESTS-BAFA19** — Feature rows map to real tests or documented gap/status. — `test_rows_map_real_tests_documented` — PASS (row 1986)
- **MISC-0490-AREA-HAS-EXPLICIT-CRITERIA-A9A52E** — Area has explicit criteria for happy, failure, blocked, skipped, and static-only cases. — `test_area_has_explicit_criteria_happy` — PASS (row 1987)
- **MISC-0491-COVERAGE-STATUS-JUSTIFIED-NOT-F55553** — Coverage status is justified and not treated as execution PASS without run evidence. — `test_coverage_status_justified_not_treated` — PASS (row 1988)

## Solar harness workflow: install / verify (3)

- **WF-0001-INSTALL-COMPLETES-USER-SCOPED-190948** — Install completes under user-scoped paths and writes receipt without sudo. — `test_install_completes_user_scoped_paths` — PASS (row 2)
- **WF-0002-VERIFICATION-REPORTS-DETERMINISTIC-DEPENDENCY-6F3D30** — Verification reports deterministic dependency and path status. — `test_verification_reports_deterministic_dependency_path` — PASS (row 3)
- **WF-0003-MISSING-DEPENDENCY-YIELDS-EXPLICIT-3493D5** — Missing dependency yields explicit remedy and no false live-readiness. — `test_missing_dependency_yields_explicit_remedy` — PASS (row 4)

## Solar harness workflow: migration / deployment (3)

- **WF-0025-PRODUCES-PLAN-DATA-PATHS-875510** — Produces plan with data paths and exclusions. — `test_produces_plan_data_paths_exclusions` — INCONCLUSIVE_EXPECTED (row 26)
- **WF-0026-EXTERNAL-TRANSFER-GATED-RECORDS-63588A** — External transfer is gated and records runtime evidence. — `test_external_transfer_gated_records_runtime` — SKIPPED_ENV (row 27)
- **WF-0027-FAILURE-LEAVES-SOURCE-DATA-40F13A** — Failure leaves source data intact and reports partial state. — `test_failure_leaves_source_data_intact` — FAIL (row 28)
