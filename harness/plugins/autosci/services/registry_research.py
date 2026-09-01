"""Fixed research stages using registry transports with complete call evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any
import uuid

from structured_model import StructuredModelError, create_model
from structured_output import OutputContractError
from .codex_research import CodexResearchModelService, _response_schema, _write_json
from .production_research import ResearchOperatorError


class RegistryResearchModelService(CodexResearchModelService):
    def __init__(self, *args: Any, provider: str, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.client = create_model(model=self.model, provider=provider, timeout_seconds=self.timeout_seconds)
        self.model = self.client.model
        self.usage_provider = self.client.provider
        self.service_id = "autosci-registry-research-model"

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        node_id = str(kwargs.get("node_id") or "")
        system, user = self._prompt(node_id, kwargs)
        invocation_id = str(uuid.uuid4())
        root = self.workspace_root / "service-evidence" / "registry" / f"{node_id}-{invocation_id}"
        root.mkdir(parents=True, exist_ok=False)
        schema_path, request_path = root / "response.schema.json", root / "request.json"
        response_path, events_path = root / "response.json", root / "events.jsonl"
        _write_json(schema_path, _response_schema(node_id))
        prompt = {"system": system, "input": user, "node_id": node_id, "role": self.role}
        _write_json(request_path, prompt)
        events_path.write_text("", encoding="utf-8")
        prompt_text = json.dumps(prompt, ensure_ascii=False, sort_keys=True)
        started = time.monotonic()
        payload, error = None, None
        try:
            payload = self.client.generate(prompt_text, schema_path, root / "model-call")
            _write_json(response_path, payload)
        except (StructuredModelError, OutputContractError) as exc:
            error = ResearchOperatorError(str(exc), error_type="provider_contract" if isinstance(exc, OutputContractError) else "provider_unavailable")
        usage = self._record_invocation(
            invocation_id=invocation_id, node_id=node_id, started=started,
            request_sha256=hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            prompt_payload=prompt, request_path=request_path, schema_path=schema_path,
            response_path=response_path, events_path=events_path, response_payload=payload,
            status="failed" if error else "completed", exit_code=1 if error else 0,
            error_type=error.error_type if error else "", error=str(error) if error else "",
        )
        # The shared journal must also declare the transport's source/wire
        # schemas and failure receipt, even when an operator hides an exception.
        for path in sorted((root / "model-call").glob("*.json")):
            relative = path.relative_to(self.workspace_root).as_posix()
            usage["evidence_sha256"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        usage["evidence_paths"] = sorted(usage["evidence_sha256"])
        usage["transport"] = self.client.transport
        usage["schema_mode"] = self.client.schema_mode
        if error:
            raise error
        result = dict(payload)
        result.pop("node_id", None)
        return self._attach_provider_usage(result, usage)
