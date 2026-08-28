"""rc.10 evaluated/published-byte authority regressions.

The published rc.9 ordinary-prompt archive proved a byte-identity gap:
``jsonl_stats.py`` was published with SHA-256 ``2e2f...acb9`` and the sprint
staging copy changed seven seconds later to ``4df0...2735``.  The final
verifier inspected mutable staging, so its PASS was not a verdict over the
exact bytes the user received.

These tests pin the class boundary rather than that prompt:

* a manifest is a content commitment, not a late path lookup;
* evaluator PASS is bound to an immutable digest of declared read/write bytes;
* published ancestor bytes are authoritative for downstream review and must
  agree with any staging mirror;
* contracted PASS receipts carry the byte-binding evidence the scheduler can
  validate before accepting the state transition.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import pytest


HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
LIB = HARNESS / "lib"
FIXTURES = (Path(__file__).resolve().parents[3] / 'tests' / 'harness') / "fixtures" / "rc9_byte_drift"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import artifact_manifest as am  # noqa: E402
import gate_ledger as gl  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import workspace_binding  # noqa: E402


PUBLISHED_SHA256 = "2e2f343c5d771d127ad2bff0acc507b894c9f6e12076b9dc2c60f4d1ebc6acb9"
LATE_STAGING_SHA256 = "4df05734525be61021f4332f652b7c08816e98ad84df9114281f6c7bef0d2735"


def _published_bytes() -> bytes:
    payload = (FIXTURES / "jsonl_stats.published.py").read_bytes()
    assert hashlib.sha256(payload).hexdigest() == PUBLISHED_SHA256
    return payload


def _late_staging_bytes() -> bytes:
    before = (
        b'                raise ValueError(f"invalid JSON object at line {line_no}: '
        b'got {type(value).__name__}")\n'
    )
    after = (
        b"                kind = type(value).__name__\n"
        b"                raise ValueError(\n"
        b'                    f"invalid JSON object at line {line_no}: got {kind}"\n'
        b"                )\n"
    )
    payload = _published_bytes().replace(before, after)
    assert payload != _published_bytes()
    assert hashlib.sha256(payload).hexdigest() == LATE_STAGING_SHA256
    return payload


def _contracted_graph(sid: str, nodes: list[dict]) -> dict:
    return {
        "sprint_id": sid,
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1.0",
        "plan_certificate": {"schema": "solar.plan_certificate.v1", "verdict": "PASS"},
        "nodes": nodes,
        "node_results": {
            str(node["id"]): {"status": str(node.get("status") or "pending")}
            for node in nodes
        },
        "gate_results": {},
    }


def _write_publication_authority(
    sprints: Path,
    sid: str,
    builder: dict,
    staging_file: Path,
    product: Path,
    product_file: Path,
) -> dict:
    workdir = sprints / sid / "workdir"
    manifest = am.write_manifest(
        sprints,
        sid,
        builder,
        generation=0,
        base_dir=workdir,
        roots={"canonical": "workspace/"},
    )
    assert manifest is not None
    assert manifest["rows"][0]["sha256"] == PUBLISHED_SHA256
    published = [
        {
            "from": str(staging_file),
            "to": str(product_file),
            "sha256": PUBLISHED_SHA256,
        }
    ]
    payload = {
        "schema": "solar.workspace_publish.v1",
        "sid": sid,
        "node_id": "S1",
        "required": True,
        "ok": True,
        "workspace_root": str(product),
        "published": published,
        "manifest_digest": manifest["content_digest"],
        "published_digest": am.published_content_digest(published),
    }
    (sprints / f"{sid}.S1-publish.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    builder["closeout_receipt"] = {
        "schema": "solar.node_closeout.v1",
        "sid": sid,
        "node_id": "S1",
        "verdict": "passed",
        "manifest": {
            "content_digest": manifest["content_digest"],
        },
        "publication": {
            "required": True,
            "ok": True,
            "published_count": 1,
            "manifest_digest": manifest["content_digest"],
            "published_digest": payload["published_digest"],
        },
    }
    return payload


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    harness.mkdir()
    sprints.mkdir()
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gs, "HARNESS_DIR", harness)
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    return harness, sprints


def test_rc9_source_change_after_manifest_is_rejected_before_publish(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    source = staging / "workspace" / "jsonl_stats.py"
    destination_root = tmp_path / "product"
    source.parent.mkdir(parents=True)
    destination_root.mkdir()
    source.write_bytes(_published_bytes())
    (destination_root / "jsonl_stats.py").write_bytes(_published_bytes())
    manifest = am.write_manifest(
        tmp_path / "sprints",
        "sid",
        {"id": "S1", "write_scope": ["workspace/jsonl_stats.py"]},
        generation=0,
        base_dir=staging,
        roots={"canonical": "workspace/"},
    )
    assert manifest is not None
    assert manifest["rows"][0]["sha256"] == PUBLISHED_SHA256

    # Exact archived transition: the path now contains different bytes after
    # the manifest/evaluation point but before publication.
    source.write_bytes(_late_staging_bytes())
    result = am.publish_workspace_outputs(manifest, destination_root)

    assert result["ok"] is False, result
    assert result["reason"] == "workspace_publish_content_mismatch"
    assert hashlib.sha256((destination_root / "jsonl_stats.py").read_bytes()).hexdigest() == PUBLISHED_SHA256


def _stage_two_file_publish(tmp_path: Path) -> tuple[dict, Path, Path, Path]:
    staging = tmp_path / "staging"
    destination_root = tmp_path / "product"
    source_a = staging / "workspace" / "a.txt"
    source_b = staging / "workspace" / "b.txt"
    destination_a = destination_root / "a.txt"
    destination_b = destination_root / "b.txt"
    source_a.parent.mkdir(parents=True)
    destination_root.mkdir()
    source_a.write_text("new-a\n", encoding="utf-8")
    source_b.write_text("new-b\n", encoding="utf-8")
    destination_a.write_text("old-a\n", encoding="utf-8")
    destination_b.write_text("old-b\n", encoding="utf-8")
    manifest = am.write_manifest(
        tmp_path / "sprints",
        "sid",
        {
            "id": "S1",
            "write_scope": ["workspace/a.txt", "workspace/b.txt"],
        },
        generation=0,
        base_dir=staging,
        roots={"canonical": "workspace/"},
    )
    assert manifest is not None
    return manifest, destination_root, destination_a, destination_b


def test_multi_file_publish_rolls_back_when_a_later_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, destination_root, destination_a, destination_b = _stage_two_file_publish(
        tmp_path
    )
    real_replace = am.os.replace

    def fail_second_destination(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == destination_b:
            raise OSError("injected second-destination replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(am.os, "replace", fail_second_destination)

    result = am.publish_workspace_outputs(manifest, destination_root)

    assert result["ok"] is False, result
    assert destination_a.read_text(encoding="utf-8") == "old-a\n"
    assert destination_b.read_text(encoding="utf-8") == "old-b\n"
    assert not list(destination_root.glob(".*.solar-publish-*"))


def test_directory_publish_replaces_existing_tree_without_hashing_transaction_backups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Windows rejects fsync() on the read-only verification descriptor; the
    # production path under test runs in WSL. Keep this regression focused on
    # the directory transaction digest rather than that existing portability gap.
    monkeypatch.setattr(am.os, "fsync", lambda _fd: None)
    staging = tmp_path / "staging"
    source = staging / "workspace" / "report" / "final.md"
    destination_root = tmp_path / "product"
    destination = destination_root / "report" / "final.md"
    source.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    source.write_text("verified report\n", encoding="utf-8")
    destination.write_text("older report\n", encoding="utf-8")
    manifest = am.write_manifest(
        tmp_path / "sprints",
        "sid",
        {"id": "S1", "write_scope": ["workspace/report/"]},
        generation=0,
        base_dir=staging,
        roots={"canonical": "workspace/"},
    )
    assert manifest is not None

    result = am.publish_workspace_outputs(manifest, destination_root)

    assert result["ok"] is True, result
    assert destination.read_text(encoding="utf-8") == "verified report\n"
    assert not list((destination_root / "report").glob(".*.solar-publish-*"))


def test_failed_rollback_preserves_the_original_file_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, destination_root, destination_a, destination_b = _stage_two_file_publish(
        tmp_path
    )
    real_replace = am.os.replace

    def fail_publish_and_restore(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if destination_path == destination_b:
            raise OSError("injected second-destination replace failure")
        if (
            destination_path == destination_a
            and ".solar-publish-backup-" in source_path.name
        ):
            raise OSError("injected rollback restore failure")
        real_replace(source, destination)

    monkeypatch.setattr(am.os, "replace", fail_publish_and_restore)

    result = am.publish_workspace_outputs(manifest, destination_root)

    assert result["ok"] is False, result
    backups = list(destination_root.glob(".a.txt.solar-publish-backup-*"))
    assert len(backups) == 1, result
    assert backups[0].read_text(encoding="utf-8") == "old-a\n"
    assert any("rollback also failed" in error for error in result["errors"])


def test_eval_pass_is_invalidated_when_declared_output_changes_before_closeout(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-eval-drift"
    node = {
        "id": "S1",
        "status": "reviewing",
        "depends_on": [],
        "read_scope": [],
        "write_scope": ["workspace/jsonl_stats.py"],
        "proof_obligations": [],
    }
    graph = _contracted_graph(sid, [node])
    graph_path = sprints / f"{sid}.task_graph.json"
    output = sprints / sid / "workdir" / "workspace" / "jsonl_stats.py"
    output.parent.mkdir(parents=True)
    output.write_bytes(_published_bytes())

    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)
    assert snapshot["ok"] is True, snapshot
    eval_path = sprints / f"{sid}.S1-eval.json"
    eval_path.write_text(
        json.dumps(
            {
                "node_id": "S1",
                "verdict": "PASS",
                "artifact_snapshot_schema": snapshot["schema"],
                "artifact_snapshot_path": snapshot["path"],
                "artifact_snapshot_digest": snapshot["snapshot_digest"],
            }
        ),
        encoding="utf-8",
    )
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    output.write_bytes(_late_staging_bytes())
    result = gnd.node_verdict(
        str(graph_path),
        "S1",
        "pass",
        eval_json=str(eval_path),
        dispatch_downstream=False,
    )

    assert result["ok"] is False, result
    assert result["reason"] == "eval_artifact_snapshot_changed"
    saved = gs.load_graph(graph_path)
    assert gs.node_status(saved, "S1") == "needs_human_review"
    assert next(item for item in saved["nodes"] if item["id"] == "S1").get("repair_attempts", 0) == 0


def test_failed_closeout_never_exposes_a_gate_consumable_pass(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-no-early-consumable-pass"
    node = {
        "id": "S1",
        "status": "reviewing",
        "depends_on": [],
        "read_scope": [],
        "write_scope": ["workspace/jsonl_stats.py"],
        "proof_obligations": [],
    }
    graph = _contracted_graph(sid, [node])
    output = sprints / sid / "workdir" / "workspace" / "jsonl_stats.py"
    output.parent.mkdir(parents=True)
    output.write_bytes(_published_bytes())
    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)
    assert snapshot["ok"] is True, snapshot
    eval_path = sprints / f"{sid}.S1-eval.json"
    eval_path.write_text(
        json.dumps(
            {
                "node_id": "S1",
                "verdict": "PASS",
                "artifact_snapshot_schema": snapshot["schema"],
                "artifact_snapshot_path": snapshot["path"],
                "artifact_snapshot_digest": snapshot["snapshot_digest"],
            }
        ),
        encoding="utf-8",
    )

    # The evaluator judged A, but A changed before the closeout authority ran.
    # A rejected closeout must not leak an independently consumable PASS into
    # the append-only ledger for another gate reader to observe.
    output.write_bytes(_late_staging_bytes())
    result = gnd._finalize_node_pass(
        sid,
        node,
        graph,
        eval_json=eval_path,
    )

    assert result["ok"] is False, result
    assert result["reason"] == "eval_artifact_snapshot_changed"
    assert gl.latest_consumable_verdict(
        sprints,
        sid,
        "S1",
        current_generation=0,
    ) is None


def _stage_failed_eval_then_drift(
    sprints: Path,
    sid: str,
) -> tuple[dict, dict, Path, Path]:
    node = {
        "id": "S1",
        "status": "reviewing",
        "depends_on": [],
        "read_scope": [],
        "write_scope": ["workspace/jsonl_stats.py"],
        "proof_obligations": [],
    }
    graph = _contracted_graph(sid, [node])
    graph_path = sprints / f"{sid}.task_graph.json"
    output = sprints / sid / "workdir" / "workspace" / "jsonl_stats.py"
    output.parent.mkdir(parents=True)
    output.write_bytes(_published_bytes())
    (sprints / f"{sid}.S1-handoff.md").write_text(
        "# Builder handoff\n\nImplementation ready for independent review.\n",
        encoding="utf-8",
    )
    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)
    assert snapshot["ok"] is True, snapshot
    eval_path = sprints / f"{sid}.S1-eval.json"
    eval_path.write_text(
        json.dumps(
            {
                "node_id": "S1",
                "verdict": "FAIL",
                "summary": "output does not meet the contract",
                "artifact_snapshot_schema": snapshot["schema"],
                "artifact_snapshot_path": snapshot["path"],
                "artifact_snapshot_digest": snapshot["snapshot_digest"],
            }
        ),
        encoding="utf-8",
    )
    (sprints / f"{sid}.S1-eval.md").write_text(
        "# Independent evaluation\n\nFAIL: output does not meet the contract.\n",
        encoding="utf-8",
    )
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    output.write_bytes(_late_staging_bytes())
    return graph, node, graph_path, eval_path


def test_stale_failed_verdict_cannot_start_repair(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    graph, _node, graph_path, eval_path = _stage_failed_eval_then_drift(
        sprints,
        "sprint-rc10-failed-eval-drift",
    )

    result = gnd.node_verdict(
        str(graph_path),
        "S1",
        "fail",
        eval_json=str(eval_path),
        dispatch_downstream=False,
    )

    assert result["ok"] is False, result
    assert result["reason"] == "eval_artifact_snapshot_changed"
    saved = gs.load_graph(graph_path)
    saved_node = next(item for item in saved["nodes"] if item["id"] == "S1")
    assert gs.node_status(saved, "S1") == "needs_human_review"
    assert saved_node.get("repair_attempts", 0) == 0
    assert not saved_node.get("repair_context")


def test_proof_sidecar_refresh_does_not_change_snapshotted_bytes(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    sid = "sprint-rc10-proof-sidecar-idempotent"
    node = {
        "id": "S1",
        "status": "reviewing",
        "depends_on": [],
        "read_scope": [],
        "write_scope": ["workspace/out.txt"],
        "proof_obligations": [],
    }
    output = sprints / sid / "workdir" / "workspace" / "out.txt"
    output.parent.mkdir(parents=True)
    output.write_text("stable output\n", encoding="utf-8")
    (sprints / f"{sid}.S1-handoff.md").write_text(
        "# Handoff\n\nStable output ready.\n",
        encoding="utf-8",
    )
    gnd._emit_node_proof_sidecars(sid, node)
    paths = [
        sprints / f"{sid}.S1-guard_decision.json",
        sprints / f"{sid}.S1-resource_binding.json",
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}

    # Cross the old one-second checked_at boundary. Closeout may rescan, but
    # unchanged evidence must remain byte-identical to the evaluator snapshot.
    time.sleep(1.05)
    gnd._emit_node_proof_sidecars(sid, node)

    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    assert after == before


def test_eval_snapshot_rejects_declared_path_outside_artifact_roots(
    sandbox: tuple[Path, Path],
) -> None:
    harness, _sprints = sandbox
    sid = "sprint-rc10-eval-root-escape"
    outside = harness.parent / "outside.txt"
    outside.write_text("not sprint-owned\n", encoding="utf-8")
    node = {
        "id": "S1",
        "status": "reviewing",
        "depends_on": [],
        "read_scope": [],
        "write_scope": [str(outside)],
        "proof_obligations": [],
    }
    graph = _contracted_graph(sid, [node])

    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)

    assert snapshot["ok"] is False, snapshot
    assert any(
        item.get("code") == "DECLARED_EVAL_BYTES_OUTSIDE_ROOT"
        and item.get("declared") == str(outside)
        for item in snapshot["violations"]
    )


def test_reconcile_cannot_repair_from_stale_failed_verdict(
    sandbox: tuple[Path, Path],
) -> None:
    _harness, sprints = sandbox
    graph, node, graph_path, _eval_path = _stage_failed_eval_then_drift(
        sprints,
        "sprint-rc10-reconcile-failed-eval-drift",
    )

    reconciled = gnd._reconcile_existing_dispatches(graph, graph_path)

    assert any(
        item.get("node") == "S1"
        and item.get("status") == "needs_human_review"
        and item.get("reason") == "eval_artifact_snapshot_changed"
        for item in reconciled
    ), reconciled
    assert gs.node_status(graph, "S1") == "needs_human_review"
    assert node.get("repair_attempts", 0) == 0
    assert not node.get("repair_context")


def test_final_verifier_refuses_published_and_staging_read_scope_drift(
    sandbox: tuple[Path, Path],
) -> None:
    harness, sprints = sandbox
    sid = "sprint-rc10-final-review-drift"
    product = harness.parent / "product"
    product.mkdir()
    workspace_binding.bind_active_workspace(harness, product)
    (sprints / f"{sid}.raw_intent.json").write_text(
        json.dumps({"context": {"repo": str(product)}}),
        encoding="utf-8",
    )
    product_file = product / "jsonl_stats.py"
    product_file.write_bytes(_published_bytes())
    staging_file = sprints / sid / "workdir" / "workspace" / "jsonl_stats.py"
    staging_file.parent.mkdir(parents=True)
    staging_file.write_bytes(_published_bytes())
    review_file = staging_file.parent / ".pm" / "evidence" / "review_decision.json"
    review_file.parent.mkdir(parents=True)
    review_file.write_text('{"verdict":"PASS"}\n', encoding="utf-8")

    builder = {
        "id": "S1",
        "status": "passed",
        "depends_on": [],
        "read_scope": [],
        "write_scope": ["workspace/jsonl_stats.py"],
    }
    _write_publication_authority(
        sprints,
        sid,
        builder,
        staging_file,
        product,
        product_file,
    )
    staging_file.write_bytes(_late_staging_bytes())
    verifier = {
        "id": "S3",
        "status": "reviewing",
        "depends_on": ["S1"],
        "read_scope": ["workspace/jsonl_stats.py"],
        "write_scope": ["workspace/.pm/evidence/review_decision.json"],
        "proof_obligations": [],
    }
    graph = _contracted_graph(sid, [builder, verifier])

    snapshot = gnd._capture_eval_artifact_snapshot(sid, verifier, graph)

    assert snapshot["ok"] is False, snapshot
    assert any(
        item.get("code") == "PUBLISHED_STAGING_CONTENT_MISMATCH"
        and item.get("declared") == "workspace/jsonl_stats.py"
        for item in snapshot["violations"]
    )
    published_rows = [row for row in snapshot["rows"] if row.get("authority") == "published_frozen"]
    assert published_rows[0]["published_path"] == str(product_file.resolve())
    assert Path(published_rows[0]["path"]).is_relative_to(sprints)
    assert Path(published_rows[0]["path"]).read_bytes() == _published_bytes()
    assert published_rows[0]["sha256"] == PUBLISHED_SHA256


def test_downstream_review_rejects_rewritten_publication_authority(
    sandbox: tuple[Path, Path],
) -> None:
    harness, sprints = sandbox
    sid = "sprint-rc10-publish-sidecar-tamper"
    product = harness.parent / "product"
    product.mkdir()
    workspace_binding.bind_active_workspace(harness, product)
    (sprints / f"{sid}.raw_intent.json").write_text(
        json.dumps({"context": {"repo": str(product)}}),
        encoding="utf-8",
    )
    product_file = product / "jsonl_stats.py"
    product_file.write_bytes(_published_bytes())
    staging_file = sprints / sid / "workdir" / "workspace" / "jsonl_stats.py"
    staging_file.parent.mkdir(parents=True)
    staging_file.write_bytes(_published_bytes())
    review_file = staging_file.parent / ".pm" / "evidence" / "review_decision.json"
    review_file.parent.mkdir(parents=True)
    review_file.write_text('{"verdict":"PASS"}\n', encoding="utf-8")
    builder = {
        "id": "S1",
        "status": "passed",
        "depends_on": [],
        "read_scope": [],
        "write_scope": ["workspace/jsonl_stats.py"],
    }
    original_sidecar = _write_publication_authority(
        sprints,
        sid,
        builder,
        staging_file,
        product,
        product_file,
    )
    verifier = {
        "id": "S3",
        "status": "reviewing",
        "depends_on": ["S1"],
        "read_scope": ["workspace/jsonl_stats.py"],
        "write_scope": ["workspace/.pm/evidence/review_decision.json"],
        "proof_obligations": [],
    }
    graph = _contracted_graph(sid, [builder, verifier])

    # Rewrite both visible copies and make the sidecar self-consistent with B.
    # The producer receipt and manifest remain committed to A, so downstream
    # evaluation must not accept B as a newly-defined publication authority.
    product_file.write_bytes(_late_staging_bytes())
    staging_file.write_bytes(_late_staging_bytes())
    tampered = json.loads(json.dumps(original_sidecar))
    tampered["published"][0]["sha256"] = LATE_STAGING_SHA256
    tampered["published_digest"] = am.published_content_digest(tampered["published"])
    (sprints / f"{sid}.S1-publish.json").write_text(
        json.dumps(tampered),
        encoding="utf-8",
    )

    snapshot = gnd._capture_eval_artifact_snapshot(sid, verifier, graph)

    assert snapshot["ok"] is False, snapshot
    assert any(
        item.get("code") == "PUBLISHED_READ_AUTHORITY_DIGEST_MISMATCH"
        and item.get("declared") == "workspace/jsonl_stats.py"
        for item in snapshot["violations"]
    )


def test_downstream_review_accepts_exact_published_directory_tree(
    sandbox: tuple[Path, Path],
) -> None:
    harness, sprints = sandbox
    sid = "sprint-rc10-published-directory"
    product = harness.parent / "product"
    product.mkdir()
    workspace_binding.bind_active_workspace(harness, product)
    (sprints / f"{sid}.raw_intent.json").write_text(
        json.dumps({"context": {"repo": str(product)}}),
        encoding="utf-8",
    )
    workdir = sprints / sid / "workdir"
    staging_dir = workdir / "workspace" / "pkg"
    (staging_dir / "empty").mkdir(parents=True)
    (staging_dir / "a.txt").write_text("alpha\n", encoding="utf-8")
    (staging_dir / "nested").mkdir()
    (staging_dir / "nested" / "b.txt").write_text("beta\n", encoding="utf-8")
    builder = {
        "id": "S1",
        "status": "passed",
        "depends_on": [],
        "read_scope": [],
        "write_scope": ["workspace/pkg/"],
    }
    manifest = am.write_manifest(
        sprints,
        sid,
        builder,
        generation=0,
        base_dir=workdir,
        roots={"canonical": "workspace/"},
    )
    assert manifest is not None
    assert manifest["rows"][0]["kind"] == "directory"
    publish = am.publish_workspace_outputs(manifest, product)
    assert publish["ok"] is True, publish
    sidecar = {
        "schema": "solar.workspace_publish.v1",
        "sid": sid,
        "node_id": "S1",
        "required": True,
        "ok": True,
        "workspace_root": str(product),
        **publish,
    }
    (sprints / f"{sid}.S1-publish.json").write_text(
        json.dumps(sidecar),
        encoding="utf-8",
    )
    builder["closeout_receipt"] = {
        "schema": "solar.node_closeout.v1",
        "sid": sid,
        "node_id": "S1",
        "verdict": "passed",
        "manifest": {"content_digest": manifest["content_digest"]},
        "publication": {
            "required": True,
            "ok": True,
            "published_count": len(publish["published"]),
            "manifest_digest": publish["manifest_digest"],
            "published_digest": publish["published_digest"],
        },
    }
    review = workdir / "workspace" / "review.json"
    review.write_text('{"verdict":"PASS"}\n', encoding="utf-8")
    verifier = {
        "id": "S2",
        "status": "reviewing",
        "depends_on": ["S1"],
        "read_scope": ["workspace/pkg/"],
        "write_scope": ["workspace/review.json"],
        "proof_obligations": [],
    }
    graph = _contracted_graph(sid, [builder, verifier])

    snapshot = gnd._capture_eval_artifact_snapshot(sid, verifier, graph)

    assert snapshot["ok"] is True, snapshot
    published_rows = [
        row
        for row in snapshot["rows"]
        if row.get("authority") == "published_frozen"
    ]
    assert len(published_rows) == 1
    assert published_rows[0]["kind"] == "directory"
    assert published_rows[0]["sha256"] == manifest["rows"][0]["sha256"]



def test_downstream_review_accepts_published_file_inside_manifest_directory(
    sandbox: tuple[Path, Path],
) -> None:
    harness, sprints = sandbox
    sid = "sprint-rc10-published-directory-child"
    product = harness.parent / "product"
    product.mkdir()
    workspace_binding.bind_active_workspace(harness, product)
    (sprints / f"{sid}.raw_intent.json").write_text(
        json.dumps({"context": {"repo": str(product)}}),
        encoding="utf-8",
    )
    workdir = sprints / sid / "workdir"
    staging_dir = workdir / "workspace" / "pkg"
    staging_file = staging_dir / "nested" / "b.txt"
    staging_file.parent.mkdir(parents=True)
    staging_file.write_text("beta\n", encoding="utf-8")
    builder = {
        "id": "S1",
        "status": "passed",
        "depends_on": [],
        "read_scope": [],
        "write_scope": ["workspace/pkg/"],
    }
    manifest = am.write_manifest(
        sprints,
        sid,
        builder,
        generation=0,
        base_dir=workdir,
        roots={"canonical": "workspace/"},
    )
    assert manifest is not None
    assert manifest["rows"][0]["kind"] == "directory"
    child = next(
        entry
        for entry in manifest["rows"][0]["entries"]
        if entry.get("rel_path") == "nested/b.txt"
    )
    product_file = product / "pkg" / "nested" / "b.txt"
    product_file.parent.mkdir(parents=True)
    product_file.write_bytes(staging_file.read_bytes())
    published = [
        {
            "from": str(staging_file),
            "to": str(product_file),
            "sha256": child["sha256"],
        }
    ]
    publish_sidecar = {
        "schema": "solar.workspace_publish.v1",
        "sid": sid,
        "node_id": "S1",
        "required": True,
        "ok": True,
        "workspace_root": str(product),
        "published": published,
        "manifest_digest": manifest["content_digest"],
        "published_digest": am.published_content_digest(published),
    }
    (sprints / f"{sid}.S1-publish.json").write_text(
        json.dumps(publish_sidecar),
        encoding="utf-8",
    )
    builder["closeout_receipt"] = {
        "schema": "solar.node_closeout.v1",
        "sid": sid,
        "node_id": "S1",
        "verdict": "passed",
        "manifest": {"content_digest": manifest["content_digest"]},
        "publication": {
            "required": True,
            "ok": True,
            "published_count": 1,
            "manifest_digest": manifest["content_digest"],
            "published_digest": publish_sidecar["published_digest"],
        },
    }
    verifier = {
        "id": "S2",
        "status": "reviewing",
        "depends_on": ["S1"],
        "read_scope": ["workspace/pkg/nested/b.txt"],
        "write_scope": [],
        "proof_obligations": [],
    }
    graph = _contracted_graph(sid, [builder, verifier])

    snapshot = gnd._capture_eval_artifact_snapshot(sid, verifier, graph)

    assert snapshot["ok"] is True, snapshot
    published_rows = [
        row for row in snapshot["rows"] if row.get("authority") == "published_frozen"
    ]
    assert len(published_rows) == 1
    assert published_rows[0]["kind"] == "file"
    assert published_rows[0]["sha256"] == child["sha256"]


def test_contracted_pass_receipt_requires_snapshot_and_publication_digests() -> None:
    graph = _contracted_graph(
        "sprint-rc10-receipt-bytes",
        [{"id": "S1", "status": "reviewing", "depends_on": []}],
    )
    receipt = {
        "schema": "solar.node_closeout.v1",
        "sid": graph["sprint_id"],
        "node_id": "S1",
        "verdict": "passed",
        "eval": {"consumable": True, "record_id": "record-1", "path": "/tmp/eval.json"},
        "manifest": {
            "ok": True,
            "schema": "solar.artifact_manifest.v1",
            "path": "/tmp/manifest.json",
        },
        "proof": {"ok": True},
        "research_quality": {"ok": True},
        "publication": {"ok": True, "required": True, "published_count": 1},
    }

    with pytest.raises(ValueError, match="contracted_pass_invalid_closeout_receipt:S1:eval_snapshot"):
        gs._validate_contract_closeout_receipt(graph, "S1", receipt)
