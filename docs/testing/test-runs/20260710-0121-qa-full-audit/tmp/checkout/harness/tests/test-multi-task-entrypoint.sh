#!/usr/bin/env bash
# Regression: `solar-harness multi-task` launches ready DAG nodes into an
# independent tmux worker pool without requiring extra four-pane sessions.
set -euo pipefail
cd "$(dirname "$0")/.."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP"/{bin,config,lib,sprints,personas,templates,run/multi-task,work}
export SOLAR_INTENT_DB="$TMP/solar.db"
export SOLAR_GEMINI_CLI_AUTH=auto

cp solar-harness.sh "$TMP/solar-harness.sh"
cp lib/run-state.sh "$TMP/lib/run-state.sh"
cp lib/events.sh "$TMP/lib/events.sh"
cp lib/graph_scheduler.py "$TMP/lib/graph_scheduler.py"
cp lib/prerequisite_resolver.py "$TMP/lib/prerequisite_resolver.py"
cp lib/intent_engine_adapter.py "$TMP/lib/intent_engine_adapter.py"
cp lib/multi_task_runner.py "$TMP/lib/multi_task_runner.py"
cp lib/tvs_render_cli.ts "$TMP/lib/tvs_render_cli.ts"
cp lib/claude_surface.py "$TMP/lib/claude_surface.py"
cp lib/gemini_adapter.py "$TMP/lib/gemini_adapter.py"
cp config/multi-task-profiles.json "$TMP/config/multi-task-profiles.json"
cp config/model-registry.json "$TMP/config/model-registry.json"
cp personas/builder.md "$TMP/personas/builder.md"
cp personas/planner.md "$TMP/personas/planner.md"

python3 - "$SOLAR_INTENT_DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE sys_intent_patterns (pattern TEXT NOT NULL, intent_type TEXT NOT NULL, confidence REAL DEFAULT 0.8, success_count INTEGER DEFAULT 0, UNIQUE(pattern, intent_type))")
conn.execute("CREATE TABLE sys_intent_unknown (id INTEGER PRIMARY KEY AUTOINCREMENT, input TEXT NOT NULL, resolved_intent TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
conn.execute("""CREATE TABLE intent_patterns (
    pattern_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    triggers TEXT,
    typical_actions TEXT,
    capability_mapping TEXT,
    frequency INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0.5,
    avg_confidence REAL DEFAULT 0.5,
    last_used DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)""")
conn.execute("""INSERT INTO intent_patterns
    (pattern_id, name, category, triggers, typical_actions, capability_mapping, frequency, success_count, success_rate, avg_confidence)
    VALUES
    ('bench_perf', '性能基准', 'BUILD', '["跑基准", "benchmark"]', '["/benchmark"]', '', 10, 0, 0.8, 0.83),
    ('brain_deepseek', '切换DeepSeek模式', 'CONTROL', '["DS"]', '["switch_mode"]', '{"mcps":["brain-router"],"params":{"mode":"deepseek"}}', 2, 0, 0.7, 0.7),
    ('bad_json', '坏 JSON', 'QUERY', '{bad json', '[]', '', 1, 0, 0.5, 0.5)
""")
conn.commit()
conn.close()
PY

python3 - "$TMP/solar-harness.sh" "$TMP" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
tmp = sys.argv[2]
s = p.read_text()
s = s.replace('HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"', f'HARNESS_DIR="${{HARNESS_DIR:-{tmp}}}"', 1)
p.write_text(s)
PY
chmod +x "$TMP/solar-harness.sh"

cat > "$TMP/bin/tmux" <<'EOF'
#!/usr/bin/env bash
echo "$@" >> "$HARNESS_DIR/tmux-calls.log"
case "$1" in
  has-session)
    exit 1
    ;;
  list-panes)
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "solar-harness" "Product Delivery" "0" "PM 产品经理 | 模型:Opus | 状态:ready" "bash" "0" "1001" \
      "solar-harness" "Product Delivery" "1" "Planner 规划者 | 模型:Opus | 状态:ready" "bash" "0" "1002" \
      "solar-harness" "Product Delivery" "2" "Builder 主建设者 | 模型:Opus | 状态:working/demo" "bash" "0" "1003" \
      "solar-harness" "Product Delivery" "3" "Evaluator 审判官 | 模型:Opus | 状态:ready" "bash" "0" "1004" \
      "solar-harness-lab" "Builder Lab" "0" "Builder 1 | 模型:Sonnet | 状态:ready" "bash" "0" "2001"
    exit 0
    ;;
  list-windows)
    exit 0
    ;;
  new-session|new-window|kill-window|attach)
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
EOF
chmod +x "$TMP/bin/tmux"

cat > "$TMP/bin/gemini" <<'EOF'
#!/usr/bin/env bash
echo "$@" >> "$HARNESS_DIR/gemini-calls.log"
exit 0
EOF
chmod +x "$TMP/bin/gemini"

cat > "$TMP/bin/claude" <<'EOF'
#!/usr/bin/env bash
echo "$@" >> "$HARNESS_DIR/claude-calls.log"
exit 0
EOF
chmod +x "$TMP/bin/claude"

graph="$TMP/sprints/sprint-20260520-multi-task.task_graph.json"
cat > "$graph" <<'JSON'
{
  "sprint_id": "sprint-20260520-multi-task",
  "nodes": [
    {
      "id": "A",
      "goal": "touch A",
      "target_role": "planner",
      "depends_on": [],
      "write_scope": ["work/a.txt"],
      "acceptance": ["A handoff exists"]
    },
    {
      "id": "B",
      "goal": "touch B",
      "depends_on": [],
      "write_scope": ["work/b.txt"],
      "acceptance": ["B handoff exists"]
    }
  ]
}
JSON

PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task start --graph "$graph" --max-workers 2 --cooldown-sec 0 --memory-reserve-gb 0 --once --no-clear >/tmp/solar-multi-task-test.out

status_count=$(find "$TMP/run/multi-task" -name status.json | wc -l | tr -d ' ')
[[ "$status_count" -eq 2 ]] || { echo "FAIL: expected two multi-task status files, got $status_count"; exit 1; }

grep -q "new-session" "$TMP/tmux-calls.log" || { echo "FAIL: tmux new-session not called"; exit 1; }
grep -q "Solar Harness Multi-Task" /tmp/solar-multi-task-test.out || { echo "FAIL: summary not rendered"; exit 1; }
find "$TMP/run/multi-task" -name runner.sh -print0 | xargs -0 -n1 bash -n

python3 - "$graph" <<'PY'
import json, sys
graph = json.load(open(sys.argv[1], encoding="utf-8"))
nodes = {n["id"]: n for n in graph["nodes"]}
for node_id in ("A", "B"):
    n = nodes[node_id]
    assert n.get("status") == "dispatched", (node_id, n)
    assert str(n.get("assigned_to", "")).startswith("multi-task:"), (node_id, n)
    assert str(n.get("dispatch_id", "")).startswith("mt-"), (node_id, n)
PY

planner_status=$(python3 - "$TMP/run/multi-task" <<'PY'
import json, sys
from pathlib import Path
for path in Path(sys.argv[1]).glob("*/status.json"):
    data = json.loads(path.read_text())
    if data.get("node_id") == "A":
        print(data.get("role"), data.get("profile"), data.get("backend"), data.get("model"))
PY
)
[[ "$planner_status" == "planner planner claude-cli opus" ]] || { echo "FAIL: planner profile routing wrong: $planner_status"; exit 1; }

PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task profiles | grep -q "gemini-builder" \
  || { echo "FAIL: profiles did not include gemini-builder"; exit 1; }
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task matrix | grep -q "gemini-builder" \
  || { echo "FAIL: matrix did not include gemini-builder"; exit 1; }
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task foreground planner | grep -q "tmux attach -t solar-harness-multi-task:" \
  || { echo "FAIL: foreground selector did not resolve planner"; exit 1; }
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" python3 "$TMP/lib/gemini_adapter.py" doctor | grep -q '"cli"' \
  || { echo "FAIL: gemini adapter doctor missing cli section"; exit 1; }

graph2="$TMP/sprints/sprint-20260520-gemini.task_graph.json"
cat > "$graph2" <<'JSON'
{
  "sprint_id": "sprint-20260520-gemini",
  "nodes": [
    {
      "id": "G1",
      "goal": "gemini smoke",
      "depends_on": [],
      "write_scope": ["work/gemini.txt"],
      "preferred_model": "gemini",
      "acceptance": ["Gemini dispatch exists"]
    }
  ]
}
JSON
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task start --graph "$graph2" --profile gemini-builder --max-workers 3 --cooldown-sec 0 --memory-reserve-gb 0 --once --no-clear >/tmp/solar-multi-task-gemini.out
gemini_runner=$(find "$TMP/run/multi-task" -path "*sprint-20260520-gemini*/runner.sh" -print | head -1)
[[ -n "$gemini_runner" ]] || { echo "FAIL: gemini runner missing"; exit 1; }
grep -q "gemini_adapter.py" "$gemini_runner" || { echo "FAIL: gemini runner does not use gemini adapter"; exit 1; }
grep -q '"backend": "gemini-cli"' "$(dirname "$gemini_runner")/status.json" || { echo "FAIL: gemini status backend missing"; exit 1; }
grep -q '"provider": "gemini"' "$(dirname "$gemini_runner")/status.json" || { echo "FAIL: gemini status provider missing"; exit 1; }
grep -q '"capability_status": "ok"' "$(dirname "$gemini_runner")/status.json" || { echo "FAIL: gemini status capability missing"; exit 1; }
grep -q "tmux select-pane -T" "$gemini_runner" || { echo "FAIL: runner does not update tmux pane title"; exit 1; }
grep -q "模型:\$MODEL" "$gemini_runner" || { echo "FAIL: runner pane title does not include model"; exit 1; }

graph_deepseek="$TMP/sprints/sprint-20260520-deepseek-gated.task_graph.json"
cat > "$graph_deepseek" <<'JSON'
{
  "sprint_id": "sprint-20260520-deepseek-gated",
  "nodes": [
    {
      "id": "D1",
      "goal": "must not dispatch without a passing DeepSeek probe",
      "depends_on": [],
      "write_scope": ["work/deepseek.txt"],
      "acceptance": ["No dispatch until capability is ok"]
    }
  ]
}
JSON
before_deepseek=$(find "$TMP/run/multi-task" -name status.json | wc -l | tr -d ' ')
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task start --graph "$graph_deepseek" --profile deepseek-builder --max-workers 10 --cooldown-sec 0 --memory-reserve-gb 0 --once --no-clear >/tmp/solar-multi-task-deepseek-gate.out
after_deepseek=$(find "$TMP/run/multi-task" -name status.json | wc -l | tr -d ' ')
[[ "$before_deepseek" -eq "$after_deepseek" ]] \
  || { echo "FAIL: unavailable DeepSeek profile dispatched work"; exit 1; }
grep -Eq "capability_unavailable|model_matrix.*error=1" /tmp/solar-multi-task-deepseek-gate.out \
  || { echo "FAIL: unavailable DeepSeek profile did not expose capability gate"; exit 1; }

old_task="$TMP/run/multi-task/mt-old-terminal"
mkdir -p "$old_task"
python3 - "$old_task/status.json" <<'PY'
import json, sys
payload = {
    "id": "mt-old-terminal",
    "status": "completed",
    "window": "old-window",
    "updated_at": "2000-01-01T00:00:00Z",
}
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(payload) + "\n")
PY
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task reap --ttl-min 1 --dry-run | grep -q "dry-run" \
  || { echo "FAIL: reap dry-run did not report candidate"; exit 1; }
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task reap --ttl-min 1 >/tmp/solar-multi-task-reap.out
grep -q "kill-window" "$TMP/tmux-calls.log" \
  || { echo "FAIL: reap did not kill old terminal tmux window"; exit 1; }
grep -q '"status": "reaped"' "$old_task/status.json" \
  || { echo "FAIL: reap did not mark old terminal task reaped"; exit 1; }

cat > "$TMP/run/dispatch-ledger.jsonl" <<'JSONL'
{"ts":"2026-05-20T10:00:00Z","kind":"intent_injected","sid":"sprint-20260520-multi-task","pane":"solar-harness:0.2","dispatch_id":"graph-sprint-20260520-multi-task-B-20260520T100000Z","instruction_file":"/tmp/sprint-20260520-multi-task.B-dispatch.md","capability_providers":["Solar-Harness Runtime"]}
JSONL

PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task status --graph "$graph" --no-clear >/tmp/solar-multi-task-status.out
grep -q "sprint-20260520-multi-task" /tmp/solar-multi-task-status.out \
  || { echo "FAIL: status did not include graph"; exit 1; }
grep -q "pane_type" /tmp/solar-multi-task-status.out \
  || { echo "FAIL: status did not include pane_type column"; exit 1; }
grep -q "cmd" /tmp/solar-multi-task-status.out \
  || { echo "FAIL: status did not include runtime command column"; exit 1; }
grep -q "refresh_mode" /tmp/solar-multi-task-status.out \
  || { echo "FAIL: status did not expose refresh mode"; exit 1; }
grep -q "harness_panes" /tmp/solar-multi-task-status.out \
  || { echo "FAIL: status did not summarize harness panes"; exit 1; }
grep -q "four-pane" /tmp/solar-multi-task-status.out \
  || { echo "FAIL: status did not include four-pane harness panes"; exit 1; }
grep -q "builder-lab" /tmp/solar-multi-task-status.out \
  || { echo "FAIL: status did not include builder lab panes"; exit 1; }
grep -q "sprint-20260520-multi-task#B" /tmp/solar-multi-task-status.out \
  || { echo "FAIL: status did not include recent four-pane dispatch history"; exit 1; }

COLUMNS=80 LINES=20 PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task screen --graph "$graph" --command "显示状态" --no-clear >/tmp/solar-multi-task-screen.out
grep -q "自然语言指令" /tmp/solar-multi-task-screen.out \
  || { echo "FAIL: screen did not render input pane"; exit 1; }
grep -q "models" /tmp/solar-multi-task-screen.out \
  || { echo "FAIL: screen did not show model matrix summary"; exit 1; }
grep -q "models" /tmp/solar-multi-task-screen.out \
  || { echo "FAIL: screen model matrix summary did not show dispatchable combos"; exit 1; }
grep -q "PANE MAP" /tmp/solar-multi-task-screen.out \
  || { echo "FAIL: screen did not show compact harness pane section"; exit 1; }
grep -q "main:2" /tmp/solar-multi-task-screen.out \
  || { echo "FAIL: screen did not show four-pane builder pane"; exit 1; }
grep -q "WORKERS" /tmp/solar-multi-task-screen.out \
  || { echo "FAIL: screen did not show worker summary section"; exit 1; }
grep -q "solar>" /tmp/solar-multi-task-screen.out \
  || { echo "FAIL: screen did not expose interactive prompt"; exit 1; }
screen_lines=$(wc -l < /tmp/solar-multi-task-screen.out | tr -d ' ')
[[ "$screen_lines" -le 20 ]] || { echo "FAIL: screen exceeded terminal height: $screen_lines"; exit 1; }
python3 - /tmp/solar-multi-task-screen.out <<'PY'
import sys, unicodedata
def width(s):
    n = 0
    for ch in s.rstrip("\n"):
        if unicodedata.combining(ch):
            continue
        n += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
    return n
bad = [(i, width(line)) for i, line in enumerate(open(sys.argv[1], encoding="utf-8"), 1) if width(line) > 80]
if bad:
    raise SystemExit(f"screen exceeded terminal width: {bad[:3]}")
PY
grep -q '"action": "status"' "$TMP/run/multi-task/screen-commands.jsonl" \
  || { echo "FAIL: screen command was not logged through intent path"; exit 1; }

COLUMNS=120 LINES=24 PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task screen --graph "$graph" --command "gemini" --no-clear >/tmp/solar-multi-task-screen-profile-gemini.out
grep -q "profile=gemini-builder backend=gemini-cli model=gemini provider=gemini capability=ok" /tmp/solar-multi-task-screen-profile-gemini.out \
  || { echo "FAIL: ok profile switch did not update screen selection"; exit 1; }
grep -q "intent=profile_switch action=profile" /tmp/solar-multi-task-screen-profile-gemini.out \
  || { echo "FAIL: ok profile switch did not route through profile action"; exit 1; }

COLUMNS=120 LINES=24 PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task screen --graph "$graph" --command "deepseek" --no-clear >/tmp/solar-multi-task-screen-profile-deepseek.out
grep -q "profile_rejected=deepseek-builder" /tmp/solar-multi-task-screen-profile-deepseek.out \
  || { echo "FAIL: unavailable profile switch was not rejected"; exit 1; }
if grep -q "profile=deepseek-builder" /tmp/solar-multi-task-screen-profile-deepseek.out; then
  echo "FAIL: unavailable profile polluted current screen selection"
  exit 1
fi

COLUMNS=120 LINES=24 PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task screen --graph "$graph" --command "有哪些任务在执行" --no-clear >/tmp/solar-multi-task-screen-status-query.out
grep -q "action=status" /tmp/solar-multi-task-screen-status-query.out \
  || { echo "FAIL: task status query did not route to status"; exit 1; }
grep -q "intent=task_status_query" /tmp/solar-multi-task-screen-status-query.out \
  || { echo "FAIL: task status query did not get readable intent label"; exit 1; }
grep -q "当前后台任务" /tmp/solar-multi-task-screen-status-query.out \
  || grep -q "当前任务:" /tmp/solar-multi-task-screen-status-query.out \
  || { echo "FAIL: task status query did not return task summary"; exit 1; }
grep -q "DAG working" /tmp/solar-multi-task-screen-status-query.out \
  || { echo "FAIL: task status query did not include DAG summary"; exit 1; }
if tail -1 "$TMP/run/multi-task/screen-commands.jsonl" | grep -q '"action": "schedule_once"'; then
  echo "FAIL: task status query was misrouted to schedule_once"
  exit 1
fi

COLUMNS=120 LINES=24 PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task screen --graph "$graph" --command "有哪些任务" --no-clear >/tmp/solar-multi-task-screen-short-task-query.out
grep -q "intent=task_status_query" /tmp/solar-multi-task-screen-short-task-query.out \
  || { echo "FAIL: short task query did not route to task status"; exit 1; }
grep -q "DAG working" /tmp/solar-multi-task-screen-short-task-query.out \
  || { echo "FAIL: short task query did not include DAG summary"; exit 1; }
grep -q "history: ↑/↓" /tmp/solar-multi-task-screen-short-task-query.out \
  || { echo "FAIL: screen did not advertise input history"; exit 1; }
grep -q "有哪些任务" "$TMP/run/multi-task/screen-history.txt" \
  || { echo "FAIL: screen history did not persist command"; exit 1; }
unknown_count=$(python3 - "$SOLAR_INTENT_DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
print(conn.execute("SELECT COUNT(*) FROM sys_intent_unknown").fetchone()[0])
conn.close()
PY
)
[[ "$unknown_count" -eq 0 ]] \
  || { echo "FAIL: local screen commands polluted sys_intent_unknown: $unknown_count"; exit 1; }
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" python3 "$TMP/lib/intent_engine_adapter.py" match "有哪些任务" --record --json >/tmp/solar-intent-task-status.json
grep -q '"type": "task_status_query"' /tmp/solar-intent-task-status.json \
  || { echo "FAIL: intent adapter did not classify task status query"; exit 1; }
unknown_count_after_task_query=$(python3 - "$SOLAR_INTENT_DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
print(conn.execute("SELECT COUNT(*) FROM sys_intent_unknown").fetchone()[0])
conn.close()
PY
)
[[ "$unknown_count_after_task_query" -eq 0 ]] \
  || { echo "FAIL: classified task query polluted sys_intent_unknown: $unknown_count_after_task_query"; exit 1; }
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" python3 "$TMP/lib/intent_engine_adapter.py" match "未命中测试输入" --record >/tmp/solar-intent-dedupe-1.out
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" python3 "$TMP/lib/intent_engine_adapter.py" match "未命中测试输入" --record >/tmp/solar-intent-dedupe-2.out
unknown_dedupe_count=$(python3 - "$SOLAR_INTENT_DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
print(conn.execute("SELECT COUNT(*) FROM sys_intent_unknown WHERE input='未命中测试输入'").fetchone()[0])
conn.close()
PY
)
[[ "$unknown_dedupe_count" -eq 1 ]] \
  || { echo "FAIL: intent unknown dedupe failed: $unknown_dedupe_count"; exit 1; }
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" python3 "$TMP/lib/intent_engine_adapter.py" match "帮我跑基准" --json >/tmp/solar-intent-configured.json
grep -q '"source": "solar-intent-patterns"' /tmp/solar-intent-configured.json \
  || { echo "FAIL: intent_patterns source did not match configured trigger"; exit 1; }
grep -q '"type": "bench_perf"' /tmp/solar-intent-configured.json \
  || { echo "FAIL: configured trigger did not return pattern_id"; exit 1; }
python3 - "$SOLAR_INTENT_DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
row = conn.execute("SELECT frequency, success_count, last_used FROM intent_patterns WHERE pattern_id='bench_perf'").fetchone()
conn.close()
assert row == (10, 0, None), row
PY
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" python3 "$TMP/lib/intent_engine_adapter.py" match "帮我跑基准" --record --json >/tmp/solar-intent-configured-record.json
python3 - "$SOLAR_INTENT_DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
row = conn.execute("SELECT frequency, success_count, last_used FROM intent_patterns WHERE pattern_id='bench_perf'").fetchone()
conn.close()
if not (row[0] == 11 and row[1] == 1 and row[2]):
    raise SystemExit(f"configured intent telemetry not updated: {row}")
PY
PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" python3 "$TMP/lib/intent_engine_adapter.py" match "docs" --json >/tmp/solar-intent-short-token.json
if grep -q '"type": "brain_deepseek"' /tmp/solar-intent-short-token.json; then
  echo "FAIL: short trigger DS matched inside unrelated text"
  exit 1
fi

graph3="$TMP/sprints/sprint-20260520-readonly-screen.task_graph.json"
cat > "$graph3" <<'JSON'
{
  "sprint_id": "sprint-20260520-readonly-screen",
  "nodes": [
    {
      "id": "R1",
      "goal": "must not dispatch from status screen query",
      "depends_on": [],
      "write_scope": ["work/readonly.txt"],
      "acceptance": ["No dispatch on status query"]
    }
  ]
}
JSON
before_readonly=$(find "$TMP/run/multi-task" -name status.json | wc -l | tr -d ' ')
COLUMNS=120 LINES=24 PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task screen --graph "$graph3" --command "有哪些任务" --max-workers 10 --cooldown-sec 0 --memory-reserve-gb 0 --no-clear >/tmp/solar-multi-task-screen-readonly-query.out
after_readonly=$(find "$TMP/run/multi-task" -name status.json | wc -l | tr -d ' ')
[[ "$before_readonly" -eq "$after_readonly" ]] \
  || { echo "FAIL: screen status query dispatched work: before=$before_readonly after=$after_readonly"; exit 1; }
python3 - "$graph3" <<'PY'
import json, sys
graph = json.load(open(sys.argv[1], encoding="utf-8"))
node = graph["nodes"][0]
if node.get("status") or node.get("assigned_to") or node.get("dispatch_id"):
    raise SystemExit(f"screen status query mutated graph node: {node}")
PY
[[ -s "$TMP/run/multi-task/graph-summary-cache.json" ]] \
  || { echo "FAIL: graph summary cache was not written"; exit 1; }
python3 - "$graph3" <<'PY'
import json, os, sys, time
path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    graph = json.load(fh)
graph["nodes"][0]["status"] = "passed"
with open(path, "w", encoding="utf-8") as fh:
    json.dump(graph, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
future = time.time() + 5
os.utime(path, (future, future))
PY
COLUMNS=120 LINES=24 PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" multi-task status --graph "$graph3" --no-clear >/tmp/solar-multi-task-cache-invalidation.out
grep -q "passed:1" /tmp/solar-multi-task-cache-invalidation.out \
  || { echo "FAIL: graph summary cache did not invalidate after graph mutation"; exit 1; }

echo "PASS: multi-task entrypoint dispatches ready DAG nodes to tmux worker pool"
