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
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BRIDGE = Path(__file__).resolve().parent / "autosci_bridge.py"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from adapters.solar_envelope_to_autosci import normalize_envelope

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


def _tail_text(path: Path, *, limit: int = 20000) -> str:
    """The end of a streamed log, for the in-memory record.

    The full log stays on disk; only a bounded tail travels in the JSON.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]


def autosci_progress(home: Path) -> dict[str, Any]:
    """AutoSci's own per-stage progress, if its pipeline wrote any.

    `$research` records every stage and gate to wiki/outputs/pipeline-progress.md
    with a status and a duration, for its own cross-session resume. That file is
    a better account of where Part B spends its time than anything we could
    infer from outside, so read it rather than instrument their pipeline.
    """
    path = home / "wiki" / "outputs" / "pipeline-progress.md"
    if not path.is_file():
        return {"present": False}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"present": False, "unreadable": True}
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        # "| Stage 1: Idea Discovery | completed | 12m |"
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3 or not cells[0].lower().startswith(("stage", "gate")):
            continue
        # "| Stage | Status | Duration |" is the header, not a stage; its own
        # first cell also starts with "stage".
        if cells[1].lower() in {"status", "---"} or set(cells[1]) <= {"-", ":"}:
            continue
        rows.append({"stage": cells[0], "status": cells[1], "duration": cells[2]})
    return {"present": True, "path": str(path), "stages": rows}


def wiki_fingerprint(home: Path) -> dict[str, Any]:
    """Every wiki file the skills write, with a content hash.

    Taken before and after a stage, the difference is the only honest answer to
    "what did this stage actually change". Two of this workflow's defects were
    stages that reported success while changing nothing, and neither was
    visible from an exit code.
    """
    root = home / "wiki"
    files: dict[str, str] = {}
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            except OSError:
                digest = "unreadable"
            files[str(path.relative_to(root))] = digest
    return files


def wiki_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "modified": sorted(k for k in set(before) & set(after) if before[k] != after[k]),
    }


def _redacted_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """The envelope as the bridge received it, with obvious secrets removed.

    The envelope is retained because the fixture-mode defect was invisible
    anywhere else: the bug was entirely in what the bridge was handed.
    """
    safe = json.loads(json.dumps(envelope, default=str))
    inputs = safe.get("inputs")
    if isinstance(inputs, dict):
        for key in list(inputs):
            if any(marker in key.lower() for marker in ("key", "token", "secret", "password")):
                inputs[key] = "<redacted>"
    return safe


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

    record_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path = record_path.with_suffix(".stdout.log")
    stderr_path = record_path.with_suffix(".stderr.log")

    started_at = _now()
    started_monotonic = time.monotonic()
    # Stream to files rather than buffering in memory. capture_output=True keeps
    # everything in the parent's pipes until the child exits, so a skill killed
    # on timeout yielded NOTHING: the 40-minute experiment_design run left a
    # 0-byte stdout log while the run that finished left 4 KB. That is exactly
    # backwards -- the run you cannot explain is the one you need the log for.
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(argv, cwd=home, env=_skill_env(), stdout=out, stderr=err, text=True)
        try:
            exit_code = proc.wait(timeout=timeout_seconds)
            timed_out = False
        except subprocess.TimeoutExpired:
            # Terminate first so the child can flush; kill only if it will not go.
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=15)
            exit_code = 124
            timed_out = True
            err.write(f"\ntimed out after {timeout_seconds}s\n")

    stdout = _tail_text(stdout_path)
    stderr = _tail_text(stderr_path)

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
        # Wall clock is unreliable on this host: a sleep across a WSL2 clock
        # jump recorded a 40-minute run as 9h48m. Duration is monotonic.
        "duration_seconds": round(time.monotonic() - started_monotonic, 3),
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
    envelope = normalize_envelope(envelope, action=action)

    declared_work_dir = args.work_dir or str(envelope.get("work_dir") or "")
    work_dir = Path(declared_work_dir).expanduser() if declared_work_dir else envelope_path.parent
    run_id = uuid.uuid4().hex[:12]
    record_path = work_dir / "autosci-runtime" / f"{stage}-{run_id}.runtime.json"

    request = str(args.request or (envelope.get("inputs") or {}).get("request") or "").strip()
    wiki_before = wiki_fingerprint(_autosci_home())
    record = run_skill(
        stage=stage,
        request=request,
        record_path=record_path,
        timeout_seconds=args.timeout_seconds,
    )
    wiki_after = wiki_fingerprint(_autosci_home())
    delta = wiki_delta(wiki_before, wiki_after)

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
    # A stage that changed no wiki file produced nothing, whatever it returned.
    # This is not part of the verdict -- some stages legitimately only read --
    # but it is recorded so "succeeded" and "did something" stay distinguishable.
    changed_anything = any(delta.values())

    trace = {
        "schema": "solar.autosci_stage_trace.v1",
        "stage": stage,
        "run_id": run_id,
        "bridge_action": action,
        "verdicts": {
            "ok": bridged.returncode == 0 and skill_ok,
            "skill_ok": skill_ok,
            "bridge_ok": bridged.returncode == 0,
            "changed_wiki": changed_anything,
        },
        "skill": {
            "invocation": record.get("skill_invocation"),
            "exit_code": record["exit_code"],
            "timed_out": record["timed_out"],
            "duration_seconds": record.get("duration_seconds"),
            "model": record.get("model"),
            "stdout_path": record.get("stdout_path"),
            "stderr_path": record.get("stderr_path"),
        },
        "argument_resolution": {
            "argument": record.get("stage_argument"),
            "source": record.get("stage_argument_source"),
            "candidates_considered": record.get("stage_argument_candidates"),
        },
        "wiki": {
            "root": str(_autosci_home() / "wiki"),
            "files_before": len(wiki_before),
            "files_after": len(wiki_after),
            "delta": delta,
        },
        # AutoSci's own account of where its time went, when its pipeline
        # wrote one. Their instrumentation beats ours from outside the process.
        "autosci_progress": autosci_progress(_autosci_home()),
        "bridge": {
            "envelope_path": str(augmented),
            "envelope_as_sent": _redacted_envelope(envelope),
            "returncode": bridged.returncode,
            "stderr_tail": (bridged.stderr or "")[-2000:],
        },
        "recorded_at": _now(),
    }
    trace_path = work_dir / "autosci-runtime" / f"{stage}-{run_id}.trace.json"
    trace_path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "ok": bridged.returncode == 0 and skill_ok,
        "skill_ok": skill_ok,
        "bridge_ok": bridged.returncode == 0,
        "changed_wiki": changed_anything,
        "stage": stage,
        "bridge_action": action,
        "skill_exit_code": record["exit_code"],
        "timed_out": record["timed_out"],
        "duration_seconds": record.get("duration_seconds"),
        "wiki_delta": delta,
        "runtime_record": str(record_path),
        "trace": str(trace_path),
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
