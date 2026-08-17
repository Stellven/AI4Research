"""Resolve a runnable Codex CLI across native Unix and Windows-hosted WSL.

The Windows Codex desktop package includes a Linux CLI binary, but the
WindowsApps mount exposes it to WSL without the executable bit.  Solar runs its
engine inside WSL, so merely finding that file is not enough: the runtime must
copy it into a Solar-owned directory before it can be executed.
"""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import tempfile
from pathlib import Path
from typing import Mapping


_WINDOWS_APPS_PREFIX = "/mnt/c/Program Files/WindowsApps/OpenAI.Codex_"
_WINDOWS_APPS_SUFFIX = "/app/resources/codex"


def _is_wsl() -> bool:
    if os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"):
        return True
    return platform.system() == "Linux" and "microsoft" in platform.release().lower()


def _is_runnable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return stream.read(4) == b"\x7fELF"
    except OSError:
        return False


def _trusted_windows_desktop_source(path: Path) -> bool:
    normalized = path.as_posix()
    return (
        normalized.startswith(_WINDOWS_APPS_PREFIX)
        and normalized.endswith(_WINDOWS_APPS_SUFFIX)
        and path.is_file()
        and _is_elf(path)
    )


def _desktop_cli_sources(env: Mapping[str, str]) -> list[Path]:
    candidates: list[Path] = []
    explicit = str(env.get("SOLAR_CODEX_DESKTOP_CLI_SOURCE") or "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    for entry in str(env.get("PATH") or "").split(os.pathsep):
        if entry:
            candidates.append(Path(entry) / "codex")
    windows_apps = Path("/mnt/c/Program Files/WindowsApps")
    try:
        candidates.extend(windows_apps.glob("OpenAI.Codex_*/app/resources/codex"))
    except OSError:
        pass

    unique: dict[str, Path] = {}
    for candidate in candidates:
        try:
            key = str(candidate.resolve(strict=False))
        except OSError:
            key = str(candidate)
        unique[key] = candidate
    trusted = [path for path in unique.values() if _trusted_windows_desktop_source(path)]
    return sorted(
        trusted,
        key=lambda path: path.stat().st_mtime_ns if path.exists() else 0,
        reverse=True,
    )


def _materialize_desktop_cli(source: Path, runtime_root: Path) -> Path:
    stat = source.stat()
    fingerprint = hashlib.sha256(
        f"{source.resolve(strict=False)}\0{stat.st_size}\0{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()[:20]
    target_dir = runtime_root / fingerprint
    target = target_dir / "codex"
    if _is_runnable(target) and target.stat().st_size == stat.st_size and _is_elf(target):
        return target

    target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="codex.", suffix=".tmp", dir=str(target_dir))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copyfile(source, tmp)
        tmp.chmod(0o700)
        if not _is_runnable(tmp) or not _is_elf(tmp):
            raise OSError("materialized Codex CLI is not runnable ELF")
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return target


def resolve_codex_cli(
    harness_dir: Path,
    *,
    env: Mapping[str, str] | None = None,
    configured_path: str = "",
) -> tuple[Path | None, str]:
    """Return a runnable Codex CLI and a non-secret resolution reason."""
    runtime_env: Mapping[str, str] = env or os.environ
    configured = str(configured_path or "").strip()
    if configured:
        configured_candidate = Path(configured).expanduser()
        if _is_runnable(configured_candidate):
            return configured_candidate.resolve(strict=False), "configured_path"

    resolved = shutil.which("codex", path=str(runtime_env.get("PATH") or ""))
    if resolved:
        candidate = Path(resolved)
        if _is_runnable(candidate):
            return candidate.resolve(strict=False), "path"

    if _is_wsl():
        runtime_root = Path(
            str(runtime_env.get("SOLAR_CODEX_RUNTIME_DIR") or "")
            or str(Path(harness_dir) / "run" / "codex-cli-runtime")
        ).expanduser()
        for source in _desktop_cli_sources(runtime_env):
            try:
                return _materialize_desktop_cli(source, runtime_root), "windows_desktop_wsl_copy"
            except OSError:
                continue

    return None, f"command_path_missing:{configured or 'codex'}"
