#!/usr/bin/env python3
"""contract_gate_executor — runs a contracted stage's non-LLM evaluator gate.

The workflow-contract schema admits evaluator_gate kinds none |
deterministic_command | llm_eval. The structure guard enforces them, but until
P3 nothing EXECUTED the first two — `evaluator_gate` was consumed only by the
guard, so any contracted stage without an llm_eval gate wedged in `reviewing`
(found by the P3 rehearsal; both P2 contracts are all-llm_eval, so latent).

Design: this executor is a DETERMINISTIC EVALUATOR. It produces the exact
sidecar pair a live evaluator produces ({sid}.{node}-eval.json + -eval.md,
stamped with the node's current generation), so the proven consume machinery
— sidecar reconcile -> mark_node_result -> ledger eval_verdict -> repair on
FAIL — runs unchanged. No new consumption path, no fabricated provenance:
generation_mode says exactly what produced the verdict.

Verdict mapping:
- exit 0            -> PASS, verdict_kind "content"
- nonzero exit      -> FAIL, verdict_kind "content" (a real content judgment)
- unrunnable/timeout-> FAIL, verdict_kind "infrastructure" (AC-R4.1 already
                       prevents infrastructure FAILs from flipping
                       policy-passed nodes)
- gate kind "none"  -> PASS, generation_mode "evaluator_gate_none" (records
                       that the contract declares no evaluator for the stage;
                       the proof gate still applies at mark time)

Command convention (commands arrive fully substituted from instantiate()):
- `research <args>`   -> [sys.executable, -m, research.cli, <args>]
- `python3 <x.py> ..` -> [sys.executable, <x.py>, ..]
- anything else       -> bash -lc <command>
CWD = HARNESS_DIR (the same anchor the artifact manifest uses, so relative
artifact roots like workspace/... and harness-shipped scripts/ resolve
identically in dev checkouts and installed/sandbox harnesses). Timeout:
SOLAR_CONTRACT_GATE_TIMEOUT_SEC (default 300s).
"""
from __future__ import annotations

import datetime
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

EXECUTABLE_GATE_KINDS = {"none", "deterministic_command"}
_OUTPUT_TAIL_CHARS = 4000


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _harness_dir() -> Path:
    return Path(
        os.environ.get("HARNESS_DIR")
        or os.environ.get("SOLAR_HARNESS_DIR")
        or Path.home() / ".solar" / "harness"
    )


def _timeout_seconds() -> float:
    try:
        return float(os.environ.get("SOLAR_CONTRACT_GATE_TIMEOUT_SEC", "300"))
    except Exception:
        return 300.0


def _plan_validator_enabled() -> bool:
    # G4 default-on: the validator is the runtime default; explicit 0 kills it.
    return str(os.environ.get("SOLAR_PLAN_VALIDATOR", "") or "").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _sprint_is_certified_generic(sprints_dir: Path, sid: str) -> bool:
    """True when the sprint's task graph is the pm.generic.v1 kind.

    G4 default-on audit (blocker 1): pytest hardening keyed on the flag
    alone would, once the flag defaults on, break fixed-contract suites
    that keep fixtures in a local conftest.py (the REVIEW-FIXROUND2
    finding-6 legacy case). The hardening target is planner-authored
    generic gates, so key on the GRAPH KIND: fixed contracts and legacy
    uncontracted graphs keep byte-identical pytest behavior regardless of
    the flag."""
    try:
        graph = json.loads(
            (sprints_dir / f"{sid}.task_graph.json").read_text(encoding="utf-8")
        )
        return str(graph.get("workflow_contract_id") or "").strip() == "pm.generic.v1"
    except Exception:
        return False


def recover_stray_workdir(sprints_dir: Any, sid: str) -> Dict[str, Any]:
    """Relocate sprints/<sid>.workdir content into the canonical sprint workdir.

    G4-lite run 2 (p5-g4-lite-live-rung-20260710T133158Z): the builder agent —
    cwd correctly set to sprints/<sid>/workdir — constructed an ABSOLUTE path
    by analogy with the sprint's dot-suffixed artifact files and wrote real
    work under sprints/<sid>.workdir; the canonical workdir stayed empty and
    the proof gate failed a functionally-passing node (patch emission:
    no_write_scope_targets). Same recovery philosophy as the P2 closeout
    exact-basename net: relocate real work onto the declared vocabulary,
    never overwrite, record what moved. Certified-generic sprints only;
    kill switch SOLAR_WORKDIR_STRAY_RECOVERY=0."""
    result: Dict[str, Any] = {"recovered": [], "skipped_existing": []}
    try:
        if str(os.environ.get("SOLAR_WORKDIR_STRAY_RECOVERY", "") or "").strip().lower() in {
            "0", "false", "no", "off",
        }:
            return result
        sprints = Path(sprints_dir)
        if not _sprint_is_certified_generic(sprints, sid):
            return result
        stray_root = sprints / f"{sid}.workdir"
        if not stray_root.is_dir():
            return result
        canonical_root = sprints / sid / "workdir"
        canonical_root.mkdir(parents=True, exist_ok=True)
        for stray in sorted(stray_root.rglob("*")):
            if not stray.is_file():
                continue
            rel = stray.relative_to(stray_root)
            target = canonical_root / rel
            if target.exists():
                result["skipped_existing"].append(str(rel))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stray, target)
            result["recovered"].append(str(rel))
        # remove emptied stray directories so the split cannot re-confuse a
        # later scan; anything non-empty (skipped collisions) stays in place
        for leftover in sorted(stray_root.rglob("*"), reverse=True):
            if leftover.is_dir():
                try:
                    leftover.rmdir()
                except OSError:
                    pass
        try:
            stray_root.rmdir()
        except OSError:
            pass
        return result
    except Exception:
        return result


def _gate_argv(command: str) -> list[str] | None:
    """Map a contract gate command string to argv; None means bash -lc."""
    try:
        # POSIX shlex treats every backslash as an escape. Contract
        # substitution emits native Windows paths, so ``sprints\sid`` became
        # ``sprintssid`` and a valid artifact was evaluated as missing.
        argv = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return None
    if not argv:
        return None
    head = argv[0]
    if head == "research":
        return [sys.executable, "-m", "research.cli", *argv[1:]]
    if head in {"python3", "python"}:
        return [sys.executable, *argv[1:]]
    return None


def _node_generation(node: Dict[str, Any]) -> int:
    raw = node.get("repair_attempts")
    try:
        return max(0, int(raw or 0))
    except Exception:
        return 0


def execute_gate(
    sprints_dir: Any,
    sid: str,
    node: Dict[str, Any],
    gate: Dict[str, Any],
    *,
    harness_dir: Optional[os.PathLike] = None,
    artifact_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a none/deterministic_command gate; write the eval sidecar pair.

    Returns {ok, verdict, verdict_kind, eval_json, eval_md, exit_code}.
    Never raises on gate failure — a failing gate is a verdict, not an error.
    """
    node_id = str(node.get("id") or "")
    kind = str(gate.get("kind") or "none")
    generation = _node_generation(node)
    sprints = Path(sprints_dir)
    sprints.mkdir(parents=True, exist_ok=True)
    eval_json_path = sprints / f"{sid}.{node_id}-eval.json"
    eval_md_path = sprints / f"{sid}.{node_id}-eval.md"

    if kind == "none":
        verdict, verdict_kind, exit_code = "PASS", "content", 0
        generation_mode = "evaluator_gate_none"
        command = ""
        summary = (
            "Contract declares no evaluator gate for this stage "
            "(evaluator_gate.kind=none); policy pass recorded. The proof gate "
            "(manifest/proof obligations) still applies at mark time."
        )
        output_tail = ""
        duration = 0.0
    else:
        command = str(gate.get("command") or "").strip()
        generation_mode = "deterministic_command"
        started = datetime.datetime.now(datetime.timezone.utc)
        argv = _gate_argv(command)
        # Pytest hardening is scoped to the plan-validator flag (fix-round 2
        # finding 6) AND to the sprint's graph being certified-generic (G4
        # default-on audit, blocker 1): validator-governed PLANNER gates must
        # not import conftest.py or env-named plugins, but fixed-contract and
        # legacy uncontracted gates (e.g. code.cli_smoke's
        # sprints/<sid>/workdir/tests suite, whose fixtures live in a local
        # conftest.py) keep legacy pytest behavior even when the flag
        # defaults on.
        harden_pytest = (
            argv is not None
            and argv[1:3] == ["-m", "pytest"]
            and _plan_validator_enabled()
            and _sprint_is_certified_generic(sprints, sid)
        )
        if harden_pytest:
            # G2b review finding 3: pytest auto-imports conftest.py from every
            # positional path's directory chain, so a planner/builder-writable
            # directory would contribute import-time code and config to the
            # gate process. Gate suites must keep fixtures inside test files.
            argv = [*argv, "--noconftest"]
        harness = Path(harness_dir) if harness_dir else _harness_dir()
        # G3 run-5 fix (p5-g3-live-rung-20260709T210652Z): builders execute
        # with work_dir = sprints/<sid>/workdir and write canonical-alias
        # paths (workspace/...) relative to it, but this gate ran from
        # HARNESS_DIR — the contract's workspace/ ≡ sprints/<sid>/workdir/
        # alias equivalence exists only at validation time, so the gate
        # exited 4 on files the builder had genuinely written (F-CLASS-16
        # live on the generic path). Certified-generic gates now run from
        # the builder's anchor; fixed contracts keep HARNESS_DIR (their
        # commands address sprints/<sid>/... forms — the P2/P3 convention).
        gate_cwd = harness
        if _sprint_is_certified_generic(sprints, sid):
            # G4-lite run 2: builder output may sit under the stray
            # sprints/<sid>.workdir spelling — relocate BEFORE cwd selection
            # so the gate judges the real work.
            recover_stray_workdir(sprints, sid)
            workdir = sprints / sid / "workdir"
            if workdir.is_dir():
                gate_cwd = workdir
                if argv is not None and argv[1:3] == ["-m", "pytest"]:
                    # the contract's alias forms (sprints/<sid>/workdir/X,
                    # workdir/X) are validation-legal spellings of the same
                    # root — normalize them onto the new cwd
                    aliases = (f"sprints/{sid}/workdir/", "workdir/")
                    rewritten = list(argv[:3])
                    for token in argv[3:]:
                        if not token.startswith("-"):
                            for alias in aliases:
                                if token.startswith(alias):
                                    token = token[len(alias):]
                                    break
                        rewritten.append(token)
                    argv = rewritten
                elif (
                    argv is not None
                    and len(argv) >= 2
                    and not (gate_cwd / argv[1]).exists()
                    and (harness / argv[1]).exists()
                ):
                    # allowlisted harness-shipped scripts (e.g. scripts/...)
                    # still resolve against the harness when cwd moves
                    argv = [argv[0], str(harness / argv[1]), *argv[2:]]
        popen_args: Any = argv if argv is not None else ["bash", "-lc", command]
        env = dict(os.environ)
        if harden_pytest:
            # fix-round 2 finding 3: inherited PYTEST_ADDOPTS / PYTEST_PLUGINS
            # load caller-named plugins inside the gate process, overriding
            # the isolation --noconftest establishes.
            env.pop("PYTEST_ADDOPTS", None)
            env.pop("PYTEST_PLUGINS", None)
        lib_dir = str(harness / "lib")
        env["PYTHONPATH"] = os.pathsep.join(
            [lib_dir, env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        try:
            proc = subprocess.run(
                popen_args,
                cwd=str(gate_cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=_timeout_seconds(),
            )
            exit_code = int(proc.returncode)
            output_tail = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-_OUTPUT_TAIL_CHARS:]
            if exit_code == 0:
                verdict, verdict_kind = "PASS", "content"
                summary = f"Deterministic gate passed: `{command}` exit 0."
            elif exit_code in (2, 4) or _looks_unrunnable(output_tail):
                # pytest exit 4 = usage error (e.g. file or directory not
                # found) — a mechanical miss, not a content judgment
                # (F-CLASS-10; G3 run 5 burned S2's repair budget on one)
                # argparse usage errors / missing interpreter targets are
                # machinery failures, not content judgments
                verdict, verdict_kind = "FAIL", "infrastructure"
                summary = f"Deterministic gate could not run meaningfully: `{command}` exit {exit_code}."
            else:
                verdict, verdict_kind = "FAIL", "content"
                summary = f"Deterministic gate failed: `{command}` exit {exit_code}."
        except subprocess.TimeoutExpired:
            exit_code = -1
            output_tail = f"timeout after {_timeout_seconds()}s"
            verdict, verdict_kind = "FAIL", "infrastructure"
            summary = f"Deterministic gate timed out: `{command}`."
        except Exception as exc:
            exit_code = -1
            output_tail = f"{type(exc).__name__}: {exc}"
            verdict, verdict_kind = "FAIL", "infrastructure"
            summary = f"Deterministic gate unrunnable: `{command}` ({type(exc).__name__})."
        duration = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()

    payload = {
        "node_id": node_id,
        "verdict": verdict,
        "verdict_kind": verdict_kind,
        "summary": summary,
        "eval_generation": generation,
        "repair_attempt": generation,
        "generation_mode": generation_mode,
        "gate_kind": kind,
        "command": command,
        "exit_code": exit_code,
        "duration_seconds": round(duration, 3),
        "evaluated_at": _utc_now(),
        "artifact_snapshot_schema": str((artifact_snapshot or {}).get("schema") or ""),
        "artifact_snapshot_path": str((artifact_snapshot or {}).get("path") or ""),
        "artifact_snapshot_digest": str((artifact_snapshot or {}).get("snapshot_digest") or ""),
    }
    tmp = str(eval_json_path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    os.replace(tmp, str(eval_json_path))

    md_lines = [
        f"# {node_id} deterministic gate report",
        "",
        f"- verdict: **{verdict}** ({verdict_kind})",
        f"- gate kind: {kind}",
        f"- command: `{command}`" if command else "- command: (none — contract declares no evaluator gate)",
        f"- exit code: {exit_code}",
        f"- generation: {generation}",
        f"- evaluated at: {payload['evaluated_at']}",
        f"- artifact snapshot: `{payload['artifact_snapshot_digest']}`",
        "",
        summary,
    ]
    if output_tail.strip():
        md_lines += ["", "## Output tail", "", "```", output_tail.strip(), "```"]
    eval_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return {
        "ok": verdict == "PASS",
        "verdict": verdict,
        "verdict_kind": verdict_kind,
        "eval_json": str(eval_json_path),
        "eval_md": str(eval_md_path),
        "exit_code": exit_code,
    }


def _looks_unrunnable(output_tail: str) -> bool:
    markers = (
        "can't open file",
        "No such file or directory",
        "ModuleNotFoundError",
        "command not found",
        "file or directory not found",  # pytest usage-error phrasing (exit 4)
    )
    return any(marker in output_tail for marker in markers)
