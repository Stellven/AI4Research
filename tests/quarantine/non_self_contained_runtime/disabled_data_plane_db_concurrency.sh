#!/usr/bin/env bash
# test-data-plane-db-concurrency.sh — A3: SQLite concurrency test
# 5 parallel processes read+write simultaneously; no "database is locked" errors.
set -uo pipefail

DB_PATH="$HOME/.solar/solar.db"

echo "[test] data-plane DB concurrency (5 parallel R/W)"

# Ensure WAL mode
sqlite3 "$DB_PATH" "PRAGMA journal_mode=WAL;" 2>/dev/null || true

FAILS=0
PIDS=()

for i in 1 2 3 4 5; do
  (
    python3 -c "
import sqlite3, sys
sys.path.insert(0, '$HOME/.solar/harness/lib')
from solar_db import open_solar_db
conn = open_solar_db()
# Read
count = conn.execute('SELECT count(*) FROM cortex_sources').fetchone()[0]
# Write test row
conn.execute('INSERT OR IGNORE INTO state (key, value) VALUES (?, ?)',
             (f'concurrency_test_$i', '{\"ok\": true, \"pid\": $i}'))
conn.commit()
conn.close()
print(f'worker $i: read {count} rows, wrote ok')
" 2>&1
  ) &
  PIDS+=($!)
done

# Wait and collect results
for pid in "${PIDS[@]}"; do
  if ! wait "$pid"; then
    echo "FAIL: worker pid=$pid exited non-zero"
    FAILS=$((FAILS + 1))
  fi
done

# Cleanup test rows
python3 -c "
import sqlite3, sys
sys.path.insert(0, '$HOME/.solar/harness/lib')
from solar_db import open_solar_db
conn = open_solar_db()
deleted = conn.execute(\"DELETE FROM state WHERE key LIKE 'concurrency_test_%'\").rowcount
conn.commit()
conn.close()
print(f'cleanup: removed {deleted} test rows')
"

if (( FAILS == 0 )); then
  echo "PASS: concurrency test — no database is locked errors"
else
  echo "FAIL: ${FAILS} workers failed"
fi

exit $FAILS
