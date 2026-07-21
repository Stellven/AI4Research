import asyncio
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class HostClaudeCode(BaseAgent):
    """Run Claude Code on the host and sync /app back into Harbor.

    This avoids trying to perform Claude subscription login inside the benchmark
    container. The host CLI keeps using its existing interactive login/session.
    """

    SUPPORTS_WINDOWS: bool = False

    @staticmethod
    def name() -> str:
        return "host-claude-code"

    def version(self) -> str:
        try:
            result = subprocess.run(
                ["claude", "--version"],
                text=True,
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip() or "host"
        except Exception:
            pass
        return "host"

    async def setup(self, environment: BaseEnvironment) -> None:
        return

    def _model_arg(self) -> str | None:
        if not self.model_name:
            return None
        model = self.model_name.split("/", 1)[-1]
        lowered = model.lower()
        if "opus" in lowered:
            return "opus"
        if "sonnet" in lowered:
            return "sonnet"
        if "haiku" in lowered:
            return "haiku"
        return model

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = self.logs_dir / "host-claude-code.stdout.txt"
        stderr_path = self.logs_dir / "host-claude-code.stderr.txt"
        prompt_path = self.logs_dir / "host-claude-code.prompt.txt"
        command_path = self.logs_dir / "host-claude-code.command.txt"
        repair_stdout_path = self.logs_dir / "host-claude-code.repair.stdout.txt"
        repair_stderr_path = self.logs_dir / "host-claude-code.repair.stderr.txt"
        files_before_path = self.logs_dir / "host-claude-code.files-before.txt"
        files_after_path = self.logs_dir / "host-claude-code.files-after.txt"
        container_postrun_path = self.logs_dir / "host-claude-code.container-postrun.txt"
        container_postrun_repair_path = self.logs_dir / "host-claude-code.container-postrun-repair.txt"
        sync_check_path = self.logs_dir / "host-claude-code.sync-check.txt"
        mcp_config_path = self.logs_dir / "host-claude-empty-mcp.json"
        mcp_config_path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

        with tempfile.TemporaryDirectory(prefix="harbor-host-claude-") as tmp:
            workspace = Path(tmp) / "app"
            workspace.mkdir(parents=True, exist_ok=True)
            await environment.download_dir("/app", workspace)
            files_before = self._file_inventory(workspace)
            self._write_file_inventory(workspace, files_before_path)

            prompt = (
                f"{instruction}\n\n"
                "Execution contract:\n"
                "- You are working in a host-side copy of the benchmark /app directory.\n"
                "- The current working directory is the benchmark /app directory copy.\n"
                "- Mandatory first step: inspect the actual files in this directory using tools; do not answer from memory or visual guessing.\n"
                "- If the task references an image, dataset, script, or test file, open and use that file with Read/Bash/Python before deciding.\n"
                "- For image tasks, use the image file itself as evidence. If the task is a board/game puzzle, reconstruct the state from the file and validate legal candidates programmatically when practical.\n"
                "- If the task needs Linux-native binaries, package installation, or writes to absolute paths outside /app such as /usr/local/bin, create a shell script named .host-claude-container.sh in the current directory. The host agent will upload /app and execute that script inside the benchmark container from /app.\n"
                "- Do not treat host-built macOS binaries as final Linux container artifacts.\n"
                "- Prefer executable verification over visual guessing when a small script or existing CLI can validate the answer.\n"
                "- If the instruction asks for multiple valid outputs or says 'if there are multiple', search for the complete set, not only the first valid answer.\n"
                "- If you find one candidate answer, explicitly check whether another equally winning or valid answer exists before writing the final file.\n"
                "- Create or edit the required output files inside the current working directory.\n"
                "- Do not only explain the answer on stdout; the verifier reads files from /app.\n"
                "- Do not write outside this directory.\n"
                "- Before final response, verify that the expected output file exists and contains the exact required format.\n"
            )
            prompt_path.write_text(prompt, encoding="utf-8")

            cmd = self._build_claude_cmd(workspace, mcp_config_path, prompt)
            command_path.write_text(
                " ".join(shlex.quote(part) for part in cmd[:-1]) + " -- <prompt>\n",
                encoding="utf-8",
            )

            timeout = int(os.environ.get("HOST_CLAUDE_TIMEOUT_SEC", "600"))

            try:
                result = await self._run_claude_cmd(cmd, workspace, timeout)
            except subprocess.TimeoutExpired as exc:
                stdout_path.write_text(exc.stdout or "", encoding="utf-8")
                stderr_path.write_text(
                    exc.stderr or f"Timed out after {timeout}s",
                    encoding="utf-8",
                )
                raise RuntimeError(f"host claude timed out after {timeout}s") from exc

            stdout_path.write_text(result.stdout or "", encoding="utf-8")
            stderr_path.write_text(result.stderr or "", encoding="utf-8")
            files_after = self._file_inventory(workspace)
            self._write_file_inventory(workspace, files_after_path)

            workspace_changed = files_after != files_before
            allow_partial = os.environ.get(
                "HOST_CLAUDE_ALLOW_PARTIAL_ON_ERROR",
                "1",
            ).strip().lower() not in {"0", "false", "no", "off"}

            if result.returncode != 0 and not (allow_partial and workspace_changed):
                quoted = " ".join(shlex.quote(part) for part in cmd[:4])
                raise RuntimeError(
                    f"host claude failed with exit {result.returncode}: {quoted}"
                )

            await environment.upload_dir(workspace, "/app")
            postrun_code = await self._run_container_postrun(
                environment,
                container_postrun_path,
            )
            if postrun_code not in (0, None) and self._repair_enabled():
                await environment.download_dir("/app", workspace)
                repair_prompt = (
                    f"{prompt}\n\n"
                    "The container post-run script failed inside the Linux benchmark container. "
                    "You must inspect the failure log below, patch .host-claude-container.sh "
                    "or the workspace files, and make the script succeed when run from /app. "
                    "Focus on the first compile/install error; do not explain only.\n\n"
                    "Container post-run failure log:\n"
                    "```text\n"
                    f"{self._tail_file(container_postrun_path, 20000)}\n"
                    "```\n"
                )
                repair_cmd = self._build_claude_cmd(
                    workspace,
                    mcp_config_path,
                    repair_prompt,
                )
                try:
                    repair_result = await self._run_claude_cmd(
                        repair_cmd,
                        workspace,
                        int(os.environ.get("HOST_CLAUDE_REPAIR_TIMEOUT_SEC", str(timeout))),
                    )
                    repair_stdout_path.write_text(
                        repair_result.stdout or "",
                        encoding="utf-8",
                    )
                    repair_stderr_path.write_text(
                        repair_result.stderr or "",
                        encoding="utf-8",
                    )
                    await environment.upload_dir(workspace, "/app")
                    await self._run_container_postrun(
                        environment,
                        container_postrun_repair_path,
                    )
                except subprocess.TimeoutExpired as exc:
                    repair_stdout_path.write_text(exc.stdout or "", encoding="utf-8")
                    repair_stderr_path.write_text(
                        exc.stderr or f"Repair timed out after {exc.timeout}s",
                        encoding="utf-8",
                    )
            await self._write_sync_check(environment, sync_check_path)

            if result.returncode != 0:
                stderr_note = (
                    "\n[host-claude-code] Claude exited non-zero after modifying "
                    "the workspace; uploaded partial workspace for verifier.\n"
                )
                with stderr_path.open("a", encoding="utf-8") as fh:
                    fh.write(stderr_note)

    def _build_claude_cmd(
        self,
        workspace: Path,
        mcp_config_path: Path,
        prompt: str,
    ) -> list[str]:
        cmd = [
            "claude",
            "-p",
            "--add-dir",
            str(workspace),
            "--tools",
            "default",
            "--permission-mode",
            "bypassPermissions",
            "--strict-mcp-config",
            "--mcp-config",
            str(mcp_config_path),
        ]
        model = self._model_arg()
        if model:
            cmd.extend(["--model", model])
        cmd.extend(["--", prompt])
        return cmd

    async def _run_claude_cmd(
        self,
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
                env=os.environ.copy(),
            )

        return await asyncio.to_thread(_run)

    def _repair_enabled(self) -> bool:
        return os.environ.get(
            "HOST_CLAUDE_REPAIR_CONTAINER_POSTRUN",
            "1",
        ).strip().lower() not in {"0", "false", "no", "off"}

    def _tail_file(self, path: Path, max_chars: int) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"<failed to read {path}: {exc}>"
        return text[-max_chars:]

    def _file_inventory(self, workspace: Path) -> dict[str, int | str]:
        rows: dict[str, int | str] = {}
        for path in sorted(workspace.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(workspace))
            try:
                stat = path.stat()
                rows[rel] = stat.st_size
            except OSError as exc:
                rows[rel] = f"ERROR:{exc}"
        return rows

    def _write_file_inventory(self, workspace: Path, output_path: Path) -> None:
        rows = [
            f"{rel}\t{size}"
            for rel, size in self._file_inventory(workspace).items()
        ]
        output_path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")

    async def _write_sync_check(
        self,
        environment: BaseEnvironment,
        output_path: Path,
    ) -> None:
        try:
            result = await environment.exec(
                "cd /app && "
                "printf '%s\\n' '--- files ---' && "
                "find . -maxdepth 2 -type f -printf '%P\\t%s\\n' | sort && "
                "printf '%s\\n' '--- likely outputs ---' && "
                "for f in move.txt answer.txt output.txt result.txt solution.txt; do "
                "[ -f \"$f\" ] && { printf '## %s\\n' \"$f\"; sed -n '1,80p' \"$f\"; }; "
                "done"
            )
            output_path.write_text(result.stdout or "", encoding="utf-8")
        except Exception as exc:
            output_path.write_text(f"sync check failed: {exc}\n", encoding="utf-8")

    async def _run_container_postrun(
        self,
        environment: BaseEnvironment,
        output_path: Path,
    ) -> int | None:
        try:
            result = await environment.exec(
                "cd /app && "
                "if [ -f .host-claude-container.sh ]; then "
                "chmod +x .host-claude-container.sh && "
                "printf '%s\\n' '--- running .host-claude-container.sh ---' && "
                "./.host-claude-container.sh; "
                "else printf '%s\\n' 'no .host-claude-container.sh'; fi",
                timeout_sec=int(os.environ.get("HOST_CLAUDE_CONTAINER_POSTRUN_TIMEOUT_SEC", "600")),
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
