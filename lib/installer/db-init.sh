#!/usr/bin/env bash

# Database initialization uses python3's stdlib sqlite3 instead of the
# sqlite3 CLI: python3 is already a hard installer requirement, and its
# bundled SQLite reliably includes FTS5, which the cortex schema needs
# (the macOS runner's sqlite3 CLI ships without the fts5 module).
db_init() {
    schema_dir="$SOURCE_DIR/core/db/schema"
    [ -d "$schema_dir" ] || die "schema directory missing: $schema_dir"
    dry_run_note "initialize $SOLAR_DB from $schema_dir/*.sql" && return 0
    mkdir -p "$(dirname "$SOLAR_DB")"
    SOLAR_DB="$SOLAR_DB" SCHEMA_DIR="$schema_dir" "${SOLAR_PYTHON:-python3}" - <<'PY'
import glob
import os
import sqlite3

db_path = os.environ["SOLAR_DB"]
schema_dir = os.environ["SCHEMA_DIR"]
conn = sqlite3.connect(db_path)
try:
    for path in sorted(glob.glob(os.path.join(schema_dir, "*.sql"))):
        with open(path, encoding="utf-8") as f:
            sql = f.read()
        try:
            conn.executescript(sql)
        except sqlite3.Error as exc:
            raise SystemExit(
                f"schema apply failed: {os.path.basename(path)}: {exc}"
            )
    conn.commit()
finally:
    conn.close()
print(f"database initialized: {db_path}")
PY
}
