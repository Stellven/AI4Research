"""Harbor CLI adapter for Terminal-Bench 2.0.

S03 N2: Pure-function Harbor argv builder + environment probes.
Never executes Harbor/Docker in this module — only detects availability
and constructs command arguments for downstream execution.

Functions:
    detect() — check if harbor/uvx binary is on PATH
    docker_available() — check if Docker daemon is responding
    build_argv(req) — construct Harbor CLI argv list
    api_key_env_for(agent) — map agent name to API key env var name
    probe_api_key(agent) — check env var presence (never reads value)
    probe_dataset(dataset) — HEAD-check Harbor registry for dataset
"""

from __future__ import annotations

import os
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

from .schemas import DEFAULT_DATASET, BenchmarkRunRequest

_AGENT_KEY_MAP: dict[str, str] = {
    "claude-code": "ANTHROPIC_API_KEY",
    "deepagents-cli": "ANTHROPIC_API_KEY",
    "codex": "OPENAI_API_KEY",
    "openai-cli": "OPENAI_API_KEY",
}

_REGISTRY_BASE_URL = "https://www.harborframework.com/registry"
_DEFAULT_HARBOR_SOURCE = (
    Path.home() / ".solar" / "harness" / "vendor" / "harbor-framework" / "harbor"
)
_HOST_CLAUDE_IMPORT_PATH = "harbor.agents.installed.host_claude_code:HostClaudeCode"
_SOLAR_HARNESS_IMPORT_PATH = "harbor.agents.installed.solar_harness_agent:SolarHarnessAgent"


def _harbor_source_dir() -> Path | None:
    configured = os.environ.get("SOLAR_HARBOR_SOURCE", "").strip()
    path = Path(configured).expanduser() if configured else _DEFAULT_HARBOR_SOURCE
    return path if (path / "pyproject.toml").is_file() else None


def _host_claude_agent_source_path() -> Path:
    return Path(__file__).resolve().parent / "harbor_agents" / "host_claude_code.py"


def _solar_harness_agent_source_path() -> Path:
    return Path(__file__).resolve().parent / "harbor_agents" / "solar_harness_agent.py"


def _install_harbor_agent(source: Path, target_name: str) -> tuple[bool, str]:
    source_dir = _harbor_source_dir()
    if source_dir is None:
        return False, "harbor_source_missing"
    if not source.is_file():
        return False, f"source_missing:{source}"
    target = source_dir / "src" / "harbor" / "agents" / "installed" / target_name
    try:
        content = source.read_text(encoding="utf-8")
        if target.is_file() and target.read_text(encoding="utf-8") == content:
            return True, str(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True, str(target)
    except OSError as exc:
        return False, f"install_failed:{exc}"


def ensure_host_claude_agent_installed() -> tuple[bool, str]:
    """Install Solar's host Claude Harbor agent into the active Harbor source.

    Harbor loads custom agents from its own Python environment when run with
    `uv run --directory <harbor-source> harbor`. Copying this small adapter into
    the vendored source makes the subscription-based host Claude path
    reproducible after runtime syncs.
    """
    return _install_harbor_agent(
        _host_claude_agent_source_path(),
        "host_claude_code.py",
    )


def ensure_solar_harness_agent_installed() -> tuple[bool, str]:
    """Install Solar's Harbor agent into the active Harbor source."""
    return _install_harbor_agent(
        _solar_harness_agent_source_path(),
        "solar_harness_agent.py",
    )


def detect() -> tuple[bool, str]:
    """Check if Harbor CLI is available on PATH.

    Returns:
        (available, kind) where kind is 'source', 'binary', 'uvx', or 'missing'.
    """
    if _harbor_source_dir() is not None and shutil.which("uv"):
        return True, "source"
    if shutil.which("harbor"):
        return True, "binary"
    if shutil.which("uvx"):
        return True, "uvx"
    return False, "missing"


def docker_available() -> bool:
    """Check if Docker daemon is reachable.

    Uses `docker info --format {{.ServerVersion}}` with 2s timeout.
    Returns False on any error or non-zero exit.
    """
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def build_argv(req: BenchmarkRunRequest) -> list[str]:
    """Construct the Harbor CLI argv list for a benchmark run.

    This is a pure function — it never executes the command.
    The returned argv starts with the patched local Harbor source runner,
    'harbor', or 'uvx harbor' depending on which is available; falls back
    to 'harbor' if detect fails.

    Per S02 §5.1, the command shape is:
        harbor run --dataset terminal-bench@2.0 --agent <agent>
            --model <model> --n-concurrent <n>
            [--env docker|...] [task...]
    """
    _, kind = detect()
    if kind == "source":
        source_dir = _harbor_source_dir()
        if source_dir is None:
            argv = ["harbor"]
        else:
            argv = ["uv", "run", "--directory", str(source_dir), "harbor"]
    elif kind == "binary":
        argv = ["harbor"]
    elif kind == "uvx":
        argv = ["uvx", "harbor"]
    else:
        argv = ["harbor"]

    argv.append("run")
    argv.extend(["--dataset", req.adapter_id or DEFAULT_DATASET])
    if req.agent == "host-claude-code":
        argv.extend(["--agent-import-path", _HOST_CLAUDE_IMPORT_PATH])
    elif req.agent == "solar-harness-agent":
        argv.extend(["--agent-import-path", _SOLAR_HARNESS_IMPORT_PATH])
    else:
        argv.extend(["--agent", req.agent])
    argv.extend(["--model", req.model])
    argv.extend(["--n-concurrent", str(req.n_concurrent)])

    if req.env:
        argv.extend(["--env", req.env])

    if req.run_dir:
        argv.extend(["--jobs-dir", req.run_dir])

    argv.extend(agent_env_args(req.agent))

    if req.tasks:
        for task in req.tasks:
            argv.extend(["--include-task-name", task])

    return argv


def api_key_env_for(agent: str) -> Optional[str]:
    """Return the env var name holding the API key for the given agent.

    Returns None for unknown agents. Never reads or returns the value.
    """
    return _AGENT_KEY_MAP.get(agent)


def probe_api_key(agent: str) -> bool:
    """Check whether the API key env var for the agent is present.

    Uses os.environ.get(name) is not None — never reads or logs the value.
    """
    env_name = api_key_env_for(agent)
    if env_name is None:
        return False
    return os.environ.get(env_name) is not None


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _codex_auth_json_path() -> Path | None:
    explicit = os.environ.get("CODEX_AUTH_JSON_PATH", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None
    default = Path.home() / ".codex" / "auth.json"
    return default if default.is_file() else None


def _claude_config_json_path() -> Path | None:
    explicit = os.environ.get("CLAUDE_CODE_CONFIG_JSON_PATH", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None
    default = Path.home() / ".claude.json"
    return default if default.is_file() else None


def agent_auth_status(agent: str) -> tuple[str, str]:
    """Return (status, evidence) without exposing secret values.

    status is one of:
      - env_api_key
      - cli_session_auth
      - cli_oauth_token
      - builtin
      - missing
    """
    if agent == "oracle":
        return "builtin", "harbor_oracle"
    if agent == "solar-harness-agent":
        return "cli_session_auth", "solar_harness_cli"
    if agent == "host-claude-code":
        return "cli_session_auth", "host_claude_cli"

    if probe_api_key(agent):
        key_name = api_key_env_for(agent) or "api_key"
        return "env_api_key", key_name

    if agent == "codex" or agent == "openai-cli":
        if _codex_auth_json_path() is not None or _truthy_env("CODEX_FORCE_AUTH_JSON"):
            return "cli_session_auth", "codex_auth_json"

    if agent == "claude-code":
        if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            return "cli_oauth_token", "CLAUDE_CODE_OAUTH_TOKEN"
        if _claude_config_json_path() is not None:
            return "cli_session_auth", "claude_config_json"

    return "missing", api_key_env_for(agent) or "unknown_auth"


def agent_env_args(agent: str) -> list[str]:
    """Return Harbor --agent-env args needed to reuse local CLI auth.

    Values are host paths or boolean markers, never secret contents.
    """
    args: list[str] = []
    if (agent == "codex" or agent == "openai-cli") and not probe_api_key(agent):
        auth_path = _codex_auth_json_path()
        if auth_path is not None:
            args.extend(["--ae", f"CODEX_AUTH_JSON_PATH={auth_path}"])
    if agent == "claude-code" and not probe_api_key(agent):
        auth_path = _claude_config_json_path()
        if auth_path is not None:
            args.extend(["--ae", f"CLAUDE_CODE_CONFIG_JSON_PATH={auth_path}"])
    return args


def probe_dataset(dataset: str, timeout: float = 5.0) -> bool:
    """Probe the Harbor registry to see if a dataset is listed.

    Uses urllib HEAD-style request with short timeout.
    Returns False on any network error.
    """
    source_dir = _harbor_source_dir()
    if source_dir is not None:
        registry_path = source_dir / "registry.json"
        if registry_path.is_file():
            try:
                with registry_path.open(encoding="utf-8") as fh:
                    registry = json.load(fh)
                name, version = dataset.split("@", 1) if "@" in dataset else (dataset, "")
                for item in registry:
                    if item.get("name") == name and (not version or item.get("version") == version):
                        return True
            except (OSError, json.JSONDecodeError, ValueError):
                pass

    registry_slug = dataset.replace("@", "/")
    url = f"{_REGISTRY_BASE_URL}/{registry_slug}/"
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 400
    except Exception:
        return False


def list_dataset_tasks(dataset: str) -> list[str]:
    """Return task names for a dataset from the local Harbor registry when present."""
    source_dir = _harbor_source_dir()
    if source_dir is None:
        return []
    registry_path = source_dir / "registry.json"
    if not registry_path.is_file():
        return []
    try:
        with registry_path.open(encoding="utf-8") as fh:
            registry = json.load(fh)
        name, version = dataset.split("@", 1) if "@" in dataset else (dataset, "")
        for item in registry:
            if item.get("name") != name:
                continue
            if version and item.get("version") != version:
                continue
            tasks = item.get("tasks") or []
            names = [task.get("name") for task in tasks if isinstance(task, dict)]
            return sorted(name for name in names if isinstance(name, str) and name)
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    return []
