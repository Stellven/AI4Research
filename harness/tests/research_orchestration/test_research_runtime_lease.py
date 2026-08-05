from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from harness.lib.research_orchestration.runtime_lease import ResearchLeaseAdapter, _pid_exists


class Clock:
    def __init__(self) -> None:
        self.value = dt.datetime(2026, 8, 5, 12, 0, tzinfo=dt.timezone.utc)

    def __call__(self) -> dt.datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += dt.timedelta(seconds=seconds)


_TEST_OPERATORS = {
    "operator-a",
    "operator-b",
    "operator-compat",
    "operator-after-crash",
    "operator-new",
    "shared-operator",
    "op/a",
    "op?a",
    *(f"operator-{index}" for index in range(8)),
}


def _write_registry(root: Path, operator_ids=()) -> None:
    registry = root / "config" / "physical-operators.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    ids = _TEST_OPERATORS | set(operator_ids)
    registry.write_text(
        json.dumps(
            {
                "version": 1,
                "operators": {
                    operator_id: {"enabled": True} for operator_id in sorted(ids)
                },
            }
        ),
        encoding="utf-8",
    )


def _adapter(root: Path, **kwargs) -> ResearchLeaseAdapter:
    _write_registry(root)
    return ResearchLeaseAdapter(root, **kwargs)


def test_acquire_conflict_same_run_node_returns_blocker(tmp_path) -> None:
    adapter = _adapter(tmp_path, clock=Clock())
    first = adapter.acquire("run-1", "N1", "operator-a")
    second = adapter.acquire("run-1", "N1", "operator-b")

    assert first["acquired"] is True
    assert second["acquired"] is False
    assert second["blocker"]["reason"] == "run_node_already_active"


def test_operator_busy_conflict_returns_structured_blocker(tmp_path) -> None:
    adapter = _adapter(tmp_path, clock=Clock())
    adapter.acquire("run-1", "N1", "operator-a")
    blocked = adapter.acquire("run-2", "N2", "operator-a")

    assert blocked["blocker"]["reason"] == "operator_busy"
    assert blocked["blocker"]["operator_id"] == "operator-a"


def test_heartbeat_renews_expiry_and_writes_status(tmp_path) -> None:
    clock = Clock()
    adapter = _adapter(tmp_path, clock=clock)
    lease = adapter.acquire("run-1", "N1", "operator-a", ttl_seconds=30)["lease"]
    clock.advance(10)

    renewed = adapter.heartbeat("run-1", "N1", "operator-a", lease_id=lease["lease_id"], ttl_seconds=90)
    status = json.loads((tmp_path / "run" / "operator-status" / "operator-a.json").read_text(encoding="utf-8"))

    assert renewed["ok"] is True
    assert renewed["lease"]["state"] == "running"
    assert renewed["lease"]["expires_at"] == "2026-08-05T12:01:40Z"
    assert status["runtime_state"] == "running"


def test_stale_lease_recovery_allows_new_acquire(tmp_path) -> None:
    clock = Clock()
    adapter = _adapter(tmp_path, clock=clock)
    adapter.acquire("run-1", "N1", "operator-a", ttl_seconds=5, heartbeat_timeout_seconds=5)
    clock.advance(10)

    blocked = adapter.acquire("run-1", "N1", "operator-b")
    recovered = adapter.acquire("run-1", "N1", "operator-b", recover_stale=True)

    assert blocked["blocker"]["reason"] == "stale_lease_requires_recovery"
    assert recovered["acquired"] is True
    assert recovered["lease"]["operator_id"] == "operator-b"


def test_live_lease_is_not_recovered_or_preempted(tmp_path) -> None:
    adapter = _adapter(tmp_path, clock=Clock())
    adapter.acquire("run-1", "N1", "operator-a", ttl_seconds=300)
    recovered = adapter.recover_stale("run-1", "N1")

    assert recovered["blocker"]["reason"] == "active_lease_not_recovered"
    assert (tmp_path / "run" / "operator-leases" / "operator-a.json").exists()


def test_release_removes_active_lease_and_archives(tmp_path) -> None:
    adapter = _adapter(tmp_path, clock=Clock())
    lease = adapter.acquire("run-1", "N1", "operator-a")["lease"]
    released = adapter.release("run-1", "N1", "operator-a", lease_id=lease["lease_id"], reason="done")

    assert released["released"] is True
    assert not (tmp_path / "run" / "operator-leases" / "operator-a.json").exists()
    assert list((tmp_path / "run" / "operator-leases" / "archive").glob("*.json"))


def test_crash_restart_reads_existing_active_lease(tmp_path) -> None:
    clock = Clock()
    _adapter(tmp_path, clock=clock).acquire("run-1", "N1", "operator-a", ttl_seconds=300)
    restarted = _adapter(tmp_path, clock=clock)

    blocked = restarted.acquire("run-1", "N1", "operator-b")

    assert blocked["blocker"]["reason"] == "run_node_already_active"


def test_corrupted_lease_can_be_recovered_by_operator(tmp_path) -> None:
    lease_dir = tmp_path / "run" / "operator-leases"
    lease_dir.mkdir(parents=True)
    (lease_dir / "operator-a.json").write_text("{not json", encoding="utf-8")
    adapter = _adapter(tmp_path, clock=Clock())

    result = adapter.acquire("run-1", "N1", "operator-a", recover_stale=True)

    assert result["acquired"] is True


def test_concurrent_same_node_only_one_acquisition_succeeds(tmp_path) -> None:
    adapter = _adapter(tmp_path, clock=Clock())

    def acquire(index: int) -> bool:
        return bool(adapter.acquire("run-1", "N1", f"operator-{index}")["acquired"])

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(acquire, range(4)))

    assert results.count(True) == 1


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[3]
    env["PYTHONPATH"] = str(repo_root)
    return env


def test_independent_processes_same_node_have_exactly_one_winner(tmp_path) -> None:
    """This is the contention that the old thread-only Windows test missed."""

    start = tmp_path / "start"
    _write_registry(tmp_path / "harness")
    script = """
import json, pathlib, sys, time
from harness.lib.research_orchestration.runtime_lease import ResearchLeaseAdapter
root, start, output, operator_id = map(pathlib.Path, sys.argv[1:5])
deadline = time.time() + 15
while not start.exists() and time.time() < deadline:
    time.sleep(0.005)
result = ResearchLeaseAdapter(root).acquire('run-process', 'node-process', operator_id.name)
output.write_text(json.dumps(result), encoding='utf-8')
"""
    processes: list[tuple[subprocess.Popen[str], Path]] = []
    for index in range(4):
        output = tmp_path / f"result-{index}.json"
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(tmp_path / "harness"),
                str(start),
                str(output),
                f"operator-{index}",
            ],
            env=_subprocess_env(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append((process, output))
    start.touch()

    results = []
    for process, output in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, (stdout, stderr)
        results.append(json.loads(output.read_text(encoding="utf-8")))

    assert sum(result.get("acquired") is True for result in results) == 1
    assert sum(result.get("acquired") is False for result in results) == 3
    lease_dir = tmp_path / "harness" / "run" / "operator-leases"
    assert not list(lease_dir.rglob("*.tmp"))


def test_independent_processes_same_operator_different_nodes_have_one_winner(
    tmp_path,
) -> None:
    start = tmp_path / "start-operator"
    _write_registry(tmp_path / "operator-harness")
    script = """
import json, pathlib, sys, time
from harness.lib.research_orchestration.runtime_lease import ResearchLeaseAdapter
root, start, output = map(pathlib.Path, sys.argv[1:4])
node_id = sys.argv[4]
deadline = time.time() + 15
while not start.exists() and time.time() < deadline:
    time.sleep(0.005)
result = ResearchLeaseAdapter(root).acquire('run-process', node_id, 'shared-operator')
output.write_text(json.dumps(result), encoding='utf-8')
"""
    processes: list[tuple[subprocess.Popen[str], Path]] = []
    for index in range(4):
        output = tmp_path / f"operator-result-{index}.json"
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(tmp_path / "operator-harness"),
                str(start),
                str(output),
                f"node-{index}",
            ],
            env=_subprocess_env(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append((process, output))
    start.touch()

    results = []
    for process, output in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, (stdout, stderr)
        results.append(json.loads(output.read_text(encoding="utf-8")))

    assert sum(result.get("acquired") is True for result in results) == 1
    assert sum(result.get("acquired") is False for result in results) == 3
    assert all(
        result.get("acquired") is True
        or result["blocker"]["reason"] == "operator_busy"
        for result in results
    )


def test_abandoned_process_claim_is_recovered_after_crash(tmp_path) -> None:
    root = tmp_path / "harness"
    claim = root / "run" / "operator-leases" / ".research-run-run-crash-node-crash.claim"
    marker = tmp_path / "claim-created"
    script = """
import json, os, pathlib, sys, time
claim, marker = map(pathlib.Path, sys.argv[1:3])
claim.mkdir(parents=True)
(claim / 'owner.json').write_text(json.dumps({
    'pid': os.getpid(), 'token': 'crashed-owner', 'created_at_epoch': time.time()
}), encoding='utf-8')
marker.touch()
os._exit(23)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(claim), str(marker)],
        env=_subprocess_env(),
    )
    deadline = time.time() + 10
    while not marker.exists() and time.time() < deadline:
        time.sleep(0.01)
    assert marker.exists()
    assert process.wait(timeout=10) == 23

    result = _adapter(
        root, claim_timeout_seconds=2, abandoned_claim_seconds=300
    ).acquire("run-crash", "node-crash", "operator-after-crash")

    assert result["acquired"] is True
    assert not claim.exists()


def test_exited_process_is_not_reported_alive_after_wait() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "raise SystemExit(0)"],
        env=_subprocess_env(),
    )
    pid = process.pid
    assert process.wait(timeout=10) == 0

    # On Windows OpenProcess can still succeed for an exited process while a
    # parent-owned process handle remains open. GetExitCodeProcess is required
    # to distinguish that state from a live claim owner.
    assert _pid_exists(pid) is False


def test_nested_secrets_are_never_persisted(tmp_path) -> None:
    opaque_secret = "opaque-provider-value-9f82d17"
    metadata = {
        "topic": "bounded synthesis",
        "provider_label": opaque_secret,
        "secretariat_notes": "meeting retained",
        "token_budget": "token budget=1000",
        "token": "token-direct-canary",
        "authorization": "Bearer nested-secret-canary",
        "nested": {
            "label": opaque_secret,
            "password": "password-canary",
            "accessToken": "token-canary",
        },
    }
    adapter = _adapter(tmp_path, clock=Clock())
    acquired = adapter.acquire(
        "run-1",
        "N1",
        "operator-a",
        metadata=metadata,
        secret_values=[opaque_secret],
        safe_metadata_fields=["topic", "secretariat_notes", "token_budget"],
    )

    persisted = (tmp_path / "run" / "operator-leases" / "operator-a.json").read_text(
        encoding="utf-8"
    )
    emitted = json.dumps(
        adapter.acquire(
            "run-2",
            "N2",
            "operator-b",
            metadata=metadata,
            secret_values=[opaque_secret],
            safe_metadata_fields=["topic", "secretariat_notes", "token_budget"],
        )
    )
    adapter.release(
        "run-1",
        "N1",
        "operator-a",
        lease_id=acquired["lease"]["lease_id"],
        reason=f"completed with {opaque_secret}",
        secret_values=[opaque_secret],
    )
    all_persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "run").rglob("*.json")
    )
    assert "bounded synthesis" in persisted
    assert "retained" in persisted
    assert "secretariat_notes" in persisted
    assert "token budget=1000" in persisted
    assert "secret_values" not in persisted
    for secret in (
        "nested-secret-canary",
        "password-canary",
        "key-canary",
        "token-canary",
        "token-direct-canary",
        opaque_secret,
    ):
        assert secret not in persisted
        assert secret not in emitted
        assert secret not in all_persisted


def test_fallback_record_uses_canonical_operator_lease_fields(tmp_path) -> None:
    adapter = _adapter(tmp_path, clock=Clock())
    result = adapter.acquire("run-compat", "node-compat", "operator-compat")
    lease = json.loads(
        (tmp_path / "run" / "operator-leases" / "operator-compat.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["acquired"] is True
    assert {
        "operator_id",
        "task_id",
        "sprint_id",
        "node_id",
        "leased_at",
        "expires_at",
        "state",
    } <= set(lease)
    assert lease["sprint_id"] == "run-compat"
    assert "schema" not in lease


def test_live_process_claim_is_never_stolen_only_because_it_is_old(tmp_path) -> None:
    root = tmp_path / "harness"
    claim = root / "run" / "operator-leases" / ".research-run-run-live-node-live.claim"
    claim.mkdir(parents=True)
    (claim / "owner.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "token": "live-owner",
                "created_at_epoch": time.time() - 3600,
            }
        ),
        encoding="utf-8",
    )

    adapter = _adapter(
        root, claim_timeout_seconds=0.1, abandoned_claim_seconds=1
    )
    blocked = adapter.acquire("run-live", "node-live", "operator-new")

    assert blocked["acquired"] is False
    assert blocked["blocker"]["reason"] == "lease_claim_busy"
    assert claim.exists()


def test_adapter_delegates_acquire_to_canonical_operator_runtime_api(tmp_path) -> None:
    class FakeOperatorRuntime:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []
            self.lease: dict = {}

        def acquire_operator_lease(self, **kwargs):
            self.calls.append(("acquire", dict(kwargs)))
            self.lease = {
                "operator_id": kwargs["operator_id"],
                "task_id": kwargs["task_id"],
                "sprint_id": kwargs["sprint_id"],
                "node_id": kwargs["node_id"],
                "leased_at": "2026-08-05T12:00:00Z",
                "expires_at": "2026-08-05T12:15:00Z",
                "state": kwargs["initial_state"],
            }
            return dict(self.lease)

        def update_operator_lease_metadata(self, operator_id, **fields):
            self.calls.append(("metadata", {"operator_id": operator_id, **fields}))
            self.lease.update(fields)
            return dict(self.lease)

    api = FakeOperatorRuntime()
    result = ResearchLeaseAdapter(
        tmp_path, clock=Clock(), operator_runtime_api=api
    ).acquire("run-native", "node-native", "operator-native")

    assert result["acquired"] is True
    assert [name for name, _payload in api.calls] == ["acquire", "metadata"]
    assert api.calls[0][1]["sprint_id"] == "run-native"
    assert api.calls[0][1]["node_id"] == "node-native"
    assert api.calls[1][1]["research_run_id"] == "run-native"


def test_ownerless_abandoned_claim_is_cleaned_after_stale_threshold(tmp_path) -> None:
    root = tmp_path / "harness"
    claim = root / "run" / "operator-leases" / ".research-run-run-old-node-old.claim"
    claim.mkdir(parents=True)
    old = time.time() - 120
    os.utime(claim, (old, old))

    result = _adapter(
        root, claim_timeout_seconds=1, abandoned_claim_seconds=1
    ).acquire("run-old", "node-old", "operator-new")

    assert result["acquired"] is True
    assert not claim.exists()


def test_unsafe_operator_ids_use_distinct_stable_filenames(tmp_path) -> None:
    adapter = _adapter(tmp_path, clock=Clock())
    first = adapter.acquire("run-a", "node-a", "op/a")
    second = adapter.acquire("run-b", "node-b", "op?a")

    assert first["acquired"] is True
    assert second["acquired"] is True
    paths = sorted((tmp_path / "run" / "operator-leases").glob("*.json"))
    assert len(paths) == 2
    assert paths[0].name != paths[1].name
    records = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert {record["operator_id"] for record in records} == {"op/a", "op?a"}


def test_legacy_lossy_filename_migrates_only_for_exact_identity(tmp_path) -> None:
    lease_dir = tmp_path / "run" / "operator-leases"
    lease_dir.mkdir(parents=True)
    legacy = lease_dir / "op-a.json"
    legacy.write_text(
        json.dumps(
            {
                "operator_id": "op/a",
                "task_id": "task-old",
                "sprint_id": "run-old",
                "run_id": "run-old",
                "research_run_id": "run-old",
                "node_id": "node-old",
                "lease_id": "lease-old",
                "leased_at": "2026-08-05T12:00:00Z",
                "heartbeat_at": "2026-08-05T12:00:00Z",
                "expires_at": "2026-08-05T13:00:00Z",
                "heartbeat_timeout_seconds": 7200,
                "state": "leased",
            }
        ),
        encoding="utf-8",
    )
    adapter = _adapter(tmp_path, clock=Clock())

    renewed = adapter.heartbeat(
        "run-old", "node-old", "op/a", lease_id="lease-old"
    )

    assert renewed["ok"] is True
    assert not legacy.exists()
    migrated = list(lease_dir.glob("op-a--*.json"))
    assert len(migrated) == 1
    assert json.loads(migrated[0].read_text(encoding="utf-8"))["operator_id"] == "op/a"


def test_windows_fallback_enforces_available_operator_registry(tmp_path) -> None:
    registry = tmp_path / "config" / "physical-operators.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "version": 1,
                "operators": {
                    "known": {"enabled": True},
                    "disabled": {"enabled": False},
                },
            }
        ),
        encoding="utf-8",
    )
    adapter = ResearchLeaseAdapter(tmp_path, clock=Clock())

    unknown = adapter.acquire("run-unknown", "node-unknown", "unknown")
    disabled = adapter.acquire("run-disabled", "node-disabled", "disabled")
    known = adapter.acquire("run-known", "node-known", "known")

    assert unknown["blocker"]["reason"] == "operator_not_found"
    assert disabled["blocker"]["reason"] == "operator_disabled"
    assert known["acquired"] is True


def test_windows_fallback_missing_registry_fails_closed(tmp_path) -> None:
    result = ResearchLeaseAdapter(tmp_path, clock=Clock()).acquire(
        "run-missing", "node-missing", "unknown"
    )

    assert result["acquired"] is False
    assert result["blocker"]["reason"] == "operator_registry_missing"
    assert not list((tmp_path / "run" / "operator-leases").glob("*.json"))


def test_metadata_without_secret_values_omits_opaque_and_nested_values(tmp_path) -> None:
    opaque = "opaque-provider-credential-4d9281"
    adapter = _adapter(tmp_path, clock=Clock())
    result = adapter.acquire(
        "run-metadata",
        "node-metadata",
        "operator-a",
        metadata={
            "provider_label": opaque,
            "secretariat_notes": "agenda retained",
            "token_budget": 1000,
            "nested": {"label": opaque},
        },
        safe_metadata_fields=["secretariat_notes"],
    )

    persisted = (tmp_path / "run" / "operator-leases" / "operator-a.json").read_text(
        encoding="utf-8"
    )
    assert result["acquired"] is True
    assert opaque not in persisted
    assert "provider_label" not in persisted
    assert "nested" not in persisted
    assert "agenda retained" in persisted
    assert '"token_budget": 1000' in persisted


@pytest.mark.skipif(os.name != "nt", reason="Windows subprocess contention stress")
@pytest.mark.parametrize("shape", ["different_operators_same_node", "same_operator_different_nodes"])
def test_windows_subprocess_contention_stress_50_rounds(tmp_path, shape) -> None:
    script = """
import json, pathlib, sys, time
from harness.lib.research_orchestration.runtime_lease import ResearchLeaseAdapter
root, start, output = map(pathlib.Path, sys.argv[1:4])
operator_id, node_id = sys.argv[4:6]
deadline = time.time() + 15
while not start.exists() and time.time() < deadline:
    time.sleep(0.002)
result = ResearchLeaseAdapter(root).acquire('stress-run', node_id, operator_id)
output.write_text(json.dumps(result), encoding='utf-8')
"""

    for round_index in range(50):
        root = tmp_path / shape / f"round-{round_index}" / "harness"
        _write_registry(root, {"stress-a", "stress-b", "stress-shared"})
        start = root.parent / "start"
        if shape == "different_operators_same_node":
            contenders = [("stress-a", "same-node"), ("stress-b", "same-node")]
        else:
            contenders = [("stress-shared", "node-a"), ("stress-shared", "node-b")]

        processes: list[tuple[subprocess.Popen[str], Path]] = []
        for index, (operator_id, node_id) in enumerate(contenders):
            output = root.parent / f"result-{index}.json"
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(root),
                    str(start),
                    str(output),
                    operator_id,
                    node_id,
                ],
                env=_subprocess_env(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            processes.append((process, output))
        start.touch()

        results = []
        for process, output in processes:
            stdout, stderr = process.communicate(timeout=20)
            assert process.returncode == 0, (round_index, stdout, stderr)
            results.append(json.loads(output.read_text(encoding="utf-8")))

        assert sum(result.get("acquired") is True for result in results) == 1, (
            round_index,
            results,
        )
        assert sum(result.get("acquired") is False for result in results) == 1
        assert all("Traceback" not in json.dumps(result) for result in results)
