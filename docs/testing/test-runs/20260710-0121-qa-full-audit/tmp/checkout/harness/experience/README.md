# Solar Harness Experience Memory

This directory is the runtime store for the harness experience-memory layer.

Committed files:

- `index.db.schema.sql` defines the SQLite + FTS5 schema.
- `.gitignore` keeps local runtime data out of the public repository.

Generated locally:

- `index.db`, `experience.db`, WAL/SHM files
- `entries/`
- `trajectory/`
- `decisions.jsonl`
- `backfill.lock`

The generated files can contain local paths, sprint history, operator notes, and
machine-specific evidence. They are intentionally regenerated or exported through
controlled artifacts instead of being committed directly.

