#!/usr/bin/env python3
"""Run an AutoSci skill and hand its runtime evidence to the AutoSci bridge.

The bridge (``autosci_bridge.py``) verifies runtime evidence and converts it to
typed Solar evidence; it does not execute anything. AutoSci's real executor is
an agent running its skills (``$ideate``, ``$exp-design``, ``$exp-run``,
``$exp-status``, ``$exp-eval``, ``$paper-draft``). Nothing occupied that seam,
which is why Part B was reimplemented as Solar command operators instead of
using the bridge that already existed.

This executor is that seam. For one stage it:

1. runs the stage's AutoSci skill through the Codex CLI inside the configured
   AutoSci checkout,
2. writes a runtime record with the real exit code, command, streams, and any
   result path the skill produced,
3. rewrites the operator envelope so ``inputs.runtime_evidence`` points at that
   record,
4. invokes the matching bridge action and returns its typed evidence.

It never synthesises a runtime record. A failed or unavailable skill run is
recorded with its real non-zero exit code so the bridge fails closed, which is
the behaviour the governance depends on now that no approval node precedes
execution.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BRIDGE = Path(__file__).resolve().parent / "autosci_bridge.py"

# stage -> (AutoSci skill invocation, bridge action)
STAGES: dict[str, tuple[str, str]] = {
    "idea_generation": ("$ideate", "generate_ideas"),
    "idea_evaluation": ("$ideate", "evaluate_ideas"),
    "experiment_design": ("$exp-design", "design_experiment"),
    "experiment_run": ("$exp-run", "run_experiment"),
    "experiment_monitor": ("$exp-status", "monitor_experiment"),
    "claim_verification": ("$exp-eval", "verify_claim"),
    "report_delivery": ("$paper-draft", "write_report"),
}

# Only the first stage takes the free-text request. Every later skill takes an
# identifier the previous stage wrote into the AutoSci wiki:
#
#   $ideate      [topic]                    -> writes wiki/ideas/{slug}.md
#   $exp-design  <idea-slug>                -> writes wiki/experiments/{slug}.md
#   $exp-run     <experiment-slug>          -> moves that page planned -> running -> completed
#   $exp-status  --pipeline <slug>
#   $exp-eval    <experiment-slug>
#   $paper-draft <paper-plan-path>          -> reads wiki/outputs/paper-plan-*.md
#
# Passing the original request to any of them, which is what this executor used
# to do, cannot resolve to an idea or an experiment, so Part B could never get
# past experiment_design. The wiki is AutoSci's own state store and is how its
# skills chain to each other, so that is what the resolvers read.
ARGUMENT_SOURCES: dict[str, dict[str, Any]] = {
    "idea_generation": {"kind": "request"},
    "idea_evaluation": {"kind": "request"},
    "experiment_design": {"kind": "wiki_slug", "collection": "ideas", "statuses": ("proposed",)},
    "experiment_run": {"kind": "wiki_slug", "collection": "experiments", "statuses": ("planned", "running")},
    "experiment_monitor": {"kind": "wiki_slug", "collection": "experiments", "statuses": ("running", "planned")},
    "claim_verification": {"kind": "wiki_slug", "collection": "experiments", "statuses": ("completed", "running")},
    "report_delivery": {"kind": "paper_plan"},
}

# The user's contract for this workflow is that nothing pauses for approval, so
# every skill that offers a non-interactive mode is told to use it. A skill that
# stops to ask a question inside `codex exec` would hang until the timeout and
# then be recorded as a real failure, which is correct but useless.
STAGE_FLAGS: dict[str, tuple[str, ...]] = {
    "idea_generation": ("--auto",),
    "idea_evaluation": ("--auto",),
    "experiment_run": ("--full",),
    "experiment_monitor": ("--auto-advance",),
    "claim_verification": ("--auto",),
}

# Never forward an inherited provider credential into the skill subprocess; the
# Codex CLI authenticates from its own CODEX_HOME.
SECRET_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
}


class ExecutorError(RuntimeError):
    """The executor failed closed before producing runtime evidence."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _autosci_home() -> Path:
    raw = str(os.environ.get("SOLAR_AUTOSCI_HOME") or "").strip()
    if not raw:
        raise ExecutorError(
            "SOLAR_AUTOSCI_HOME is not set; the AutoSci checkout location is "
            "machine-specific and has no safe default"
        )
    home = Path(raw).expanduser()
    if not home.is_dir():
        raise ExecutorError(f"SOLAR_AUTOSCI_HOME is not a directory: {home}")
    return home.resolve()


def _skill_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in SECRET_ENV_KEYS}
    codex_home = str(os.environ.get("SOLAR_CODEX_SOURCE_HOME") or "").strip()
    if codex_home:
        env["CODEX_HOME"] = codex_home
    return env


def _frontmatter(path: Path) -> dict[str, str]:
    """The leading `---` block of a wiki page, as flat string fields.

    Deliberately not a YAML parse: these pages are written by an agent and a
    malformed body must not stop us reading the two fields we need.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("\n")
    block, sep, _ = rest.partition("\n---")
    if not sep:
        return {}
    fields: dict[str, str] = {}
    for line in block.splitlines():
        key, colon, value = line.partition(":")
        if not colon or line.startswith((" ", "\t", "-")):
            continue
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def _wiki_pages(home: Path, collection: str) -> list[Path]:
    root = home / "wiki" / collection
    if not root.is_dir():
        return []
    # Most recently written first, name as the tie-break so the choice is
    # reproducible when two pages share an mtime.
    return sorted(root.glob("*.md"), key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def resolve_stage_argument(*, stage: str, request: str, home: Path) -> dict[str, Any]:
    """Work out what to hand this stage's skill, and record how we decided.

    An explicit override always wins, so a caller that already knows the slug
    can pin it instead of relying on wiki inspection.
    """
    override = str(os.environ.get("SOLAR_AUTOSCI_STAGE_ARGUMENT") or "").strip()
    if override:
        return {"argument": override, "source": "explicit_override", "considered": []}

    source = ARGUMENT_SOURCES.get(stage) or {"kind": "request"}
    kind = str(source.get("kind"))

    if kind == "request":
        if not request:
            raise ExecutorError(f"stage {stage} needs a research topic and none was supplied")
        return {"argument": request, "source": "request", "considered": []}

    if kind == "paper_plan":
        plans = sorted(
            (home / "wiki" / "outputs").glob("paper-plan-*.md"),
            key=lambda p: (p.stat().st_mtime, p.name),
            reverse=True,
        ) if (home / "wiki" / "outputs").is_dir() else []
        if not plans:
            raise ExecutorError(
                "no wiki/outputs/paper-plan-*.md exists; $paper-draft has nothing to draft from "
                "and $paper-plan has not run"
            )
        chosen = plans[0]
        return {
            "argument": str(chosen.relative_to(home)),
            "source": "wiki_paper_plan",
            "considered": [str(p.relative_to(home)) for p in plans[:10]],
        }

    collection = str(source.get("collection") or "")
    wanted = tuple(source.get("statuses") or ())
    considered: list[dict[str, str]] = []
    for page in _wiki_pages(home, collection):
        fields = _frontmatter(page)
        slug = fields.get("slug") or page.stem
        status = fields.get("status", "")
        considered.append({"slug": slug, "status": status, "page": page.name})
        if status in wanted:
            return {
                "argument": slug,
                "source": f"wiki/{collection}",
                "matched_status": status,
                "considered": considered[:10],
            }
    raise ExecutorError(
        f"stage {stage} found no wiki/{collection} page with status in {list(wanted)}; "
        f"the previous stage produced nothing usable (saw {considered[:10] or 'no pages'})"
    )


def run_skill(
    *,
    stage: str,
    request: str,
    record_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run the stage's AutoSci skill and write a truthful runtime record."""
    skill, _action = STAGES[stage]
    home = _autosci_home()
    binary = shutil.which(str(os.environ.get("SOLAR_CODEX_BINARY") or "codex"))
    if not binary:
        raise ExecutorError("Codex CLI is unavailable on PATH")
    model = str(os.environ.get("SOLAR_AUTOSCI_SKILL_MODEL") or "").strip()

    resolved = resolve_stage_argument(stage=stage, request=request, home=home)
    parts = [skill, str(resolved["argument"]), *STAGE_FLAGS.get(stage, ())]
    prompt = " ".join(part for part in parts if part).strip()
    argv = [binary, "exec", "--skip-git-repo-check"]
    if model:
        argv += ["--model", model]
    argv.append(prompt)

    started_at = _now()
    try:
        proc = subprocess.run(
            argv,
            cwd=home,
            env=_skill_env(),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr if isinstance(exc.stderr, str) else "") + f"\ntimed out after {timeout_seconds}s"
        timed_out = True

    record_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path = record_path.with_suffix(".stdout.log")
    stderr_path = record_path.with_suffix(".stderr.log")
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")

    record = {
        "schema": "solar.autosci_skill_runtime.v1",
        "stage": stage,
        "skill": skill,
        "autosci_home": str(home),
        "command_run": " ".join(argv[:-1] + ["<prompt>"]),
        "skill_invocation": prompt,
        "stage_argument": resolved["argument"],
        "stage_argument_source": resolved["source"],
        "stage_argument_candidates": resolved.get("considered") or [],
        "exit_code": exit_code,
        "timed_out": timed_out,
        "started_at": started_at,
        "finished_at": _now(),
        "model": model or "codex-default",
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "logs": [line for line in (stdout or "").splitlines()[-40:] if line.strip()],
        "credential_contents_recorded": False,
    }
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


# Which envelope input names the thing this stage acted on, by wiki collection.
_SUBJECT_KEY_BY_COLLECTION = {"ideas": "idea_id", "experiments": "experiment_id"}


def _bridge_subject_inputs(*, stage: str, record: dict[str, Any]) -> dict[str, str]:
    """Tell the bridge which wiki, and which entity in it, this run was about.

    The bridge can read the AutoSci wiki, but `_should_resolve_wiki_state`
    only turns that on when the envelope carries one of wiki_root, from_wiki,
    target, topic, query, idea_id or experiment_id. An envelope holding only
    `request` matched none of them, so the bridge silently fell back to
    `convert_idea_candidate({})` and emitted typed evidence about the fixture
    `idea-001` while the skill had really just written
    `wiki/ideas/jepa-augmented-transmamba-long-context-abstraction.md`.

    Evidence that passes its gates while describing something other than the
    run it claims to describe is the failure mode this whole workflow exists to
    prevent, so the executor now always states the subject.
    """
    subject: dict[str, str] = {"wiki_root": str(Path(record["autosci_home"]) / "wiki")}
    argument = str(record.get("stage_argument") or "").strip()
    source = ARGUMENT_SOURCES.get(stage) or {}
    key = _SUBJECT_KEY_BY_COLLECTION.get(str(source.get("collection") or ""))
    if key and argument:
        subject[key] = argument
    elif str(source.get("kind")) == "request" and argument:
        # $ideate is given a topic rather than an entity id; the bridge accepts
        # `topic` as a wiki-resolution trigger in its own right.
        subject["topic"] = argument
    return subject


def invoke_bridge(*, action: str, envelope_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BRIDGE), "run", "--action", action, "--envelope", str(envelope_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def execute(args: argparse.Namespace) -> dict[str, Any]:
    stage = args.stage
    if stage not in STAGES:
        raise ExecutorError(f"unknown stage: {stage}")
    _skill, action = STAGES[stage]

    envelope_path = Path(args.envelope).expanduser().resolve(strict=True)
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    if not isinstance(envelope, dict):
        raise ExecutorError("operator envelope must be a JSON object")

    work_dir = Path(args.work_dir).expanduser() if args.work_dir else envelope_path.parent
    run_id = uuid.uuid4().hex[:12]
    record_path = work_dir / "autosci-runtime" / f"{stage}-{run_id}.runtime.json"

    request = str(args.request or (envelope.get("inputs") or {}).get("request") or "").strip()
    record = run_skill(
        stage=stage,
        request=request,
        record_path=record_path,
        timeout_seconds=args.timeout_seconds,
    )

    # Point the bridge at the record we just produced. The bridge decides
    # whether the run counts; the executor never asserts success on its behalf.
    inputs = dict(envelope.get("inputs") or {})
    existing = inputs.get("runtime_evidence")
    entries = list(existing) if isinstance(existing, list) else []
    entries.append({"path": str(record_path), "exists": record_path.is_file()})
    inputs["runtime_evidence"] = entries
    inputs.update(_bridge_subject_inputs(stage=stage, record=record))
    envelope["inputs"] = inputs
    # adapters/solar_envelope_to_autosci.normalize_envelope defaults an
    # unstated mode to "fixture", and the bridge treats a fixture envelope as
    # licence to skip wiki resolution and synthesise evidence from
    # convert_idea_candidate({}). A real skill just ran, so declaring "fixture"
    # by omission is simply false: the first live Part B run produced typed
    # evidence about `idea-001` while $ideate had written a real idea page.
    # State the mode we are actually in and let the bridge read the wiki.
    envelope["mode"] = str(envelope.get("mode") or "solar_native")

    augmented = work_dir / "autosci-runtime" / f"{stage}-{run_id}.envelope.json"
    augmented.parent.mkdir(parents=True, exist_ok=True)
    augmented.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    bridged = invoke_bridge(action=action, envelope_path=augmented)
    try:
        bridge_payload = json.loads(bridged.stdout or "{}")
    except json.JSONDecodeError:
        bridge_payload = {"ok": False, "reason": "bridge_output_not_json", "stdout": bridged.stdout[-2000:]}

    # A clean bridge return is not on its own a successful stage. The first
    # live experiment_design run timed out at 124, wrote no experiment page,
    # and the bridge still returned 0 -- so this reported ok=True for a stage
    # that had produced nothing. Anyone reading the top line would have been
    # told the stage succeeded. The skill's own exit is part of the verdict.
    skill_ok = int(record["exit_code"]) == 0 and not record["timed_out"]
    return {
        "ok": bridged.returncode == 0 and skill_ok,
        "skill_ok": skill_ok,
        "bridge_ok": bridged.returncode == 0,
        "stage": stage,
        "bridge_action": action,
        "skill_exit_code": record["exit_code"],
        "timed_out": record["timed_out"],
        "runtime_record": str(record_path),
        "envelope": str(augmented),
        "bridge_returncode": bridged.returncode,
        "bridge": bridge_payload,
        "bridge_stderr": (bridged.stderr or "")[-2000:],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an AutoSci skill and convert its runtime evidence through the AutoSci bridge",
        epilog="stages: " + ", ".join(sorted(STAGES)),
    )
    parser.add_argument("--stage", required=True, choices=sorted(STAGES))
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--request", default="")
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = execute(args)
    except (ExecutorError, OSError, ValueError) as exc:
        print(
            json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc)}, indent=2),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
