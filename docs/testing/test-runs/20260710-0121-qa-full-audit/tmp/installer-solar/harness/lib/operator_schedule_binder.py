"""
Operator Schedule Binder — reads operator_registry.json and generates
operator_schedules.json with cron/manual bindings for each operator line.

Part of Solar Harness AI Influence operator consolidation (S04 N1).
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from operator_registry_loader import (
    RegistryLoadError,
    RegistryValidationError,
    load_registry,
)

_HARNESS_ROOT = Path(
    os.environ.get("SOLAR_HARNESS_DIR", os.path.expanduser("~/.solar/harness"))
)
_DEFAULT_OUTPUT_PATH = _HARNESS_ROOT / "config" / "operator_schedules.json"

SCHEMA_VERSION = "solar.operator_schedules.v1"

# Default cron templates per schedule type.
# daily lines are staggered by 30-minute offsets starting at 08:00 UTC.
_SCHEDULE_TEMPLATES: dict[str, str | None] = {
    "daily": "0 {hour} * * *",
    "weekly": "0 8 * * 1",
    "hourly": "0 * * * *",
    "on_demand": None,  # manual — no cron
}

_DAILY_BASE_HOUR = 8
_DAILY_STAGGER_MINUTES = 30


def bind_schedules(
    registry: dict[str, Any] | None = None,
    registry_path: str | Path | None = None,
    daily_base_hour: int = _DAILY_BASE_HOUR,
    daily_stagger_minutes: int = _DAILY_STAGGER_MINUTES,
) -> dict[str, Any]:
    """
    Generate schedule bindings from operator registry.

    Args:
        registry: Pre-loaded registry dict. If None, loads from default/given path.
        registry_path: Path to operator_registry.json (used if registry is None).
        daily_base_hour: UTC hour for the first daily line.
        daily_stagger_minutes: Minutes between consecutive daily lines.

    Returns:
        Schedule binding dict ready to be serialized as operator_schedules.json.

    Raises:
        RegistryLoadError: If registry cannot be loaded.
        RegistryValidationError: If registry fails validation.
    """
    if registry is None:
        kwargs: dict[str, Any] = {}
        if registry_path is not None:
            kwargs["registry_path"] = registry_path
        registry = load_registry(**kwargs)

    lines = registry.get("lines", {})
    bindings: dict[str, dict[str, Any]] = {}
    daily_index = 0

    for line_name, line_def in lines.items():
        source_schedule = line_def.get("schedule", "on_demand")
        binding: dict[str, Any] = {
            "line": line_name,
            "primary": line_def.get("primary", ""),
            "source_schedule": source_schedule,
        }

        if source_schedule == "daily":
            total_minutes = daily_base_hour * 60 + daily_index * daily_stagger_minutes
            hour = total_minutes // 60
            minute = total_minutes % 60
            binding["type"] = "cron"
            binding["cron"] = f"{minute} {hour} * * *"
            daily_index += 1
        elif source_schedule in _SCHEDULE_TEMPLATES:
            template = _SCHEDULE_TEMPLATES[source_schedule]
            if template is None:
                binding["type"] = "manual"
                binding["cron"] = None
            else:
                binding["type"] = "cron"
                binding["cron"] = template
        else:
            # Unknown schedule type — treat as manual
            binding["type"] = "manual"
            binding["cron"] = None

        # Carry over dual_run config if present
        dual_run = line_def.get("dual_run")
        if dual_run is not None:
            binding["dual_run"] = dual_run

        bindings[line_name] = binding

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bindings": bindings,
    }


def write_schedules(
    output_path: str | Path | None = None,
    registry: dict[str, Any] | None = None,
    registry_path: str | Path | None = None,
) -> Path:
    """
    Generate and write operator_schedules.json.

    Args:
        output_path: Where to write the output. Defaults to config/operator_schedules.json.
        registry: Pre-loaded registry dict.
        registry_path: Path to registry JSON.

    Returns:
        Path to the written file.
    """
    out = Path(output_path) if output_path else _DEFAULT_OUTPUT_PATH
    schedules = bind_schedules(registry=registry, registry_path=registry_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schedules, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    result_path = write_schedules()
    data = json.loads(result_path.read_text(encoding="utf-8"))
    print(f"Wrote {len(data.get('bindings', {}))} bindings to {result_path}")
    for name, b in data.get("bindings", {}).items():
        cron_str = b.get("cron") or "(manual)"
        print(f"  {name}: {b['type']} — {cron_str}")
