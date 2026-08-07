# Quarantined historical tests

Files in this directory are retained for diagnostic history but are not
accepted as executable product evidence. Each file is renamed with a
`disabled_` prefix and is listed in `legacy_harness/manifest.json` with its
original path and reason.

A quarantined test may return to an executable test directory only after its
production target exists and its assertions exercise current behavior.
