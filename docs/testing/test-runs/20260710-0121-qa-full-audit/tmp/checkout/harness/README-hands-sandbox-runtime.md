# Solar-Harness Hands Sandbox Runtime v1

`SandboxHand` is the disposable local data-plane adapter for Solar-Harness.

## Lifecycle

```python
from hands_runtime import SandboxHand

hand = SandboxHand()
ref = hand.provision(capabilities=["shell"])
result = hand.execute(ref, "build", {
    "command": "pytest -q",
    "env_allow": ["PYTHONPATH"],
    "secret_refs": {"TOKEN": "env:UPSTREAM_TOKEN"},
}, idempotency_key="build-1")
hand.dispose(ref)
```

## Guarantees

- `provision` creates a private workspace and private HOME under `run/hands-sandbox/`.
- `execute` runs with a sanitized environment; host env is not inherited by default.
- `env_allow` is explicit and excludes secret-looking names.
- `secret_refs` inject secrets only by reference (`env:NAME` or files under `~/.solar/harness/secrets`).
- stdout/stderr, evidence payloads, and stored command strings are redacted before being stored.
- evidence is written under `reports/hands-sandbox-evidence/<hand_id>/evidence.json`.
- `dispose` removes the workspace while preserving evidence.
- activity events are written through `ActivityRuntime` into the session log.

## Boundary

This is a local process sandbox, not a VM/container security boundary. It solves runtime lifecycle, env isolation, evidence collection, idempotency, and disposal. Strong OS/container isolation remains a future adapter.
