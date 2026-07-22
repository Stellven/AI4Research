#!/usr/bin/env python3
"""PTY smoke tests for the interactive installer wizard.

Uses only Python stdlib. Every child gets a real controlling TTY so installer
reads from /dev/tty are exercised, not bypassed.
"""

import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import sys
import tempfile
import time


REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "install.sh"


# Signals that force the installer non-interactive regardless of a TTY
# (solar_can_prompt honors these before testing /dev/tty). The interactive
# wizard tests below provide a real PTY, which models a human terminal --
# mutually exclusive with a CI runner -- so these must be cleared, or the
# installer correctly refuses to prompt. CI is inherited from the GitHub
# Actions environment; SOLAR_NONINTERACTIVE/SOLAR_* are dropped by the prefix
# filter. (test_ci_forces_noninteractive re-adds CI to prove the guard.)
NONINTERACTIVE_SIGNALS = ("CI",)


def clean_env(home: Path) -> dict:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("SOLAR_") and k not in NONINTERACTIVE_SIGNALS
    }
    env["HOME"] = str(home)
    env["PATH"] = path_without_bun()
    return env


def path_without_bun() -> str:
    kept = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        if (Path(entry) / "bun").exists():
            continue
        kept.append(entry)
    return os.pathsep.join(kept)


def snapshot(home: Path) -> list[str]:
    if not home.exists():
        return []
    return sorted(str(p.relative_to(home)) for p in home.rglob("*"))


def receipt_components(home: Path) -> list[str]:
    with (home / ".solar" / "install-receipt.json").open(encoding="utf-8") as f:
        return json.load(f)["components"]


def run_pty(
    home: Path,
    args: list[str],
    responses: list[tuple[str, str]],
    expect_exit: int,
    timeout: float = 45.0,
    env: dict | None = None,
) -> str:
    child_env = env if env is not None else clean_env(home)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(str(REPO))
        os.execvpe("bash", ["bash", str(INSTALL)] + args, child_env)

    output = bytearray()
    sent = 0
    deadline = time.time() + timeout
    status = None
    try:
        while True:
            if time.time() > deadline:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                raise AssertionError(
                    "wizard timed out after %.1fs; output:\n%s"
                    % (timeout, output.decode(errors="replace"))
                )

            ready, _, _ = select.select([fd], [], [], 0.05)
            if ready:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    chunk = b""
                if chunk:
                    output.extend(chunk)

            text = output.decode(errors="replace")
            if sent < len(responses) and responses[sent][0] in text:
                os.write(fd, responses[sent][1].encode())
                sent += 1

            waited_pid, waited_status = os.waitpid(pid, os.WNOHANG)
            if waited_pid == pid:
                status = waited_status
                break
    finally:
        try:
            os.close(fd)
        except OSError:
            pass

    if status is None:
        _, status = os.waitpid(pid, 0)
    if os.WIFEXITED(status):
        code = os.WEXITSTATUS(status)
    elif os.WIFSIGNALED(status):
        code = 128 + os.WTERMSIG(status)
    else:
        code = 1

    text = output.decode(errors="replace")
    if sent != len(responses):
        raise AssertionError(
            "wizard exited before all prompts were answered; sent %d/%d; output:\n%s"
            % (sent, len(responses), text)
        )
    if code != expect_exit:
        raise AssertionError(
            "wizard exit mismatch: expected %s got %s; output:\n%s"
            % (expect_exit, code, text)
        )
    return text


def assert_components(home: Path, expected: list[str]) -> None:
    actual = receipt_components(home)
    if actual != expected:
        raise AssertionError(f"expected components {expected!r}, got {actual!r}")


def test_proceed_path(root: Path) -> None:
    home = root / "proceed"
    home.mkdir()
    run_pty(
        home,
        ["--fake-keys", "--skip-llm-cli"],
        [("Choice [1-3]:", "1\n"), ("Confirm install? [y/N]", "y\n")],
        0,
    )
    assert_components(home, ["kernel", "harness", "autosci"])
    print("wizard proceed path: ok")


def test_components_tty_skips_selection(root: Path) -> None:
    home = root / "components"
    home.mkdir()
    output = run_pty(
        home,
        ["--components", "kernel", "--fake-keys", "--skip-llm-cli"],
        [("Confirm install? [y/N]", "y\n")],
        0,
    )
    if "Choice [1-3]:" in output or "Available components" in output:
        raise AssertionError("--components path unexpectedly entered component selection")
    assert_components(home, ["kernel"])
    print("wizard --components skip-selection path: ok")


def test_customize_kernel_only(root: Path) -> None:
    home = root / "customize"
    home.mkdir()
    run_pty(
        home,
        ["--fake-keys", "--skip-llm-cli"],
        [
            ("Choice [1-3]:", "2\n"),
            ("Selection:", "kernel\n"),
            ("Confirm install? [y/N]", "y\n"),
        ],
        0,
    )
    assert_components(home, ["kernel"])
    print("wizard customize kernel-only path: ok")


def test_cancel_writes_nothing(root: Path) -> None:
    home = root / "cancel"
    home.mkdir()
    before = snapshot(home)
    run_pty(
        home,
        ["--fake-keys", "--skip-llm-cli"],
        [("Choice [1-3]:", "3\n")],
        130,
    )
    after = snapshot(home)
    if before != after:
        raise AssertionError(f"cancel changed HOME snapshot: before={before} after={after}")
    print("wizard cancel zero-write path: ok")


def test_dry_run_wizard_writes_nothing(root: Path) -> None:
    home = root / "dry-run"
    home.mkdir()
    before = snapshot(home)
    run_pty(
        home,
        ["--dry-run", "--fake-keys", "--skip-llm-cli"],
        [
            ("Choice [1-3]:", "2\n"),
            ("Selection:", "kernel\n"),
            ("Confirm install? [y/N]", "y\n"),
        ],
        0,
    )
    after = snapshot(home)
    if before != after:
        raise AssertionError(f"dry-run changed HOME snapshot: before={before} after={after}")
    print("wizard dry-run zero-write path: ok")


def test_ci_forces_noninteractive(root: Path) -> None:
    """Production guarantee: CI wins over a present TTY.

    Even with a real controlling PTY, CI=true (and no --yes) must keep the
    installer non-interactive -- it must NOT prompt and must exit non-zero
    asking for --yes. This is the exact rule solar_can_prompt enforces; the
    other tests clear CI to reach the wizard, so this one re-adds it to prove
    the guard is intact (a real CI runner never hangs on a prompt).
    """
    home = root / "ci-noninteractive"
    home.mkdir()
    env = clean_env(home)
    env["CI"] = "true"
    before = snapshot(home)
    output = run_pty(
        home,
        ["--fake-keys", "--skip-llm-cli"],
        [],  # send nothing: a prompt here would be the bug
        1,
        env=env,
    )
    if "Choice [1-3]:" in output or "Confirm install? [y/N]" in output:
        raise AssertionError("CI=true reached an interactive prompt; output:\n" + output)
    if "non-interactive input detected" not in output:
        raise AssertionError("CI=true did not emit the non-interactive die; output:\n" + output)
    if snapshot(home) != before:
        raise AssertionError("CI=true non-interactive refusal still wrote to HOME")
    print("wizard CI-forces-non-interactive guard: ok")


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="solar-wizard-pty."))
    try:
        test_proceed_path(root)
        test_components_tty_skips_selection(root)
        test_customize_kernel_only(root)
        test_cancel_writes_nothing(root)
        test_dry_run_wizard_writes_nothing(root)
        test_ci_forces_noninteractive(root)
        print("smoke-installer-wizard-pty passed")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
