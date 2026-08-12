#!/usr/bin/env bash
set -euo pipefail

archive="${OPENJIUWEN_SOLAR_RUNTIME_SOURCE_ARCHIVE:?runtime source archive is required}"
destination="${SOLAR_SRC:?SOLAR_SRC is required}"

[ -f "$archive" ] || { echo "runtime source archive not found: $archive" >&2; exit 1; }
if [ -e "$destination" ] && [ -n "$(find "$destination" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    echo "runtime source destination must be empty: $destination" >&2
    exit 1
fi
mkdir -p "$destination"

python3 - "$archive" "$destination" <<'PY'
import os
import stat
import sys
import zipfile
from pathlib import Path

archive_path = Path(sys.argv[1])
destination = Path(sys.argv[2]).resolve()
with zipfile.ZipFile(archive_path) as archive:
    for info in archive.infolist():
        relative = Path(info.filename)
        mode = (info.external_attr >> 16) & 0o170000
        if relative.is_absolute() or ".." in relative.parts:
            raise SystemExit(f"unsafe runtime source member: {info.filename}")
        if mode == stat.S_IFLNK:
            raise SystemExit(f"symlink runtime source member is forbidden: {info.filename}")
        target = (destination / relative).resolve()
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise SystemExit(f"runtime source member escapes destination: {info.filename}") from exc
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as output:
            output.write(source.read())
        permissions = (info.external_attr >> 16) & 0o777
        if permissions:
            os.chmod(target, permissions)
PY

[ -f "$destination/install.sh" ] || { echo "bundled runtime source lacks install.sh" >&2; exit 1; }
exec bash "$destination/install.sh" "$@"
