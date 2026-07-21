# Paper Compile Checklist Diagnostics

Target: /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v3/temp/eligible-0006/pytest/test_autosci_skill_shim_reject0/invalid-pdf-paper
Resolved target: /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v3/temp/eligible-0006/pytest/test_autosci_skill_shim_reject0/invalid-pdf-paper
Status: inconclusive

| Check | Status | Detail |
| --- | --- | --- |
| target_resolved | ok | Resolved to /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v3/temp/eligible-0006/pytest/test_autosci_skill_shim_reject0/invalid-pdf-paper |
| latex_source_present | ok | 1 LaTeX source file(s) found. |
| compiled_pdf_present | warn | No structurally valid compiled PDF was found. |
| bibliography_present | warn | No .bib files were found. |
| latexmk_available | ok | /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v3/temp/eligible-0006/pytest/test_autosci_skill_shim_reject0/bin/latexmk |
| tex_executor_available | ok | latexmk=/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v3/temp/eligible-0006/pytest/test_autosci_skill_shim_reject0/bin/latexmk, pdflatex=/Library/TeX/texbin/pdflatex, xelatex=/Library/TeX/texbin/xelatex, lualatex=/Library/TeX/texbin/lualatex |
| checklist_requested | ok | Checklist mode was requested. |
| auto_fix_requested | ok | Auto-fix was not requested. |
| compile_execution | warn | Approved executor did not complete: semantic runtime incomplete |
| approval_contract_verified | ok | Approval, allowlist, runtime, and before/after evidence are verified. |
| runtime_semantic_verified | warn | Runtime evidence did not pass compile-specific semantic checks. |
| unconfirmed_marker_scan | ok | No [UNCONFIRMED] markers were found in scanned source files. |
| anonymity_check | warn | Anonymous/double-blind submission mode was not requested, so anonymity is not claimed. |
| page_limit_check | warn | Page limit compliance is unconfirmed; supply page_limit and verified_page_count evidence. |
| font_size_check | warn | Font-size compliance is unconfirmed; supply minimum font-size evidence from a PDF checker. |
| venue_submission_profile | warn | Venue submission profile is missing, invalid, or conflicts with CLI evidence. |
| pdf_inspection | warn | PDF inspection evidence is missing or invalid; page/font proof may be CLI-only. |
| publication_submission_audit | warn | Publication submission audit evidence is missing, invalid, or has blocking checks. |
| publication_submission_boundary | warn | Submission readiness boundary is incomplete; see publication_submission_boundary.json. |

## Submission Checks

| Check | Status | Detail |
| --- | --- | --- |
| unconfirmed_marker_scan | ok | No [UNCONFIRMED] markers were found in scanned source files. |
| anonymity_check | warn | Anonymous/double-blind submission mode was not requested, so anonymity is not claimed. |
| page_limit_check | warn | Page limit compliance is unconfirmed; supply page_limit and verified_page_count evidence. |
| font_size_check | warn | Font-size compliance is unconfirmed; supply minimum font-size evidence from a PDF checker. |

## Submission Boundary

- status: submission_incomplete
- submission_ready: False
- blocking_checks: anonymity_check, font_size_check, page_limit_check, compiled_pdf_verified
- venue_status: venue_profile_missing
- venue_submission_ready: False
- venue_blocking_checks: venue_submission_profile, pdf_inspection
- submission_audit_status: submission_audit_missing
- submission_audit_ready: False
- submission_audit_blocking_checks: venue_submission_ready, publication_submission_audit
- portal_submission_completed: False
- submission_profile_status: missing
- submission_profile_path: N/A
- pdf_inspection_status: missing
- pdf_inspection_path: N/A
- submission_audit_evidence_status: missing
- submission_audit_path: N/A

## Files

- latex_files: invalid-pdf-paper/main.tex
- pdf_files: invalid-pdf-paper/main.pdf
- markdown_files: N/A
- bibliography_files: N/A

## Limitations

- Paper compile currently performs a bounded checklist and diagnostics pass only.
- The bridge does not run a TeX executor, mutate source files, or claim PDF compilation without explicit approved execution.
- No structurally valid compiled PDF was found in the target path.
- Submission readiness includes warnings or unconfirmed checks; see submission_checks in the compile checklist.
- Publication compile evidence does not prove submission readiness; review blocking_checks and submission_checks.
- Venue submission readiness is not proven; supply a valid submission_profile and pdf_inspection evidence.
- Publication submission audit readiness is not proven; supply valid submission_audit evidence.
