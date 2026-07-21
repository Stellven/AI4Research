#!/usr/bin/env python3
"""Deterministic multi-task agent for Solar knowledge extraction backfills.

This worker deliberately avoids Claude. It handles coarse extraction/indexing
tasks with local filesystem tools and QMD. If a future step needs model text,
route it through the local ThunderOMLX service or a Gemini profile, not Claude.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
SPRINTS_DIR = Path(os.environ.get("SPRINTS_DIR", HARNESS_DIR / "sprints"))
KNOWLEDGE_DIR = HOME / "Knowledge" / "_raw" / "solar-harness"
EXPORTER = HARNESS_DIR / "tools" / "runtime-artifact-knowledge-export.py"
TEST = HARNESS_DIR / "tests" / "test-runtime-artifact-knowledge-export.sh"
REPORTS_DIR = HARNESS_DIR / "monitor-reports"
SID = os.environ.get("SID", "")
NODE_ID = os.environ.get("NODE_ID", "")
HANDOFF = Path(os.environ.get("HANDOFF", SPRINTS_DIR / f"{SID}.{NODE_ID}-handoff.md"))


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd: list[str], *, timeout: int = 300) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    return {
        "cmd": " ".join(cmd),
        "rc": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fenced_json(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def audit_sources() -> dict[str, Any]:
    sprint_patterns = ("*.prd.md", "*.contract.md", "*.task_graph.json", "*.N*-handoff.md", "*.handoff.md")
    sources: list[Path] = []
    for pattern in sprint_patterns:
        sources.extend(SPRINTS_DIR.glob(pattern))
    if REPORTS_DIR.exists():
        sources.extend(p for p in REPORTS_DIR.rglob("*") if p.suffix in {".md", ".json"})
    source_count = len({p.resolve() for p in sources if p.is_file()})
    knowledge_files = list(KNOWLEDGE_DIR.rglob("*.md")) if KNOWLEDGE_DIR.exists() else []
    manifest = load_json(KNOWLEDGE_DIR / ".manifest" / "runtime-artifacts.json", {})
    stale_manifest = load_json(HARNESS_DIR / "state" / "knowledge-manifest.json", {})
    probe = load_json(HARNESS_DIR / "state" / "knowledge-probe-health.json", {})
    return {
        "checked_at": now(),
        "source_count": source_count,
        "knowledge_file_count": len(knowledge_files),
        "runtime_manifest_entries": len(manifest.get("entries", manifest if isinstance(manifest, list) else []) or []),
        "legacy_manifest": stale_manifest,
        "probe_health": {
            "ok": probe.get("ok"),
            "status": probe.get("status"),
            "probes_passed": probe.get("probes_passed"),
            "probes_failed": probe.get("probes_failed"),
        },
        "root_cause": "accepted-artifact export only covered passed/finalized artifacts; multi-task handoffs, PRD/contract/task_graph, and monitor reports were not all covered.",
    }


def node_n1() -> None:
    audit = audit_sources()
    report = f"""# Knowledge extraction runtime artifact audit

Generated: {now()}

## 结论

- 不是全量抽取。
- 断点是 accepted-artifact-only pipeline 覆盖面过窄，遗漏 multi-task runtime artifacts 和 monitor reports。
- 本节点未调用 Claude；后续粗活走本地 deterministic/ThunderOMLX command profile。

## Evidence

{fenced_json(audit)}
"""
    write(REPORTS_DIR / "knowledge-extraction-runtime-artifact-backfill-N1-audit.md", report)
    handoff("N1", "coverage gap root cause documented", ["audit report written", "Claude not used"])


def node_n2() -> None:
    test_result = run(["bash", str(TEST)], timeout=120) if TEST.exists() else {"rc": 127, "stdout": "", "stderr": "test missing"}
    report = f"""# Runtime artifact exporter implementation

Generated: {now()}

## 交付

- Exporter: `{EXPORTER}`
- Test: `{TEST}`
- Backend policy: local command profile, model label `thunderomlx`; no Claude.

## Test

{fenced_json(test_result)}
"""
    write(REPORTS_DIR / "knowledge-extraction-runtime-artifact-backfill-N2-exporter.md", report)
    if test_result["rc"] != 0:
        raise SystemExit(f"exporter test failed: {test_result['rc']}")
    handoff("N2", "runtime artifact exporter tests pass", ["exporter present", "regression test passed"])


def node_n3() -> None:
    if not EXPORTER.exists():
        raise SystemExit(f"missing exporter: {EXPORTER}")
    export_result = run([str(EXPORTER), "export", "--since", "2026-05-20", "--json"], timeout=600)
    audit_result = run([str(EXPORTER), "audit", "--since", "2026-05-20", "--json"], timeout=180)
    qmd_update = run([str(HARNESS_DIR / "solar-harness.sh"), "wiki", "qmd-update"], timeout=900)
    report = {
        "generated_at": now(),
        "export": parse_json_output(export_result),
        "audit_after": parse_json_output(audit_result),
        "qmd_update": summarize_run(qmd_update),
        "policy": "Claude not used; local deterministic extraction under thunderomlx command profile.",
    }
    write(REPORTS_DIR / "knowledge-extraction-runtime-artifact-backfill-N3-backfill.md", "# Runtime artifact backfill\n\n" + fenced_json(report) + "\n")
    if export_result["rc"] != 0 or audit_result["rc"] != 0 or qmd_update["rc"] != 0:
        raise SystemExit("backfill/qmd update failed")
    handoff("N3", "backfill exported recent runtime artifacts", ["export completed", "qmd update completed"])


def node_n4() -> None:
    refresh = run([str(EXPORTER), "export", "--since", "2026-05-20", "--json"], timeout=600)
    embed = run([str(HARNESS_DIR / "solar-harness.sh"), "wiki", "qmd-embed", "run-now"], timeout=1800)
    qmd_status = run([str(HARNESS_DIR / "solar-harness.sh"), "wiki", "qmd-status"], timeout=120)
    searches = [
        run([str(HARNESS_DIR / "solar-harness.sh"), "wiki", "qmd-search", "readiness probe auth", "-n", "10", "--json"], timeout=180),
        run([str(HARNESS_DIR / "solar-harness.sh"), "wiki", "qmd-search", "thunderomlx readiness", "-n", "10", "--json"], timeout=180),
        run([str(HARNESS_DIR / "solar-harness.sh"), "context", "inject", "--query", "ThunderOMLX readiness probe auth cache_read_input_tokens runtime artifact", "--format", "markdown"], timeout=240),
    ]
    manifest_audit = run([str(EXPORTER), "audit", "--since", "2026-05-20", "--json"], timeout=180)
    retrieval_ok = any(
        "thunderomlx-readiness-probe-auth" in (item["stdout"] or "").lower()
        and "runtime-artifacts" in (item["stdout"] or "").lower()
        for item in searches
    )
    report = {
        "generated_at": now(),
        "refresh_export": parse_json_output(refresh),
        "manifest_audit": parse_json_output(manifest_audit),
        "qmd_embed": summarize_run(embed),
        "qmd_status_tail": qmd_status["stdout"][-2000:],
        "retrieval_ok": retrieval_ok,
        "searches": [summarize_run(item) for item in searches],
        "policy": "Claude not used. If cloud review is needed later, use Gemini profile only.",
    }
    write(REPORTS_DIR / "knowledge-extraction-runtime-artifact-backfill.md", "# Knowledge extraction runtime artifact backfill final report\n\n" + fenced_json(report) + "\n")
    if not retrieval_ok:
        raise SystemExit("retrieval did not return newly exported runtime artifact")
    handoff("N4", "knowledge retrieval verifies new artifacts", ["qmd/context retrieval verified", "final report written"])


def parse_json_output(result: dict[str, Any]) -> Any:
    try:
        return json.loads(result.get("stdout") or "{}")
    except Exception:
        return summarize_run(result)


def summarize_run(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "cmd": result["cmd"],
        "rc": result["rc"],
        "stdout_tail": result.get("stdout", "")[-1200:],
        "stderr_tail": result.get("stderr", "")[-1200:],
    }


def handoff(node: str, gate: str, verified: list[str]) -> None:
    body = f"""# Handoff — {SID} / {node}

## 已完成

- Gate: {gate}
- Policy: no Claude usage for knowledge extraction coarse work.

## 已验证

{chr(10).join(f"- {item}" for item in verified)}

## 未验证

- N/A

## 风险

- QMD embedding/search latency may lag after large backfills; final retrieval node verifies it explicitly.

## 后续待办

- Continue next DAG node.
"""
    write(HANDOFF, body)


def main() -> int:
    handlers = {"N1": node_n1, "N2": node_n2, "N3": node_n3, "N4": node_n4}
    handler = handlers.get(NODE_ID)
    if not handler:
        print(f"unsupported knowledge extraction node: {NODE_ID}", file=sys.stderr)
        return 64
    print(f"[knowledge-extractor] sid={SID} node={NODE_ID} start={now()}")
    handler()
    print(f"[knowledge-extractor] sid={SID} node={NODE_ID} done={now()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
