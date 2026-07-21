#!/usr/bin/env bash
set -euo pipefail

LIVE_HARNESS="${LIVE_HARNESS:-$HOME/.solar/harness}"
SOLAR_REPO="${SOLAR_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
REPO_HARNESS="${REPO_HARNESS:-$SOLAR_REPO/harness}"
KNOWLEDGE_DIR="${KNOWLEDGE_DIR:-$HOME/.solar/extracted_knowledge}"
ELIGIBLE_STATUSES="${ELIGIBLE_STATUSES:-passed}"
DO_COMMIT=0

usage() {
  cat <<'USAGE'
Usage: scripts/export-harness-artifacts.sh [--commit]

Exports usable Solar Harness code/artifacts from ~/.solar/harness into the
tracked Solar repo harness/ directory, writes knowledge extraction markdown, and
optionally commits only the controlled Solar harness paths.

Environment:
  LIVE_HARNESS       default $HOME/.solar/harness
  SOLAR_REPO         default (auto-detect from script location)
  KNOWLEDGE_DIR      default $HOME/.solar/extracted_knowledge
  ELIGIBLE_STATUSES  default passed
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --commit) DO_COMMIT=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

require_dir() {
  local path="$1"
  [[ -d "$path" ]] || { echo "missing directory: $path" >&2; exit 1; }
}

require_dir "$LIVE_HARNESS"
require_dir "$SOLAR_REPO"
git -C "$SOLAR_REPO" rev-parse --show-toplevel >/dev/null

mkdir -p "$REPO_HARNESS" "$REPO_HARNESS/sprints"
knowledge_dir_ready=1
if ! mkdir -p "$KNOWLEDGE_DIR" 2>/dev/null; then
  knowledge_dir_ready=0
fi

rsync_excludes=(
  --exclude '.*'
  --exclude '$*'
  --exclude '.DS_Store'
  --exclude '__pycache__/***'
  --exclude '*.pyc'
  --exclude '.*.pid'
  --exclude '.*.port'
  --exclude '*.pid'
  --exclude '*.port'
  --exclude '*.log'
  --exclude '*.bak'
  --exclude '*.bak-*'
  --exclude '*.bak.*'
  --exclude '*.backup'
  --exclude '*.tmp'
  --exclude '*~'
  --exclude '.coordinator.log'
  --exclude '.watchdog.log'
  --exclude '.autopilot-launchd.log'
  --exclude '.wiki-capture-server.log'
  --exclude '.solar-config-server.log'
  --exclude '.coordinator.pid'
  --exclude '.watchdog.pid'
  --exclude '.wiki-capture-server.pid'
  --exclude '.solar-config-server.pid'
  --exclude '.planner-inbox.md'
  --exclude 'PLANNER-INBOX.md'
  --exclude 'cache/***'
  --exclude 'logs/***'
  --exclude 'run/***'
  --exclude 'state/***'
  --exclude 'venvs/***'
  --exclude 'vendor/***'
  --exclude 'quarantine/***'
  --exclude 'pm-predrafts/***'
  --exclude 'sprints/***'
  --exclude 'codex-bridge.deprecated.*/***'
  --exclude '.backup-*/***'
)

rsync -a "${rsync_excludes[@]}" "$LIVE_HARNESS/" "$REPO_HARNESS/"

export LIVE_HARNESS REPO_HARNESS KNOWLEDGE_DIR ELIGIBLE_STATUSES
summary_json="$(python3 <<'PY'
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

live = Path(os.environ["LIVE_HARNESS"])
repo_harness = Path(os.environ["REPO_HARNESS"])
knowledge_dir = Path(os.environ["KNOWLEDGE_DIR"])
eligible = {s.strip() for s in os.environ["ELIGIBLE_STATUSES"].split(",") if s.strip()}
sprints = live / "sprints"

fallback_knowledge_dir = repo_harness / "_extracted_knowledge_fallback"
fallback_used = False
errors = []

artifact_suffixes = [
    ".status.json",
    ".contract.md",
    ".prd.md",
    ".design.md",
    ".plan.md",
    ".handoff.md",
    ".eval.md",
    ".dispatch.md",
    ".events.jsonl",
]

def safe_name(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")
    return text[:180] or "unknown"

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def first_existing(paths):
    for path in paths:
        if path.exists():
            return path
    return None

exported = []
skipped = []
if sprints.exists():
    for status_path in sorted(sprints.glob("*.status.json")):
        status = read_json(status_path)
        sid = status_path.name[:-len(".status.json")]
        if not isinstance(status, dict):
            skipped.append({"sprint": sid, "reason": "corrupt status.json"})
            continue
        state = str(status.get("status") or "")
        if state not in eligible:
            skipped.append({"sprint": sid, "status": state, "reason": "not eligible"})
            continue
        dest = repo_harness / "sprints" / sid
        dest.mkdir(parents=True, exist_ok=True)
        copied = []
        for suffix in artifact_suffixes:
            src = sprints / f"{sid}{suffix}"
            if src.exists():
                shutil.copy2(src, dest / src.name)
                copied.append(src.name)
        title = status.get("title") or sid
        eval_path = first_existing([sprints / f"{sid}.eval.md", dest / f"{sid}.eval.md"])
        handoff_path = first_existing([sprints / f"{sid}.handoff.md", dest / f"{sid}.handoff.md"])
        plan_path = first_existing([sprints / f"{sid}.plan.md", dest / f"{sid}.plan.md"])
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        knowledge_name = f"solar-harness_{safe_name(sid)}.md"
        knowledge_path = knowledge_dir / knowledge_name
        eval_excerpt = eval_path.read_text(encoding="utf-8", errors="replace")[:4000] if eval_path else "N/A"
        handoff_excerpt = handoff_path.read_text(encoding="utf-8", errors="replace")[:3000] if handoff_path else "N/A"
        plan_excerpt = plan_path.read_text(encoding="utf-8", errors="replace")[:2500] if plan_path else "N/A"
        try:
            knowledge_path.parent.mkdir(parents=True, exist_ok=True)
            knowledge_path.write_text(f"""# Solar Harness 可用功能归档：{title}

生成时间：{now}
Sprint：`{sid}`
状态：`{state}`
归档目录：`{dest}`

## 功能模块

{title}

## 用户价值

该 sprint 已达到 `{state}` 状态，视为可用功能候选；其代码和交付材料已从 live harness 导出到 Solar 仓库的 `harness/` 目录，便于版本化、审查和回滚。

## 设计结构

```text
live: {live}
repo: {repo_harness}
sprint archive: {dest}
```

## 关键文件

{chr(10).join(f"- `{name}`" for name in copied) if copied else "- N/A"}

## 核心 API / 命令

- `scripts/export-harness-artifacts.sh --commit`
- `solar-harness` sprint lifecycle commands

## 验证方法

- 以 sprint `.eval.md` 为准。
- 本归档任务只提交状态为 `{state}` 的 sprint 产物。

## 风险边界

- 不归档 runtime 日志、pid/port、cache、venv、vendor、quarantine、planner inbox。
- 不提交 Solar 仓库中与 `harness/` 和本导出脚本无关的既有脏改。

## 后续改进

- 为每个功能模块补充更细粒度的 code-owner 和测试命令映射。
- 将 eval 中的真实命令结构化为机器可读字段。

## Plan 摘要

```text
{plan_excerpt}
```

## Handoff 摘要

```text
{handoff_excerpt}
```

## Eval 摘要

```text
{eval_excerpt}
```
""", encoding="utf-8")
        except Exception as exc:
            fallback_used = True
            try:
                fallback_knowledge_dir.mkdir(parents=True, exist_ok=True)
                fallback_path = fallback_knowledge_dir / knowledge_name
                fallback_path.write_text(f"""# Solar Harness 可用功能归档：{title}

生成时间：{now}
Sprint：`{sid}`
状态：`{state}`
归档目录：`{dest}`

> WARN: 无法写入目标知识目录：`{knowledge_dir}`。已写入仓库 fallback：`{fallback_path}`。

## 功能模块

{title}

## 用户价值

该 sprint 已达到 `{state}` 状态，视为可用功能候选；其代码和交付材料已从 live harness 导出到 Solar 仓库的 `harness/` 目录，便于版本化、审查和回滚。

## 设计结构

```text
live: {live}
repo: {repo_harness}
sprint archive: {dest}
```

## 关键文件

{chr(10).join(f"- `{name}`" for name in copied) if copied else "- N/A"}

## 核心 API / 命令

- `scripts/export-harness-artifacts.sh --commit`
- `solar-harness` sprint lifecycle commands

## 验证方法

- 以 sprint `.eval.md` 为准。
- 本归档任务只提交状态为 `{state}` 的 sprint 产物。

## 风险边界

- 不归档 runtime 日志、pid/port、cache、venv、vendor、quarantine、planner inbox。
- 不提交 Solar 仓库中与 `harness/` 和本导出脚本无关的既有脏改。

## 后续改进

- 为每个功能模块补充更细粒度的 code-owner 和测试命令映射。
- 将 eval 中的真实命令结构化为机器可读字段。

## Plan 摘要

```text
{plan_excerpt}
```

## Handoff 摘要

```text
{handoff_excerpt}
```

## Eval 摘要

```text
{eval_excerpt}
```
""", encoding="utf-8")
                knowledge_path = fallback_path
            except Exception as exc2:
                errors.append({"sprint": sid, "error": f"knowledge write failed: {exc!r}; fallback failed: {exc2!r}"})
                knowledge_path = Path("N/A")
        exported.append({
            "sprint": sid,
            "status": state,
            "archive": str(dest),
            "knowledge": str(knowledge_path),
            "files": copied,
        })

print(json.dumps({"exported": exported, "skipped": skipped, "knowledge_fallback_used": fallback_used, "errors": errors}, ensure_ascii=False))
PY
)"

echo "$summary_json"
exported_count="$(python3 -c 'import json,sys; print(len(json.load(sys.stdin)["exported"]))' <<<"$summary_json")"

if [[ "$exported_count" == "0" ]]; then
  echo "pending: no eligible harness sprint artifacts found"
  exit 0
fi

if [[ "$DO_COMMIT" == "1" ]]; then
  stage_file="$(mktemp)"
  export SOLAR_REPO REPO_HARNESS
  python3 <<'PY' > "$stage_file"
import os
from pathlib import Path
import re

repo = Path(os.environ["SOLAR_REPO"])
harness = Path(os.environ["REPO_HARNESS"])

allowed_dirs = {
    "ADR",
    "ai-influence-digest",
    "autopilot",
    "brain",
    "chrome-extension-update",
    "config",
    "docker",
    "docs",
    "evals",
    "extensions",
    "hooks",
    "installer",
    "integrations",
    "lib",
    "personas",
    "plugins",
    "release",
    "runbooks",
    "scripts",
    "schemas",
    "skills",
    "status-server",
    "sprints",
    "templates",
    "tests",
    "tools",
}
top_suffixes = {".sh", ".ts", ".json", ".md", ".toml", ".plist", ".py"}
top_names = {"VERSION"}
deny_suffixes = {".pyc"}
deny_names = {
    ".DS_Store",
    "STATE.md",
    "PLANNER-INBOX.md",
    "pending-improvements.jsonl",
    "low-quality-capabilities.json",
    "capability-graph.jsonl",
    "kpi.json",
    "codex-budget.json",
    "google-cse-token.json",
}
deny_fragments = [
    ".bak",
    ".backup",
    ".pid",
    ".port",
    ".log",
    ".lock",
    ".state",
]
deny_dir_names = {"__pycache__", "inbox", "cache", "quarantine", "telemetry", "reports", "events", "logs", "run", "state", "venvs", "vendor"}
deny_name_re = re.compile(r'(^|[-_.])(token|tokens|oauth|refresh_token|credential|credentials)([-_.]|$)')

def denied(path: Path) -> bool:
    parts = path.parts
    name = path.name
    if name in deny_names:
        return True
    if deny_name_re.search(name.lower()) and name.lower().endswith(".json"):
        return True
    if path.suffix in deny_suffixes:
        return True
    if any(part.startswith(".") for part in parts):
        return True
    if any(part in deny_dir_names for part in parts):
        return True
    lowered = str(path).lower()
    return any(fragment in lowered for fragment in deny_fragments)

print("scripts/export-harness-artifacts.sh")
for child in sorted(harness.iterdir()):
    rel = child.relative_to(repo)
    if child.is_file():
        if (child.suffix in top_suffixes or child.name in top_names) and not denied(child.relative_to(harness)):
            print(rel.as_posix())
    elif child.is_dir() and child.name in allowed_dirs:
        for path in sorted(child.rglob("*")):
            if path.is_file() and not denied(path.relative_to(harness)):
                print(path.relative_to(repo).as_posix())
PY
  stage_file_filtered="$(mktemp)"
  ignored_paths_file="$(mktemp)"
  ignored_paths_lines="$(mktemp)"
  # `git check-ignore` will escape/quote non-ASCII paths unless -z is used.
  # `git check-ignore` exits with 1 when there are no matches; treat that as success.
  git -C "$SOLAR_REPO" check-ignore -z --stdin < "$stage_file" > "$ignored_paths_file" || true
  if [[ -s "$ignored_paths_file" ]]; then
    tr '\0' '\n' < "$ignored_paths_file" > "$ignored_paths_lines"
    grep -Fvx -f "$ignored_paths_lines" "$stage_file" > "$stage_file_filtered" || true
  else
    cp "$stage_file" "$stage_file_filtered"
  fi
  rm -f "$ignored_paths_file" "$ignored_paths_lines" "$stage_file"

  git -C "$SOLAR_REPO" add -A --pathspec-from-file="$stage_file_filtered"
  rm -f "$stage_file_filtered"
  if git -C "$SOLAR_REPO" diff --cached --quiet; then
    echo "pending: no staged repo changes after export"
    exit 0
  fi
  knowledge_paths="$(python3 -c 'import json,sys; print("\n".join(item["knowledge"] for item in json.load(sys.stdin)["exported"]))' <<<"$summary_json")"
  commit_body="$(mktemp)"
  {
    echo "feat(solar): archive usable harness feature artifacts"
    echo
    echo "Export usable Solar Harness artifacts into Solar/harness."
    echo
    echo "Validation:"
    echo "- Eligible sprint status filter: $ELIGIBLE_STATUSES"
    echo "- Exported sprint count: $exported_count"
    echo
    echo "Knowledge extraction files:"
    echo "$knowledge_paths" | sed 's/^/- /'
  } > "$commit_body"
  git -C "$SOLAR_REPO" commit -F "$commit_body"
  rm -f "$commit_body"
  git -C "$SOLAR_REPO" rev-parse --short HEAD
fi
