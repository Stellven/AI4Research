"""Registry-selected, single-call structured model transports for every stage.

No automatic provider/model fallback, no credential discovery, no tool execution
for HTTP calls, and no automatic retry. Stage owners retain repair budgets.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import model_registry
from structured_output import OutputContractError, parse_json, project_schema, validate_output


class StructuredModelError(RuntimeError):
    pass


ALIASES = {"codex": "openai", "codex_cli": "openai", "claude": "anthropic",
           "claude_cli": "anthropic", "glm": "zhipu", "google": "gemini",
           "google_api": "gemini", "thunderomlx": "local"}


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a credential to a redirected origin.
        raise StructuredModelError("Model endpoint redirect refused")


def _post(endpoint: str, body: dict, headers: dict, timeout: int) -> dict:
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise StructuredModelError("Model endpoint must not contain credentials, query or fragment")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
        raise StructuredModelError("Model endpoint requires HTTPS (except loopback)")
    request = urllib.request.Request(endpoint, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            data = response.read(4 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        raise StructuredModelError(f"Model service rejected request: HTTP {exc.code}") from None
    except (OSError, urllib.error.URLError, TimeoutError):
        raise StructuredModelError("Model service connection failed or timed out") from None
    if len(data) > 4 * 1024 * 1024:
        raise StructuredModelError("Model response exceeds size limit")
    result = parse_json(data.decode("utf-8"))
    if not isinstance(result, dict):
        raise StructuredModelError("Invalid model response envelope")
    return result


class StructuredJsonModel:
    def __init__(self, *, model: str, provider: str, transport: str, schema_mode: str,
                 timeout_seconds: int = 240, endpoint: str = "", key_envs: tuple[str, ...] = (),
                 registry_id: str = "", max_output_tokens: int = 8192):
        self.model, self.provider = model, provider
        self.transport, self.schema_mode = transport, schema_mode
        self.timeout_seconds, self.endpoint = timeout_seconds, endpoint
        self.key_envs, self.registry_id = key_envs, registry_id
        self.max_output_tokens = max_output_tokens

    def generate(self, prompt: str, schema_path: Path, work_dir: Path) -> dict[str, Any]:
        source = parse_json(schema_path.read_text(encoding="utf-8"))
        work_dir = work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        native = self.schema_mode == "native"
        profile = "openai" if self.transport == "codex_cli" else self.provider
        started = time.monotonic()
        receipt = {"provider": self.provider, "model": self.model or "configured_default",
                   "registry_id": self.registry_id, "transport": self.transport,
                   "schema_mode": self.schema_mode, "source_schema_sha256": _hash(source)}
        try:
            # Schema validation is required in every mode, including JSON-only.
            from jsonschema import Draft202012Validator
            Draft202012Validator.check_schema(source)
            wire = project_schema(source, profile) if native else source
            receipt["wire_schema_sha256"] = _hash(wire)
            _write(work_dir / "model_output.schema.json", wire)
            _write(work_dir / "model_source.schema.json", source)
            instruction = (
                "Return exactly one JSON object matching the source contract below. "
                "Do not execute tools, read files, or add prose/markdown. "
                "For a wire-required field optional in the source, use null only when unspecified. "
                "Never invent resource requirements or fill defaults. "
                "All source constraints are checked locally, including ranges, uniqueness and tuple positions.\n"
                + json.dumps(source, ensure_ascii=False) + "\n\n" + prompt
            )
            if self.transport in {"codex_cli", "claude_cli"}:
                raw = self._cli(instruction, work_dir, wire)
            else:
                raw = self._http(instruction, wire)
            _write(work_dir / "model_output.raw.json", raw)
            result = validate_output(raw, source, profile=profile if native else "")
            _write(work_dir / "model_output.json", result)
            receipt["status"] = "passed"
            return result
        except (OutputContractError, StructuredModelError, OSError, subprocess.TimeoutExpired) as exc:
            receipt["status"] = "failed"
            receipt["error_type"] = type(exc).__name__
            if isinstance(exc, (OutputContractError, StructuredModelError)):
                raise
            raise StructuredModelError(f"{self.provider} transport failed ({type(exc).__name__})") from None
        finally:
            receipt["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
            _write(work_dir / "model_call_receipt.json", receipt)

    def _cli(self, prompt: str, work_dir: Path, wire: dict) -> Any:
        if self.transport == "codex_cli":
            if self.schema_mode != "native":
                raise StructuredModelError("Codex CLI requires native schema mode")
            output = work_dir / "model_output.raw.json"
            if output.exists():
                raise StructuredModelError("Model call directory contains an earlier output; use a fresh call directory")
            command = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                       "--skip-git-repo-check", "--sandbox", "read-only", "--output-schema",
                       str(work_dir / "model_output.schema.json"), "--output-last-message", str(output)]
            if self.model:
                command += ["--model", self.model]
            command.append("-")
        else:
            base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
            if base != "https://api.anthropic.com":
                raise StructuredModelError("Claude CLI has a provider proxy configured; select that provider explicitly")
            command = ["claude", "-p", "--output-format", "json", "--tools", "", "--strict-mcp-config",
                       "--mcp-config", '{"mcpServers":{}}', "--no-session-persistence"]
            if self.model:
                command += ["--model", self.model]
            if self.schema_mode == "native":
                command += ["--json-schema", json.dumps(wire, ensure_ascii=False)]
        completed = subprocess.run(command, input=prompt, text=True, encoding="utf-8", capture_output=True,
                                   timeout=self.timeout_seconds, cwd=work_dir, check=False)
        if completed.returncode:
            # Raw stderr can include credentials/URLs; do not copy it to evidence.
            raise StructuredModelError(f"{self.provider} CLI exited {completed.returncode}")
        if self.transport == "codex_cli":
            if not output.is_file() or output.is_symlink() or output.stat().st_size > 4 * 1024 * 1024:
                raise StructuredModelError("Codex CLI produced no usable output")
            return parse_json(output.read_text(encoding="utf-8"))
        envelope = parse_json(completed.stdout)
        if not isinstance(envelope, dict) or envelope.get("is_error"):
            raise StructuredModelError("Claude CLI returned an error envelope")
        body = envelope.get("structured_output", envelope.get("result"))
        return parse_json(body) if isinstance(body, str) else body

    def _http(self, prompt: str, wire: dict) -> Any:
        key = next((os.environ[name] for name in self.key_envs if os.environ.get(name)), "")
        if not key and self.provider != "local":
            raise StructuredModelError(f"{self.provider} authentication missing; expected configured key environment")
        if not self.endpoint or not self.model:
            raise StructuredModelError(f"{self.provider} requires an explicit endpoint and model")
        endpoint = self.endpoint
        if self.transport == "gemini_api":
            endpoint = endpoint.rstrip("/") + "/models/" + urllib.parse.quote(self.model, safe="-._") + ":generateContent"
            config = {"responseMimeType": "application/json", "maxOutputTokens": self.max_output_tokens}
            if self.schema_mode == "native":
                config["responseJsonSchema"] = wire
            body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": config}
            envelope = _post(endpoint, body, {"x-goog-api-key": key}, self.timeout_seconds)
            candidates = envelope.get("candidates") or []
            if not candidates or candidates[0].get("finishReason") != "STOP":
                raise StructuredModelError("Gemini response refused, truncated or incomplete")
            text = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []) if not p.get("thought"))
        elif self.transport == "anthropic_api":
            body = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": self.max_output_tokens}
            if self.schema_mode == "native":
                body["output_config"] = {"format": {"type": "json_schema", "schema": wire}}
            envelope = _post(endpoint, body, {"x-api-key": key, "anthropic-version": "2023-06-01"}, self.timeout_seconds)
            if envelope.get("stop_reason") != "end_turn":
                raise StructuredModelError("Claude response refused, truncated or incomplete")
            text = "".join(p.get("text", "") for p in envelope.get("content", []) if p.get("type") == "text")
        elif self.transport == "chat_completions":
            body = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
            if self.schema_mode == "native":
                body["response_format"] = {"type": "json_schema", "json_schema": {"name": "solar_output", "strict": True, "schema": wire}}
            elif self.schema_mode == "json_object":
                body["response_format"] = {"type": "json_object"}
            body["max_completion_tokens" if self.provider == "openai" else "max_tokens"] = self.max_output_tokens
            envelope = _post(endpoint, body, {"Authorization": f"Bearer {key}"} if key else {}, self.timeout_seconds)
            choices = envelope.get("choices") or []
            if not choices or choices[0].get("finish_reason") != "stop" or choices[0].get("message", {}).get("refusal"):
                raise StructuredModelError("Model response refused, truncated or incomplete")
            text = choices[0].get("message", {}).get("content")
        else:
            raise StructuredModelError(f"Unsupported model transport: {self.transport}")
        return parse_json(text)


def create_model(*, model: str = "", provider: str = "", timeout_seconds: int = 240) -> StructuredJsonModel:
    reg = model_registry.load_registry()
    model = str(model or "").strip()
    provider = str(provider or "").strip().lower()
    spec = None
    if model:
        try:
            spec = model_registry.spec(reg, model)
        except SystemExit:
            if not provider:
                raise StructuredModelError(f"Unregistered model requires an explicit provider: {model}") from None
    canonical = ALIASES.get(provider, provider) or (spec or {}).get("provider") or "openai"
    if spec and spec["provider"] != canonical:
        raise StructuredModelError("Selected model and explicit provider disagree")
    profile = reg.get("structured_output_providers", {}).get(canonical)
    if not profile:
        raise StructuredModelError(f"No structured output adapter for provider: {canonical}")
    prefix = "SOLAR_LLM_" + canonical.upper()
    transport = os.environ.get(prefix + "_TRANSPORT") or profile["transport"]
    if transport not in profile["allowed_transports"]:
        raise StructuredModelError(f"Unsupported {canonical} transport: {transport}")
    mode = os.environ.get(prefix + "_SCHEMA_MODE") or profile["schema_mode"]
    if mode not in profile["allowed_schema_modes"]:
        raise StructuredModelError(f"Unsupported {canonical} schema mode: {mode}")
    if spec:
        flag = shlex.split(spec.get("model_flag", ""))
        model = spec.get("structured_model") or (flag[1] if len(flag) == 2 and flag[0] == "--model" else "")
        model = spec.get("transport_models", {}).get(transport, model)
    model = os.environ.get(prefix + "_MODEL") or model
    endpoint = os.environ.get(prefix + "_ENDPOINT") or profile.get("endpoints", {}).get(transport, "")
    key_envs = tuple(profile.get("key_envs", []))
    if os.environ.get(prefix + "_KEY_ENV"):
        key_envs = (os.environ[prefix + "_KEY_ENV"],)
    return StructuredJsonModel(model=model, provider=canonical, transport=transport, schema_mode=mode,
                               timeout_seconds=timeout_seconds, endpoint=endpoint, key_envs=key_envs,
                               registry_id=(spec or {}).get("id", ""),
                               max_output_tokens=int(os.environ.get(prefix + "_MAX_OUTPUT_TOKENS", "8192")))


def stage_model(stage: str, role: str, *, timeout_seconds: int = 240,
                default_model: str = "") -> StructuredJsonModel:
    prefix = "SOLAR_" + stage.upper()
    model = (os.environ.get(f"{prefix}_{role.upper()}_MODEL") or os.environ.get(prefix + "_MODEL")
             or os.environ.get("SOLAR_LLM_MODEL") or "")
    provider = (os.environ.get(f"{prefix}_{role.upper()}_PROVIDER") or os.environ.get(prefix + "_PROVIDER")
                or os.environ.get("SOLAR_LLM_PROVIDER") or "")
    return create_model(model=model or (default_model if not provider else ""), provider=provider, timeout_seconds=timeout_seconds)
