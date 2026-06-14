"""Thin pipx-friendly wrapper for the OpenJiuwen Solar shell installer."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable, Sequence

PUBLIC_GET_SOLAR_URL = (
    "https://raw.githubusercontent.com/suraj-subrahmanyan/OpenSolar/stable/"
    "get-solar.sh"
)
CLI_NAME = "openjiuwen-solar"
GET_SOLAR_URL_ENV = "OPENJIUWEN_SOLAR_GET_SOLAR_URL"
LEGACY_GET_SOLAR_URL_ENV = "OPENSOLAR_GET_SOLAR_URL"

PASSTHROUGH_ENV = (
    "SOLAR_REPO",
    "SOLAR_CHANNEL",
    "SOLAR_SRC",
    "SOLAR_COMPONENTS",
    GET_SOLAR_URL_ENV,
    LEGACY_GET_SOLAR_URL_ENV,
)

HELP = f"""\
OpenJiuwen Solar pipx wrapper

Usage:
  openjiuwen-solar <command> [args...]
  openjiuwen-solar --help

Commands:
  install [args...]       Download/run get-solar.sh; forwards args unchanged.
  doctor [args...]        Delegate to ~/.solar/bin/solar doctor.
  update [args...]        Delegate to ~/.solar/bin/solar update.
  uninstall [args...]     Delegate to ~/.solar/bin/solar uninstall.
  source                  Print the retained OpenSolar source checkout path.

Install:
  pipx install ./distribution/pipx
  pipx install "git+https://github.com/suraj-subrahmanyan/OpenSolar.git@stable#subdirectory=distribution/pipx"

Package name:
  openjiuwen-solar installs the `openjiuwen-solar` command.

Examples:
  openjiuwen-solar install --yes --components kernel,harness
  openjiuwen-solar doctor --json
  openjiuwen-solar update
  openjiuwen-solar uninstall --yes

Installer environment passed through:
  SOLAR_REPO, SOLAR_CHANNEL, SOLAR_SRC, SOLAR_COMPONENTS

Wrapper environment:
  OPENJIUWEN_SOLAR_GET_SOLAR_URL=/path/to/get-solar.sh
  OPENJIUWEN_SOLAR_GET_SOLAR_URL=file:///absolute/path/to/get-solar.sh
  OPENJIUWEN_SOLAR_GET_SOLAR_URL=https://example.invalid/get-solar.sh
  OPENSOLAR_GET_SOLAR_URL is also accepted for older local scripts.

Defaults:
  get-solar.sh URL: {PUBLIC_GET_SOLAR_URL}
  source path: $SOLAR_SRC/OpenSolar when present, otherwise ~/.solar-src/OpenSolar
  source not found exit: 1

Warnings:
  pipx uninstalling this wrapper does NOT uninstall OpenSolar.
  Run `openjiuwen-solar uninstall --yes` before removing the pipx wrapper.
  Native Windows is not supported by this wrapper. Use WSL and the repository
  install.ps1 bootstrapper instead.
"""


def _print_help() -> None:
    sys.stdout.write(HELP)


def _err(message: str) -> None:
    sys.stderr.write(message.rstrip() + "\n")


def _native_windows() -> bool:
    return os.name == "nt" or platform.system().lower() == "windows"


def _windows_error() -> int:
    _err(
        f"{CLI_NAME}: native Windows is not supported. Use WSL and run the "
        "repository install.ps1 bootstrapper, or install inside a WSL Linux "
        "distro."
    )
    return 1


def _run(command: Sequence[str]) -> int:
    try:
        completed = subprocess.run(command, env=os.environ.copy(), check=False)
    except FileNotFoundError:
        _err(f"{CLI_NAME}: command not found: {command[0]}")
        return 127
    except PermissionError as exc:
        _err(f"{CLI_NAME}: cannot execute {command[0]}: {exc}")
        return 126
    return completed.returncode


def _file_url_to_path(value: str) -> Path:
    parsed = urllib.parse.urlparse(value)
    path = urllib.request.url2pathname(urllib.parse.unquote(parsed.path))
    if parsed.netloc and parsed.netloc != "localhost":
        path = f"//{parsed.netloc}{path}"
    return Path(path)


def _local_get_solar_path(value: str) -> Path | None:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme == "file":
        return _file_url_to_path(value)
    if parsed.scheme in ("http", "https"):
        return None
    if parsed.scheme:
        return None
    return Path(value).expanduser()


def _run_local_get_solar(value: str, args: Sequence[str]) -> int:
    path = _local_get_solar_path(value)
    if path is None:
        raise ValueError(f"not a local get-solar reference: {value}")
    if not path.is_file():
        _err(f"{CLI_NAME}: get-solar.sh not found at {path}")
        return 1
    return _run(["bash", str(path), *args])


def _run_remote_get_solar(url: str, args: Sequence[str]) -> int:
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    except (OSError, urllib.error.URLError) as exc:
        _err(f"{CLI_NAME}: failed to download get-solar.sh from {url}: {exc}")
        _err(f"Set {GET_SOLAR_URL_ENV}=/path/to/get-solar.sh for local runs.")
        return 1

    if not data.strip():
        _err(f"{CLI_NAME}: downloaded get-solar.sh from {url} was empty")
        return 1

    with tempfile.TemporaryDirectory(prefix="openjiuwen-solar-get-solar-") as tmpdir:
        script = Path(tmpdir) / "get-solar.sh"
        script.write_bytes(data)
        return _run(["bash", str(script), *args])


def install(args: Sequence[str]) -> int:
    override = os.environ.get(GET_SOLAR_URL_ENV) or os.environ.get(LEGACY_GET_SOLAR_URL_ENV)
    get_solar = override or PUBLIC_GET_SOLAR_URL
    local_path = _local_get_solar_path(get_solar)
    if local_path is not None:
        return _run_local_get_solar(get_solar, args)
    return _run_remote_get_solar(get_solar, args)


def _solar_bin() -> Path:
    # Honor SOLAR_HOME so the wrapper delegates to a non-default install instead
    # of always assuming ~/.solar (bin/solar itself honors SOLAR_HOME).
    home = os.environ.get("SOLAR_HOME")
    base = Path(home) if home else Path.home() / ".solar"
    return base / "bin" / "solar"


def _delegate_lifecycle(command: str, args: Sequence[str]) -> int:
    solar = _solar_bin()
    if not solar.is_file():
        _err(f"{CLI_NAME}: OpenSolar lifecycle command not found: {solar}")
        _err(f"Install OpenSolar first with: {CLI_NAME} install --yes")
        return 1
    return _run([str(solar), command, *args])


def _source_candidates() -> list[Path]:
    env_src = os.environ.get("SOLAR_SRC")
    if env_src:
        base = Path(env_src).expanduser()
        if base.name == "OpenSolar":
            return [base, base / "OpenSolar"]
        candidates = [base / "OpenSolar"]
        if (base / "install.sh").is_file():
            candidates.append(base)
        return candidates
    return [Path.home() / ".solar-src" / "OpenSolar"]


def source(args: Sequence[str]) -> int:
    if args:
        _err(f"{CLI_NAME}: source does not accept arguments")
        return 2
    candidates = _source_candidates()
    for candidate in candidates:
        if candidate.exists():
            print(candidate)
            return 0
    looked = ", ".join(str(path) for path in candidates)
    _err(f"{CLI_NAME}: OpenSolar source checkout not found. Looked for: {looked}")
    _err(f"Run {CLI_NAME} install --yes, or set SOLAR_SRC to the checkout path.")
    return 1


def main(argv: Iterable[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"--help", "-h", "help"}:
        _print_help()
        return 0

    command = args[0]
    rest = args[1:]
    if _native_windows():
        return _windows_error()

    if command == "install":
        return install(rest)
    if command in {"doctor", "update", "uninstall"}:
        return _delegate_lifecycle(command, rest)
    if command == "source":
        return source(rest)

    _err(f"{CLI_NAME}: unknown command: {command}")
    _print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
