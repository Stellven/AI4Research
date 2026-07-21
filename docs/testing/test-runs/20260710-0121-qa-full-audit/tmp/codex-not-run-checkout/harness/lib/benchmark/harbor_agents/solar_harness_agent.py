import asyncio
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class SolarHarnessAgent(BaseAgent):
    """Run a Terminal-Bench task through the local Solar-Harness benchmark solver."""

    SUPPORTS_WINDOWS: bool = False

    @staticmethod
    def name() -> str:
        return "solar-harness-agent"

    def version(self) -> str:
        binary = _solar_harness_binary()
        try:
            result = subprocess.run(
                [binary, "--help"],
                text=True,
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                return "solar-harness"
        except Exception:
            pass
        return "host"

    async def setup(self, environment: BaseEnvironment) -> None:
        return

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        command_path = self.logs_dir / "solar-harness-agent.command.txt"
        stdout_path = self.logs_dir / "solar-harness-agent.stdout.txt"
        stderr_path = self.logs_dir / "solar-harness-agent.stderr.txt"
        postrun_path = self.logs_dir / "solar-harness-agent.container-postrun.txt"
        sync_check_path = self.logs_dir / "solar-harness-agent.sync-check.txt"

        with tempfile.TemporaryDirectory(prefix="harbor-solar-harness-") as tmp:
            workspace = Path(tmp) / "app"
            workspace.mkdir(parents=True, exist_ok=True)
            await environment.download_dir("/app", workspace)

            instruction_path = self.logs_dir / "solar-harness-agent.instruction.txt"
            instruction_path.write_text(instruction, encoding="utf-8")
            solver_logs = self.logs_dir / "solver"
            solver_logs.mkdir(parents=True, exist_ok=True)

            cmd = [
                _solar_harness_binary(),
                "benchmark",
                "solve-terminal-task",
                "--workspace",
                str(workspace),
                "--instruction-file",
                str(instruction_path),
                "--backend",
                os.environ.get("SOLAR_HARNESS_BENCH_BACKEND", "auto"),
                "--model",
                self.model_name or "gpt-5.4",
                "--logs-dir",
                str(solver_logs),
            ]
            command_path.write_text(
                " ".join(shlex.quote(part) for part in cmd),
                encoding="utf-8",
            )

            timeout = int(os.environ.get("SOLAR_HARNESS_AGENT_TIMEOUT_SEC", "900"))
            result = await _run_command(cmd, workspace, timeout)
            stdout_path.write_text(result.stdout or "", encoding="utf-8")
            stderr_path.write_text(result.stderr or "", encoding="utf-8")

            if result.returncode != 0:
                raise RuntimeError(
                    f"solar-harness solver failed with exit {result.returncode}"
                )

            await environment.upload_dir(workspace, "/app")
            postrun_code = await self._run_container_postrun(environment, postrun_path)
            await self._write_sync_check(environment, sync_check_path)

            if postrun_code != 0:
                raise RuntimeError(
                    f"solar-harness container postrun failed with exit {postrun_code}"
                )

    async def _run_container_postrun(
        self,
        environment: BaseEnvironment,
        output_path: Path,
    ) -> int | None:
        try:
            result = await environment.exec(
                "cd /app && "
                "script='' && "
                "[ -f .solar-harness-container.sh ] && script=.solar-harness-container.sh; "
                "[ -z \"$script\" ] && [ -f .host-claude-container.sh ] && script=.host-claude-container.sh; "
                "if [ -n \"$script\" ]; then "
                "chmod +x \"$script\" && printf '%s\\n' \"--- running $script ---\" && ./$script; "
                "else printf '%s\\n' 'no container postrun script'; fi",
                timeout_sec=int(os.environ.get("SOLAR_HARNESS_CONTAINER_POSTRUN_TIMEOUT_SEC", "600")),
            )
            output_path.write_text(
                f"return_code={result.return_code}\n"
                "--- stdout ---\n"
                f"{result.stdout or ''}\n"
                "--- stderr ---\n"
                f"{result.stderr or ''}\n",
                encoding="utf-8",
            )
            return result.return_code
        except Exception as exc:
            output_path.write_text(f"container postrun failed: {exc}\n", encoding="utf-8")
            return None

    async def _write_sync_check(
        self,
        environment: BaseEnvironment,
        output_path: Path,
    ) -> None:
        try:
            result = await environment.exec(
                "cd /app && find . -maxdepth 2 -type f -printf '%P\\t%s\\n' | sort"
            )
            output_path.write_text(result.stdout or "", encoding="utf-8")
        except Exception as exc:
            output_path.write_text(f"sync check failed: {exc}\n", encoding="utf-8")


async def _run_command(
    cmd: list[str],
    workspace: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            cwd=str(workspace),
            text=True,
            capture_output=True,
            timeout=timeout,
            env=_solar_harness_env(),
        )

    return await asyncio.to_thread(_run)


def _solar_harness_binary() -> str:
    explicit = os.environ.get("SOLAR_HARNESS_BIN", "").strip()
    if explicit:
        return explicit
    found = shutil.which("solar-harness")
    if found:
        return found
    return str(Path.home() / ".solar" / "bin" / "solar-harness")


def _solar_harness_env() -> dict[str, str]:
    env = os.environ.copy()
    harness_dir = Path(env.get("HARNESS_DIR", Path.home() / ".solar" / "harness"))
    package_root = str(harness_dir.parent)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        package_root if not existing else f"{package_root}{os.pathsep}{existing}"
    )
    env["HARNESS_DIR"] = str(harness_dir)
    return env
