"""Research control-plane intake helpers for the AutoSci bridge.

The helpers in this module are deterministic and side-effect-light: they
classify the user input, validate local material before dispatch, and prepare
bounded source/evidence snapshots for the Solar research runtime.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ResearchControlPlaneError(ValueError):
    """Raised when the research request cannot be safely routed."""


_URL_RE = re.compile(
    r"https?://[^\s<>()\[\]{}\"'，。；：！？、（）【】《》「」『』\u4e00-\u9fff]+",
    re.IGNORECASE,
)
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]|\b(?:chinese|zh-cn|mandarin)\b", re.IGNORECASE)
_ENGLISH_RE = re.compile(r"\b(?:english|en-us|en-gb)\b", re.IGNORECASE)
_SOURCE_PACK_SUFFIXES = {".md", ".markdown", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".csv", ".tsv"}
_EXPERIMENT_KEYS = {
    "experiment",
    "experiment_result",
    "experiment_status",
    "metrics",
    "claim_verdict",
    "run_id",
    "hypothesis",
}


@dataclass(frozen=True)
class InputClassification:
    input_kind: str
    workflow_kind: str
    start_stage: str
    internal_seed_kind: str
    reason_codes: tuple[str, ...]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_kind": self.input_kind,
            "workflow_kind": self.workflow_kind,
            "start_stage": self.start_stage,
            "internal_seed_kind": self.internal_seed_kind,
            "reason_codes": list(self.reason_codes),
            "confidence": self.confidence,
        }


def classify_research_input(
    *,
    prompt: str,
    sources: list[str],
    import_evidence: list[str],
    run_mode: str,
    explicit_workflow: str | None = None,
) -> InputClassification:
    text = str(prompt or "")
    if not text.strip():
        raise ResearchControlPlaneError("prompt must be a non-empty string")
    reasons: list[str] = []
    if run_mode == "resume":
        return InputClassification(
            "resume",
            explicit_workflow or "scientific_lifecycle",
            "evidence_import",
            "external_evidence",
            ("run_mode_resume",),
            0.92,
        )
    if import_evidence:
        kind = "experiment_evidence" if any(_looks_like_experiment_evidence(Path(item)) for item in import_evidence) else "source_pack"
        return InputClassification(
            kind,
            explicit_workflow or "scientific_lifecycle",
            "evidence_import",
            "external_evidence",
            ("import_evidence_supplied", f"classified_{kind}"),
            0.9,
        )

    source_kinds = [_classify_source_value(item) for item in sources if str(item).strip()]
    if _URL_RE.search(text) and not source_kinds:
        source_kinds.append("website")
        reasons.append("prompt_url")
    if not source_kinds:
        return InputClassification(
            "topic",
            explicit_workflow or "literature_synthesis",
            "source_discovery",
            "topic",
            tuple([*reasons, "implicit_topic"]),
            0.76,
        )

    if "experiment_evidence" in source_kinds:
        return InputClassification(
            "experiment_evidence",
            explicit_workflow or "scientific_lifecycle",
            "evidence_import",
            "external_evidence",
            tuple([*reasons, "experiment_evidence_source"]),
            0.88,
        )
    if "source_pack" in source_kinds or len(source_kinds) > 1:
        return InputClassification(
            "source_pack",
            explicit_workflow or "paper_ingestion",
            "material_ingest",
            "markdown",
            tuple([*reasons, "source_pack_supplied"]),
            0.86,
        )
    if "local_pdf" in source_kinds:
        return InputClassification(
            "local_pdf",
            explicit_workflow or "paper_ingestion",
            "paper_ingest",
            "pdf",
            tuple([*reasons, "local_pdf_supplied"]),
            0.9,
        )
    if "website" in source_kinds:
        return InputClassification(
            "website",
            explicit_workflow or "research_synthesis",
            "web_fetch",
            "url",
            tuple([*reasons, "website_supplied"]),
            0.88,
        )
    return InputClassification(
        "topic",
        explicit_workflow or "literature_synthesis",
        "source_discovery",
        "topic",
        tuple([*reasons, "fallback_topic"]),
        0.64,
    )


def validate_request_constraints(prompt: str, classification: InputClassification) -> dict[str, Any]:
    text = str(prompt or "")
    contradictions: list[str] = []
    questions: list[str] = []
    if _CHINESE_RE.search(text) and _ENGLISH_RE.search(text):
        contradictions.append("output_language")
        questions.append("Should the final deliverable be in Chinese or English?")
    if classification.input_kind == "topic" and len(text.strip().split()) <= 2:
        questions.append("What exact research question and acceptance criteria should Solar use?")
    return {
        "status": "needs_clarification" if contradictions or questions else "ready",
        "contradictions": contradictions,
        "questions": list(dict.fromkeys(questions)),
    }


def prepare_runtime_inputs(
    *,
    prompt: str,
    sources: list[str],
    import_evidence: list[str],
    run_mode: str,
    artifact_root: Path,
    run_id: str,
    classification: InputClassification,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    artifact_root = Path(artifact_root).resolve()
    evidence_refs: list[dict[str, Any]] = []
    if classification.input_kind == "resume":
        return ([{"seed_id": "resume-state", "seed_kind": "external_evidence", "value": f"resume:{run_id}"}], [])
    if classification.input_kind == "website":
        values = sources or (_URL_RE.findall(prompt)[:1])
        return ([{"seed_id": f"website-{idx}", "seed_kind": "url", "value": value} for idx, value in enumerate(values, 1)], [])
    if classification.input_kind == "local_pdf":
        source = _single_source(sources, "local PDF")
        _validate_local_pdf(Path(source))
        return ([{"seed_id": "local-pdf-1", "seed_kind": "pdf", "value": source}], [])
    if classification.input_kind == "source_pack":
        manifest = _write_source_pack_manifest(
            [*sources, *import_evidence],
            artifact_root=artifact_root,
            run_id=run_id,
        )
        return ([{"seed_id": "source-pack-1", "seed_kind": "markdown", "value": str(manifest)}], [])
    if classification.input_kind == "experiment_evidence":
        raw_paths = import_evidence or sources
        if not raw_paths:
            raise ResearchControlPlaneError("experiment evidence requires at least one source or import-evidence path")
        snapshot_paths = [_snapshot_evidence(Path(item), artifact_root=artifact_root, run_id=run_id, index=idx) for idx, item in enumerate(raw_paths, 1)]
        evidence_refs = [_artifact_reference(path, artifact_root=artifact_root, artifact_id=f"experiment-evidence-{idx}") for idx, path in enumerate(snapshot_paths, 1)]
        return (
            [{"seed_id": "experiment-evidence-1", "seed_kind": "external_evidence", "value": str(snapshot_paths[0])}],
            evidence_refs,
        )
    return ([{"seed_id": "topic-1", "seed_kind": "topic", "value": prompt}], [])


def error_result(*, run_id: str, prompt: str, run_mode: str, error: Exception, final_status: str = "failed") -> dict[str, Any]:
    return {
        "schema": "solar_research_runtime_result.v1",
        "run_id": run_id,
        "prompt": prompt,
        "run_mode": run_mode,
        "final_status": final_status,
        "error_type": type(error).__name__,
        "error": str(error),
    }


def clarification_result(
    *,
    run_id: str,
    prompt: str,
    run_mode: str,
    classification: InputClassification,
    readiness: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "solar_research_runtime_result.v1",
        "run_id": run_id,
        "prompt": prompt,
        "run_mode": run_mode,
        "input_classification": classification.to_dict(),
        "final_status": "awaiting_human",
        "current_blockers": [
            {
                "blocker_id": "research_control_plane_needs_clarification",
                "node_id": "__intake__",
                "reason": "Core research requirements are missing or contradictory.",
                "questions": readiness.get("questions") or [],
                "contradictions": readiness.get("contradictions") or [],
            }
        ],
    }


def _classify_source_value(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ResearchControlPlaneError("source value must be non-empty")
    if _URL_RE.fullmatch(text):
        return "website"
    path = Path(text).expanduser()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "local_pdf"
    if path.exists() and path.is_dir():
        return "source_pack"
    if suffix in {".zip", ".tar", ".gz"}:
        return "source_pack"
    if suffix == ".json" and _looks_like_experiment_evidence(path):
        return "experiment_evidence"
    if suffix in _SOURCE_PACK_SUFFIXES:
        return "source_pack"
    return "topic"


def _single_source(sources: list[str], label: str) -> str:
    values = [str(item).strip() for item in sources if str(item).strip()]
    if len(values) != 1:
        raise ResearchControlPlaneError(f"{label} routing requires exactly one source")
    return values[0]


def _validate_local_pdf(path: Path) -> None:
    source = path.expanduser().resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise ResearchControlPlaneError(f"local PDF source is missing or empty: {source}")
    with source.open("rb") as handle:
        header = handle.read(5)
    if header != b"%PDF-":
        raise ResearchControlPlaneError(f"local PDF source is not a readable PDF artifact: {source}")


def _looks_like_experiment_evidence(path: Path) -> bool:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    keys = {str(key).lower() for key in payload}
    if keys & _EXPERIMENT_KEYS:
        return True
    text = json.dumps(payload, ensure_ascii=False).lower()
    return "experiment" in text and ("metric" in text or "hypothesis" in text or "result" in text)


def _write_source_pack_manifest(sources: list[str], *, artifact_root: Path, run_id: str) -> Path:
    values = [str(item).strip() for item in sources if str(item).strip()]
    if not values:
        raise ResearchControlPlaneError("source pack requires at least one source")
    out_dir = artifact_root / "inputs" / _safe_component(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "source-pack-manifest.md"
    sections = [f"# Source Pack Manifest\n\nrun_id: `{run_id}`\n"]
    for index, raw in enumerate(values, start=1):
        path = Path(raw).expanduser()
        sections.append(f"\n## Source {index}: {raw}\n")
        if path.is_dir():
            members = sorted(item for item in path.rglob("*") if item.is_file())[:50]
            sections.append(f"kind: directory\nfile_count_sampled: {len(members)}\n")
            for member in members:
                sections.append(f"- `{member}` ({member.stat().st_size} bytes)\n")
        elif path.is_file():
            if path.stat().st_size <= 0:
                raise ResearchControlPlaneError(f"source pack member is empty: {path.resolve()}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            sections.append(f"kind: file\nsha256: `{digest}`\n")
            if path.suffix.lower() in {".md", ".markdown", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".csv", ".tsv"}:
                snippet = path.read_text(encoding="utf-8", errors="replace")[:4000]
                sections.append("\n```text\n" + snippet + "\n```\n")
        elif _URL_RE.fullmatch(raw):
            sections.append("kind: url\n")
        else:
            raise ResearchControlPlaneError(f"source pack member is missing: {path.resolve()}")
    manifest.write_text("".join(sections), encoding="utf-8")
    return manifest


def _snapshot_evidence(path: Path, *, artifact_root: Path, run_id: str, index: int) -> Path:
    source = path.expanduser().resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise ResearchControlPlaneError(f"evidence source is missing or empty: {source}")
    out_dir = artifact_root / "inputs" / _safe_component(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"evidence-{index:02d}-{_safe_component(source.name)}"
    shutil.copyfile(source, target)
    return target


def _artifact_reference(path: Path, *, artifact_root: Path, artifact_id: str) -> dict[str, Any]:
    resolved = path.resolve()
    captured_at = datetime.fromtimestamp(resolved.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z")
    return {
        "artifact_id": artifact_id,
        "path": str(resolved),
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "provenance": {"source": "research_control_plane_snapshot", "captured_at": captured_at},
    }


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip(".-")
    return cleaned[:120] or "research-input"
