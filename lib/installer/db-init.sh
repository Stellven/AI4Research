#!/usr/bin/env bash

db_init() {
    schema_dir="$SOURCE_DIR/core/db/schema"
    [ -d "$schema_dir" ] || die "schema directory missing: $schema_dir"
    if ! command -v sqlite3 >/dev/null 2>&1; then
        yellow "sqlite3 not found; skipping database initialization"
        return 0
    fi
    dry_run_note "initialize $SOLAR_DB from $schema_dir/*.sql" && return 0
    mkdir -p "$(dirname "$SOLAR_DB")"
    for schema in "$schema_dir"/*.sql; do
        [ -f "$schema" ] || continue
        sqlite3 "$SOLAR_DB" < "$schema"
    done
}
