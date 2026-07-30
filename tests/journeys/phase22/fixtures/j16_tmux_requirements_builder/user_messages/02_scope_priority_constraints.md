Target repository path: {project_path}

Priority: P0 because trial billing safety is more important than loyalty discounts.

Scope: repair only the checkout discount rule in discounts.py and update tests only if the existing test intent is wrong. Do not modify unrelated files.

Constraints: stdlib only, no new dependencies, no network calls, no generated data files, no report edits, no commits.

Acceptance: running `{test_command}` from the target repository passes. Trial users must always receive 0 percent discount even if their tier is pro or enterprise. Non-trial pro users should still receive 20 percent and non-trial enterprise users should still receive 30 percent.
