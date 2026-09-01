"""Deterministic resource preflight. Unknown hard limits are not a PASS."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def local_capacity() -> dict[str, Any]:
    result: dict[str, Any] = {"cpu_cores": os.cpu_count(), "memory_mb": None, "gpu_available": None}
    try:
        import psutil
        result["memory_mb"] = int(psutil.virtual_memory().available / (1024 * 1024))
    except ImportError:
        if os.name == "posix" and Path("/proc/meminfo").exists():
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    result["memory_mb"] = int(line.split()[1]) // 1024
    return result


def check(requirements: dict[str, Any], operator: dict[str, Any], *,
          capacity: dict[str, Any] | None = None) -> list[str]:
    declared = operator.get("resource_capacity") or {}
    errors: list[str] = []
    minimum = int(requirements.get("minimum_context_tokens") or 0)
    context = (declared.get("context_tokens") or operator.get("context_window")
               or operator.get("context_tokens") or operator.get("max_context_tokens"))
    if minimum and (not isinstance(context, (int, float)) or context < minimum):
        errors.append("CONTEXT_CAPACITY_UNKNOWN" if context is None else "CONTEXT_CAPACITY_INSUFFICIENT")
    needs_host = (float(requirements.get("cpu_cores_min") or 0) > 0
                  or int(requirements.get("memory_mb_min") or 0) > 0
                  or requirements.get("gpu_required") is True)
    if not needs_host:
        return errors
    binding = operator.get("runtime_binding") or {}
    remote = binding.get("kind") in {"remote", "ssh", "remote_host"} or bool(binding.get("host") or binding.get("host_id"))
    probe_local_gpu = capacity is None and not remote
    capacity = dict(capacity) if capacity is not None else (dict(declared) if remote else local_capacity())
    for required, available in (("cpu_cores_min", "cpu_cores"), ("memory_mb_min", "memory_mb")):
        minimum_value = float(requirements.get(required) or 0)
        actual = capacity.get(available)
        if minimum_value > 0 and (actual is None or float(actual) < minimum_value):
            errors.append(f"{available.upper()}_" + ("UNKNOWN" if actual is None else "INSUFFICIENT"))
    if requirements.get("gpu_required") is True:
        available = capacity.get("gpu_available")
        if available is None and probe_local_gpu and shutil.which("nvidia-smi"):
            try:
                probe = subprocess.run(["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"],
                                       capture_output=True, text=True, timeout=5)
                available = probe.returncode == 0 and bool(probe.stdout.strip())
            except (OSError, subprocess.TimeoutExpired):
                available = None
        if available is not True:
            errors.append("GPU_CAPACITY_UNKNOWN" if available is None else "GPU_UNAVAILABLE")
    return errors
