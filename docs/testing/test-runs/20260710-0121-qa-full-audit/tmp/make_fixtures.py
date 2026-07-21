from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


LOCKED_SHA = "fb3f589b08e4167ac3cb0043fb3d59801a0f110b"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    for directory in ("papers", "wiki/minimal", "wiki/empty", "providers", "evidence", "approvals", "experiments", "review", "ui"):
        (root / directory).mkdir(parents=True, exist_ok=True)

    write_text(root / "papers/valid-paper.md", """---
fixture_source: true
title: "Fixture: Deterministic Solar QA Paper"
---

# Fixture: Deterministic Solar QA Paper

## Abstract

This fixture states one bounded claim: deterministic gates reject malformed evidence.

## Method

Validate one well-formed and one malformed local JSON payload without network access.

## Result

The expected fixture result is a typed pass for valid evidence and a typed rejection for malformed evidence.
""")
    write_text(root / "papers/malformed-paper.md", "# Fixture: Malformed Paper\n\n[broken-link](\n\n```json\n{not-json}\n")
    write_text(root / "papers/source.tex", r"""\documentclass{article}
\title{Fixture: Deterministic Solar QA Paper}
\author{Fixture Data}
\begin{document}
\maketitle
Fixture source only. No live-provider evidence.
\end{document}
""")
    pdf_path = root / "papers/valid-paper.pdf"
    pdf = canvas.Canvas(str(pdf_path), pagesize=letter)
    pdf.setTitle("Fixture: Deterministic Solar QA Paper")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, 720, "Fixture: Deterministic Solar QA Paper")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 690, "fixture_source=true")
    pdf.drawString(72, 668, "Local deterministic parser fixture; not live-provider evidence.")
    pdf.save()
    (root / "papers/malformed.pdf").write_bytes(b"%PDF-1.7\nfixture_source=true\nmalformed-no-xref")

    providers = {
        "arxiv.json": {"fixture_source": True, "provider": "arxiv", "entries": [{"id": "fixture-arxiv-1", "title": "Fixture Paper", "url": "https://example.invalid/arxiv"}]},
        "semantic-scholar.json": {"fixture_source": True, "provider": "semantic-scholar", "data": [{"paperId": "fixture-s2-1", "title": "Fixture Paper"}]},
        "deepxiv.json": {"fixture_source": True, "provider": "deepxiv", "results": [{"id": "fixture-deepxiv-1", "score": 0.9}]},
        "paper-copilot-venue.json": {"fixture_source": True, "provider": "paper-copilot", "venue": "FixtureConf", "papers": []},
        "provider-unavailable.json": {"fixture_source": True, "provider": "fixture", "status": "unavailable", "reason": "offline audit"},
    }
    for name, payload in providers.items():
        write_json(root / "providers" / name, payload)

    write_text(root / "wiki/minimal/Home.md", "---\nfixture_source: true\n---\n# Fixture Home\n\nSee [[Claim]].\n")
    write_text(root / "wiki/minimal/Claim.md", "---\nfixture_source: true\n---\n# Fixture Claim\n\nMalformed evidence must be rejected.\n")
    write_text(root / "wiki/empty/README.md", "fixture_source=true; intentionally empty wiki\n")
    write_text(root / "wiki/invalid-graph.jsonl", '{"fixture_source":true,"node":"ok"}\n{not-json}\n')
    write_text(root / "wiki/broken-wikilink.md", "fixture_source=true\n\n[[Missing Fixture Page]]\n")

    write_json(root / "evidence/valid-generic-v1.json", {"schema": "fixture_evidence.v1", "fixture_source": True, "status": "complete", "evidence_refs": ["fixture://local"]})
    write_json(root / "evidence/invalid-generic-v1.json", {"schema": "fixture_evidence.v1", "fixture_source": True, "status": 17, "evidence_refs": "not-an-array"})
    write_json(root / "approvals/approval-ref.json", {"schema": "fixture_approval.v1", "fixture_source": True, "approval_ref": "fixture-approval-denied-by-default", "approved": False})
    write_json(root / "approvals/allowlist.json", {"schema": "fixture_allowlist.v1", "fixture_source": True, "allowed_targets": []})
    write_json(root / "approvals/before.json", {"schema": "fixture_before.v1", "fixture_source": True, "state": "unchanged"})
    write_json(root / "approvals/runtime.json", {"schema": "fixture_runtime.v1", "fixture_source": True, "status": "blocked_expected", "continuation_required": True})
    write_json(root / "approvals/after.json", {"schema": "fixture_after.v1", "fixture_source": True, "state": "unchanged"})

    write_json(root / "experiments/plan.json", {"schema": "experiment_plan.v1", "fixture_source": True, "hypothesis": "Malformed evidence is rejected", "metrics": ["typed_rejection"], "budget": {"runs": 1}})
    write_text(root / "experiments/runtime.log", "fixture_source=true status=completed exit_code=0\n")
    write_json(root / "experiments/result.json", {"schema": "experiment_result.v1", "fixture_source": True, "status": "completed", "metrics": {"typed_rejection": 1}})
    write_text(root / "experiments/missing-result-directory.README", "fixture_source=true; path intentionally has no result directory\n")

    write_json(root / "review/valid-review.json", {"fixture_source": True, "verdict": "supported", "limitations": ["fixture-only"], "evidence_refs": ["fixture://local"]})
    write_json(root / "review/invalid-review.json", {"fixture_source": True, "verdict": 1, "evidence_refs": None})
    write_json(root / "review/missing-review.json", {"fixture_source": True, "status": "missing", "reason": "Review LLM not invoked in offline audit"})

    write_json(root / "ui/status-ok.json", {"fixture_source": True, "status": "ok", "runtime": "fixture", "live": False})
    write_json(root / "ui/status-missing-runtime.json", {"fixture_source": True, "status": "inconclusive", "runtime": None})
    write_json(root / "ui/status-stalled.json", {"fixture_source": True, "status": "stalled", "last_progress_seconds": 999})

    fixture_entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            kind = path.parent.name
            polarity = "negative" if any(term in path.name for term in ("malformed", "invalid", "missing", "broken", "unavailable", "stalled", "empty")) else "positive"
            fixture_entries.append({
                "id": "fixture-" + str(path.relative_to(root)).replace("/", "-").replace(".", "-").lower(),
                "path": str(path.relative_to(root)),
                "supports_feature_ids": [],
                "kind": kind,
                "positive_or_negative": polarity,
                "notes": "fixture_source=true; local deterministic control material; never count as live parity",
            })
    write_json(root / "manifest.json", {
        "schema": "ai4research_fixture_manifest.v1",
        "created_for_commit": LOCKED_SHA,
        "fixture_only_not_live_parity": True,
        "fixtures": fixture_entries,
    })
    print(json.dumps({"fixture_count": len(fixture_entries), "root": str(root)}))


if __name__ == "__main__":
    main()
