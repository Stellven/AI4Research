# Schema migrations

Incremental, forward-only schema changes applied on top of the baseline schema
in `core/db/schema/`. The runner is `lib/installer/migrate.sh` (`db_migrate`),
invoked by `install.sh` after `db_init` and therefore by `solar update`.

## How it works

- A global `solar_meta(key, value)` table holds `schema_version`; a
  `schema_migrations(id, applied_at)` ledger records which files have run.
- On every install/update the runner applies each `NNNN-*.sql` file here that
  is not yet in the ledger, in filename order, recording each as it goes.
- Re-running is a no-op (already-applied files are skipped).

## Authoring a migration

1. **Never edit the baseline** in `core/db/schema/` for a schema change to an
   already-shipped table. Add a new file here instead. The baseline is frozen as
   "the schema as of the migrations feature"; migrations carry it forward. (New,
   self-contained subsystems may still ship as a new baseline `core/db/schema/`
   file, since `IF NOT EXISTS` makes that safe for existing databases.)
2. Name it `NNNN-short-description.sql` with a zero-padded incrementing number
   (`0001-...`, `0002-...`). The number drives both apply order and the reported
   `schema_version`.
3. Make the SQL safe to apply once on a database created from the frozen
   baseline plus all prior migrations. Wrap multi-statement migrations in
   `BEGIN; ... COMMIT;` so a mid-file failure rolls back cleanly.

There are no migrations yet: the baseline is current, so a fresh install records
`schema_version = 0` and applies nothing.
