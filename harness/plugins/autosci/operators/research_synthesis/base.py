"""Bounded operator helpers for the draft research_synthesis_v1 workflow."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"completed", "failed", "blocked", "cancelled"}
NONTERMINAL_STATUSES = {"pending", "ready", "running", "awaiting_human", "awaiting_external"}
NODE_STATUSES = TERMINAL_STATUSES | NONTERMINAL_STATUSES


class ResearchOperatorError(Exception):
    """Raised when a bounded operator cannot safely fulfill its node request."""

    def __init__(self, message: str, *, error_type: str = "operator_error") -> None:
        super().__init__(message)
        self.error_type = error_type


@dataclass(frozen=True)
class OperatorContext:
    """Execution context for one Solar-owned node request."""

    node_request: dict[str, Any]
    services: dict[str, Any]
    workspace_root: Path

    @classmethod
    def from_request(
        cls,
        node_request: dict[str, Any],
        *,
        services: dict[str, Any] | None = None,
        workspace_root: Path | None = None,
    ) -> "OperatorContext":
        return cls(
            node_request=node_request,
            services=dict(services or {}),
            workspace_root=(workspace_root or Path.cwd()).resolve(),
        )

    @property
    def payload(self) -> dict[str, Any]:
        typed_inputs = self.node_request.get("typed_inputs") if isinstance(self.node_request.get("typed_inputs"), dict) else {}
        payload = typed_inputs.get("payload") if isinstance(typed_inputs.get("payload"), dict) else {}
        return payload

    @property
    def read_scope(self) -> list[str]:
        return [str(item) for item in self.node_request.get("read_scope") or []]

    @property
    def write_scope(self) -> list[str]:
        return [str(item) for item in self.node_request.get("write_scope") or []]

    @property
    def secret_refs(self) -> list[str]:
        authorization = self.node_request.get("authorization") if isinstance(self.node_request.get("authorization"), dict) else {}
        return [str(item) for item in authorization.get("secret_refs") or [] if str(item).strip()]

    @property
    def secret_values(self) -> dict[str, str]:
        """Return explicitly injected secret values without copying them to artifacts.

        Callers may inject ``services["secret_values"]`` solely so the bounded
        sanitizer can recognize otherwise opaque credentials.  Values are kept
        in memory and are never included in node requests or result metadata.
        """

        supplied = self.services.get("secret_values")
        if not isinstance(supplied, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in supplied.items()
            if str(key).strip() and str(value)
        }

    @property
    def secret_verification_complete(self) -> bool:
        return not self.secret_refs or all(ref in self.secret_values for ref in self.secret_refs)

    def input_artifact_refs(self) -> list[dict[str, Any]]:
        return [item for item in self.node_request.get("input_artifact_refs") or [] if isinstance(item, dict)]

    def load_json_artifact(self, artifact_ref: dict[str, Any]) -> dict[str, Any]:
        path = validate_scoped_path(artifact_ref.get("path", ""), self.read_scope, workspace_root=self.workspace_root)
        try:
            data = path.read_bytes()
            expected_hash = str(artifact_ref.get("sha256") or "")
            if expected_hash and sha256_bytes(data).lower() != expected_hash.lower():
                raise ResearchOperatorError(
                    f"Input artifact hash does not match reference: {artifact_ref.get('path')}",
                    error_type="artifact_hash_mismatch",
                )
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResearchOperatorError(f"Input artifact is not valid JSON: {artifact_ref.get('path')}", error_type="invalid_input") from exc
        except OSError as exc:
            raise ResearchOperatorError(f"Input artifact cannot be read: {artifact_ref.get('path')}", error_type="scope_read_error") from exc
        if not isinstance(payload, dict):
            raise ResearchOperatorError("Input artifact JSON must be an object", error_type="invalid_input")
        return payload


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def stable_json_sha256(payload: Any) -> str:
    return sha256_bytes(stable_json_bytes(payload))


def _resolve(path_text: str | Path, workspace_root: Path) -> Path:
    path = Path(str(path_text))
    if path.is_absolute():
        return path.resolve()
    return (workspace_root / path).resolve()


def _is_same_or_child(path: Path, scope: Path) -> bool:
    try:
        common = os.path.commonpath([str(path), str(scope)])
    except ValueError:
        return False
    return common == str(scope)


def validate_scoped_path(
    path_text: str | Path,
    scopes: list[str],
    *,
    workspace_root: Path | None = None,
    must_exist: bool = False,
) -> Path:
    """Resolve a path only if it is equal to, or below, one declared scope."""

    workspace = (workspace_root or Path.cwd()).resolve()
    if not str(path_text or "").strip():
        raise ResearchOperatorError("Path is empty", error_type="scope_violation")
    target = _resolve(path_text, workspace)
    scope_entries = [(str(scope), _resolve(scope, workspace)) for scope in scopes if str(scope).strip()]
    scope_paths = [path for _raw, path in scope_entries]
    if not scope_paths:
        raise ResearchOperatorError("No scope was declared for path access", error_type="scope_violation")
    if not _is_same_or_child(target, workspace):
        raise ResearchOperatorError(f"Path escapes workspace root: {path_text}", error_type="scope_violation")
    outside_scopes = [raw for raw, scope_path in scope_entries if not _is_same_or_child(scope_path, workspace)]
    if outside_scopes:
        raise ResearchOperatorError(
            "Declared scope escapes workspace root: " + ", ".join(outside_scopes),
            error_type="scope_violation",
        )

    def scope_allows(target_path: Path, raw_scope: str, scope_path: Path) -> bool:
        if target_path == scope_path:
            return True
        raw = raw_scope.replace("\\", "/")
        scope_is_directory = raw.endswith("/") or raw.endswith("/.") or Path(raw_scope).suffix == ""
        return scope_is_directory and _is_same_or_child(target_path, scope_path)

    if not any(scope_allows(target, raw_scope, scope_path) for raw_scope, scope_path in scope_entries):
        raise ResearchOperatorError(f"Path escapes declared scope: {path_text}", error_type="scope_violation")
    if must_exist and not target.exists():
        raise ResearchOperatorError(f"Scoped path does not exist: {path_text}", error_type="missing_input")
    return target


def display_path(path: Path, workspace_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


_SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(?:api[_-]?key|access[_-]?token|token|auth(?:orization)?|cookie|credential|password|private[_-]?key|secret)(?:$|[_-])",
    re.IGNORECASE,
)
_SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[^\s,;]+"),
)


def _scrub_sensitive_text(value: str) -> str:
    redacted = value
    for pattern in _SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_secrets(
    value: Any,
    secret_refs: list[str] | None = None,
    secret_values: dict[str, str] | None = None,
) -> Any:
    """Sanitize observable secret shapes.

    ``secret_refs`` are identifiers for secrets held outside the operator.  They
    are deliberately *not* treated as secret values: seeing ``OPENAI_API_KEY``
    in a contract is not proof that the corresponding credential was exposed.
    """

    opaque_values = sorted(
        {str(item) for item in (secret_values or {}).values() if str(item)},
        key=len,
        reverse=True,
    )

    def scrub(item: Any) -> Any:
        if isinstance(item, dict):
            out: dict[str, Any] = {}
            for key, child in item.items():
                key_text = str(key)
                lowered = key_text.lower()
                if key_text in {"secret_redaction_assertion", "no_secrets_observed", "redaction_review", "input_tokens", "output_tokens"}:
                    out[key_text] = scrub(child)
                elif _SENSITIVE_KEY.search(lowered):
                    out[key_text] = "[REDACTED]"
                else:
                    out[key_text] = scrub(child)
            return out
        if isinstance(item, list):
            return [scrub(child) for child in item]
        if isinstance(item, str):
            redacted = item
            for secret_value in opaque_values:
                redacted = redacted.replace(secret_value, "[REDACTED]")
            return _scrub_sensitive_text(redacted)
        return item

    return scrub(value)


def load_artifact(
    context: OperatorContext,
    *,
    schemas: tuple[str, ...],
    artifact_ids: tuple[str, ...],
    filenames: tuple[str, ...] = (),
    payload_keys: tuple[str, ...] = (),
    expected_node_ids: tuple[str, ...] = (),
    require_hash: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Load one upstream artifact by stable identity.

    Preserved schema wins, followed by exact artifact id.  A filename fallback
    is accepted only when the loaded document itself declares an expected
    schema.  Inline payloads remain a compatibility fallback for isolated
    operator calls, never a replacement for an available artifact reference.
    """

    candidates: list[tuple[int, int, dict[str, Any]]] = []
    expected_schemas = set(schemas)
    expected_ids = set(artifact_ids)
    expected_filenames = {name.replace("\\", "/").rsplit("/", 1)[-1] for name in filenames}
    for index, ref in enumerate(context.input_artifact_refs()):
        schema = str(ref.get("schema") or "")
        artifact_id = str(ref.get("artifact_id") or "")
        filename = str(ref.get("path") or "").replace("\\", "/").rsplit("/", 1)[-1]
        score = 300 if schema in expected_schemas else 200 if artifact_id in expected_ids else 100 if filename in expected_filenames else 0
        if score:
            candidates.append((score, index, ref))
    for score, _index, ref in sorted(candidates, key=lambda item: (-item[0], item[1])):
        if require_hash and not str(ref.get("sha256") or ""):
            raise ResearchOperatorError(
                f"Acceptance-critical artifact reference has no sha256: {ref.get('path')}",
                error_type="missing_artifact_hash",
            )
        payload = context.load_json_artifact(ref)
        embedded_schema = str(payload.get("schema") or "")
        if embedded_schema and embedded_schema not in expected_schemas:
            raise ResearchOperatorError(
                f"Input artifact identity does not match expected schema: {ref.get('path')}",
                error_type="artifact_identity_mismatch",
            )
        embedded_node_id = str(payload.get("node_id") or "")
        if expected_node_ids and not embedded_node_id:
            raise ResearchOperatorError(
                f"Input artifact is missing required node_id: {ref.get('path')}",
                error_type="artifact_identity_missing",
            )
        if expected_node_ids and embedded_node_id not in set(expected_node_ids):
            raise ResearchOperatorError(
                f"Input artifact has wrong upstream node identity: {embedded_node_id}",
                error_type="artifact_identity_mismatch",
            )
        for identity_key in ("task_id", "run_id", "workflow_id"):
            embedded_identity = str(payload.get(identity_key) or "")
            request_identity = str(context.node_request.get(identity_key) or "")
            if not embedded_identity:
                raise ResearchOperatorError(
                    f"Input artifact is missing required {identity_key}: {ref.get('path')}",
                    error_type="artifact_identity_missing",
                )
            if not request_identity or embedded_identity != request_identity:
                raise ResearchOperatorError(
                    f"Input artifact {identity_key} does not match node request.",
                    error_type="artifact_identity_mismatch",
                )
        if embedded_schema in expected_schemas:
            return payload, ref
    if context.input_artifact_refs():
        # A referenced artifact is authoritative; do not silently replace a
        # malformed/mismatched upstream result with convenient inline data.
        return {}, None
    for key in payload_keys:
        value = context.payload.get(key)
        if isinstance(value, dict):
            return value, None
    return {}, None


def write_artifact(
    context: OperatorContext,
    relative_path: str,
    payload: Any,
    *,
    artifact_id: str,
    schema: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    target = validate_scoped_path(relative_path, context.write_scope, workspace_root=context.workspace_root)
    artifact_payload = dict(payload) if isinstance(payload, dict) else payload
    if isinstance(artifact_payload, dict):
        embedded_artifact_id = str(artifact_payload.get("artifact_id") or "")
        if embedded_artifact_id and embedded_artifact_id != artifact_id:
            raise ResearchOperatorError(
                "Artifact payload artifact_id does not match the declared artifact_id.",
                error_type="artifact_identity_mismatch",
            )
        artifact_payload["artifact_id"] = artifact_id
        artifact_payload.setdefault("task_id", str(context.node_request.get("task_id") or ""))
        artifact_payload.setdefault("run_id", str(context.node_request.get("run_id") or ""))
        artifact_payload.setdefault("workflow_id", str(context.node_request.get("workflow_id") or ""))
    redacted = redact_secrets(artifact_payload, context.secret_refs, context.secret_values)
    body = json.dumps(redacted, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    digest = sha256_bytes(target.read_bytes())
    artifact = {
        "artifact_id": artifact_id,
        "path": display_path(target, context.workspace_root),
        "schema": schema,
        "sha256": digest,
    }
    hash_record = {"hash_id": artifact_id, "algorithm": "sha256", "value": digest}
    return artifact, hash_record


def build_node_result(
    context: OperatorContext,
    *,
    status: str,
    output_artifacts: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    hashes: list[dict[str, Any]] | None = None,
    model_provider_usage: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    if status not in NODE_STATUSES:
        raise ResearchOperatorError(f"Unsupported node status: {status}", error_type="invalid_status")
    result = {
        "schema": "research_node_result.v1",
        "task_id": str(context.node_request.get("task_id") or ""),
        "run_id": str(context.node_request.get("run_id") or ""),
        "workflow_id": str(context.node_request.get("workflow_id") or ""),
        "node_id": str(context.node_request.get("node_id") or ""),
        "status": status,
        "status_is_terminal": status in TERMINAL_STATUSES,
        "output_artifacts": list(output_artifacts or []),
        "evidence": list(evidence or []),
        "hashes": list(hashes or []),
        "model_provider_usage": list(model_provider_usage or []),
        "errors": list(errors or []),
        "limitations": [str(item) for item in limitations or [] if str(item).strip()],
        "secret_redaction_assertion": {
            "no_secrets_observed": context.secret_verification_complete,
            "redaction_review": "passed" if context.secret_verification_complete else "not_applicable",
        },
    }
    return redact_secrets(result, context.secret_refs, context.secret_values)


def error_result(context: OperatorContext, exc: ResearchOperatorError) -> dict[str, Any]:
    return build_node_result(
        context,
        status="failed",
        errors=[{"error_id": "operator.error", "error_type": exc.error_type, "message": str(exc)[:500]}],
        limitations=["The operator stopped before writing an output artifact."],
    )


def require_node(context: OperatorContext, expected: str) -> None:
    actual = str(context.node_request.get("node_id") or "")
    if actual != expected:
        raise ResearchOperatorError(f"Operator expected node_id={expected}, got {actual}", error_type="wrong_node_identity")


def output_path(context: OperatorContext, filename: str) -> str:
    if not context.write_scope:
        raise ResearchOperatorError("No write scope declared", error_type="scope_violation")
    first_scope = context.write_scope[0].replace("\\", "/").rstrip("/")
    return f"{first_scope}/{filename}"


def evidence_ref(evidence_id: str, kind: str, summary: str, artifact_id: str) -> dict[str, str]:
    return {
        "evidence_id": evidence_id,
        "kind": kind,
        "summary": summary,
        "artifact_id": artifact_id,
    }


def no_provider_result(context: OperatorContext, service_name: str, *, status: str = "awaiting_external") -> dict[str, Any]:
    return build_node_result(
        context,
        status=status,
        limitations=[f"Required injected service `{service_name}` is unavailable; no synthetic evidence was generated."],
    )


def provider_usage_from(response: dict[str, Any], *, usage_kind: str) -> list[dict[str, Any]]:
    usage = response.get("provider_usage") or response.get("model_provider_usage") or response.get("usage")
    if isinstance(usage, list):
        return [item for item in usage if isinstance(item, dict)]
    if isinstance(usage, dict):
        provider = str(usage.get("provider") or response.get("provider") or "injected")
        model = str(usage.get("model") or response.get("model") or "injected")
        return [{
            "provider": provider,
            "model": model,
            "usage_kind": str(usage.get("usage_kind") or usage_kind),
            **{key: value for key, value in usage.items() if key not in {"provider", "model", "usage_kind"}},
        }]
    return [{
        "provider": str(response.get("provider") or "injected"),
        "model": str(response.get("model") or "injected"),
        "usage_kind": usage_kind,
    }]


def normalize_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return normalized or "item"
