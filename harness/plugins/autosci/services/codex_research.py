"""Schema-bound Codex CLI model service for fixed Solar research nodes.

This is a physical model service, not a scheduler.  Solar still owns node
dispatch and AutoSci still owns the research operator contract.  Each call
starts one ephemeral Codex context and returns one JSON object constrained by
the node-specific output schema.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from structured_output import OutputContractError, parse_json, project_schema, validate_output

from .production_research import ResearchModelService, ResearchOperatorError


class SharedInvocationJournal(list):
    """A journal that survives the resolver's deepcopy of the services dict.

    `default_production_resolver` hands operators `deepcopy(services)`, so the
    service objects an operator calls are copies and their journals are copies
    too. The adapter's `_merge_codex_invocation_usage` reads the ORIGINAL
    services to recover calls the operator's failure hid, and was therefore
    guaranteed to find nothing: on success the payload carries its own usage, so
    the breakage only showed up on failure, which is the one case the merge
    exists for. A failed provider call then left its service-evidence files
    undeclared and the node died reporting "operator changed unreported files"
    instead of the provider error.

    Returning self from __deepcopy__ keeps this one object shared without
    changing deepcopy semantics for anything else in the services dict.
    """

    def __deepcopy__(self, memo: dict) -> "SharedInvocationJournal":
        memo[id(self)] = self
        return self


CODEX_RESEARCH_SERVICE_ID = "autosci-codex-research-model"
CODEX_RESEARCH_SERVICE_VERSION = "1.0"
MAX_CODEX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_CODEX_TRANSPORT_ATTEMPTS = 2
_TRANSPORT_ATTEMPT_KEY = "_solar_codex_transport_attempt"
_TRANSIENT_TRANSPORT_MARKERS = (
    "failed to lookup address information",
    "failed to connect to websocket",
    "error sending request for url",
    "stream disconnected before completion",
    "connection reset",
    "connection timed out",
    "temporary failure in name resolution",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    data = (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha256_bytes(data)


def _is_transient_transport_failure(events: str) -> bool:
    """Recognize only explicit connection/DNS failures emitted by Codex CLI."""

    lowered = str(events or "").lower()
    return any(marker in lowered for marker in _TRANSIENT_TRANSPORT_MARKERS)


def _string_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def _response_schema(node_id: str) -> dict[str, Any]:
    limitations = _string_array()
    base: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "node_id": {"type": "string", "const": node_id},
            "limitations": limitations,
        },
        "required": ["node_id", "limitations"],
        "additionalProperties": False,
    }
    properties = base["properties"]
    required = base["required"]
    if node_id == "evidence_synthesis":
        properties["claims"] = {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string", "minLength": 1},
                    "text": {"type": "string", "minLength": 1},
                    "evidence_ids": _string_array(),
                    # The verbatim sentence behind each cited source. Without
                    # it a claim records WHICH source supported it but never
                    # WHICH TEXT, so support cannot be verified downstream --
                    # only linkage. additionalProperties is False here, so a
                    # field absent from this schema is not merely unrequested
                    # but forbidden: the prompt asking for quotes achieves
                    # nothing until the schema admits them.
                    "evidence_quotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_id": {"type": "string", "minLength": 1},
                                "quote": {"type": "string", "minLength": 1},
                            },
                            "required": ["source_id", "quote"],
                            "additionalProperties": False,
                        },
                    },
                    "uncertainty": {"enum": ["low", "medium", "high", "unknown"]},
                    "limitations": limitations,
                },
                "required": [
                    "claim_id", "text", "evidence_ids", "evidence_quotes",
                    "uncertainty", "limitations",
                ],
                "additionalProperties": False,
            },
        }
        required.append("claims")
    elif node_id in {"report_draft", "report_revision"}:
        properties["report"] = {
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "body": {"type": "string", "minLength": 1},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "minLength": 1},
                            "body": {"type": "string", "minLength": 1},
                        },
                        "required": ["title", "body"],
                        "additionalProperties": False,
                    },
                },
                "conclusions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "conclusion_id": {"type": "string", "minLength": 1},
                            "text": {"type": "string", "minLength": 1},
                            "evidence_ids": _string_array(),
                        },
                        "required": ["conclusion_id", "text", "evidence_ids"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["title", "body", "sections", "conclusions"],
            "additionalProperties": False,
        }
        required.append("report")
        if node_id == "report_revision":
            properties["preservation"] = {
                "type": "object",
                "properties": {
                    "preserved_conclusion_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "preserved_method_sha256": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                    "preserved_limitations": _string_array(),
                },
                "required": [
                    "preserved_conclusion_ids",
                    "preserved_method_sha256",
                    "preserved_limitations",
                ],
                "additionalProperties": False,
            }
            required.append("preservation")
    elif node_id == "publication_produce":
        properties["files"] = {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "relative_path": {"type": "string", "minLength": 1},
                    "content": {"type": "string", "minLength": 1},
                },
                "required": ["relative_path", "content"],
                "additionalProperties": False,
            },
        }
        required.append("files")
    elif node_id in {"independent_review", "report_revision_review", "artifact_review"}:
        properties["findings"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_id": {"type": "string", "minLength": 1},
                    "severity": {"enum": ["low", "medium", "high", "critical"]},
                    "category": {"type": "string", "minLength": 1},
                    "message": {"type": "string", "minLength": 1},
                },
                "required": ["finding_id", "severity", "category", "message"],
                "additionalProperties": False,
            },
        }
        properties["verdict_suggestion"] = {"enum": ["accept", "revise", "reject"]}
        required.extend(["findings", "verdict_suggestion"])
    else:
        raise ResearchOperatorError(
            f"Unsupported Codex research node: {node_id}",
            error_type="invalid_input",
        )
    return base


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except Exception:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            process.kill()


class CodexResearchModelService(ResearchModelService):
    """Implement the AutoSci model service contract with one Codex agent call."""

    service_id = CODEX_RESEARCH_SERVICE_ID
    service_version = CODEX_RESEARCH_SERVICE_VERSION
    # The provenance label recorded for every invocation. An attribute rather
    # than a literal because a subclass driving a different CLI must not be able
    # to inherit this one's identity: a Claude call recorded as
    # codex_subscription is a false provenance record, and checkable provenance
    # is the point of this workflow.
    usage_provider = "codex_subscription"

    def __init__(
        self,
        workspace_root: Path,
        *,
        model: str,
        role: str,
        reasoning_effort: str = "high",
        timeout_seconds: int = 900,
        codex_binary: str = "codex",
        invocation_journal: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(workspace_root=workspace_root, routes=[], timeout_seconds=timeout_seconds, max_attempts=1)
        self.service_id = CODEX_RESEARCH_SERVICE_ID
        self.service_version = CODEX_RESEARCH_SERVICE_VERSION
        self.model = str(model or "").strip()
        self.role = str(role or "").strip()
        self.reasoning_effort = str(reasoning_effort or "").strip()
        self.codex_binary = str(codex_binary or "").strip()
        self.invocation_usage: list[dict[str, Any]] = []
        self.invocation_journal = invocation_journal if invocation_journal is not None else []
        if not self.model or self.role not in {"writer", "reviewer"}:
            raise ResearchOperatorError(
                "Codex research service requires an exact model and writer/reviewer role",
                error_type="provider_configuration",
            )

    def _attach_provider_usage(
        self, payload: dict[str, Any], usage: dict[str, Any]
    ) -> dict[str, Any]:
        """Stamp the returned payload with the provenance the operator reads.

        Every `__call__` implementation must end here. `provider_usage_from`
        synthesises a row labelled "injected" when these keys are absent, so a
        service that forgets them does not fail loudly -- it reports
        plausible-looking provenance for a call that recorded none. Keeping the
        three assignments in one place is what stops a new provider inheriting
        that omission.
        """
        payload["provider"] = self.usage_provider
        payload["model"] = self.model
        # A successful bounded transport retry must retain the failed attempt
        # as provenance instead of reporting only the final successful call.
        payload["provider_usage"] = [dict(item) for item in self.invocation_usage]
        return payload

    def _record_invocation(
        self,
        *,
        invocation_id: str,
        node_id: str,
        status: str,
        started: float,
        request_sha256: str,
        prompt_payload: dict[str, Any],
        request_path: Path,
        schema_path: Path,
        response_path: Path,
        events_path: Path,
        response_payload: dict[str, Any] | None,
        exit_code: int,
        error_type: str = "",
        error: str = "",
    ) -> dict[str, Any]:
        if not response_path.exists():
            _write_json(
                response_path,
                {
                    "schema": "solar.codex_research_failed_response.v1",
                    "node_id": node_id,
                    "status": "failed",
                    "error_type": error_type or "provider_unavailable",
                    "error": error or "Codex emitted no final response.",
                },
            )
        response_bytes = response_path.read_bytes()
        response_sha256 = _sha256_bytes(response_bytes)
        archive_path = response_path.parent / "exchange.json"
        role_call_index = len(self.invocation_usage) + 1
        aggregate_call_index = len(self.invocation_journal) + 1
        archive_payload = {
            "schema": "solar.codex_research_exchange.v1",
            "service_id": self.service_id,
            "service_version": self.service_version,
            "invocation_id": invocation_id,
            "call_index": role_call_index,
            "aggregate_call_index": aggregate_call_index,
            "node_id": node_id,
            "role": self.role,
            "model": self.model,
            "session_mode": "ephemeral",
            "status": status,
            "exit_code": int(exit_code),
            "error_type": error_type,
            "error": error,
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
            "events_sha256": _sha256_bytes(events_path.read_bytes()),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "request": prompt_payload,
            "response": response_payload,
        }
        archive_sha256 = _write_json(archive_path, archive_payload)
        evidence_paths = [request_path, schema_path, response_path, events_path, archive_path]
        evidence_sha256 = {
            str(path.relative_to(self.workspace_root)).replace("\\", "/"): _sha256_bytes(path.read_bytes())
            for path in evidence_paths
        }
        usage = {
            "provider": self.usage_provider,
            "model": self.model,
            "usage_kind": "llm",
            "principal_role": self.role,
            "session_mode": "ephemeral",
            "status": status,
            "invocation_id": invocation_id,
            "call_index": role_call_index,
            "role_call_index": role_call_index,
            "aggregate_call_index": aggregate_call_index,
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
            "service_id": self.service_id,
            "service_version": self.service_version,
            "archive_path": str(archive_path.relative_to(self.workspace_root)).replace("\\", "/"),
            "archive_sha256": archive_sha256,
            "evidence_paths": sorted(evidence_sha256),
            "evidence_sha256": evidence_sha256,
        }
        self.invocation_usage.append(usage)
        self.invocation_journal.append(usage)
        return usage

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        node_id = str(kwargs.get("node_id") or "")
        try:
            transport_attempt = max(1, int(kwargs.get(_TRANSPORT_ATTEMPT_KEY) or 1))
        except (TypeError, ValueError):
            transport_attempt = 1
        prompt_kwargs = dict(kwargs)
        prompt_kwargs.pop(_TRANSPORT_ATTEMPT_KEY, None)
        system, user = self._prompt(node_id, prompt_kwargs)
        binary = shutil.which(self.codex_binary)
        if not binary:
            raise ResearchOperatorError("Codex CLI is unavailable", error_type="provider_unavailable")
        source_home = Path(
            os.environ.get("SOLAR_CODEX_SOURCE_HOME")
            or os.environ.get("CODEX_HOME")
            or (Path.home() / ".codex")
        ).expanduser()
        source_auth = source_home / "auth.json"
        if source_auth.is_symlink() or not source_auth.is_file():
            raise ResearchOperatorError(
                "Codex subscription authentication is unavailable",
                error_type="provider_unavailable",
            )
        invocation_id = str(uuid.uuid4())
        invocation_root = self.workspace_root / "service-evidence" / "codex" / f"{node_id}-{invocation_id}"
        invocation_root.mkdir(parents=True, exist_ok=False)
        schema_path = invocation_root / "response.schema.json"
        request_path = invocation_root / "request.json"
        response_path = invocation_root / "response.json"
        events_path = invocation_root / "events.jsonl"
        schema = _response_schema(node_id)
        _write_json(schema_path, project_schema(schema, "openai"))
        prompt_payload = {
            "schema": "solar.codex_research_prompt.v1",
            "node_id": node_id,
            "role": self.role,
            "model": self.model,
            "system": system,
            "input": user,
            "source_output_contract": schema,
            "instructions": [
                "Return exactly the JSON object required by the output schema.",
                "Do not call tools; every authoritative input is included in this prompt.",
                "Do not use outside knowledge as evidence and do not invent identifiers.",
            ],
        }
        prompt_bytes = json.dumps(prompt_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        request_sha256 = _sha256_bytes(prompt_bytes)
        _write_json(request_path, prompt_payload)
        command = [
            binary,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--model",
            self.model,
            "--config",
            f"model_reasoning_effort={self.reasoning_effort}",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(response_path),
            "--json",
            "--cd",
            str(invocation_root),
            "-",
        ]
        env = os.environ.copy()
        for name in (
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "AUTOSCI_REVIEW_LLM_API_KEY",
            "AUTOSCI_RESEARCH_LLM_ENDPOINT",
            "AUTOSCI_RESEARCH_LLM_PROVIDER",
            "AUTOSCI_RESEARCH_LLM_MODEL",
            "AUTOSCI_RESEARCH_ALLOW_OPENAI_FALLBACK",
            "SOLAR_CODEX_EXTRA_FLAGS",
        ):
            env.pop(name, None)
        # os.getuid() is unavailable on Windows. The process id keeps the
        # default state sandbox isolated there; callers can still provide a
        # stable explicit root through SOLAR_CODEX_OPERATOR_STATE_ROOT.
        owner_id = os.getuid() if hasattr(os, "getuid") else os.getpid()
        state_parent = Path(
            env.get("SOLAR_CODEX_OPERATOR_STATE_ROOT")
            or (tempfile.gettempdir() + f"/solar-codex-research-state-{owner_id}")
        ).expanduser()
        state_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="agent-", dir=state_parent) as state_raw:
            state_root = Path(state_raw)
            codex_home = state_root / "home"
            codex_home.mkdir(mode=0o700)
            shutil.copyfile(source_auth, codex_home / "auth.json")
            (codex_home / "auth.json").chmod(0o600)
            (codex_home / "config.toml").write_text(
                'cli_auth_credentials_store = "file"\n',
                encoding="utf-8",
            )
            (codex_home / "config.toml").chmod(0o600)
            env["CODEX_HOME"] = str(codex_home)
            env["CODEX_SQLITE_HOME"] = str(state_root / "sqlite")
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                    env=env,
                )
            except OSError as exc:
                events_path.write_text("", encoding="utf-8")
                message = f"Codex research agent could not start at node={node_id}"
                self._record_invocation(
                    invocation_id=invocation_id,
                    node_id=node_id,
                    status="failed",
                    started=started,
                    request_sha256=request_sha256,
                    prompt_payload=prompt_payload,
                    request_path=request_path,
                    schema_path=schema_path,
                    response_path=response_path,
                    events_path=events_path,
                    response_payload=None,
                    exit_code=-1,
                    error_type="provider_unavailable",
                    error=message,
                )
                raise ResearchOperatorError(message, error_type="provider_unavailable") from exc
            try:
                stdout, _ = process.communicate(prompt_bytes.decode("utf-8"), timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                _terminate_process_group(process)
                events_path.write_text("", encoding="utf-8")
                message = f"Codex research agent timed out at node={node_id}"
                self._record_invocation(
                    invocation_id=invocation_id,
                    node_id=node_id,
                    status="failed",
                    started=started,
                    request_sha256=request_sha256,
                    prompt_payload=prompt_payload,
                    request_path=request_path,
                    schema_path=schema_path,
                    response_path=response_path,
                    events_path=events_path,
                    response_payload=None,
                    exit_code=-1,
                    error_type="provider_unavailable",
                    error=message,
                )
                raise ResearchOperatorError(
                    message,
                    error_type="provider_unavailable",
                ) from exc
        events_path.write_text(stdout, encoding="utf-8")
        if process.returncode != 0:
            transient_transport = _is_transient_transport_failure(stdout)
            error_type = (
                "transient_provider_failure"
                if transient_transport
                else "provider_unavailable"
            )
            message = f"Codex research agent failed at node={node_id} exit={process.returncode}"
            self._record_invocation(
                invocation_id=invocation_id,
                node_id=node_id,
                status="failed",
                started=started,
                request_sha256=request_sha256,
                prompt_payload=prompt_payload,
                request_path=request_path,
                schema_path=schema_path,
                response_path=response_path,
                events_path=events_path,
                response_payload=None,
                exit_code=int(process.returncode),
                error_type=error_type,
                error=message,
            )
            if transient_transport and transport_attempt < MAX_CODEX_TRANSPORT_ATTEMPTS:
                retry_kwargs = dict(prompt_kwargs)
                retry_kwargs[_TRANSPORT_ATTEMPT_KEY] = transport_attempt + 1
                return self(**retry_kwargs)
            raise ResearchOperatorError(
                message,
                error_type=error_type,
            )
        try:
            if response_path.is_symlink() or not response_path.is_file():
                raise ResearchOperatorError("Codex research agent emitted no final response", error_type="provider_contract")
            response_bytes = response_path.read_bytes()
            if not response_bytes or len(response_bytes) > MAX_CODEX_RESPONSE_BYTES:
                raise ResearchOperatorError("Codex research response is empty or oversized", error_type="provider_contract")
            try:
                parsed = parse_json(response_bytes.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise ResearchOperatorError("Codex research response is invalid JSON", error_type="provider_contract") from exc
            try:
                payload = validate_output(parsed, schema, profile="openai")
            except OutputContractError as exc:
                raise ResearchOperatorError(
                    f"Codex research response violates its schema: {str(exc)[:300]}",
                    error_type="provider_contract",
                ) from exc
            schema_errors = sorted(
                Draft202012Validator(schema).iter_errors(payload),
                key=lambda item: list(item.absolute_path),
            )
            if schema_errors:
                raise ResearchOperatorError(
                    f"Codex research response violates its schema: {schema_errors[0].message}",
                    error_type="provider_contract",
                )
            if not isinstance(payload, dict) or str(payload.get("node_id") or "") != node_id:
                raise ResearchOperatorError("Codex research response has the wrong node identity", error_type="provider_contract")
        except ResearchOperatorError as exc:
            self._record_invocation(
                invocation_id=invocation_id,
                node_id=node_id,
                status="failed",
                started=started,
                request_sha256=request_sha256,
                prompt_payload=prompt_payload,
                request_path=request_path,
                schema_path=schema_path,
                response_path=response_path,
                events_path=events_path,
                response_payload=None,
                exit_code=int(process.returncode),
                error_type=exc.error_type,
                error=str(exc),
            )
            raise
        response_payload = dict(payload)
        payload.pop("node_id", None)
        usage = self._record_invocation(
            invocation_id=invocation_id,
            node_id=node_id,
            status="completed",
            started=started,
            request_sha256=request_sha256,
            prompt_payload=prompt_payload,
            request_path=request_path,
            schema_path=schema_path,
            response_path=response_path,
            events_path=events_path,
            response_payload=response_payload,
            exit_code=int(process.returncode),
        )
        return self._attach_provider_usage(payload, usage)
