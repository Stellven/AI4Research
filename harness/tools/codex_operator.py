#!/usr/bin/env python3
"""Run a Solar PM dispatch through Codex CLI non-interactively."""
from __future__ import annotations

import atexit
import json
import os
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_HARNESS_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _HARNESS_LIB_DIR not in sys.path:
    sys.path.insert(0, _HARNESS_LIB_DIR)

from codex_cli_runtime import resolve_codex_cli


_SKILL_BRIDGE_CAPSULE_ID = "cap.skill-execution-bridge"
_DEFAULT_SKILL_WORKFLOW_PHASES = [
    "frame_objective_and_constraints",
    "apply_skill_workflow",
    "validate_against_acceptance",
    "summarize_decisions_and_evidence",
]


def _read_operator_envelope() -> dict[str, object]:
    raw = os.environ.get("SOLAR_OPERATOR_ENVELOPE_JSON") or ""
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _selected_skills(envelope: dict[str, object]) -> list[str]:
    candidates: list[object] = [envelope.get("selected_skills")]
    for key in ("capsule_plan", "resolved_capability_capsule", "task_graph_node"):
        nested = envelope.get(key)
        if isinstance(nested, dict):
            candidates.extend(
                [
                    nested.get("selected_skills"),
                    nested.get("required_skills"),
                ]
            )
    selected: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, list):
            continue
        for item in candidate:
            skill_id = str(item or "").strip()
            if skill_id and skill_id not in selected:
                selected.append(skill_id)
    return selected


def _materialize_skill_bridge_evidence(task_dir: Path, dispatch: str) -> dict[str, object]:
    envelope = _read_operator_envelope()
    capsule = envelope.get("resolved_capability_capsule")
    capsule_id = ""
    if isinstance(capsule, dict):
        capsule_id = str(capsule.get("id") or capsule.get("capsule_id") or "").strip()
    if not capsule_id:
        capsule_id = str(envelope.get("capability_capsule_id") or "").strip()
    if capsule_id != _SKILL_BRIDGE_CAPSULE_ID:
        return {}

    selected_skills = _selected_skills(envelope)
    try:
        from skill_capsule_bridge import resolve_skill_records

        records = resolve_skill_records(selected_skills)
    except Exception as exc:
        records = []
        resolution_error = f"{type(exc).__name__}: {exc}"
    else:
        resolution_error = ""

    resolved_skill_ids = [
        str(record.get("skill_id") or "").strip()
        for record in records
        if isinstance(record, dict) and str(record.get("skill_id") or "").strip()
    ]
    primary = records[0] if records and isinstance(records[0], dict) else {}
    workflow_phases = [
        str(item).strip()
        for item in primary.get("workflow_phases", [])
        if str(item).strip()
    ] or list(_DEFAULT_SKILL_WORKFLOW_PHASES)
    selection_mode = "resolved_skill_record" if records else "direct_command_fallback"
    fallback_reason = ""
    if not records:
        fallback_reason = resolution_error or "selected_skill_not_resolved"

    evidence = {
        "schema": "solar.skill_bridge.direct_command.v1",
        "capsule_id": capsule_id,
        "selected_skills": selected_skills,
        "resolved_skill_ids": resolved_skill_ids,
        "selection_mode": selection_mode,
        "fallback_reason": fallback_reason,
        "command_protocol": {
            "mode": str(primary.get("template_profile") or "prompt_context_skill"),
            "execution_surface": "direct_command_operator",
            "record_exact_commands": True,
        },
        "workflow_contract": {
            "phases": workflow_phases,
            "delivery_expectation": str(
                primary.get("delivery_expectation") or "phase_checklist_and_decision_log"
            ),
        },
    }
    task_dir.mkdir(parents=True, exist_ok=True)
    prompt = (
        "# Skill dispatch pane prompt\n\n"
        f"- capsule: `{capsule_id}`\n"
        f"- selected_skills: `{json.dumps(selected_skills, ensure_ascii=False)}`\n"
        f"- selection_mode: `{selection_mode}`\n"
        f"- fallback_reason: `{fallback_reason or 'none'}`\n"
        "- execution_surface: `direct_command_operator`\n\n"
        "## Dispatch\n\n"
        f"{dispatch.rstrip()}\n"
    )
    (task_dir / "skill-dispatch-pane-prompt.md").write_text(prompt, encoding="utf-8")
    (task_dir / "skill-dispatch-selection-proof.json").write_text(
        json.dumps(
            {
                "schema": evidence["schema"],
                "capsule_id": capsule_id,
                "selected_skills": selected_skills,
                "resolved_skill_ids": resolved_skill_ids,
                "selection_mode": selection_mode,
                "fallback_reason": fallback_reason,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "skill-dispatch-bridge-contract.json").write_text(
        json.dumps(
            {
                "schema": evidence["schema"],
                "capsule_id": capsule_id,
                "command_protocol": evidence["command_protocol"],
                "workflow_contract": evidence["workflow_contract"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return evidence


def _write_skill_bridge_result(task_dir: Path, evidence: dict[str, object], exit_code: int) -> None:
    if not evidence:
        return
    payload = dict(evidence)
    payload.update(
        {
            "status": "completed" if exit_code == 0 else "failed",
            "exit_code": exit_code,
        }
    )
    (task_dir / "skill-dispatch-result.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _declared_output_guidance() -> str:
    try:
        outputs = json.loads(os.environ.get("SOLAR_OPERATOR_ALLOWED_OUTPUTS_JSON") or "[]")
    except (TypeError, ValueError):
        return ""
    paths = [str(item).strip() for item in outputs if isinstance(item, str) and item.strip()]
    if not paths:
        return ""
    rendered = "\n".join(f"- `{path}`" for path in paths)
    return (
        "## Solar filesystem output contract\n\n"
        "Solar may pre-create the exact declared output paths as zero-byte placeholders so "
        "Landlock can grant file-level write access. A placeholder is not a completed artifact. "
        "Write these files in place; do not delete and recreate them. When using apply_patch on "
        "an existing placeholder, use Update File rather than Add File.\n\n"
        "Declared writable outputs:\n"
        f"{rendered}"
    )


def _read_dispatch() -> str:
    dispatch_file = os.environ.get("DISPATCH_FILE") or os.environ.get("SOLAR_MULTI_TASK_DISPATCH_FILE")
    if dispatch_file:
        path = Path(dispatch_file).expanduser()
        if path.exists():
            dispatch = path.read_text(encoding="utf-8", errors="replace")
        else:
            dispatch = sys.stdin.read()
    else:
        dispatch = sys.stdin.read()
    guidance = _declared_output_guidance()
    return f"{dispatch.rstrip()}\n\n{guidance}\n" if guidance else dispatch


def _write_pm_result(task_dir: Path, output_file: Path, output: str, exit_code: int) -> None:
    result_path = os.environ.get("PM_RESULT_PATH") or os.environ.get("RESULT_PATH")
    if not result_path:
        return
    path = Path(result_path).expanduser()
    if path.exists() and path.stat().st_size > 0:
        return
    text = output.strip()
    if not text and output_file.exists():
        text = output_file.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) > 20000:
        text = text[:20000] + "\n\n[truncated]"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            f"# PM Task Result — {os.environ.get('TASK_ID', 'codex-operator')}\n\n"
            "## 已完成\n"
            "- Codex CLI command backend 已执行 PM dispatch。\n\n"
            "## 已验证\n"
            f"- codex exec exit_code={exit_code}。\n"
            f"- output_file={output_file}\n"
            f"- task_dir={task_dir}\n\n"
            "## 结论摘要\n"
            f"{text or 'N/A'}\n\n"
            "## 风险/限制\n"
            "- 该结果由 Codex wrapper 从最后消息/stdout 转写；仍需 evaluator 复核真实文件修改和测试证据。\n\n"
            "## 后续建议\n"
            "- 按 dispatch Definition of Done 复核文件变更、命令输出和测试证据。\n"
        ),
        encoding="utf-8",
    )


def _timeout_seconds() -> float:
    raw = (
        os.environ.get("CODEX_OPERATOR_TIMEOUT_SECONDS")
        or os.environ.get("SOLAR_CODEX_OPERATOR_TIMEOUT_SECONDS")
        or "900"
    )
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 900.0


def _truthy_env(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in {"0", "false", "off", "no", ""}


def _prepend_env_path(env: dict[str, str], name: str, entries: list[Path | str]) -> None:
    existing = [part for part in env.get(name, "").split(os.pathsep) if part]
    prefix = [str(Path(part).expanduser()) for part in entries if str(part)]
    seen: set[str] = set()
    merged: list[str] = []
    for part in prefix + existing:
        if part and part not in seen:
            merged.append(part)
            seen.add(part)
    env[name] = os.pathsep.join(merged)


def _install_harness_command_shims(task_dir: Path, harness_dir: Path) -> Path:
    shim_dir = task_dir / "cmd-shims"
    shim_dir.mkdir(parents=True, exist_ok=True)
    solar_harness = shim_dir / "solar-harness"
    solar_harness.write_text(
        (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "exec \"${HARNESS_DIR}/solar-harness.sh\" \"$@\"\n"
        ),
        encoding="utf-8",
    )
    solar_harness.chmod(0o755)
    return shim_dir


def _codex_exec_env(task_dir: Path) -> dict[str, str]:
    """Build a deterministic environment for non-interactive Codex operator runs.

    The strict wrapper later gives each run a harness-owned CODEX_HOME and
    exposes the user's auth/config through read-only symlinks. SQLite/app-server
    state therefore stays inside the harness. The model shell must also resolve
    Solar helper commands from this active harness, not from any installed
    ~/.solar runtime left on the developer machine.
    """
    env = os.environ.copy()
    harness_dir = Path(env.get("HARNESS_DIR") or Path.home() / ".solar" / "harness").expanduser().resolve(strict=False)
    shim_dir = _install_harness_command_shims(task_dir, harness_dir)
    state_home = Path(
        env.get("CODEX_SQLITE_HOME")
        or env.get("SOLAR_CODEX_STATE_HOME")
        or harness_dir / "run" / "codex-state"
    ).expanduser()
    state_home.mkdir(parents=True, exist_ok=True)
    configured_codex_home = env.get("SOLAR_CODEX_SOURCE_HOME")
    source_codex_home = Path(configured_codex_home).expanduser() if configured_codex_home else Path.home() / ".codex"
    sprints_dir = Path(
        env.get("SPRINTS_DIR")
        or env.get("HARNESS_SPRINTS_DIR")
        or harness_dir / "sprints"
    ).expanduser().resolve(strict=False)
    env["HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_HARNESS_DIR"] = str(harness_dir)
    env["SPRINTS_DIR"] = str(sprints_dir)
    env["HARNESS_SPRINTS_DIR"] = str(sprints_dir)
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(sprints_dir)
    env["SOLAR_HARNESS_CMD"] = str(shim_dir / "solar-harness")
    env["SOLAR_CODEX_SOURCE_HOME"] = str(source_codex_home)
    env["CODEX_SQLITE_HOME"] = str(state_home)
    _prepend_env_path(env, "PATH", [shim_dir, harness_dir / "bin", harness_dir])
    _prepend_env_path(env, "PYTHONPATH", [harness_dir / "lib", harness_dir / "tools"])
    return env


def _codex_live_search_requested() -> bool:
    """Project the dashboard's search setting onto the safe CLI capability.

    ``SOLAR_CODEX_EXTRA_FLAGS`` is assembled by ``solar-harness.sh`` for
    interactive panes, but the operator backend must not blindly forward that
    shell-shaped string.  Codex exposes live search as a global option, so the
    only supported projection here is the exact ``--search`` token placed
    before ``exec``.  Reasoning effort already has its own typed argument.
    """
    raw = os.environ.get("SOLAR_CODEX_EXTRA_FLAGS", "").strip()
    if not raw:
        return False
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return False
    return "--search" in tokens


def _codex_model() -> str:
    """Resolve the model while honoring the harness-wide Codex policy."""
    policy_model = os.environ.get("SOLAR_CODEX_MODEL", "").strip()
    configured_model = os.environ.get("CODEX_MODEL", "").strip()
    return policy_model or configured_model or "gpt-5.5"


def _codex_exec_command(
    model: str,
    effort: str,
    cwd: str,
    output_file: Path,
    codex_binary: str = "codex",
) -> list[str]:
    cmd = [codex_binary]
    if _codex_live_search_requested():
        cmd.append("--search")
    cmd.append("exec")
    if _truthy_env("SOLAR_CODEX_OPERATOR_EPHEMERAL", "1"):
        cmd.append("--ephemeral")
    cmd.extend([
        "--model",
        model,
        "--config",
        f"model_reasoning_effort={effort}",
        "--config",
        'cli_auth_credentials_store="file"',
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd",
        cwd,
        "--output-last-message",
        str(output_file),
        "-",
    ])
    return cmd


def _existing_paths(values: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        resolved = value.expanduser().resolve(strict=False)
        key = str(resolved)
        if resolved.exists() and key not in seen:
            result.append(resolved)
            seen.add(key)
    return result


def _declared_read_scope_paths(env: dict[str, str], cwd: Path) -> list[Path]:
    """Resolve the operator envelope's exact read grants.

    Relative graph scopes are anchored to the sprint workdir. Evaluator
    snapshots may add absolute published paths after their bytes and digest
    have been frozen by graph dispatch.
    """
    try:
        declared = json.loads(env.get("SOLAR_OPERATOR_READ_SCOPE_JSON") or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(declared, list):
        return []
    paths: list[Path] = []
    for value in declared:
        if not isinstance(value, str) or not value.strip():
            continue
        path = Path(value).expanduser()
        paths.append(path if path.is_absolute() else cwd / path)
    return _existing_paths(paths)


def _path_filesystem_type(path: Path) -> str:
    """Return the Linux mount type containing path, using longest-prefix match."""
    try:
        resolved = path.expanduser().resolve(strict=False)
        best: tuple[int, str] | None = None
        for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
            fields = line.split()
            separator = fields.index("-")
            mountpoint = Path(
                fields[4]
                .replace("\\040", " ")
                .replace("\\011", "\t")
                .replace("\\012", "\n")
                .replace("\\134", "\\")
            )
            if resolved == mountpoint or resolved.is_relative_to(mountpoint):
                candidate = (len(mountpoint.parts), fields[separator + 1].lower())
                if best is None or candidate[0] > best[0]:
                    best = candidate
        return best[1] if best else ""
    except (OSError, ValueError):
        return ""


def _filesystem_isolated_command(
    command: list[str],
    *,
    task_dir: Path,
    cwd: Path,
    env: dict[str, str],
) -> tuple[list[str], dict[str, object]]:
    """Wrap a strict Solar operator in a kernel-enforced filesystem allowlist."""
    strict = _truthy_env("SOLAR_OPERATOR_STRICT_FS_SCOPE", "0")
    mode = env.get("SOLAR_CODEX_OPERATOR_FS_ISOLATION", "landlock").strip().lower()
    if mode in {"0", "off", "disabled", "none"}:
        if strict:
            raise RuntimeError("strict operator filesystem scope cannot disable Landlock")
        return command, {"mode": "disabled", "strict": False}

    harness_dir = Path(env["HARNESS_DIR"]).expanduser().resolve(strict=False)
    state_root = Path(
        env.get("SOLAR_CODEX_OPERATOR_STATE_ROOT")
        or f"/tmp/solar-codex-operator-state-{os.getuid()}"
    ).expanduser()
    state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_root.chmod(0o700)
    state_home = Path(tempfile.mkdtemp(prefix=f"{os.getpid()}-", dir=state_root))
    atexit.register(shutil.rmtree, state_home, ignore_errors=True)
    env["CODEX_SQLITE_HOME"] = str(state_home)
    # Login shells spawned by Codex must not probe the operator user's real
    # profile, which is intentionally outside the Landlock read boundary.
    env["HOME"] = str(state_home)
    tmp_dir = task_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(tmp_dir)
    env["TMP"] = str(tmp_dir)
    env["TEMP"] = str(tmp_dir)

    source_codex_home = Path(env["SOLAR_CODEX_SOURCE_HOME"]).expanduser()
    codex_home = state_home / "home"
    codex_home.mkdir(parents=True, exist_ok=True)
    source = source_codex_home / "auth.json"
    destination = codex_home / "auth.json"
    if source.is_file():
        shutil.copyfile(source, destination)
        destination.chmod(0o600)
    config = codex_home / "config.toml"
    config.write_text('cli_auth_credentials_store = "file"\n', encoding="utf-8")
    config.chmod(0o600)
    env["CODEX_HOME"] = str(codex_home)

    if sys.platform != "linux":
        if strict:
            raise RuntimeError("strict operator filesystem scope requires Linux Landlock")
        return command, {"mode": "unsupported", "strict": False}

    codex_arg0_dir = codex_home / "tmp" / "arg0"
    codex_arg0_dir.mkdir(parents=True, exist_ok=True)
    command_binary = Path(command[0]).expanduser() if command else Path("codex")
    codex_binary = (
        command_binary
        if command_binary.is_file()
        else Path(shutil.which("codex", path=env.get("PATH")) or "codex")
    )
    resolved_binary = codex_binary.resolve(strict=False)
    if command and Path(command[0]).name == codex_binary.name:
        command = [str(resolved_binary), *command[1:]]
    # WSL resolves /etc/resolv.conf into /mnt/wsl. Landlock authorizes the
    # resolved inode, so /etc by itself is insufficient for DNS/token refresh.
    resolved_system_network_files = [
        path.resolve(strict=False)
        for path in (
            Path("/etc/resolv.conf"),
            Path("/etc/hosts"),
            Path("/etc/nsswitch.conf"),
            Path("/etc/gai.conf"),
        )
        if path.exists()
    ]
    declared_read_scope = _declared_read_scope_paths(env, cwd)
    read_only = _existing_paths(
        [
            Path("/usr"),
            Path("/bin"),
            Path("/sbin"),
            Path("/lib"),
            Path("/lib64"),
            Path("/etc"),
            codex_binary,
            resolved_binary.parent,
            *resolved_system_network_files,
            harness_dir,
            harness_dir.parent / "AGENTS.md",
            harness_dir.parent / ".agents",
            *declared_read_scope,
        ]
    )
    read_directories = _existing_paths([harness_dir.parent])
    try:
        declared_outputs = json.loads(env.get("SOLAR_OPERATOR_ALLOWED_OUTPUTS_JSON") or "[]")
    except (TypeError, ValueError):
        declared_outputs = []
    exact_outputs = [
        Path(str(value)).expanduser()
        for value in declared_outputs
        if isinstance(value, str) and value.strip()
    ]
    read_write = _existing_paths(
        [
            cwd,
            task_dir,
            state_home,
            tmp_dir,
            Path("/dev/null"),
            Path("/dev/urandom"),
            Path("/dev/random"),
            codex_arg0_dir,
            *exact_outputs,
        ]
    )
    wrapper = Path(__file__).with_name("landlock_exec.py").resolve(strict=False)
    if not wrapper.is_file():
        raise RuntimeError(f"Landlock wrapper is missing: {wrapper}")
    drvfs = _path_filesystem_type(harness_dir) in {"9p", "v9fs"}
    wrapped = [sys.executable, str(wrapper)]
    if drvfs:
        unshare = shutil.which("unshare", path=env.get("PATH"))
        mount_wrapper = Path(__file__).with_name("mount_namespace_exec.py").resolve(strict=False)
        if not unshare or not mount_wrapper.is_file():
            raise RuntimeError("strict WSL operator scope requires unshare and mount_namespace_exec.py")
        wrapped = [
            unshare,
            "--user",
            "--map-root-user",
            "--mount",
            sys.executable,
            str(mount_wrapper),
        ]
        for path in read_write:
            if path == Path("/dev") or path.is_relative_to(Path("/dev")):
                continue
            wrapped.extend(["--read-write", str(path)])
        wrapped.extend(["--", sys.executable, str(wrapper), "--read-scope-only"])
    for path in read_directories:
        wrapped.extend(["--read-directory", str(path)])
    for path in read_only:
        wrapped.extend(["--read-only", str(path)])
    for path in read_write:
        wrapped.extend(["--read-write", str(path)])
    wrapped.extend(["--", *command])
    return wrapped, {
        "mode": "mount_namespace+landlock-read" if drvfs else "landlock",
        "strict": strict,
        "read_directories": [str(path) for path in read_directories],
        "read_only": [str(path) for path in read_only],
        "read_write": [str(path) for path in read_write],
    }


def _pm_result_ready(started_wall: float) -> bool:
    result_path = os.environ.get("PM_RESULT_PATH") or os.environ.get("RESULT_PATH")
    if not result_path:
        return False
    path = Path(result_path).expanduser()
    try:
        return path.exists() and path.stat().st_size > 0 and path.stat().st_mtime >= started_wall
    except OSError:
        return False


def _terminate_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            return


def _register_codex_process_group(pid: int) -> bool:
    """Give the run registry ownership of Codex's detached session.

    The operatord owns its outer worker, but Codex is intentionally launched
    in a separate session so task timeouts can terminate the complete CLI
    group. Register that second boundary before sending the dispatch; otherwise
    product teardown can kill the outer wrapper and orphan Codex.
    """
    harness_dir = Path(
        os.environ.get("HARNESS_DIR")
        or os.environ.get("SOLAR_HARNESS_DIR")
        or Path.home() / ".solar" / "harness"
    ).expanduser()
    lib_dir = Path(__file__).resolve().parents[1] / "lib"
    lib_text = str(lib_dir)
    if lib_text not in sys.path:
        sys.path.insert(0, lib_text)
    try:
        import run_process_registry as registry

        registry.register(
            "harness",
            "operator-task-child",
            int(pid),
            meta={
                "task_id": str(os.environ.get("TASK_ID") or ""),
                "sprint_id": str(os.environ.get("SID") or ""),
                "node_id": str(os.environ.get("NODE_ID") or ""),
                "backend": "codex",
            },
            harness_dir=harness_dir,
            signal_scope="process_group",
        )
        return True
    except Exception as exc:
        print(
            f"ERROR: unable to register Codex process group pid={pid}: {exc}",
            file=sys.stderr,
        )
        return False


def main() -> int:
    dispatch = _read_dispatch().strip()
    if not dispatch:
        print("ERROR: empty dispatch for Codex operator", file=sys.stderr)
        return 64

    task_dir = Path(os.environ.get("TASK_DIR") or ".").expanduser()
    task_dir.mkdir(parents=True, exist_ok=True)
    skill_bridge_evidence = _materialize_skill_bridge_evidence(task_dir, dispatch)
    output_file = task_dir / "codex-last-message.md"
    model = _codex_model()
    effort = os.environ.get("CODEX_REASONING_EFFORT", "medium").strip() or "medium"
    cwd = str(Path(os.environ.get("CODEX_WORKDIR") or os.environ.get("WORK_DIR") or os.getcwd()).expanduser())
    if not Path(cwd).is_dir():
        print(f"ERROR: Codex work_dir does not exist: {cwd}", file=sys.stderr)
        return 72

    codex_env = _codex_exec_env(task_dir)
    codex_binary, resolution = resolve_codex_cli(
        Path(codex_env["HARNESS_DIR"]),
        env=codex_env,
        configured_path=os.environ.get("SOLAR_CODEX_BIN", ""),
    )
    if codex_binary is None:
        print(f"ERROR: Codex CLI unavailable: {resolution}", file=sys.stderr)
        return 69
    raw_cmd = _codex_exec_command(model, effort, cwd, output_file, str(codex_binary))
    try:
        cmd, fs_scope = _filesystem_isolated_command(
            raw_cmd,
            task_dir=task_dir,
            cwd=Path(cwd),
            env=codex_env,
        )
    except RuntimeError as exc:
        print(f"ERROR: Codex operator filesystem isolation refused: {exc}", file=sys.stderr)
        return 78
    timeout_seconds = _timeout_seconds()
    pm_result_grace = float(os.environ.get("CODEX_PM_RESULT_GRACE_SECONDS", "20"))
    print(
        "codex_operator: env "
        f"cwd={shlex.quote(cwd)} "
        f"task_dir={shlex.quote(str(task_dir))} "
        f"CODEX_HOME={shlex.quote(codex_env.get('CODEX_HOME') or str(Path.home() / '.codex'))} "
        f"CODEX_SQLITE_HOME={shlex.quote(codex_env.get('CODEX_SQLITE_HOME') or '')}"
    )
    print(
        "codex_operator: filesystem_scope "
        f"mode={fs_scope.get('mode')} strict={str(bool(fs_scope.get('strict'))).lower()} "
        f"ro={len(fs_scope.get('read_only', []))} rw={len(fs_scope.get('read_write', []))}"
    )
    print("codex_operator: invoking " + " ".join(shlex.quote(part) for part in cmd[:-1]) + " <dispatch>")
    cli_log = task_dir / "codex-cli-output.log"
    started = time.monotonic()
    started_wall = time.time()
    with open(cli_log, "w", encoding="utf-8") as log_f:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            env=codex_env,
        )
        if not _register_codex_process_group(proc.pid):
            _terminate_process_group(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
                proc.wait(timeout=5)
            return 75
        try:
            assert proc.stdin is not None
            proc.stdin.write(dispatch)
            proc.stdin.close()
        except BrokenPipeError:
            pass

        pm_ready_since: float | None = None
        while True:
            if proc.poll() is not None:
                break
            elapsed = time.monotonic() - started
            if _pm_result_ready(started_wall):
                pm_ready_since = pm_ready_since or time.monotonic()
                if (time.monotonic() - pm_ready_since) >= pm_result_grace:
                    print(
                        f"codex_operator: PM result ready; terminating lingering codex exec after {pm_result_grace:.0f}s grace"
                    )
                    _terminate_process_group(proc)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except Exception:
                            proc.kill()
                        proc.wait(timeout=5)
                    _write_skill_bridge_result(task_dir, skill_bridge_evidence, 0)
                    return 0
            if timeout_seconds > 0 and elapsed >= timeout_seconds:
                _terminate_process_group(proc)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except Exception:
                        proc.kill()
                    proc.wait(timeout=5)
                combined = cli_log.read_text(encoding="utf-8", errors="replace") if cli_log.exists() else ""
                combined = "\n".join(
                    part
                    for part in [
                        combined,
                        f"ERROR: codex exec timed out after {elapsed:.1f}s",
                    ]
                    if part
                )
                print(combined, file=sys.stderr)
                _write_pm_result(task_dir, output_file, combined, 124)
                _write_skill_bridge_result(task_dir, skill_bridge_evidence, 124)
                return 124
            time.sleep(1)

    combined = cli_log.read_text(encoding="utf-8", errors="replace") if cli_log.exists() else ""
    if combined:
        print(combined, end="" if combined.endswith("\n") else "\n")
    if proc.returncode == 0:
        _write_pm_result(task_dir, output_file, combined, int(proc.returncode))
    exit_code = int(proc.returncode or 0)
    _write_skill_bridge_result(task_dir, skill_bridge_evidence, exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
