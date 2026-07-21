"""`collect-social` CLI — 5 backend choices + 4 exit codes per S03 §C5 + O7.

Per S03 design §C5 acceptance:
  - Subcommand surface: `collect-social --backend {browser|rss|manual|x_api|auto}
    --limit-accounts N`
  - Exit codes:
      0  success
      1  lease unavailable → fell back to a secondary backend
      2  rate-limit breached (per-account or global)
      3  config error (invalid args / missing accounts / unknown backend)

The CLI is a thin orchestrator: it parses args, asks the pipeline
collaborators for status, and prints a JSON envelope. The actual
pipeline lives in C4 (`pipeline.py`). Until C4 lands, the CLI exposes
a hook (`run_callback`) so C4 can wire its `Pipeline.run(...)` in
without touching this module.

Exit-code semantics are surfaced as constants so tests can assert on
them without re-reading the spec.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from .status_surface import (
    STATUS_INDICATORS,
    VALID_SCAN_STATES,
    StatusInput,
    StatusSurface,
)

logger = logging.getLogger(__name__)

# --- Exit codes per O7 -------------------------------------------------------

EXIT_OK = 0
EXIT_LEASE_FALLBACK = 1
EXIT_RATE_LIMIT = 2
EXIT_CONFIG_ERROR = 3

EXIT_CODES: Tuple[int, ...] = (
    EXIT_OK,
    EXIT_LEASE_FALLBACK,
    EXIT_RATE_LIMIT,
    EXIT_CONFIG_ERROR,
)

# --- Backend choices per O1 --------------------------------------------------

BACKEND_BROWSER = "browser"
BACKEND_RSS = "rss"
BACKEND_MANUAL = "manual"
BACKEND_X_API = "x_api"
BACKEND_AUTO = "auto"

BACKEND_CHOICES: Tuple[str, ...] = (
    BACKEND_BROWSER,
    BACKEND_RSS,
    BACKEND_MANUAL,
    BACKEND_X_API,
    BACKEND_AUTO,
)

# CLI backend name → schema-level backend name. `auto` is resolved by
# the BackendSelector (C4), not the CLI.
CLI_TO_SCHEMA_BACKEND = {
    BACKEND_BROWSER: "browser_agent",
    BACKEND_RSS: "rss_public",
    BACKEND_MANUAL: "manual_curated",
    BACKEND_X_API: "x_api",
}


# --- Shared types -----------------------------------------------------------


@dataclass
class CliRunResult:
    """Pipeline → CLI handoff.

    `exit_code` must be one of `EXIT_CODES`. `payload` is the JSON body
    printed to stdout.
    """

    exit_code: int
    status: StatusInput
    message: str = ""


# Signature for C4's wiring hook.
RunCallback = Callable[["CliArgs"], CliRunResult]


@dataclass
class CliArgs:
    """Validated CLI arguments."""

    backend: str
    limit_accounts: Optional[int]
    json_only: bool


# --- Argument parsing -------------------------------------------------------


class _SilentArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that raises instead of calling sys.exit on errors.

    This lets `main(argv, ...)` map parser failures to `EXIT_CONFIG_ERROR`
    without leaking SystemExit codes that aren't in our 0/1/2/3 set.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ConfigError(message)


class _ConfigError(Exception):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = _SilentArgumentParser(
        prog="collect-social",
        description="Collect social posts (X 大咖监控) — multi-backend selector.",
    )
    parser.add_argument(
        "--backend",
        required=True,
        choices=list(BACKEND_CHOICES),
        help="Which backend to use. `auto` defers to BackendSelector.",
    )
    parser.add_argument(
        "--limit-accounts",
        type=int,
        default=None,
        help="Cap the number of accounts collected this run.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Suppress human prose; emit only the JSON envelope.",
    )
    return parser


def parse_args(argv: Sequence[str]) -> CliArgs:
    parser = build_parser()
    namespace = parser.parse_args(argv)
    if namespace.limit_accounts is not None and namespace.limit_accounts < 1:
        raise _ConfigError("--limit-accounts must be a positive integer")
    return CliArgs(
        backend=namespace.backend,
        limit_accounts=namespace.limit_accounts,
        json_only=namespace.json_only,
    )


# --- Default / no-pipeline behaviour ----------------------------------------


def _default_pipeline_unavailable(args: CliArgs) -> CliRunResult:
    """Fallback used when no `run_callback` is wired (e.g. CLI invoked
    before C4 lands).

    Returns `EXIT_LEASE_FALLBACK` with a 'no pipeline wired' status so
    tests can assert on the deterministic shape.
    """
    status = StatusInput(
        total_accounts=0,
        enabled_accounts=0,
        scanned_today=0,
        browser_ready=False,
        scan_state="idle",
        parse_fail_count=0,
        by_backend_count={},
    )
    return CliRunResult(
        exit_code=EXIT_LEASE_FALLBACK,
        status=status,
        message=(
            "no pipeline wired (C4 not yet integrated). "
            f"Requested backend={args.backend}, "
            f"limit_accounts={args.limit_accounts}. "
            "Returning fallback exit code."
        ),
    )


# --- Top-level entry --------------------------------------------------------


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    run_callback: Optional[RunCallback] = None,
    stdout=None,
    stderr=None,
    surface: Optional[StatusSurface] = None,
) -> int:
    """Run the CLI, return an exit code in `EXIT_CODES`."""
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    surface = surface or StatusSurface()
    argv_list: List[str] = list(sys.argv[1:] if argv is None else argv)

    try:
        cli_args = parse_args(argv_list)
    except _ConfigError as exc:
        err.write(f"collect-social: config error: {exc}\n")
        return EXIT_CONFIG_ERROR

    callback = run_callback or _default_pipeline_unavailable
    try:
        result = callback(cli_args)
    except Exception as exc:  # noqa: BLE001 — CLI surface must never crash mid-run.
        err.write(f"collect-social: pipeline error: {exc}\n")
        return EXIT_CONFIG_ERROR

    if result.exit_code not in EXIT_CODES:
        err.write(
            f"collect-social: pipeline returned invalid exit_code={result.exit_code}\n"
        )
        return EXIT_CONFIG_ERROR

    envelope = {
        "backend": cli_args.backend,
        "limit_accounts": cli_args.limit_accounts,
        "exit_code": result.exit_code,
        "status": surface.render(result.status),
        "message": result.message,
    }
    out.write(json.dumps(envelope, indent=2, sort_keys=False))
    out.write("\n")
    return result.exit_code


if __name__ == "__main__":  # pragma: no cover - exercised via tests
    sys.exit(main())
