# Paper Compile Checklist Diagnostics

Target: /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0008/pytest/test_autosci_skill_shim_paper_9/paper-submission-profile
Resolved target: /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0008/pytest/test_autosci_skill_shim_paper_9/paper-submission-profile
Status: completed

| Check | Status | Detail |
| --- | --- | --- |
| target_resolved | ok | Resolved to /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0008/pytest/test_autosci_skill_shim_paper_9/paper-submission-profile |
| latex_source_present | ok | 1 LaTeX source file(s) found. |
| compiled_pdf_present | ok | 1 structurally valid PDF file(s) found. |
| bibliography_present | warn | No .bib files were found. |
| latexmk_available | warn | latexmk was not found on PATH; approved execution may use another allowlisted TeX executor. |
| tex_executor_available | ok | pdflatex=/Library/TeX/texbin/pdflatex, xelatex=/Library/TeX/texbin/xelatex, lualatex=/Library/TeX/texbin/lualatex |
| checklist_requested | ok | Checklist mode was requested. |
| auto_fix_requested | ok | Auto-fix was not requested. |
| compile_execution | warn | The bridge produced compile diagnostics only; it did not run a TeX executor or mutate sources. |
| approval_contract_verified | warn | Approval/runtime contract is incomplete; compile side effects were not executed by this bridge. |
| runtime_semantic_verified | warn | Runtime evidence did not pass compile-specific semantic checks. |
| unconfirmed_marker_scan | ok | No [UNCONFIRMED] markers were found in scanned source files. |
| anonymity_check | ok | Anonymous mode requested and no explicit non-anonymous author blocks were found. |
| page_limit_check | ok | Verified page count 6.0 is within limit 8.0. |
| font_size_check | ok | Verified minimum font size 11.0 is >= required 10.0. |
| venue_submission_profile | ok | Venue submission profile loaded with source-backed requirements. |
| pdf_inspection | warn | PDF inspection evidence is missing or invalid; page/font proof may be CLI-only. |
| publication_submission_audit | warn | Publication submission audit evidence is missing, invalid, or has blocking checks. |
| publication_submission_boundary | ok | Submission readiness boundary passed. |

## Submission Checks

| Check | Status | Detail |
| --- | --- | --- |
| unconfirmed_marker_scan | ok | No [UNCONFIRMED] markers were found in scanned source files. |
| anonymity_check | ok | Anonymous mode requested and no explicit non-anonymous author blocks were found. |
| page_limit_check | ok | Verified page count 6.0 is within limit 8.0. |
| font_size_check | ok | Verified minimum font size 11.0 is >= required 10.0. |

## Submission Boundary

- status: submission_ready
- submission_ready: True
- blocking_checks: N/A
- venue_status: venue_submission_incomplete
- venue_submission_ready: False
- venue_blocking_checks: pdf_inspection
- submission_audit_status: submission_audit_missing
- submission_audit_ready: False
- submission_audit_blocking_checks: venue_submission_ready, publication_submission_audit
- portal_submission_completed: False
- submission_profile_status: loaded
- submission_profile_path: iclr-submission-profile.json
- pdf_inspection_status: missing
- pdf_inspection_path: N/A
- submission_audit_evidence_status: missing
- submission_audit_path: N/A

## Files

- latex_files: paper-submission-profile/main.tex
- pdf_files: paper-submission-profile/main.pdf
- markdown_files: N/A
- bibliography_files: N/A

## Limitations

- Paper compile currently performs a bounded checklist and diagnostics pass only.
- The bridge does not run a TeX executor, mutate source files, or claim PDF compilation without explicit approved execution.
- Approval/runtime evidence contract is not fully verified: approval_ref, allowlist_evidence, before_artifacts, runtime_evidence, after_artifacts
- Venue submission readiness is not proven; supply a valid submission_profile and pdf_inspection evidence.
- Publication submission audit readiness is not proven; supply valid submission_audit evidence.
