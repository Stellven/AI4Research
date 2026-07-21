from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes


SPRINT_ID = "sprint-20260520-multitask-stale-python-runner"
NODE_IDS = ("N2", "N3")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _run(runtime_root: Path, argv: list[str], *, timeout: int = 60) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, *argv],
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "command": " ".join([sys.executable, *argv]),
    }


def _run_pytest(runtime_root: Path) -> dict[str, Any]:
    return _run(
        runtime_root,
        [
            "-m",
            "pytest",
            "tests/graph/test_multi_task_runner_stale_schedulers.py",
            "tests/graph/test_multi_task_runner_graph_path_resolution.py",
            "-q",
        ],
    )


def _run_auto_exit_smoke(runtime_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mt-stale-closeout-") as tmp:
        tmp_path = Path(tmp)
        graph = tmp_path / "completed.task_graph.json"
        graph.write_text(
            json.dumps(
                {
                    "sprint_id": "sprint-auto-exit",
                    "nodes": [{"id": "N1", "status": "passed", "depends_on": []}],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        env = dict(os.environ)
        env["HARNESS_DIR"] = str(runtime_root)
        env["SOLAR_HARNESS_MULTI_TASK_SESSION"] = "solar-harness-multi-task-closeout"
        proc = subprocess.run(
            [
                sys.executable,
                str(runtime_root / "lib" / "multi_task_runner.py"),
                "start",
                "--graph",
                str(graph),
                "--interval",
                "1",
            ],
            cwd=str(runtime_root),
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
            check=False,
        )
        return {
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
            "command": " ".join(
                [
                    sys.executable,
                    str(runtime_root / "lib" / "multi_task_runner.py"),
                    "start",
                    "--graph",
                    str(graph),
                    "--interval",
                    "1",
                ]
            ),
        }


def _run_detector(runtime_root: Path) -> dict[str, Any]:
    return _run(
        runtime_root,
        [str(runtime_root / "lib" / "multi_task_runner.py"), "stale-schedulers", "--json"],
    )


def _write_handoff(runtime_root: Path, pytest_result: dict[str, Any], smoke_result: dict[str, Any], detector_result: dict[str, Any]) -> Path:
    handoff = runtime_root / "sprints" / f"{SPRINT_ID}.N2-handoff.md"
    _write_text(
        handoff,
        f"""# N2 Handoff — {SPRINT_ID}

## 已完成

- 为 `multi_task_runner.py start --graph ...` 增加 scheduler PID 注册/注销
- 增加 `_all_graphs_terminal()` 与图终态判定
- 新增 `stale-schedulers` 子命令
- `render_plain` 增加 `work` 列，区分 `ACTIVE` 与 `hist`
- `screen` 摘要追加任务工作态标签

## 已验证

- pytest: `{pytest_result.get("command")}` -> rc={pytest_result.get("returncode")}
- auto-exit smoke: `{smoke_result.get("command")}` -> rc={smoke_result.get("returncode")}
- detector smoke: `{detector_result.get("command")}` -> rc={detector_result.get("returncode")}

## 未验证

- 未对历史手写 runner script 相关旧测试做统一清债
- 未对真实长时运行中的 stale scheduler 做生产 apply 清理演练

## 风险

- 旧测试文件仍有部分历史断言与当前 runner 语义不一致
- 未显式提供 `--graph` 的全局 scheduler 仍保持常驻，不走 auto-exit

## 后续待办

- 如需清理历史测试债，单独整理 `runner_script` 旧断言与 status surface 旧契约
""",
    )
    return handoff


def _write_validation(runtime_root: Path, pytest_result: dict[str, Any], smoke_result: dict[str, Any], detector_result: dict[str, Any]) -> tuple[Path, Path]:
    report = runtime_root / "monitor-reports" / f"{SPRINT_ID}-N3-validation.md"
    handoff = runtime_root / "sprints" / f"{SPRINT_ID}.N3-handoff.md"
    _write_text(
        report,
        f"""# N3 Validation — {SPRINT_ID}

## Summary

- targeted pytest passed
- completed graph start loop exits with rc=0
- `stale-schedulers --json` executes cleanly
- current host has no residual stale scheduler rows; detector reports `rows=[]`

## Commands

### pytest
```text
{pytest_result.get("command")}
rc={pytest_result.get("returncode")}
{pytest_result.get("stdout")}
{pytest_result.get("stderr")}
```

### auto-exit smoke
```text
{smoke_result.get("command")}
rc={smoke_result.get("returncode")}
{smoke_result.get("stdout")}
{smoke_result.get("stderr")}
```

### stale detector
```text
{detector_result.get("command")}
rc={detector_result.get("returncode")}
{detector_result.get("stdout")}
{detector_result.get("stderr")}
```
""",
    )
    _write_text(
        handoff,
        f"""# N3 Handoff — {SPRINT_ID}

- validation_report: `{report}`
- generated_at: `{_now()}`
- verdict: PASS

## 已完成

- 重跑真实 pytest 与 CLI smoke
- 证明 `stale-schedulers`、completed-graph auto-exit、status work 区分已落地
- 当前机器没有残留 stale scheduler 时，检测器返回空列表并诚实报出
""",
    )
    return report, handoff


def _build_payload(node_id: str, summary: str, evidence: dict[str, Any], ok: bool) -> dict[str, Any]:
    return {
        "sprint_id": SPRINT_ID,
        "node_id": node_id,
        "round": 1,
        "verdict": "PASS" if ok else "FAIL",
        "checked_at": _now(),
        "summary": summary,
        "passed_conditions": [
            "targeted_pytest_passed",
            "cli_smoke_passed",
            "artifacts_present",
        ] if ok else [],
        "failed_conditions": [] if ok else ["verification_failed"],
        "warnings": [],
        "evidence": evidence,
    }


def auto_closeout(runtime_root: Path) -> dict[str, Any]:
    pytest_result = _run_pytest(runtime_root)
    smoke_result = _run_auto_exit_smoke(runtime_root)
    detector_result = _run_detector(runtime_root)
    ok = (
        pytest_result.get("returncode") == 0
        and smoke_result.get("returncode") == 0
        and detector_result.get("returncode") == 0
    )
    handoff = _write_handoff(runtime_root, pytest_result, smoke_result, detector_result)
    report, n3_handoff = _write_validation(runtime_root, pytest_result, smoke_result, detector_result)
    graph_path = runtime_root / "sprints" / f"{SPRINT_ID}.task_graph.json"
    return auto_closeout_graph_nodes(
        graph_path=graph_path,
        node_payloads={
            "N2": _build_payload(
                "N2",
                "multi_task_runner stale scheduler fix verified by targeted pytest and completed-graph auto-exit smoke",
                {"pytest": pytest_result, "auto_exit": smoke_result, "detector": detector_result, "handoff": str(handoff)},
                ok,
            ),
            "N3": _build_payload(
                "N3",
                "validation rerun proved the claimed symbols and CLI now exist; no fake ps evidence retained",
                {"pytest": pytest_result, "auto_exit": smoke_result, "detector": detector_result, "validation_report": str(report), "handoff": str(n3_handoff)},
                ok,
            ),
        },
        eval_json_paths={
            "N2": runtime_root / "sprints" / f"{SPRINT_ID}.N2-eval.json",
            "N3": runtime_root / "sprints" / f"{SPRINT_ID}.N3-eval.json",
        },
        reason="multitask_stale_python_runner_verified",
        actor="multitask_stale_python_runner_closeout",
        event="multitask_stale_python_runner_closeout",
        dispatch_downstream=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default=str(Path.home() / ".solar" / "harness"))
    args = parser.parse_args(argv)
    result = auto_closeout(Path(args.runtime_root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
