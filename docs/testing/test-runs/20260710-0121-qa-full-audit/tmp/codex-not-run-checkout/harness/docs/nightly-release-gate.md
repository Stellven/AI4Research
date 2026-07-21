# Solar Nightly Release Gate

`Solar Nightly Release Gate` is the heavy release validation workflow for checks
that should not block normal pull requests.

## Trigger modes

- `workflow_dispatch` with `mode=preflight`: checks syntax, release dry-run,
  plugin manifest validation, and reports whether external dependencies are
  available.
- `workflow_dispatch` with `mode=full`: runs the full S7 release gate and fails
  if external dependencies are missing.
- `schedule`: runs preflight daily. It runs full mode only when
  `SOLAR_NIGHTLY_RELEASE_FULL=1` is configured as a repository variable.

## Repository variables

- `SOLAR_NIGHTLY_RUNNER`: optional runner label. Use a self-hosted runner when
  Mirage, Google Drive, TVS, and Bun are only available on a prepared machine.
- `SOLAR_NIGHTLY_RELEASE_FULL`: set to `1` to run the full S7 release gate on the
  daily schedule.
- `SOLAR_TVS_ROOT`: path to a TVS checkout containing `index.ts`.

## Release doctor

Run the reusable doctor before enabling full mode on a new runner:

```bash
python harness/lib/nightly_release_doctor.py --harness-dir harness --markdown
```

Preflight mode exits successfully when lightweight release checks pass, even if
full-only dependencies such as `SOLAR_TVS_ROOT`, Bun, or Mirage `/drive` are not
ready. Full mode must require those dependencies:

```bash
python harness/lib/nightly_release_doctor.py --harness-dir harness --require-full --markdown
```

## Full gate coverage

Full mode runs `harness/tests/release/test-s7-release.sh`, including real release
tarball creation, checksum and manifest validation, publish audit, capability
plane E2E, expanded capability plane E2E, capability fusion benchmark, platform
workflow benchmark, Mirage `/drive`, Bun, and TVS renderer checks.

The normal `Solar CI` workflow keeps lightweight PR gates green without requiring
those external services.
