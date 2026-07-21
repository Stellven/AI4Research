#!/usr/bin/env bash
# lib/queue.sh — Per-sprint dispatch queue (S2, Coordinator Control Plane v2)
#
# Exports:
#   queue_enqueue <sid> <intent> [priority] → enqueue; prints "ok" or "duplicate"
#   queue_pop     <sid>           → dequeue first item; prints JSON or nothing
#   queue_peek    <sid>           → peek first item; prints JSON or nothing
#   queue_depth   <sid>           → prints integer count of pending items
#   queue_consume_all <sid> [reason] → mark all pending items consumed; prints count
#   queue_consume_intent_prefix <sid> <prefix> [reason] → consume matching pending intents
#   queue_archive_consumed_terminal [min_age_hours] [archive_tag] → move old terminal consumed queue files aside; prints JSON
#
# Rules:
#   - One JSONL file per sid: run/queue/<sid>.jsonl
#   - Priority FIFO semantics; each item: {id, sid, intent, priority, retry_count, intent_hash, enqueued_at, consumed}
#   - Dedup: same (sid, intent_hash) within 24h blocks re-enqueue
#   - Crash recovery: peek/pop rely only on file content, not in-memory state
#   - Atomic mutations via Python fcntl.flock + atomic rename

_QUEUE_DIR="${HARNESS_DIR:-$HOME/.solar/harness}/run/queue"

_queue_file() { echo "${_QUEUE_DIR}/${1}.jsonl"; }

_queue_cleanup_lock_if_empty() {
    local sid="${1:?_queue_cleanup_lock_if_empty: sid required}"
    local qf depth
    qf=$(_queue_file "$sid")
    [[ -f "${qf}.lock" ]] || return 0
    depth=$(queue_depth "$sid" 2>/dev/null || echo 1)
    [[ "$depth" == "0" ]] || return 0
    rm -f "${qf}.lock" 2>/dev/null || true
}

# ── queue_enqueue ─────────────────────────────────────────────────────────────
queue_enqueue() {
    local sid="${1:?queue_enqueue: sid required}"
    local intent="${2:?queue_enqueue: intent required}"
    local priority="${3:-0}"
    local qf
    qf=$(_queue_file "$sid")

    python3 -c "
import json, datetime, hashlib, fcntl, os, sys, secrets

sid      = sys.argv[1]
intent   = sys.argv[2]
priority = int(sys.argv[3])
qf       = sys.argv[4]

intent_hash = hashlib.sha256(intent.encode()).hexdigest()[:12]
now         = datetime.datetime.utcnow()
now_str     = now.strftime('%Y-%m-%dT%H:%M:%SZ')
cutoff      = (now - datetime.timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ')

os.makedirs(os.path.dirname(qf), exist_ok=True)

# Read existing items under lock
existing = []
lock_path = qf + '.lock'
with open(lock_path, 'a') as lf:
    try:
        fcntl.flock(lf, fcntl.LOCK_EX)
        if os.path.exists(qf):
            with open(qf) as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try: existing.append(json.loads(line))
                    except Exception: pass

        # Dedup check: same intent_hash within 24h, not consumed
        for item in existing:
            if (item.get('intent_hash') == intent_hash
                    and not item.get('consumed', False)
                    and item.get('enqueued_at', '') >= cutoff):
                print('duplicate')
                sys.exit(0)

        # Append new item
        item_id = 'q-' + now.strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(3)
        new_item = {
            'id': item_id, 'sid': sid, 'intent': intent,
            'priority': priority, 'retry_count': 0,
            'intent_hash': intent_hash, 'enqueued_at': now_str, 'consumed': False,
        }
        with open(qf, 'a') as f:
            f.write(json.dumps(new_item, ensure_ascii=False) + '\n')
        print('ok')
    finally:
        fcntl.flock(lf, fcntl.LOCK_UN)
" "$sid" "$intent" "$priority" "$qf" 2>/dev/null
}

# ── queue_peek ────────────────────────────────────────────────────────────────
queue_peek() {
    local sid="${1:?queue_peek: sid required}"
    local qf
    qf=$(_queue_file "$sid")
    [[ -f "$qf" ]] || return 0

    python3 -c "
import json, sys
qf = sys.argv[1]
pending = []
with open(qf) as f:
    for idx, line in enumerate(f):
        line = line.strip()
        if not line: continue
        try: item = json.loads(line)
        except Exception: continue
        if not item.get('consumed', False):
            pending.append((idx, item))
if pending:
    pending.sort(key=lambda pair: (-int(pair[1].get('priority', 0)), pair[0]))
    print(json.dumps(pending[0][1]))
" "$qf" 2>/dev/null
}

# ── queue_pop ─────────────────────────────────────────────────────────────────
queue_pop() {
    local sid="${1:?queue_pop: sid required}"
    local qf
    qf=$(_queue_file "$sid")
    [[ -f "$qf" ]] || return 0

    python3 -c "
import json, fcntl, os, sys

qf = sys.argv[1]
lock_path = qf + '.lock'

with open(lock_path, 'a') as lf:
    try:
        fcntl.flock(lf, fcntl.LOCK_EX)
        if not os.path.exists(qf):
            sys.exit(0)

        items = []
        with open(qf) as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: items.append(json.loads(line))
                except Exception: pass

        candidates = [(i, item) for i, item in enumerate(items) if not item.get('consumed', False)]
        candidates.sort(key=lambda pair: (-int(pair[1].get('priority', 0)), pair[0]))

        popped = None
        if candidates:
            i, item = candidates[0]
            popped = item
            items[i] = dict(item, consumed=True)

        if popped is None:
            sys.exit(0)

        # Atomic rewrite: write to temp then rename
        tmp = qf + '.tmp'
        with open(tmp, 'w') as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        os.replace(tmp, qf)

        print(json.dumps(popped))
    finally:
        fcntl.flock(lf, fcntl.LOCK_UN)
" "$qf" 2>/dev/null
}

# ── queue_depth ───────────────────────────────────────────────────────────────
queue_depth() {
    local sid="${1:?queue_depth: sid required}"
    local qf
    qf=$(_queue_file "$sid")
    [[ -f "$qf" ]] || { echo 0; return 0; }

    python3 -c "
import json, sys
count = 0
with open(sys.argv[1]) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            item = json.loads(line)
            if not item.get('consumed', False):
                count += 1
        except Exception: pass
print(count)
" "$qf" 2>/dev/null || echo 0
}

# ── queue_consume_all ─────────────────────────────────────────────────────────
queue_consume_all() {
    local sid="${1:?queue_consume_all: sid required}"
    local reason="${2:-terminal_sprint}"
    local qf
    qf=$(_queue_file "$sid")
    [[ -f "$qf" ]] || { echo 0; return 0; }

    python3 -c "
import json, datetime, fcntl, os, sys

qf = sys.argv[1]
reason = sys.argv[2]
lock_path = qf + '.lock'
now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
changed = 0

with open(lock_path, 'a') as lf:
    try:
        fcntl.flock(lf, fcntl.LOCK_EX)
        if not os.path.exists(qf):
            print(0)
            sys.exit(0)

        items = []
        with open(qf) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if not item.get('consumed', False):
                    item['consumed'] = True
                    item['consumed_at'] = now
                    item['consumed_by'] = 'queue_consume_all'
                    item['consume_reason'] = reason
                    changed += 1
                items.append(item)

        tmp = qf + '.tmp'
        with open(tmp, 'w') as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        os.replace(tmp, qf)
        print(changed)
    finally:
        fcntl.flock(lf, fcntl.LOCK_UN)
	" "$qf" "$reason" 2>/dev/null || echo 0
    _queue_cleanup_lock_if_empty "$sid"
}

# ── queue_consume_intent_prefix ───────────────────────────────────────────────
queue_consume_intent_prefix() {
    local sid="${1:?queue_consume_intent_prefix: sid required}"
    local prefix="${2:?queue_consume_intent_prefix: prefix required}"
    local reason="${3:-intent_prefix_superseded}"
    local qf
    qf=$(_queue_file "$sid")
    [[ -f "$qf" ]] || { echo 0; return 0; }

    python3 -c "
import json, datetime, fcntl, os, sys

qf = sys.argv[1]
prefix = sys.argv[2]
reason = sys.argv[3]
lock_path = qf + '.lock'
now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
changed = 0

with open(lock_path, 'a') as lf:
    try:
        fcntl.flock(lf, fcntl.LOCK_EX)
        if not os.path.exists(qf):
            print(0)
            sys.exit(0)

        items = []
        with open(qf) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                intent = str(item.get('intent', ''))
                if (not item.get('consumed', False)) and intent.startswith(prefix):
                    item['consumed'] = True
                    item['consumed_at'] = now
                    item['consumed_by'] = 'queue_consume_intent_prefix'
                    item['consume_reason'] = reason
                    changed += 1
                items.append(item)

        tmp = qf + '.tmp'
        with open(tmp, 'w') as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        os.replace(tmp, qf)
        print(changed)
    finally:
        fcntl.flock(lf, fcntl.LOCK_UN)
	" "$qf" "$prefix" "$reason" 2>/dev/null || echo 0
    _queue_cleanup_lock_if_empty "$sid"
}

# ── queue_archive_consumed_terminal ──────────────────────────────────────────
queue_archive_consumed_terminal() {
    local min_age_hours="${1:-24}"
    local archive_tag="${2:-queue-reaper}"
    local sprints_dir="${SPRINTS_DIR:-${HARNESS_DIR:-$HOME/.solar/harness}/sprints}"
    local archive_root="${QUEUE_ARCHIVE_DIR:-${HARNESS_DIR:-$HOME/.solar/harness}/run/queue-archive}"

    python3 -c "
import datetime, json, pathlib, shutil, sys, time

queue_dir = pathlib.Path(sys.argv[1])
sprints_dir = pathlib.Path(sys.argv[2])
archive_root = pathlib.Path(sys.argv[3])
min_age_hours = float(sys.argv[4])
archive_tag = sys.argv[5]
terminal = {'passed','failed','cancelled','superseded','interrupted','done'}
now = time.time()
stamp = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
archive_dir = archive_root / f'{archive_tag}-{stamp}'
items = []
archived_count = 0
kept_count = 0

queue_dir.mkdir(parents=True, exist_ok=True)
for qf in sorted(queue_dir.glob('*.jsonl')):
    sid = qf.name[:-6]
    lock = qf.with_name(qf.name + '.lock')
    status_path = sprints_dir / f'{sid}.status.json'
    status = {}
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text())
        except Exception as exc:
            status = {'_error': str(exc)}

    lines = qf.read_text(errors='replace').splitlines()
    all_consumed = bool(lines)
    for line in lines:
        try:
            item = json.loads(line)
        except Exception:
            all_consumed = False
            break
        if item.get('consumed') is not True:
            all_consumed = False
            break

    age_h = (now - qf.stat().st_mtime) / 3600.0
    orphan_test_queue = (
        not status_path.exists()
        and (sid.startswith('sprint-test') or sid.startswith('sprint-falsify'))
    )
    safe = (
        all_consumed
        and age_h >= min_age_hours
        and (status.get('status') in terminal or orphan_test_queue)
    )
    rec = {
        'sid': sid,
        'status': status.get('status') or ('missing_test_status' if orphan_test_queue else None),
        'phase': status.get('phase'),
        'age_h': round(age_h, 1),
        'line_count': len(lines),
        'all_consumed': all_consumed,
    }
    if not safe:
        rec['action'] = 'kept'
        rec['reason'] = 'not_terminal_consumed_or_old_enough'
        kept_count += 1
        items.append(rec)
        continue

    archive_dir.mkdir(parents=True, exist_ok=True)
    moved = []
    for src in (qf, lock):
        if src.exists():
            dst = archive_dir / src.name
            shutil.move(str(src), str(dst))
            moved.append(str(dst))
    rec['action'] = 'archived'
    rec['reason'] = 'terminal_and_all_events_consumed' if status.get('status') in terminal else 'orphan_test_queue_all_events_consumed'
    rec['moved'] = moved
    archived_count += 1
    items.append(rec)

for sidecar in sorted(queue_dir.glob('*.jsonl.lock')) + sorted(queue_dir.glob('*.jsonl.bak-*')):
    json_name = sidecar.name[:-5] if sidecar.name.endswith('.lock') else sidecar.name.split('.bak-', 1)[0]
    json_path = queue_dir / json_name
    if json_path.exists():
        continue
    age_h = (now - sidecar.stat().st_mtime) / 3600.0
    if age_h < min_age_hours:
        kept_count += 1
        items.append({
            'sid': json_name[:-6] if json_name.endswith('.jsonl') else json_name,
            'sidecar': str(sidecar),
            'age_h': round(age_h, 1),
            'action': 'kept',
            'reason': 'orphan_sidecar_not_old_enough',
        })
        continue
    archive_dir.mkdir(parents=True, exist_ok=True)
    dst = archive_dir / sidecar.name
    shutil.move(str(sidecar), str(dst))
    archived_count += 1
    items.append({
        'sid': json_name[:-6] if json_name.endswith('.jsonl') else json_name,
        'sidecar': str(sidecar),
        'age_h': round(age_h, 1),
        'action': 'archived',
        'reason': 'orphan_queue_sidecar',
        'moved': [str(dst)],
    })

if archive_dir.exists():
    (archive_dir / 'manifest.json').write_text(json.dumps({
        'ts': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'queue_dir': str(queue_dir),
        'sprints_dir': str(sprints_dir),
        'min_age_hours': min_age_hours,
        'archive': str(archive_dir),
        'items': items,
    }, ensure_ascii=False, indent=2))

print(json.dumps({
    'ok': True,
    'archive': str(archive_dir) if archive_dir.exists() else '',
    'archived': archived_count,
    'kept': kept_count,
    'remaining_queue_files': sum(1 for p in queue_dir.glob('*') if p.is_file()),
}, ensure_ascii=False))
" "$_QUEUE_DIR" "$sprints_dir" "$archive_root" "$min_age_hours" "$archive_tag" 2>/dev/null || {
        echo '{"ok":false,"archived":0,"kept":0,"error":"queue_archive_consumed_terminal_failed"}'
        return 1
    }
}
