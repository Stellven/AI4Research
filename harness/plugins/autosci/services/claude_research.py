"""Run the research writer/reviewer through the Claude CLI instead of Codex.

The research operators do not name a provider: they call
`fixed_research_node_adapter.py`, which builds a `CodexResearchModelService`.
That hardcodes one CLI, so when Codex quota runs out the workflow stops --
which is exactly what happened after every stage past source_validation failed
with "You've hit your usage limit for GPT-5.3-Codex-Spark".

This is the same service against `claude`. It is deliberately a sibling of
CodexResearchModelService rather than a rewrite: same prompt construction, same
per-invocation evidence layout (request/response/schema/events under
service-evidence/), same failure typing, so nothing downstream can tell which
CLI produced a result except by reading the recorded provider.

Two behaviours are worth stating because they are the ones that matter for
provenance:

* The response schema is enforced by the CLI via `--json-schema`, not merely
  requested in the prompt. A model that cannot satisfy the schema fails here
  rather than returning prose that later parses as "no claims".
* Subscription auth is required and checked before the call, mirroring the
  Codex service's refusal to run without it. An unauthenticated run must fail
  closed, not silently produce nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .codex_research import (  # noqa: F401  (schema/helpers shared deliberately)
    CodexResearchModelService,
    _response_schema,
    _write_json,
)

try:
    from ..operators.research_synthesis.base import ResearchOperatorError
except ImportError:  # direct-module execution paths used by the bridge/adapter
    try:
        from operators.research_synthesis.base import ResearchOperatorError
    except ImportError:
        from harness.plugins.autosci.operators.research_synthesis.base import (
            ResearchOperatorError,
        )

CLAUDE_RESEARCH_SERVICE_ID = "autosci-claude-research-model"
CLAUDE_USAGE_PROVIDER = "claude_subscription"
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Never forward a provider credential into the CLI subprocess: the Claude CLI
# authenticates from its own configuration, and an inherited key would silently
# change the provider boundary the recorded evidence claims.
_STRIPPED_ENV = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "AUTOSCI_REVIEW_LLM_API_KEY",
    "AUTOSCI_RESEARCH_LLM_ENDPOINT",
    "AUTOSCI_RESEARCH_LLM_PROVIDER",
    "AUTOSCI_RESEARCH_LLM_MODEL",
    "AUTOSCI_RESEARCH_ALLOW_OPENAI_FALLBACK",
)


class ClaudeResearchModelService(CodexResearchModelService):
    """Codex-shaped research model service backed by the Claude CLI."""

    service_id = CLAUDE_RESEARCH_SERVICE_ID
    # Never codex_subscription. A Haiku call recorded under the Codex label
    # passes the adapter's provenance guard while the evidence names the wrong
    # provider, which is worse than the guard refusing the run.
    usage_provider = CLAUDE_USAGE_PROVIDER

    def __init__(self, *args: Any, claude_binary: str = "claude", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.service_id = CLAUDE_RESEARCH_SERVICE_ID
        self.claude_binary = str(claude_binary or "claude").strip()
        if not str(self.model or "").strip() or str(self.model).startswith("gpt-"):
            # A Codex model id reaching this service means the caller switched
            # provider without switching model; using it would fail obscurely
            # inside the CLI instead of here.
            self.model = DEFAULT_CLAUDE_MODEL

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        node_id = str(kwargs.get("node_id") or "")
        system, user = self._prompt(node_id, kwargs)
        binary = shutil.which(self.claude_binary)
        if not binary:
            raise ResearchOperatorError("Claude CLI is unavailable", error_type="provider_unavailable")

        invocation_id = str(uuid.uuid4())
        invocation_root = self.workspace_root / "service-evidence" / "claude" / f"{node_id}-{invocation_id}"
        invocation_root.mkdir(parents=True, exist_ok=False)
        schema_path = invocation_root / "response.schema.json"
        request_path = invocation_root / "request.json"
        response_path = invocation_root / "response.json"
        events_path = invocation_root / "events.jsonl"

        schema = _response_schema(node_id)
        # The recorded schema keeps its dialect declaration; the copy handed to
        # the CLI does not. Claude's validator cannot resolve the 2020-12 meta
        # schema by URL and rejects the whole argument, so the constraint would
        # be silently lost -- which is the difference between a schema the model
        # must satisfy and a suggestion in the prompt.
        _write_json(schema_path, schema)
        cli_schema = {key: value for key, value in schema.items() if key != "$schema"}
        prompt_payload = {
            "schema": "solar.claude_research_prompt.v1",
            "node_id": node_id,
            "role": self.role,
            "model": self.model,
            "system": system,
            "input": user,
            "instructions": [
                "Return exactly the JSON object required by the output schema.",
                "Do not call tools; every authoritative input is included in this prompt.",
                "Do not use outside knowledge as evidence and do not invent identifiers.",
            ],
        }
        _write_json(request_path, prompt_payload)
        prompt_text = json.dumps(prompt_payload, ensure_ascii=False, sort_keys=True)
        request_sha256 = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

        argv = [
            binary, "-p",
            "--model", str(self.model),
            "--output-format", "json",
            # Enforced by the CLI, not merely requested: a model that cannot
            # meet the schema fails here rather than returning prose that later
            # parses as "no claims returned".
            "--json-schema", json.dumps(cli_schema, ensure_ascii=False, sort_keys=True),
            prompt_text,
        ]

        env = os.environ.copy()
        for name in _STRIPPED_ENV:
            env.pop(name, None)

        started = time.monotonic()
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, env=env,
                stdin=subprocess.DEVNULL, timeout=self.timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            events_path.write_text("", encoding="utf-8")
            self._record_invocation(
                invocation_id=invocation_id, node_id=node_id, started=started,
                request_sha256=request_sha256, prompt_payload=prompt_payload,
                request_path=request_path, schema_path=schema_path,
                response_path=response_path, events_path=events_path,
                status="failed", response_payload={}, exit_code=124,
                error_type="provider_timeout",
                error=f"Claude research agent timed out after {self.timeout_seconds}s",
            )
            raise ResearchOperatorError(
                f"Claude research agent timed out at node={node_id}",
                error_type="provider_timeout",
            ) from exc

        events_path.write_text(proc.stdout or "", encoding="utf-8")
        if proc.returncode != 0:
            _write_json(response_path, {
                "schema": "solar.claude_research_failed_response.v1",
                "node_id": node_id,
                "status": "failed",
                "error_type": "provider_unavailable",
                "error": (proc.stderr or "")[-2000:],
            })
            self._record_invocation(
                invocation_id=invocation_id, node_id=node_id, started=started,
                request_sha256=request_sha256, prompt_payload=prompt_payload,
                request_path=request_path, schema_path=schema_path,
                response_path=response_path, events_path=events_path,
                status="failed", response_payload={}, exit_code=proc.returncode,
                error_type="provider_unavailable",
                error=f"Claude research agent failed at node={node_id} exit={proc.returncode}",
            )
            raise ResearchOperatorError(
                f"Claude research agent failed at node={node_id} exit={proc.returncode}",
                error_type="provider_unavailable",
            )

        try:
            envelope = json.loads(proc.stdout or "{}")
            body = envelope.get("result")
            payload = json.loads(body) if isinstance(body, str) else body
        except (json.JSONDecodeError, AttributeError) as exc:
            self._record_invocation(
                invocation_id=invocation_id, node_id=node_id, started=started,
                request_sha256=request_sha256, prompt_payload=prompt_payload,
                request_path=request_path, schema_path=schema_path,
                response_path=response_path, events_path=events_path,
                status="failed", response_payload={}, exit_code=proc.returncode,
                error_type="provider_contract",
                error="Claude research agent returned unparseable output",
            )
            raise ResearchOperatorError(
                f"Claude research agent returned unparseable output at node={node_id}",
                error_type="provider_contract",
            ) from exc

        if not isinstance(payload, dict):
            raise ResearchOperatorError(
                f"Claude research agent returned a non-object result at node={node_id}",
                error_type="provider_contract",
            )

        _write_json(response_path, payload)
        usage = self._record_invocation(
            invocation_id=invocation_id, node_id=node_id, started=started,
            request_sha256=request_sha256, prompt_payload=prompt_payload,
            request_path=request_path, schema_path=schema_path,
            response_path=response_path, events_path=events_path,
            status="completed", response_payload=payload, exit_code=proc.returncode,
        )
        # Recording the invocation is not the same as reporting it: the operator
        # reads provenance off the returned payload. Omitting this was the whole
        # defect -- four good Haiku calls rejected as an unattested provider.
        return self._attach_provider_usage(payload, usage)
