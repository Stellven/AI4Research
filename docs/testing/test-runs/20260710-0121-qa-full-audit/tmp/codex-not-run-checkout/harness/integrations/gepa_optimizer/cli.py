"""
gepa_optimizer CLI — propose / run / review / promote / rollback / status

Entry point::

    python -m integrations.gepa_optimizer.cli <subcommand> [options]

Safety contract
---------------
* Default mode is **dry-run / proposal only** — no mutations without ``--execute``.
* ``run --execute`` is rejected unless ALL THREE budget caps are present:
  ``--max-evals``, ``--max-spend``, and ``--max-walltime``.
* Promotion target must be ``/tmp/...``; production paths are rejected.
* No secrets are printed; no cloud LLM spend except through the evaluator sandbox.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import NoReturn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROD_PATH_PREFIXES: tuple[str, ...] = (
    "/etc/",
    "/usr/",
    "/opt/",
    "/var/",
    os.path.expanduser("~/.claude/"),
    os.path.expanduser("~/.solar/harness/config/"),
    os.path.expanduser("~/.solar/harness/integrations/"),
)


def _is_safe_promotion_target(path: str) -> bool:
    """Return True only for paths under /tmp or explicit test fixtures.

    On macOS /tmp is a symlink to /private/tmp, so we resolve both the
    candidate path and the /tmp anchor before comparing.
    """
    resolved = str(Path(path).resolve())
    tmp_resolved = str(Path("/tmp").resolve())
    # Accept /tmp itself or any path beneath it.
    if resolved == tmp_resolved or resolved.startswith(tmp_resolved + "/"):
        return True
    return False


def _reject_production_path(path: str, flag: str) -> None:
    resolved = str(Path(path).resolve())
    for prefix in _PROD_PATH_PREFIXES:
        if resolved.startswith(str(Path(prefix).resolve())):
            _die(
                f"[SAFETY] {flag} path '{path}' resolves to a production prefix "
                f"'{prefix}'. Refusing to proceed."
            )


def _die(msg: str, code: int = 1) -> NoReturn:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _print_json(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _dry_run_notice(cmd: str) -> None:
    print(
        f"[DRY-RUN] Would execute: {cmd}\n"
        "  Pass --execute with ALL THREE budget caps (--max-evals, --max-spend,\n"
        "  --max-walltime) to enable real execution.",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Subcommand: propose
# ---------------------------------------------------------------------------

def _cmd_propose(args: argparse.Namespace) -> int:
    """Analyse the target and print an optimisation proposal (no mutations)."""
    proposal = {
        "command": "propose",
        "target": args.target,
        "operator": args.operator,
        "dry_run": True,
        "status": "proposal_only",
        "message": (
            "No optimisation run was started. "
            "Review this proposal and use 'run --execute' with budget caps to proceed."
        ),
    }

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(proposal, indent=2))
        print(f"[propose] Proposal written to {args.output}", file=sys.stderr)
    else:
        _print_json(proposal)

    return 0


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------

def _cmd_run(args: argparse.Namespace) -> int:
    """Run the GEPA optimiser.

    Dry-run by default.  Real execution requires ``--execute`` AND all three
    budget caps (``--max-evals``, ``--max-spend``, ``--max-walltime``).
    """
    if args.execute:
        # Validate that ALL THREE budget caps are present.
        missing: list[str] = []
        if args.max_evals is None:
            missing.append("--max-evals")
        if args.max_spend is None:
            missing.append("--max-spend")
        if args.max_walltime is None:
            missing.append("--max-walltime")

        if missing:
            _die(
                f"[SAFETY] '--execute' requires ALL THREE budget caps. "
                f"Missing: {', '.join(missing)}"
            )

        print(
            f"[run] Executing optimisation for target='{args.target}' "
            f"(max-evals={args.max_evals}, max-spend={args.max_spend}, "
            f"max-walltime={args.max_walltime}s)",
            file=sys.stderr,
        )

        # Lazy import so that dry-run never touches GEPA.
        try:
            from integrations.gepa_optimizer.adapter import GEPAAdapter, GEPAConfig
            from integrations.gepa_optimizer.budgets import (
                Budget,
                EvalStopper,
                SpendStopper,
                WalltimeStopper,
            )
            from integrations.gepa_optimizer.artifact_store import ArtifactStore
        except ImportError as exc:
            _die(f"Required module not available: {exc}")

        budget = Budget(
            max_evals=args.max_evals,
            max_spend_usd=args.max_spend,
            max_walltime_seconds=args.max_walltime,
        )
        cfg = GEPAConfig(target=args.target, operator=args.operator)
        store = ArtifactStore(run_dir=args.run_dir or f"/tmp/gepa_run_{os.getpid()}")
        adapter = GEPAAdapter(config=cfg, store=store)

        result = adapter.run(budget=budget)
        _print_json(result)
        return 0

    # Default: dry-run / proposal
    _dry_run_notice(
        f"gepa optimize_anything target={args.target!r} "
        f"max-evals={args.max_evals} max-spend={args.max_spend} "
        f"max-walltime={args.max_walltime}"
    )
    proposal = {
        "command": "run",
        "target": args.target,
        "operator": args.operator,
        "execute": False,
        "status": "dry_run",
        "budget": {
            "max_evals": args.max_evals,
            "max_spend_usd": args.max_spend,
            "max_walltime_seconds": args.max_walltime,
        },
    }
    _print_json(proposal)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: review
# ---------------------------------------------------------------------------

def _cmd_review(args: argparse.Namespace) -> int:
    """Show candidates and Pareto front from a completed run."""
    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        _die(f"Run directory not found: {run_dir}")

    summary_path = run_dir / "summary.json"
    pareto_path = run_dir / "pareto.json"

    result: dict[str, object] = {
        "command": "review",
        "run_dir": str(run_dir),
    }

    if summary_path.exists():
        result["summary"] = json.loads(summary_path.read_text())
    else:
        result["summary"] = "(no summary.json found)"

    if pareto_path.exists():
        result["pareto"] = json.loads(pareto_path.read_text())
    else:
        result["pareto"] = "(no pareto.json found)"

    _print_json(result)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: promote
# ---------------------------------------------------------------------------

def _cmd_promote(args: argparse.Namespace) -> int:
    """Promote a candidate from a run directory to the target path.

    Safety: target must be under /tmp.  Production paths are rejected.
    """
    if not _is_safe_promotion_target(args.target):
        _die(
            f"[SAFETY] Promotion target '{args.target}' is not under /tmp. "
            "Production promotion is not allowed. Use /tmp/gepa_seed.txt or similar."
        )

    _reject_production_path(args.target, "--target")

    if args.execute:
        print(f"[promote] Promoting candidate '{args.candidate}' → '{args.target}'", file=sys.stderr)
        try:
            from integrations.gepa_optimizer.promote import Promoter, PromotionTarget
        except ImportError as exc:
            _die(f"Required module not available: {exc}")

        pt = PromotionTarget(path=args.target)
        promoter = Promoter()
        diff = promoter.promote(
            run_dir=args.run_dir,
            candidate_id=args.candidate,
            target=pt,
        )
        _print_json({"command": "promote", "status": "promoted", "diff": diff})
        return 0

    # Dry-run default
    _dry_run_notice(
        f"promote candidate={args.candidate!r} from run_dir={args.run_dir!r} "
        f"to target={args.target!r}"
    )
    _print_json(
        {
            "command": "promote",
            "status": "dry_run",
            "candidate": args.candidate,
            "run_dir": args.run_dir,
            "target": args.target,
        }
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: rollback
# ---------------------------------------------------------------------------

def _cmd_rollback(args: argparse.Namespace) -> int:
    """Roll back the last promotion at the given target path."""
    if not _is_safe_promotion_target(args.target):
        _die(
            f"[SAFETY] Rollback target '{args.target}' is not under /tmp. "
            "Production rollback is not allowed via this CLI."
        )

    _reject_production_path(args.target, "--target")

    if args.execute:
        print(f"[rollback] Rolling back '{args.target}'", file=sys.stderr)
        try:
            from integrations.gepa_optimizer.promote import Promoter, PromotionTarget, RollbackError
        except ImportError as exc:
            _die(f"Required module not available: {exc}")

        pt = PromotionTarget(path=args.target)
        promoter = Promoter()
        try:
            promoter.rollback(target=pt)
        except RollbackError as exc:
            _die(f"Rollback failed: {exc}")

        _print_json({"command": "rollback", "status": "rolled_back", "target": args.target})
        return 0

    _dry_run_notice(f"rollback target={args.target!r}")
    _print_json({"command": "rollback", "status": "dry_run", "target": args.target})
    return 0


# ---------------------------------------------------------------------------
# Subcommand: status
# ---------------------------------------------------------------------------

def _cmd_status(args: argparse.Namespace) -> int:
    """Show the status of a run directory (or list recent runs)."""
    if args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.exists():
            _die(f"Run directory not found: {run_dir}")

        status_path = run_dir / "status.json"
        if status_path.exists():
            _print_json(json.loads(status_path.read_text()))
        else:
            _print_json(
                {
                    "run_dir": str(run_dir),
                    "status": "unknown",
                    "message": "No status.json found in run directory.",
                }
            )
    else:
        # List recent runs under /tmp matching gepa_run_*
        import glob

        runs = sorted(glob.glob("/tmp/gepa_run_*"), reverse=True)[:10]
        _print_json(
            {
                "command": "status",
                "recent_runs": runs,
                "count": len(runs),
                "hint": "Pass --run-dir <path> to inspect a specific run.",
            }
        )
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gepa_optimizer",
        description=textwrap.dedent(
            """\
            GEPA Optimizer CLI — safe interface to gepa.optimize_anything.

            Default mode is DRY-RUN (no mutations).  Pass --execute with ALL THREE
            budget caps to enable real optimisation runs.
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ---- propose ----
    p_propose = sub.add_parser(
        "propose",
        help="Analyse target and print an optimisation proposal (no mutations).",
    )
    p_propose.add_argument("target", help="Optimisation target string or path.")
    p_propose.add_argument("--operator", default=None, help="Physical operator name.")
    p_propose.add_argument("--output", default=None, help="Write proposal JSON to file.")

    # ---- run ----
    p_run = sub.add_parser(
        "run",
        help="Run the GEPA optimiser (dry-run by default; use --execute for real run).",
    )
    p_run.add_argument("target", help="Optimisation target string or path.")
    p_run.add_argument("--operator", default=None, help="Physical operator name.")
    p_run.add_argument("--run-dir", default=None, dest="run_dir", help="Artifact output directory.")
    p_run.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Enable real execution (requires ALL THREE budget caps).",
    )
    p_run.add_argument(
        "--max-evals",
        type=int,
        default=None,
        dest="max_evals",
        metavar="N",
        help="Maximum number of evaluations (required with --execute).",
    )
    p_run.add_argument(
        "--max-spend",
        type=float,
        default=None,
        dest="max_spend",
        metavar="USD",
        help="Maximum spend in USD (required with --execute).",
    )
    p_run.add_argument(
        "--max-walltime",
        type=int,
        default=None,
        dest="max_walltime",
        metavar="SECONDS",
        help="Maximum wall-clock time in seconds (required with --execute).",
    )

    # ---- review ----
    p_review = sub.add_parser(
        "review",
        help="Show candidates and Pareto front from a completed run.",
    )
    p_review.add_argument("run_dir", help="Path to the run artifact directory.")

    # ---- promote ----
    p_promote = sub.add_parser(
        "promote",
        help="Promote a candidate to the target path (must be under /tmp).",
    )
    p_promote.add_argument("run_dir", help="Path to the run artifact directory.")
    p_promote.add_argument("candidate", help="Candidate ID to promote.")
    p_promote.add_argument(
        "--target",
        required=True,
        help="Promotion target path.  MUST be under /tmp (e.g. /tmp/gepa_seed.txt).",
    )
    p_promote.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually write the promotion (dry-run by default).",
    )

    # ---- rollback ----
    p_rollback = sub.add_parser(
        "rollback",
        help="Roll back the last promotion at the given target path.",
    )
    p_rollback.add_argument(
        "--target",
        required=True,
        help="Target path that was previously promoted to.",
    )
    p_rollback.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually perform rollback (dry-run by default).",
    )

    # ---- status ----
    p_status = sub.add_parser(
        "status",
        help="Show status of a run directory or list recent runs.",
    )
    p_status.add_argument(
        "--run-dir",
        default=None,
        dest="run_dir",
        help="Path to the run artifact directory.  Omit to list recent runs.",
    )

    return parser


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_COMMANDS: dict[str, object] = {
    "propose": _cmd_propose,
    "run": _cmd_run,
    "review": _cmd_review,
    "promote": _cmd_promote,
    "rollback": _cmd_rollback,
    "status": _cmd_status,
}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = _COMMANDS[args.command]
    return handler(args)  # type: ignore[operator]


if __name__ == "__main__":
    sys.exit(main())
