from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUSES = {
    "PASS",
    "PASS_WITH_KNOWN_LIMITATIONS",
    "FAIL",
    "ENVIRONMENT_BLOCKED",
    "NOT_AVAILABLE",
    "NOT_TESTED",
}

WORKER_BATCH_ID = os.environ.get("PHASE22_JOURNEY_BATCH_ID", "journey-code-repair-002")
WORKER_RESULT_DIR = Path(".codex-tmp") / "phase22-worker-results" / WORKER_BATCH_ID

PYTEST_OUTCOME_BY_STATUS = {
    "PASS": "passed",
    "PASS_WITH_KNOWN_LIMITATIONS": "passed",
    "FAIL": "failed",
    "ENVIRONMENT_BLOCKED": "skipped",
    "NOT_AVAILABLE": "skipped",
    "NOT_TESTED": "not_run",
}


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


JOURNEYS: dict[str, dict[str, Any]] = {
    "P22-J01": {
        "name": "Install from zero and inspect running status",
        "selector": "p22_j01",
        "live": False,
    },
    "P22-J02": {
        "name": "Use Solar to fix a small code defect",
        "selector": "p22_j02",
        "live": True,
    },
    "P22-J03": {
        "name": "Run the official platform workflow benchmark",
        "selector": "p22_j03",
        "live": False,
    },
    "P22-J04": {
        "name": "Ingest and re-ingest a local paper",
        "selector": "p22_j04",
        "live": False,
    },
    "P22-J05": {
        "name": "Discover literature around a topic and anchors",
        "selector": "p22_j05",
        "live": True,
    },
    "P22-J06": {
        "name": "Generate and screen research ideas from evidence",
        "selector": "p22_j06",
        "live": False,
    },
    "P22-J07": {
        "name": "Design and run a small local experiment",
        "selector": "p22_j07",
        "live": False,
    },
    "P22-J08": {
        "name": "Verify one supported and one overbroad claim",
        "selector": "p22_j08",
        "live": False,
    },
    "P22-J09": {
        "name": "Generate and review a deliverable research report",
        "selector": "p22_j09",
        "live": False,
    },
    "P22-J10": {
        "name": "Backup, restore, and uninstall inside a sandbox",
        "selector": "p22_j10",
        "live": False,
    },
}


ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")

SECRET_PATTERNS = [
    re.compile(r"(?i)(OPENAI_API_KEY|ANTHROPIC_API_KEY|OPENROUTER_API_KEY|CLAUDE_CODE_OAUTH_TOKEN)=\S+"),
    re.compile(r"(?i)(sk-[A-Za-z0-9_-]{12,})"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._-]+"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def redact(text: str | None) -> str:
    safe = ANSI_PATTERN.sub("", text or "")
    for pattern in SECRET_PATTERNS:
        safe = pattern.sub(lambda m: f"{m.group(1) if m.groups() else ''}<redacted>", safe)
    return safe


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_head(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode == 0:
        return proc.stdout.strip()

    git_file = repo_root / ".git"
    if os.name != "nt" and git_file.is_file():
        pointer = git_file.read_text(encoding="utf-8", errors="replace").strip()
        if pointer.lower().startswith("gitdir:"):
            raw_git_dir = pointer.split(":", 1)[1].strip().replace("\\", "/")
            drive_match = re.match(r"^([A-Za-z]):/(.*)$", raw_git_dir)
            git_dir = (
                Path(f"/mnt/{drive_match.group(1).lower()}/{drive_match.group(2)}")
                if drive_match
                else (repo_root / raw_git_dir).resolve()
            )
            fallback = subprocess.run(
                ["git", f"--git-dir={git_dir}", f"--work-tree={repo_root}", "rev-parse", "HEAD"],
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if fallback.returncode == 0:
                return fallback.stdout.strip()
            proc = fallback
    return f"unavailable: {redact(proc.stderr.strip())}"


def command_exists(name: str) -> bool:
    from shutil import which

    return which(name) is not None


def relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


@dataclass
class CommandRecord:
    label: str
    argv: list[str]
    cwd: str
    exit_code: int | None
    timed_out: bool
    duration_seconds: float
    stdout_path: str
    stderr_path: str


@dataclass
class JourneyRecorder:
    repo_root: Path
    journey_id: str
    run_id: str | None = None
    started_at: str = field(default_factory=utc_now)
    commands: list[CommandRecord] = field(default_factory=list)
    assertions: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    observed_l2: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.journey_id not in JOURNEYS:
            raise ValueError(f"unknown journey id: {self.journey_id}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = self.run_id or f"{self.journey_id.lower().replace('-', '')}-{stamp}-{os.getpid()}"
        self.run_dir = self.repo_root / "outputs" / "phase22-real-journeys" / self.run_id
        self.stdout_dir = self.run_dir / "stdout"
        self.stderr_dir = self.run_dir / "stderr"
        self.artifact_dir = self.run_dir / "artifacts"
        self.stdout_dir.mkdir(parents=True, exist_ok=True)
        self.stderr_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    @property
    def selector(self) -> str:
        return JOURNEYS[self.journey_id]["selector"]

    @property
    def name(self) -> str:
        return JOURNEYS[self.journey_id]["name"]

    def add_assertion(self, name: str, passed: bool, detail: Any = None) -> None:
        self.assertions.append({"name": name, "passed": bool(passed), "detail": json_safe(detail)})

    def add_l2(self, category: str, feature: str, observation: str, evidence_path: Path, supported: bool | str) -> None:
        self.observed_l2.append(
            {
                "category": category,
                "level_2_feature": feature,
                "observation": observation,
                "evidence_path": relative_or_absolute(evidence_path, self.run_dir),
                "supported": supported,
            }
        )

    def _stable_artifact_path(self, path: Path, artifact_type: str) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.run_dir.resolve())
            return resolved
        except ValueError:
            pass
        safe_type = re.sub(r"[^A-Za-z0-9_.-]+", "-", artifact_type).strip("-") or "artifact"
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", resolved.name).strip("-") or "artifact"
        target = self.artifact_dir / f"{len(self.artifacts) + 1:02d}-{safe_type}-{safe_name}"
        if resolved.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(resolved, target)
            return target.resolve()
        return resolved

    def add_artifact(self, path: Path, artifact_type: str, description: str = "", *, required: bool = True) -> None:
        path = path.resolve()
        stable_path = self._stable_artifact_path(path, artifact_type) if path.exists() else path
        exists = path.exists()
        is_file = stable_path.is_file()
        is_dir = stable_path.is_dir()
        try:
            stable_path.relative_to(self.run_dir.resolve())
            inside_run_dir = True
        except ValueError:
            inside_run_dir = False
        if not exists:
            durability_status = "missing_required" if required else "not_applicable_optional_missing"
        elif is_dir:
            durability_status = "not_applicable_directory_reference"
        elif inside_run_dir:
            durability_status = "durable"
        else:
            durability_status = "external_file_not_copied"
        entry: dict[str, Any] = {
            "type": artifact_type,
            "path": relative_or_absolute(stable_path, self.run_dir),
            "source_path": str(path),
            "description": description,
            "exists": exists,
            "required": bool(required),
            "stable_copy": stable_path != path,
            "durability_status": durability_status,
        }
        if is_file:
            entry["bytes"] = stable_path.stat().st_size
            entry["sha256"] = sha256(stable_path)
        self.artifacts.append(entry)

    def run(
        self,
        label: str,
        argv: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> subprocess.CompletedProcess[str]:
        started = time.monotonic()
        cwd = cwd or self.repo_root
        stdout_path = self.stdout_dir / f"{len(self.commands) + 1:02d}-{label}.txt"
        stderr_path = self.stderr_dir / f"{len(self.commands) + 1:02d}-{label}.txt"
        timed_out = False
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            proc = subprocess.CompletedProcess(
                argv,
                124,
                stdout=stdout,
                stderr=stderr or f"timed out after {timeout}s",
            )
        duration = time.monotonic() - started
        stdout_path.write_text(redact(proc.stdout), encoding="utf-8", errors="replace")
        stderr_path.write_text(redact(proc.stderr), encoding="utf-8", errors="replace")
        self.commands.append(
            CommandRecord(
                label=label,
                argv=[redact(str(part)) for part in argv],
                cwd=str(cwd),
                exit_code=int(proc.returncode) if proc.returncode is not None else None,
                timed_out=timed_out,
                duration_seconds=round(duration, 3),
                stdout_path=relative_or_absolute(stdout_path, self.run_dir),
                stderr_path=relative_or_absolute(stderr_path, self.run_dir),
            )
        )
        return proc

    def _artifact_durability_summary(self) -> dict[str, Any]:
        required = [item for item in self.artifacts if item.get("required", True)]
        missing_required = [
            item["type"]
            for item in required
            if not item.get("exists") or item.get("durability_status") == "missing_required"
        ]
        non_durable = [
            item["type"]
            for item in required
            if item.get("exists")
            and item.get("durability_status") not in {"durable", "not_applicable_directory_reference"}
        ]
        if not required:
            status = "not_applicable"
        elif missing_required or non_durable:
            status = "incomplete"
        else:
            status = "complete"
        return {
            "status": status,
            "missing_required_artifacts": missing_required,
            "non_durable_required_artifacts": non_durable,
        }

    def finalize(self, status: str, *, limitations: list[str] | None = None, blockers: list[str] | None = None) -> Path:
        if status not in STATUSES:
            raise ValueError(f"invalid journey status: {status}")
        if limitations:
            self.limitations.extend(limitations)
        if blockers:
            self.blockers.extend(blockers)
        finished_at = utc_now()
        started = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        durability = self._artifact_durability_summary()
        result = {
            "schema_version": "phase22.journey_result.v1",
            "worker_batch_id": WORKER_BATCH_ID,
            "journey_id": self.journey_id,
            "name": self.name,
            "execution_selector": self.selector,
            "started_at": self.started_at,
            "finished_at": finished_at,
            "duration_seconds": round((finished - started).total_seconds(), 3),
            "repo_head": repo_head(self.repo_root),
            "runtime": {
                "os": platform.platform(),
                "system": platform.system(),
                "python": sys.version,
                "python_executable": sys.executable,
                "bash": "present" if command_exists("bash") else "missing",
                "tmux": "present" if command_exists("tmux") else "missing",
            },
            "sandbox_paths": {
                "run_dir": str(self.run_dir),
            },
            "commands": [record.__dict__ for record in self.commands],
            "artifacts": self.artifacts,
            "assertions": self.assertions,
            "observed_l2": self.observed_l2,
            "status": status,
            "pytest_outcome": PYTEST_OUTCOME_BY_STATUS[status],
            "artifact_durability": durability,
            "durable_artifacts_saved": (
                "N/A" if durability["status"] == "not_applicable" else durability["status"] == "complete"
            ),
            "limitations": self.limitations,
            "blockers": self.blockers,
            "rerun_command": (
                f".venv\\Scripts\\python.exe -m pytest "
                f"tests/journeys/phase22/code -k {self.selector} -vv"
            ),
        }
        (self.run_dir / "journey-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.run_dir / "commands.json").write_text(
            json.dumps(result["commands"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.run_dir / "artifacts.json").write_text(
            json.dumps(self.artifacts, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.run_dir / "assertions.json").write_text(
            json.dumps(self.assertions, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.run_dir / "limitations.md").write_text(
            "\n".join(f"- {item}" for item in [*self.limitations, *self.blockers]) + "\n",
            encoding="utf-8",
        )
        self._update_worker_result()
        result_path = self.run_dir / "journey-result.json"
        if status == "FAIL":
            import pytest

            pytest.fail(f"{self.journey_id} product status FAIL; evidence: {result_path}", pytrace=False)
        if status in {"ENVIRONMENT_BLOCKED", "NOT_AVAILABLE", "NOT_TESTED"}:
            import pytest

            pytest.skip(f"{self.journey_id} product status {status}; evidence: {result_path}")
        return result_path

    def _update_worker_result(self) -> None:
        result_dir = self.repo_root / WORKER_RESULT_DIR
        result_dir.mkdir(parents=True, exist_ok=True)
        latest: dict[str, dict[str, Any]] = {}
        outputs_root = self.repo_root / "outputs" / "phase22-real-journeys"
        if outputs_root.exists():
            for path in outputs_root.glob("*/journey-result.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                jid = payload.get("journey_id")
                if jid not in JOURNEYS or payload.get("worker_batch_id") != WORKER_BATCH_ID:
                    continue
                prev = latest.get(jid)
                if prev is None or str(payload.get("finished_at", "")) > str(prev.get("finished_at", "")):
                    latest[jid] = payload
        journeys = []
        product_status_counts = {status: 0 for status in STATUSES}
        pytest_outcome_counts: dict[str, int] = {"passed": 0, "failed": 0, "skipped": 0, "not_run": 0}
        for jid, spec in JOURNEYS.items():
            payload = latest.get(jid)
            if payload:
                status = payload.get("status", "NOT_TESTED")
                pytest_outcome = payload.get("pytest_outcome", PYTEST_OUTCOME_BY_STATUS.get(status, "not_run"))
                evidence_dir = str((outputs_root / Path(payload["sandbox_paths"]["run_dir"]).name).resolve())
                finished_at = payload.get("finished_at")
                blockers = payload.get("blockers", [])
                limitations = payload.get("limitations", [])
                commands = payload.get("commands", [])
                durable_artifacts_saved = payload.get("durable_artifacts_saved", False)
                exit_code = commands[-1].get("exit_code") if commands else None
                last_command_label = commands[-1].get("label") if commands else None
                duration_seconds = payload.get("duration_seconds")
            else:
                status = "NOT_TESTED"
                pytest_outcome = "not_run"
                evidence_dir = ""
                finished_at = None
                blockers = (
                    ["not run in this repair batch; live/provider execution requires explicit authorization"]
                    if spec.get("live")
                    else ["not run in this repair batch"]
                )
                limitations = []
                commands = []
                durable_artifacts_saved = False
                exit_code = None
                last_command_label = None
                duration_seconds = None
            product_status_counts[status] = product_status_counts.get(status, 0) + 1
            pytest_outcome_counts[pytest_outcome] = pytest_outcome_counts.get(pytest_outcome, 0) + 1
            journeys.append(
                {
                    "journey_id": jid,
                    "name": spec["name"],
                    "selector": spec["selector"],
                    "product_status": status,
                    "pytest_outcome": pytest_outcome,
                    "evidence_dir": evidence_dir,
                    "finished_at": finished_at,
                    "exit_code": exit_code,
                    "last_product_command_exit_code": exit_code,
                    "last_product_command_label": last_command_label,
                    "duration_seconds": duration_seconds,
                    "durable_artifacts_saved": durable_artifacts_saved,
                    "blockers": blockers,
                    "limitations": limitations,
                    "command_count": len(commands),
                    "live_not_run_reason": (
                        "No explicit live/provider authorization was supplied for this repair run."
                        if spec.get("live") and pytest_outcome == "not_run"
                        else ""
                    ),
                }
            )
        worker = {
            "schema_version": "phase22.worker_result.v2",
            "batch_id": WORKER_BATCH_ID,
            "updated_at": utc_now(),
            "repo_head": repo_head(self.repo_root),
            "journeys": journeys,
            "product_status_counts": product_status_counts,
            "pytest_outcome_counts": pytest_outcome_counts,
            "selectors": [spec["selector"] for spec in JOURNEYS.values()],
            "modified_files": [],
            "executed_commands": [],
            "authorization": {
                "live_provider_authorized": os.environ.get("PHASE22_ENABLE_LIVE_JOURNEYS") == "1",
                "network_fetch_authorized": os.environ.get("SOLAR_AUTOSCI_ALLOW_NETWORK") == "1",
                "credentials_recorded": False,
            },
            "handoffs": self._handoff_readiness(),
            "integration_requests": [],
            "non_live_command": (
                ".venv\\Scripts\\python.exe -m pytest tests/journeys/phase22/code "
                "-m \"not live_provider\" -vv --basetemp .codex-tmp/pytest-phase22-journeys-repair002 "
                "-o cache_dir=.codex-tmp/pytest-cache-phase22-journeys-repair002"
            ),
            "live_command": (
                "$env:PHASE22_ENABLE_LIVE_JOURNEYS='1'; "
                ".venv\\Scripts\\python.exe -m pytest tests/journeys/phase22/code "
                "-m live_provider -vv --basetemp .codex-tmp/pytest-phase22-journeys-live"
            ),
        }
        (result_dir / "result.json").write_text(
            json.dumps(worker, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _handoff_readiness(self) -> dict[str, dict[str, Any]]:
        handoffs: dict[str, dict[str, Any]] = {}
        for agent in ("B", "C", "D"):
            rel_path = (
                Path(".codex-tmp")
                / "phase22-worker-results"
                / f"{WORKER_BATCH_ID}-{agent}"
                / "result.json"
            )
            abs_path = self.repo_root / rel_path
            payload: dict[str, Any] = {}
            if abs_path.exists():
                try:
                    payload = json.loads(abs_path.read_text(encoding="utf-8-sig"))
                except Exception as exc:
                    payload = {"_error": redact(str(exc))}
            handoffs[agent] = {
                "path": str(rel_path).replace("\\", "/"),
                "exists": abs_path.exists(),
                "ready_for_integration": bool(payload.get("ready_for_integration")),
                "batch_id": payload.get("batch_id", ""),
                "journeys": payload.get("journeys", []),
                "integration_requests": payload.get("integration_requests", []),
                "error": payload.get("_error", ""),
            }
        return handoffs
