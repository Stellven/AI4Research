#!/usr/bin/env bash

# Apply pending schema migrations against $SOLAR_DB, after db_init has created
# the baseline. Defuses the upgrade time-bomb: today every table is CREATE IF
# NOT EXISTS with no global version marker, so the first schema change silently
# misses already-installed databases.
#
# Builds on the in-tree versioning precedents (the experience_meta
# schema_version key in core/db/schema/80-experience.sql and ont_versions in
# 59-ontology-v1-compat.sql): a global key/value meta table (solar_meta) holds
# the schema_version, and a ledger (schema_migrations) records which migration
# files have already run.
#
# Convention -- FROZEN BASELINE + ADDITIVE MIGRATIONS:
#   * core/db/schema/*.sql is the baseline schema as of this feature; it is
#     applied (idempotent, IF NOT EXISTS) on every install by db_init.
#   * every LATER schema change is a NEW file core/db/migrations/NNNN-*.sql and
#     is NEVER folded back into the baseline.
#   * the ledger makes each migration run exactly once, so applying forward on
#     a fresh install and catching up an older install use one code path, and
#     re-running is a safe no-op.
db_migrate() {
    migrations_dir="$SOURCE_DIR/core/db/migrations"
    dry_run_note "apply schema migrations from $migrations_dir" && return 0
    [ -f "$SOLAR_DB" ] || die "database missing for migration: $SOLAR_DB (run db_init first)"
    SOLAR_DB="$SOLAR_DB" MIGRATIONS_DIR="$migrations_dir" "${SOLAR_PYTHON:-python3}" - <<'PY'
import glob
import os
import re
import sqlite3

db_path = os.environ["SOLAR_DB"]
migrations_dir = os.environ["MIGRATIONS_DIR"]

conn = sqlite3.connect(db_path)
try:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS solar_meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "id TEXT PRIMARY KEY, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO solar_meta(key, value) "
        "VALUES ('created_at', datetime('now'))"
    )
    conn.commit()

    applied = {row[0] for row in conn.execute("SELECT id FROM schema_migrations")}
    pending = 0
    for path in sorted(glob.glob(os.path.join(migrations_dir, "*.sql"))):
        mig_id = os.path.basename(path)[:-4]  # drop ".sql"
        if mig_id in applied:
            continue
        with open(path, encoding="utf-8") as f:
            sql = f.read()
        try:
            conn.executescript(sql)
        except sqlite3.Error as exc:
            raise SystemExit(f"migration failed: {mig_id}: {exc}")
        conn.execute("INSERT INTO schema_migrations(id) VALUES (?)", (mig_id,))
        conn.commit()
        pending += 1

    # schema_version = numeric prefix of the highest applied migration, or "0"
    # (baseline) when none have run. A fresh install records the baseline.
    nums = []
    for row in conn.execute("SELECT id FROM schema_migrations"):
        m = re.match(r"^(\d+)", row[0])
        if m:
            nums.append(int(m.group(1)))
    version = str(max(nums)) if nums else "0"
    conn.execute(
        "INSERT OR REPLACE INTO solar_meta(key, value) VALUES ('schema_version', ?)",
        (version,),
    )
    conn.commit()
finally:
    conn.close()
print(f"schema migrations: {pending} applied, schema_version {version}")
PY
}
