#!/usr/bin/env python3
"""Command backend adapter for Antigravity multimodal/image tasks."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
import datetime as dt
from pathlib import Path


IMAGE_RE = re.compile(r"(?P<path>(?:/[^\s`'\"<>]+|~[^\s`'\"<>]+)\.(?:png|jpe?g|webp))", re.I)
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|cookie)(\s*[:=]\s*)([^\s`'\"<>]+)"
)
QUOTA_RE = re.compile(
    r"RESOURCE_EXHAUSTED|\bquota(?:\s+exhausted)?\b|rate[- ]?limit|\b429\b|resets?\s+in|"
    r"You've hit .*limit|Individual quota reached",
    re.I,
)
AUTH_RE = re.compile(
    r"not logged in|you are not logged|not authenticated|auth(?:entication)? failed|oauth token|"
    r"permission denied|login required|logged out|auth expired",
    re.I,
)
AUTH_SUCCESS_RE = re.compile(
    r"OAuth:\s*authenticated successfully|silent auth succeeded|Auth done received|authenticated via keyring",
    re.I,
)
FAILURE_RE = re.compile(r"error:\s*timed out waiting for response|timed out waiting for response|traceback|uncaught exception", re.I)
PLACEHOLDER_OUTPUT_RE = re.compile(r"^\s*#*\s*(handoff|completed|done)\s*#*\s*$", re.I)
NONFINAL_OUTPUT_RE = re.compile(
    r"^\s*(i\s+will|i'll|i\s+am\s+going\s+to|let\s+me|i\s+need\s+to|i'll\s+now)\b",
    re.I,
)
NO_ACTIVE_CONVERSATION_RE = re.compile(
    r"no active conversation|failed to send message.*no active|Error:.*no active conversation",
    re.I,
)

# Exit codes
EXIT_SUCCESS = 0
EXIT_GENERIC_FAILURE = 65
EXIT_QUOTA_EXHAUSTED = 75
EXIT_AUTH_EXPIRED = 76
EXIT_BOOTSTRAP_FAILED = 77


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def image_paths(text: str) -> list[Path]:
    paths: list[Path] = []
    explicit = os.environ.get("SOLAR_MULTIMODAL_IMAGE", "")
    for item in explicit.split(":"):
        if item.strip():
            paths.append(Path(item).expanduser())
    for match in IMAGE_RE.finditer(text):
        paths.append(Path(match.group("path")).expanduser())
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen and path.exists():
            seen.add(key)
            result.append(path)
    return result


def redact(text: str) -> str:
    return SECRET_RE.sub(r"\1\2***REDACTED***", text)


def auth_failure_is_current(text: str) -> bool:
    """Return true only when auth failure was not superseded by silent auth.

    Antigravity often logs early "not logged in" lines, then refreshes from
    keyring and continues successfully. Treating those stale lines as terminal
    auth failures blocks a healthy operator.
    """
    raw = text or ""
    last_auth = None
    for match in AUTH_RE.finditer(raw):
        last_auth = match
    if last_auth is None:
        return False
    for success in AUTH_SUCCESS_RE.finditer(raw):
        if success.start() > last_auth.start():
            return False
    return True


def output_is_placeholder(text: str) -> bool:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return True
    if len(lines) == 1 and PLACEHOLDER_OUTPUT_RE.match(lines[0]):
        return True
    if NONFINAL_OUTPUT_RE.match(clean) and not re.search(r"\b(completed|verified|done|image_unsupported|smoke_ok|handoff)\b", clean, re.I):
        return True
    # A valid operator handoff needs some evidence, not just a section title.
    return len(lines) == 1 and len(clean) < 24 and not re.search(r"\b(ok|pass|verified|image_unsupported|smoke_ok)\b", clean, re.I)


def extract_section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return "N/A"
    rest = text[start + len(marker) :].strip()
    next_heading = re.search(r"\n##\s+", rest)
    if next_heading:
        rest = rest[: next_heading.start()].strip()
    return rest or "N/A"


def write_handoff(dispatch: str, agent_output: str) -> Path:
    handoff = Path(os.environ.get("HANDOFF", "")).expanduser()
    if not str(handoff) or str(handoff) == ".":
        sid = os.environ.get("SID", "unknown-sprint")
        node_id = os.environ.get("NODE_ID", "unknown-node")
        sprints_dir = Path(os.environ.get("SPRINTS_DIR", Path.home() / ".solar" / "harness" / "sprints"))
        handoff = sprints_dir / f"{sid}.{node_id}-handoff.md"
    if handoff.exists() and handoff.stat().st_size > 0:
        return handoff

    sid = os.environ.get("SID", "unknown-sprint")
    node_id = os.environ.get("NODE_ID", "unknown-node")
    safe_output = redact(agent_output).strip()
    if len(safe_output) > 16000:
        safe_output = safe_output[:16000] + "\n\n[truncated]"
    acceptance = extract_section(dispatch, "Acceptance")
    goal = extract_section(dispatch, "Goal")
    handoff_text = f"""# Handoff — {sid} / {node_id}

Builder: Antigravity command backend adapter
Generated-At: {now()}

## 已完成

- 调用 Antigravity CLI command backend 完成本节点。
- 将 Antigravity stdout 归档为本节点 handoff，供 graph-scheduler/evaluator 后续验证。

## 节点目标

{goal}

## Acceptance 摘要

{acceptance}

## Antigravity 输出

```markdown
{safe_output}
```

## 已验证

- Antigravity CLI 进程 exit_code=0。
- handoff 文件由 command backend adapter 写入。
- 未在 handoff 中写入已知 key/token/secret/password/cookie 字段原文。

## 未验证

- 语义验收仍需后续 evaluator 按合同检查。

## 风险

- 该 handoff 由 wrapper 从 CLI stdout 转写；如果 stdout 内容质量不足，evaluator 必须 FAIL，不得直接视为最终验收。

## 后续待办

- 将 command backend handoff 生成逻辑纳入 operatord/operator_runtime.submit 的标准输出契约。
"""
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(handoff_text, encoding="utf-8")
    return handoff


def write_pm_result_if_needed(dispatch: str, agent_output: str, handoff: Path) -> None:
    result_path = os.environ.get("PM_RESULT_PATH") or os.environ.get("RESULT_PATH")
    if not result_path:
        return
    path = Path(result_path).expanduser()
    if path.exists() and path.stat().st_size > 0:
        return
    safe_output = redact(agent_output).strip()
    if len(safe_output) > 20000:
        safe_output = safe_output[:20000] + "\n\n[truncated]"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# PM Task Result — {os.environ.get('TASK_ID', 'antigravity-operator')}

## 已完成

- Antigravity command backend 已执行 PM dispatch。
- 已写入 handoff: `{handoff}`

## 已验证

- Antigravity CLI exit_code=0。
- wrapper 已补写 PM_RESULT_PATH，避免 command backend 完成后被 operatord 判为 missing_pm_result。

## 结论摘要

```markdown
{safe_output or 'N/A'}
```

## 风险/限制

- 该结果由 wrapper 从 Antigravity stdout 转写；如 stdout 未列出真实文件修改和测试证据，Evaluator 必须继续拦截。

## 后续建议

- 按 dispatch Definition of Done 复核文件变更、命令输出和测试证据。
""",
        encoding="utf-8",
    )


def _load_operator_envelope() -> dict:
    path_value = os.environ.get("SOLAR_OPERATOR_ENVELOPE_JSON", "").strip()
    if not path_value:
        return {}
    path = Path(path_value).expanduser()
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _dispatch_from_envelope(envelope: dict) -> str:
    if not envelope:
        return ""
    objective = str(envelope.get("objective") or "").strip()
    task_type = str(envelope.get("task_type") or "").strip()
    acceptance = envelope.get("acceptance")
    if isinstance(acceptance, list):
        acceptance_text = "\n".join(f"- {item}" for item in acceptance)
    else:
        acceptance_text = str(acceptance or "").strip()
    if not objective and not acceptance_text:
        return ""
    return "\n".join(
        [
            f"# Operator Dispatch — {envelope.get('task_id', 'antigravity-task')}",
            "",
            "## Goal",
            objective or "Complete the operator task described by the envelope.",
            "",
            "## Task Type",
            task_type or "N/A",
            "",
            "## Acceptance",
            acceptance_text or "- Provide a concise handoff with completed, verified, unverified, risks, and next steps.",
            "",
            "## Safety",
            "- Do not edit files unless the dispatch explicitly asks for edits.",
            "- Do not print secrets.",
        ]
    )


def load_dispatch_text() -> tuple[str, Path | None]:
    dispatch_file_value = os.environ.get("SOLAR_MULTI_TASK_DISPATCH_FILE", "").strip()
    if dispatch_file_value:
        dispatch_file = Path(dispatch_file_value).expanduser()
        if dispatch_file.exists() and dispatch_file.is_file():
            return dispatch_file.read_text(encoding="utf-8", errors="replace"), dispatch_file
        print(f"ERROR: SOLAR_MULTI_TASK_DISPATCH_FILE is not a readable file: {dispatch_file}", file=sys.stderr)
        return "", None
    envelope_dispatch = _dispatch_from_envelope(_load_operator_envelope())
    if envelope_dispatch:
        return envelope_dispatch, None
    print(
        "ERROR: dispatch missing; set SOLAR_MULTI_TASK_DISPATCH_FILE to a file or provide SOLAR_OPERATOR_ENVELOPE_JSON with objective/acceptance",
        file=sys.stderr,
    )
    return "", None




def capture_raw_intent_entrypoint(text: str) -> int:
    cmd = [
        sys.executable,
        str(Path.home() / ".solar" / "harness" / "lib" / "intent_gateway.py"),
        "capture",
        "--source-channel", "antigravity_bridge",
        "--actor", "user",
        "--device", "mac_mini_antigravity",
        "--repo", str(Path.home() / ".solar" / "harness"),
        "--source-trust", "antigravity_bridge",
        "--text", text,
        "--json",
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=30)
    proc_stdout = proc.stdout
    if proc.returncode == 0 and proc.stdout:
        try:
            payload = json.loads(proc.stdout)
            intent_id = str(payload.get("intent_id") or "")
            if intent_id:
                consumer = subprocess.run([
                    sys.executable,
                    str(Path.home() / ".solar" / "harness" / "lib" / "intent_consumer.py"),
                    "consume",
                    "--intent-id", intent_id,
                    "--json",
                ], text=True, capture_output=True, timeout=120)
                if consumer.returncode == 0:
                    payload["consumer"] = json.loads(consumer.stdout)
                    proc_stdout = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
                else:
                    print(consumer.stderr or consumer.stdout, file=sys.stderr)
        except Exception:
            proc_stdout = proc.stdout
    if proc_stdout:
        print(proc_stdout, end="" if proc_stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")
    return proc.returncode


def tail_text(path: Path, limit: int = 4000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-limit:]


def _with_continue_flag(cmd: list[str]) -> list[str]:
    if "--continue" in cmd:
        return list(cmd)
    if "--print" in cmd:
        idx = cmd.index("--print")
        return [*cmd[:idx], "--continue", *cmd[idx:]]
    return [*cmd, "--continue"]


def _terminate_proc(proc: "subprocess.Popen[str]") -> tuple[str, str]:
    proc.terminate()
    try:
        stdout, stderr = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
    return stdout or "", stderr or ""


def run_agy_command(cmd: list[str], log_file: Path) -> subprocess.CompletedProcess[str]:
    """Run Antigravity and fail fast when the live log shows hard failures.

    Exit-code semantics:
      75 — quota exhausted
      76 — auth expired / not logged in
      77 — bootstrap failed (no active conversation, --continue retry also failed)
      65 — generic backend failure
    """
    allow_continue_retry = "--continue" not in cmd
    current_cmd = list(cmd)
    tried_continue = False
    while True:
        proc = subprocess.Popen(current_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        retry_with_continue = False
        while True:
            rc = proc.poll()
            if rc is not None:
                stdout, stderr = proc.communicate()
                combined = "\n".join(
                    part for part in [stdout or "", stderr or "", tail_text(log_file)] if part
                )
                # Auth check takes priority even at process-exit time.
                if auth_failure_is_current(combined):
                    message = (
                        "ERROR: Antigravity auth expired or not logged in; refusing handoff\n"
                        "  Recovery: run `agy login` and re-authenticate.\n"
                        + redact(combined[-2000:])
                    )
                    merged_stderr = ((stderr or "") + "\n" + message).strip() + "\n"
                    return subprocess.CompletedProcess(current_cmd, EXIT_AUTH_EXPIRED, stdout=stdout or "", stderr=merged_stderr)

                if allow_continue_retry and NO_ACTIVE_CONVERSATION_RE.search(combined):
                    allow_continue_retry = False
                    current_cmd = _with_continue_flag(current_cmd)
                    tried_continue = True
                    print(
                        "INFO: Antigravity conversation missing; retrying once with --continue",
                        file=sys.stderr,
                    )
                    retry_with_continue = True
                    break

                # If we already retried with --continue and still no active conversation,
                # classify as bootstrap_failed so callers can surface a clear diagnostic.
                if tried_continue and NO_ACTIVE_CONVERSATION_RE.search(combined):
                    message = (
                        "ERROR: Antigravity bootstrap failed; no active conversation even after --continue retry.\n"
                        "  Recovery: start a new conversation in Antigravity, then retry the dispatch.\n"
                        + redact(combined[-2000:])
                    )
                    merged_stderr = ((stderr or "") + "\n" + message).strip() + "\n"
                    return subprocess.CompletedProcess(current_cmd, EXIT_BOOTSTRAP_FAILED, stdout=stdout or "", stderr=merged_stderr)

                return subprocess.CompletedProcess(current_cmd, rc, stdout=stdout or "", stderr=stderr or "")

            log_tail = tail_text(log_file)
            if QUOTA_RE.search(log_tail):
                stdout, stderr = _terminate_proc(proc)
                message = "ERROR: Antigravity quota exhausted; refusing empty handoff\n" + redact(log_tail)
                stderr = ((stderr or "") + "\n" + message).strip() + "\n"
                return subprocess.CompletedProcess(current_cmd, EXIT_QUOTA_EXHAUSTED, stdout=stdout, stderr=stderr)

            if auth_failure_is_current(log_tail):
                stdout, stderr = _terminate_proc(proc)
                message = (
                    "ERROR: Antigravity auth expired or not logged in; refusing handoff\n"
                    "  Recovery: run `agy login` and re-authenticate.\n"
                    + redact(log_tail)
                )
                stderr = ((stderr or "") + "\n" + message).strip() + "\n"
                return subprocess.CompletedProcess(current_cmd, EXIT_AUTH_EXPIRED, stdout=stdout, stderr=stderr)

            if FAILURE_RE.search(log_tail):
                stdout, stderr = _terminate_proc(proc)
                message = "ERROR: Antigravity command backend reported failure; refusing success handoff\n" + redact(log_tail)
                stderr = ((stderr or "") + "\n" + message).strip() + "\n"
                return subprocess.CompletedProcess(current_cmd, EXIT_GENERIC_FAILURE, stdout=stdout, stderr=stderr)

            time.sleep(1)

        if retry_with_continue:
            continue


def _preflight_operator_check(operator_id: str) -> int | None:
    """Check operator block state before launching Antigravity.

    Returns an exit code if blocked, or None if clear to proceed.
    """
    try:
        lib_dir = Path.home() / ".solar" / "harness" / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        import operator_flow_control as ofc  # type: ignore

        snapshot = ofc.current_block_state(operator_id, allow_unregistered=True)
        if snapshot is None:
            return None
        runtime_state = str(snapshot.get("runtime_state") or "")
        expires_at = str(snapshot.get("expires_at") or "")
        msg = ofc.format_auth_blocker_message(operator_id, runtime_state, expires_at=expires_at)
        print(f"ERROR: pre-flight operator check blocked dispatch.\n{msg}", file=sys.stderr)
        if runtime_state == "auth_expired":
            return EXIT_AUTH_EXPIRED
        return EXIT_GENERIC_FAILURE
    except Exception as exc:
        # Don't block dispatch if the check itself fails; just warn.
        print(f"WARN: pre-flight operator check error (proceeding): {exc}", file=sys.stderr)
        return None


def main() -> int:
    raw_intent = os.environ.get("SOLAR_ANTIGRAVITY_RAW_INTENT", "").strip()
    if not raw_intent and len(sys.argv) > 1:
        raw_intent = " ".join(sys.argv[1:]).strip()
    if raw_intent:
        return capture_raw_intent_entrypoint(raw_intent)

    dispatch, dispatch_file = load_dispatch_text()
    if not dispatch:
        return 2

    # Pre-flight: check if operator is blocked before launching the AGY process.
    operator_id = os.environ.get("SOLAR_OPERATOR_ID", "").strip()
    if operator_id:
        preflight_rc = _preflight_operator_check(operator_id)
        if preflight_rc is not None:
            return preflight_rc

    images = image_paths(dispatch)
    add_dirs = sorted({str(path.parent) for path in images})
    agy = os.environ.get("AGY_BIN", "~/.local/bin/agy")
    timeout = os.environ.get("AGY_PRINT_TIMEOUT", "10m")
    default_task_dir = dispatch_file.parent if dispatch_file is not None else Path.cwd()
    task_dir = Path(os.environ.get("TASK_DIR", default_task_dir)).expanduser()
    task_dir.mkdir(parents=True, exist_ok=True)
    log_file = task_dir / "antigravity.log"

    prompt = "\n".join([
        "You are running as a Solar multimodal/image physical operator.",
        "Read the dispatch below, inspect referenced image files if present, and complete only the requested node.",
        "Do not print secrets. If you cannot inspect an image, state IMAGE_UNSUPPORTED and explain the blocker.",
        "Return a concise Markdown handoff with sections: completed, verified, unverified, risks, next steps.",
        "Do not ask for confirmation; perform the node work and provide the final handoff text.",
        "",
        "Referenced image files:",
        "\n".join(f"- {path}" for path in images) if images else "- N/A",
        "",
        dispatch,
    ])

    cmd = [agy, "--log-file", str(log_file), "--dangerously-skip-permissions", "--print-timeout", timeout]
    for directory in add_dirs:
        cmd.extend(["--add-dir", directory])
    cmd.extend(["--print", prompt])
    print("[solar-harness agy-multimodal] cmd=" + " ".join(shlex.quote(part) for part in cmd[:-1]) + " <prompt>")
    proc = run_agy_command(cmd, log_file)
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")
    if proc.returncode == 0:
        output = (proc.stdout or "").strip()
        log_tail = tail_text(log_file)
        combined_output = "\n".join(part for part in [output, log_tail] if part)
        if FAILURE_RE.search(combined_output):
            print("ERROR: Antigravity command backend reported failure; refusing success handoff", file=sys.stderr)
            safe_tail = redact(combined_output[-4000:])
            if safe_tail:
                print(safe_tail, file=sys.stderr)
            return EXIT_GENERIC_FAILURE
        if not output:
            safe_tail = redact(log_tail)
            if QUOTA_RE.search(log_tail):
                print("ERROR: Antigravity quota exhausted; refusing empty handoff", file=sys.stderr)
                if safe_tail:
                    print(safe_tail, file=sys.stderr)
                return EXIT_QUOTA_EXHAUSTED
            if auth_failure_is_current(log_tail):
                print(
                    "ERROR: Antigravity auth expired or not logged in; refusing empty handoff\n"
                    "  Recovery: run `agy login` and re-authenticate.\n"
                    "  If operator tracking is enabled, clear the block:\n"
                    f"    python3 -m operator_runtime clear-override --operator <operator-id>",
                    file=sys.stderr,
                )
                if safe_tail:
                    print(safe_tail, file=sys.stderr)
                return EXIT_AUTH_EXPIRED
            if NO_ACTIVE_CONVERSATION_RE.search(log_tail):
                print(
                    "ERROR: Antigravity bootstrap failed; no active conversation.\n"
                    "  Recovery: start a new conversation in Antigravity, then retry the dispatch.",
                    file=sys.stderr,
                )
                if safe_tail:
                    print(safe_tail, file=sys.stderr)
                return EXIT_BOOTSTRAP_FAILED
            print("ERROR: Antigravity command backend returned empty stdout; refusing empty handoff", file=sys.stderr)
            if safe_tail:
                print(safe_tail, file=sys.stderr)
            return EXIT_GENERIC_FAILURE
        if output_is_placeholder(output):
            print("ERROR: Antigravity command backend returned placeholder handoff; refusing false success", file=sys.stderr)
            safe_tail = redact(combined_output[-4000:])
            if safe_tail:
                print(safe_tail, file=sys.stderr)
            return EXIT_GENERIC_FAILURE
        handoff = write_handoff(dispatch, output)
        write_pm_result_if_needed(dispatch, output, handoff)
        print(f"[solar-harness agy-multimodal] wrote_handoff={handoff}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
