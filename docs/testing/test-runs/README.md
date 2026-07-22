# Test Run Evidence Policy

Raw test-run evidence is local runtime state and must not be committed under
this directory. Store command logs, temporary checkouts, browser profiles,
coverage data, caches, screenshots, and per-case result files outside the
source checkout.

Recommended local layout:

```text
OpenSolar-canonical/        # clean source checkout
OpenSolar-QA-Evidence/      # machine-local run artifacts
```

A curated final report may be committed under `docs/testing/reports/` only
when it contains no credentials, machine-specific absolute paths, caches,
embedded environments, or raw browser state. It must identify the tested Git
commit, platform, runner command, exit status, and evidence manifest.

The historical run trees removed by the repository-hygiene cleanup remain
recoverable from Git commit `718aae9a66d291c4e1b55059188a5adfd74eea19`.
They are historical evidence only and must not be treated as current PASS
results without execution against the current canonical commit.

This README is the only path intentionally tracked below
`docs/testing/test-runs/`.
