#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui" / "orchestration"
INDEX = UI_DIR / "index.html"
MAIN = UI_DIR / "main.js"
STYLES = UI_DIR / "styles.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_orchestration_ui_exposes_evidence_regions() -> None:
    html = _read(INDEX)

    for element_id in [
        "dag-flow",
        "route-list",
        "actorhost-list",
        "degraded-list",
        "pane-supply",
    ]:
        assert f'id="{element_id}"' in html

    for heading in [
        "DAG Progress Flow",
        "Route Decisions",
        "ActorHost Taxonomy",
        "Degraded Sources",
        "Pane Supply",
    ]:
        assert heading in html


def test_orchestration_ui_renders_actorhost_and_route_api_fields() -> None:
    js = _read(MAIN)

    for token in [
        "renderRoutes",
        "renderActorHosts",
        "renderDegraded",
        "route_decision",
        "blocked_reason",
        "actor_id",
        "host_id",
        "host_type",
        "lease_state",
        "pane_carrier",
        "degraded_sources",
    ]:
        assert token in js

    assert "No active blockers detected" in js
    assert "Dashboard API unreachable" in js


def test_pane_carrier_remains_separate_from_actorhost_taxonomy() -> None:
    js = _read(MAIN)

    actorhost_block = re.search(
        r"function renderActorHosts\(data\) \{(?P<body>.*?)\n  \}\n\n  function renderDiagnostics",
        js,
        flags=re.S,
    )
    pane_block = re.search(
        r"function renderPanes\(data\) \{(?P<body>.*?)\n  \}\n\n  async function refresh",
        js,
        flags=re.S,
    )
    assert actorhost_block
    assert pane_block

    actorhost_body = actorhost_block.group("body")
    pane_body = pane_block.group("body")
    assert "resolution_source" in actorhost_body
    assert "canonical_host_type" in actorhost_body
    assert "Pane Carrier" in pane_body
    assert "pane_carrier" in pane_body


def test_desktop_and_mobile_layouts_keep_evidence_visible() -> None:
    css = _read(STYLES)

    assert ".evidence-grid" in css
    assert ".field-grid" in css
    assert "@media (max-width: 960px)" in css
    assert re.search(r"\.evidence-grid\s*\{[^}]*display:\s*grid", css, flags=re.S)
    assert re.search(r"@media \(max-width: 960px\).*?\.evidence-grid\s*\{[^}]*grid-template-columns:\s*1fr", css, flags=re.S)

    hidden_rules = re.findall(
        r"\.(?:evidence-grid|evidence-card|field-grid|pane-grid|dag-flow)[^{]*\{[^}]*(?:display:\s*none|visibility:\s*hidden)",
        css,
        flags=re.S,
    )
    assert hidden_rules == []
