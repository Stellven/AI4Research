"""browser_job_runtime.py — Async Browser Agent job control client and mock adapter.

Provides helper client to submit, poll, collect, and cancel jobs executed by the browser execution daemon.
Provides mock/dry-run adapter functionality to simulate async state transitions.
"""
from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from capability_token import CapabilityToken

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
BROWSER_JOBS_DIR = HARNESS_DIR / "run" / "browser-jobs"
OPERATOR_RESULTS_DIR = HARNESS_DIR / "run" / "operator-results"
BROWSER_USE_ROOT = HOME / ".claude" / "mcp-servers" / "browser-use"
BROWSER_USE_PYTHON = BROWSER_USE_ROOT / ".venv" / "bin" / "python"
PROFILE_CACHE_ROOT = HARNESS_DIR / "state" / "browser-profile-cache"
PROFILE_RUNTIME_ROOT = HARNESS_DIR / "state" / "browser-profile-runtime"
_CHATGPT_CAPTURE_MODULE = HARNESS_DIR / "lib" / "chatgpt-conversation-ingest.py"
CHATGPT_MONTHLY_PROJECT_PREFIX = "需求研究"
CHATGPT_FRONTDOOR_URL = "https://chatgpt.com/"
_STAGED_PROFILE_PREFIX = "browser-use-user-data-dir-"
_PERSISTENT_PROFILE_PREFIX = "browser-use-persistent-user-data-dir-"
_RESTORE_ARTIFACTS = {
    "Current Session",
    "Current Tabs",
    "Last Session",
    "Last Tabs",
    "Sessions",
}
_LOCK_ARTIFACTS = {
    "SingletonCookie",
    "SingletonLock",
    "SingletonSocket",
    "LOCK",
}
_PROTECTED_APP_DATA_ROOTS = (
    HOME / "Library" / "Application Support",
    HOME / "Library" / "Containers",
    HOME / "Library" / "Group Containers",
)

# Regex patterns for scrubbing sensitive information
_SECRET_PATTERNS = [
    (re.compile(r'(?i)Set-Cookie:\s*[^\n]+'), 'Set-Cookie: [SCRUBBED]'),
    (re.compile(r'(?i)Cookie:\s*[^\n]+'), 'Cookie: [SCRUBBED]'),
    (re.compile(r'(?i)Authorization:\s*[^\n]+'), 'Authorization: [SCRUBBED]'),
    (re.compile(r'(?i)Bearer\s+[a-zA-Z0-9\-._~+/=]+'), 'Bearer [SCRUBBED]'),
    (re.compile(r'sk-[a-zA-Z0-9]{32,}'), '[SCRUBBED]'),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), '[SCRUBBED]'),
    (re.compile(r'github_pat_[a-zA-Z0-9_]{82}'), '[SCRUBBED]'),
    (re.compile(r'AKIA[0-9A-Z]{16}'), '[SCRUBBED]'),
    (re.compile(r'(?i)\b(api[_-]?key|apikey|api_secret)\s*[=:]\s*[^\s"\']{4,}'), r'\1=[SCRUBBED]'),
    (re.compile(r'(?i)\b(password|passwd)\s*[=:]\s*[^\s"\']{4,}'), r'\1=[SCRUBBED]'),
    (re.compile(r'(?i)\b(token|secret)\s*[=:]\s*[^\s"\']{4,}'), r'\1=[SCRUBBED]'),
]

_CHATGPT_INGEST_CACHE: Any = None


def scrub_secrets(text: str) -> str:
    """Scrub raw cookies, tokens, headers, and secrets from text."""
    if not isinstance(text, str):
        return text
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def scrub_dict(d: Any) -> Any:
    """Deep-scrub a dictionary, allowing profile_ref and account_label but redacting secrets."""
    if isinstance(d, dict):
        cleaned = {}
        for k, v in d.items():
            if k in {"profile_ref", "account_label"}:
                cleaned[k] = v  # Allowed explicitly
            elif any(x in k.lower() for x in ["cookie", "token", "password", "secret", "auth", "api_key", "key"]):
                cleaned[k] = "[SCRUBBED]"
            else:
                cleaned[k] = scrub_dict(v)
        return cleaned
    elif isinstance(d, list):
        return [scrub_dict(item) for item in d]
    elif isinstance(d, str):
        return scrub_secrets(d)
    return d


def validate_browser_job_policy(envelope: Dict[str, Any], capability_token: Optional[CapabilityToken] = None) -> None:
    """Enforces capability-token policy checks for browser jobs.

    Denies payment, secrets form fill, and destructive actions.
    """
    objective = (envelope.get("objective") or "").lower()

    # 1. Deny payment actions always
    payment_keywords = ["payment", "checkout", "buy ", "purchase", "billing", "subscribe", "pay ", "credit card"]
    for kw in payment_keywords:
        if kw in objective:
            raise PermissionError(f"Denying browser job submission: objective requests prohibited payment action '{kw}'")

    # 2. Deny secrets form fill / secrets access unless explicitly allowed by token
    secrets_keywords = ["password", "secret", "private key", "api_key", "api-key", "credentials"]
    
    # Check if envelope or objective explicitly requests secrets / secrets form filling
    secrets_requested = "secret_form" in envelope or any(k in envelope for k in ["secrets_allowed", "fill_secrets"])
    if not secrets_requested:
        for kw in secrets_keywords:
            if kw in objective:
                secrets_requested = True
                break

    if secrets_requested:
        if not capability_token:
            raise PermissionError("Denying browser job submission: secrets/credentials access requested but no capability token provided")
        token_dict = capability_token.to_dict()
        secrets_allowed = token_dict.get("secrets", {}).get("allowed", False) or \
                          token_dict.get("file_scope", {}).get("secret_paths_allowed", False)
        if not secrets_allowed:
            raise PermissionError("Denying browser job submission: secrets/credentials access requested but capability token denies it")

    # 3. Deny destructive actions unless explicitly allowed by token
    destructive_keywords = ["delete", "rm -rf", "drop database", "destructive", "uninstall", "format "]
    destructive_requested = "destructive_action" in envelope or envelope.get("destructive") is True
    if not destructive_requested:
        for kw in destructive_keywords:
            if kw in objective:
                destructive_requested = True
                break

    if destructive_requested:
        if not capability_token:
            raise PermissionError("Denying browser job submission: destructive action requested but no capability token provided")
        token_dict = capability_token.to_dict()
        destructive_allowed = token_dict.get("file_scope", {}).get("destructive_allowed", False) or \
                              token_dict.get("shell_scope", {}).get("destructive_commands_allowed", False)
        if not destructive_allowed:
            raise PermissionError("Denying browser job submission: destructive action requested but capability token denies it")


class BrowserSessionBroker:
    """Manages browser session profile health and authentication state.

    Ensures zero logging of raw session credentials, cookies, or tokens.
    """

    def __init__(self, harness_dir: Optional[Path] = None):
        self.harness_dir = harness_dir or HARNESS_DIR

    def get_profile_health(self, profile_ref: str, account_label: str) -> Dict[str, Any]:
        """Check login/auth health of a browser profile.

        Does not print or write cookies/tokens/raw credentials to any logs.
        """
        # Scrub inputs to be safe
        scrubbed_ref = scrub_secrets(profile_ref)
        scrubbed_label = scrub_secrets(account_label)

        # In mock scenarios, we check if reauth is requested
        is_healthy = True
        if "reauth" in scrubbed_ref.lower() or "reauth" in scrubbed_label.lower():
            is_healthy = False

        status = "healthy" if is_healthy else "reauth_required"
        projected = "WAITING_HUMAN" if not is_healthy else "running"

        return {
            "profile_ref": scrubbed_ref,
            "account_label": scrubbed_label,
            "status": status,
            "projected_state": projected,
            "login_health": "OK" if is_healthy else "REQUIRES_2FA"
        }


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_chatgpt_ingest_module() -> Any:
    global _CHATGPT_INGEST_CACHE
    if _CHATGPT_INGEST_CACHE is not None:
        return _CHATGPT_INGEST_CACHE
    spec = importlib.util.spec_from_file_location("chatgpt_conversation_ingest", _CHATGPT_CAPTURE_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load ChatGPT ingest module from {_CHATGPT_CAPTURE_MODULE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _CHATGPT_INGEST_CACHE = module
    return module


def resolve_chatgpt_monthly_project_name(now: Optional[datetime.datetime] = None) -> str:
    current = now or datetime.datetime.now(datetime.timezone.utc)
    return f"{CHATGPT_MONTHLY_PROJECT_PREFIX}-{current.strftime('%Y-%m')}"


def build_frontdoor_research_job_envelope(
    *,
    raw_request: str,
    ingress_channel: str,
    source_url: str = CHATGPT_FRONTDOOR_URL,
    now: Optional[datetime.datetime] = None,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    project = project_name or resolve_chatgpt_monthly_project_name(now)
    objective = (
        f"Route the requirement research flow through ChatGPT project {project}, "
        "preserve the whole conversation transcript, and return a machine-readable research artifact."
    )
    return {
        "task_type": "RESEARCH",
        "objective": objective,
        "url": source_url,
        "target_url": source_url,
        "allowed_domains": ["chatgpt.com", "chat.openai.com"],
        "ingress_channel": ingress_channel,
        "raw_request": raw_request,
        "chatgpt_project": project,
        "artifact_kind": "frontdoor_research",
        "capture_policy": {
            "mode": "whole_conversation",
            "messages_required": True,
            "final_answer_only_forbidden": True,
        },
        "project_routing": {
            "project_name": project,
            "project_name_rule": f"{CHATGPT_MONTHLY_PROJECT_PREFIX}-YYYY-MM",
            "create_if_missing": True,
        },
        "research_artifact_schema": {
            "required_fields": [
                "conversation_id",
                "source_url",
                "chatgpt_project",
                "messages",
                "summary",
                "constraints",
                "risks",
                "open_questions",
                "recommended_decomposition",
            ]
        },
    }


def submit_frontdoor_research_job(
    actor_id: str,
    *,
    raw_request: str,
    ingress_channel: str,
    source_url: str = CHATGPT_FRONTDOOR_URL,
    now: Optional[datetime.datetime] = None,
    project_name: Optional[str] = None,
    mock_sequence: Optional[List[str]] = None,
    capability_token: Optional[CapabilityToken] = None,
    extra_envelope: Optional[Dict[str, Any]] = None,
) -> str:
    envelope = build_frontdoor_research_job_envelope(
        raw_request=raw_request,
        ingress_channel=ingress_channel,
        source_url=source_url,
        now=now,
        project_name=project_name,
    )
    if extra_envelope:
        envelope.update(extra_envelope)
    return submit_browser_job(
        actor_id,
        envelope,
        mock_sequence=mock_sequence,
        capability_token=capability_token,
    )


def build_frontdoor_research_artifact(
    capture: Dict[str, Any],
    *,
    raw_request: str,
    ingress_channel: str,
    project_name: str,
) -> Dict[str, Any]:
    ingest = _load_chatgpt_ingest_module()
    turns = list(capture.get("messages") or [])
    conversation = ingest.build_conversation(
        conversation_id=str(capture.get("conversation_id") or ""),
        title=str(capture.get("title") or "ChatGPT Frontdoor Research"),
        created_at=str(capture.get("captured_at") or _now()),
        updated_at=str(capture.get("captured_at") or _now()),
        source_file=Path("<browser-capture>"),
        turns=turns,
        min_answer_chars=1,
        url=str(capture.get("url") or ""),
        canonical_url=str(capture.get("canonical_url") or ""),
        metadata=capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {},
        capture_method=str(capture.get("capture_method") or ""),
        capture_schema_version=capture.get("capture_schema_version") or "",
    )
    if not conversation:
        raise ValueError("browser capture did not contain a usable conversation")
    messages = list(conversation.get("messages") or [])
    assistant_messages = [m for m in messages if str(m.get("role")) == "assistant" and str(m.get("text") or "").strip()]
    summary = str(assistant_messages[-1].get("text") if assistant_messages else "").strip()
    return {
        "artifact_type": "browser_agent_frontdoor_research.v1",
        "ingress_channel": ingress_channel,
        "raw_request": raw_request,
        "chatgpt_project": project_name,
        "conversation_id": conversation.get("conversation_id") or "",
        "source_url": conversation.get("source_url") or capture.get("url") or "",
        "canonical_url": conversation.get("canonical_url") or capture.get("canonical_url") or "",
        "captured_at": capture.get("captured_at") or _now(),
        "messages": messages,
        "summary": summary,
        "summary_source": "latest_assistant_message" if summary else "empty",
        "constraints": [],
        "risks": [],
        "open_questions": [],
        "recommended_decomposition": [],
        "capture_method": conversation.get("capture_method") or "",
        "capture_schema_version": conversation.get("capture_schema_version") or "",
        "metadata": conversation.get("metadata") or {},
        "partial_transcript": bool(conversation.get("partial_transcript")),
    }


def collect_frontdoor_research_artifact(
    *,
    browser: str = "auto",
    raw_request: str,
    ingress_channel: str,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    ingest = _load_chatgpt_ingest_module()
    browser_id, capture = ingest.capture_browser(browser)
    artifact = build_frontdoor_research_artifact(
        capture,
        raw_request=raw_request,
        ingress_channel=ingress_channel,
        project_name=project_name or resolve_chatgpt_monthly_project_name(),
    )
    artifact["browser"] = browser_id
    return artifact


def _ensure_jobs_dir() -> None:
    BROWSER_JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _job_dir(job_id: str) -> Path:
    return BROWSER_JOBS_DIR / job_id


def _state_file(job_id: str) -> Path:
    return _job_dir(job_id) / "state.json"


def _load_state(job_id: str) -> Dict[str, Any]:
    state_file = _state_file(job_id)
    if not state_file.exists():
        raise ValueError(f"Job {job_id} not found")
    return json.loads(state_file.read_text(encoding="utf-8"))


def _write_state(job_id: str, state_data: Dict[str, Any]) -> None:
    state_data["logs"] = scrub_secrets(str(state_data.get("logs") or ""))
    for artifact in state_data.get("artifacts", []):
        if "content" in artifact and isinstance(artifact["content"], str):
            artifact["content"] = scrub_secrets(artifact["content"])
        if "path" in artifact and artifact["path"]:
            artifact["path"] = scrub_secrets(str(artifact["path"]))
    _state_file(job_id).write_text(json.dumps(state_data, indent=2, ensure_ascii=False), encoding="utf-8")


def _resolve_target_url(envelope: Dict[str, Any]) -> Optional[str]:
    for key in ("url", "target_url", "start_url"):
        value = str(envelope.get(key) or "").strip()
        if value:
            return value
    return None


def _resolve_allowed_domains(url: str, envelope: Dict[str, Any]) -> List[str]:
    allowed = envelope.get("allowed_domains")
    if isinstance(allowed, list) and allowed:
        return [str(item).strip() for item in allowed if str(item).strip()]
    parsed = urllib.parse.urlparse(url)
    return [parsed.netloc] if parsed.netloc else []


def _artifact_from_path(path: Path, artifact_type: str) -> Dict[str, Any]:
    return {"name": path.name, "type": artifact_type, "path": str(path)}


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_protected_app_data_root(path: Path) -> bool:
    resolved = path.resolve()
    return any(_path_within(resolved, root) for root in _PROTECTED_APP_DATA_ROOTS if root.exists())


def _browser_profile_cache_path(user_data_dir: str | Path, profile_directory: str) -> Path:
    source_root = Path(user_data_dir).resolve()
    cache_key = hashlib.sha256(f"{source_root}::{profile_directory}".encode("utf-8")).hexdigest()[:16]
    return PROFILE_CACHE_ROOT / cache_key


def _browser_profile_runtime_path(user_data_dir: str | Path, profile_directory: str) -> Path:
    source_root = Path(user_data_dir).resolve()
    runtime_key = hashlib.sha256(f"{source_root}::{profile_directory}".encode("utf-8")).hexdigest()[:16]
    return PROFILE_RUNTIME_ROOT / f"{_PERSISTENT_PROFILE_PREFIX}{runtime_key}"


def _remove_profile_restore_artifacts(root: Path, profile_directory: str) -> None:
    profile_dir = root / profile_directory
    for name in _RESTORE_ARTIFACTS | _LOCK_ARTIFACTS:
        for candidate in (root / name, profile_dir / name):
            if candidate.is_dir():
                shutil.rmtree(candidate, ignore_errors=True)
            elif candidate.exists():
                try:
                    candidate.unlink()
                except OSError:
                    pass


def refresh_browser_profile_cache(user_data_dir: str | Path | None, profile_directory: str | None) -> Optional[Path]:
    if not user_data_dir or not profile_directory:
        return None
    source_root = Path(user_data_dir)
    source_profile = source_root / profile_directory
    if not source_root.exists() or not source_profile.exists():
        return None
    cache_root = _browser_profile_cache_path(source_root, profile_directory)
    cache_profile = cache_root / profile_directory
    if cache_root.exists():
        shutil.rmtree(cache_root, ignore_errors=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_profile, cache_profile)
    local_state_src = source_root / "Local State"
    if local_state_src.exists():
        shutil.copy(local_state_src, cache_root / "Local State")
    _remove_profile_restore_artifacts(cache_root, profile_directory)
    manifest = {
        "source_root": str(source_root),
        "profile_directory": profile_directory,
        "cached_at": _now(),
    }
    (cache_root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return cache_root


def prepare_browser_profile_runtime(
    user_data_dir: str | Path | None,
    profile_directory: str | None,
    *,
    refresh: bool = False,
) -> Optional[Path]:
    if not user_data_dir or not profile_directory:
        return None
    source_root = Path(user_data_dir)
    source_profile = source_root / profile_directory
    if not source_root.exists() or not source_profile.exists():
        return None
    runtime_root = _browser_profile_runtime_path(source_root, profile_directory)
    runtime_profile = runtime_root / profile_directory
    if refresh and runtime_root.exists():
        shutil.rmtree(runtime_root, ignore_errors=True)
    if runtime_profile.exists():
        _remove_profile_restore_artifacts(runtime_root, profile_directory)
        return runtime_root

    seed_root = source_root
    if _is_protected_app_data_root(source_root):
        if os.environ.get("TMUX"):
            cache_root = _browser_profile_cache_path(source_root, profile_directory)
            cache_profile = cache_root / profile_directory
            if cache_profile.exists():
                seed_root = cache_root
            else:
                return None
        else:
            refreshed = refresh_browser_profile_cache(source_root, profile_directory)
            if refreshed is not None:
                seed_root = refreshed

    seed_profile = seed_root / profile_directory
    if not seed_root.exists() or not seed_profile.exists():
        return None
    runtime_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(seed_profile, runtime_profile)
    local_state_src = seed_root / "Local State"
    if local_state_src.exists():
        shutil.copy(local_state_src, runtime_root / "Local State")
    _remove_profile_restore_artifacts(runtime_root, profile_directory)
    manifest = {
        "source_root": str(source_root),
        "seed_root": str(seed_root),
        "profile_directory": profile_directory,
        "runtime_prepared_at": _now(),
        "strategy": "persistent",
    }
    (runtime_root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return runtime_root


def _stage_browser_profile(
    user_data_dir: str | Path | None,
    profile_directory: str | None,
    *,
    strategy: str = "isolated",
) -> tuple[str | Path | None, Optional[Path]]:
    """Create an isolated Chrome profile copy without session-restore artifacts.

    browser-use already copies Chrome profiles, but its raw copy keeps session restore
    tabs from the live profile. Those stale tabs can trigger disallowed-domain churn
    and destabilize the CDP session before our target page opens. We pre-stage a
    cleaned temp profile so browser-use reuses this isolated copy as-is.
    """
    if not user_data_dir or not profile_directory:
        return user_data_dir, None

    source_root = Path(user_data_dir)
    if _STAGED_PROFILE_PREFIX in str(source_root):
        return str(source_root), None
    if _PERSISTENT_PROFILE_PREFIX in str(source_root):
        if strategy == "persistent":
            return str(source_root), None
        strategy = "isolated"
    if strategy == "persistent":
        runtime_root = prepare_browser_profile_runtime(source_root, profile_directory)
        return (str(runtime_root), None) if runtime_root else (None, None)
    if _is_protected_app_data_root(source_root):
        cache_root = _browser_profile_cache_path(source_root, profile_directory)
        if os.environ.get("TMUX"):
            cache_profile = cache_root / profile_directory
            if cache_profile.exists():
                source_root = cache_root
            else:
                return None, None
        else:
            refreshed = refresh_browser_profile_cache(source_root, profile_directory)
            if refreshed is not None:
                source_root = refreshed

    source_profile = source_root / profile_directory
    if not source_root.exists() or not source_profile.exists():
        return user_data_dir, None

    staged_root = Path(tempfile.mkdtemp(prefix=_STAGED_PROFILE_PREFIX))
    staged_profile = staged_root / profile_directory
    shutil.copytree(source_profile, staged_profile)

    local_state_src = source_root / "Local State"
    if local_state_src.exists():
        shutil.copy(local_state_src, staged_root / "Local State")

    _remove_profile_restore_artifacts(staged_root, profile_directory)

    return str(staged_root), staged_root


def _looks_like_login_wall(text: str) -> bool:
    sample = (text or "").lower()
    cues = [
        "log in",
        "sign in",
        "login",
        "sign up",
        "continue with google",
        "continue with apple",
        "enter your password",
        "two-factor",
        "2fa",
        "captcha",
        "verify you are human",
        "登录",
        "注册",
        "开始使用",
        "使用 google 账户继续",
        "使用 apple 账户继续",
    ]
    return any(cue in sample for cue in cues)


def _run_real_browser_probe(job_id: str, envelope: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    target_url = _resolve_target_url(envelope)
    if not target_url:
        return {"ok": False, "error": "missing target url", "error_type": "configuration"}
    if not BROWSER_USE_PYTHON.exists():
        return {"ok": False, "error": f"browser-use python missing: {BROWSER_USE_PYTHON}", "error_type": "dependency"}

    job_dir = _job_dir(job_id)
    artifact_dir = job_dir / "daemon-artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    staged_user_data_dir, cleanup_dir = _stage_browser_profile(
        envelope.get("user_data_dir"),
        str(envelope.get("profile_directory") or "Default"),
    )
    if envelope.get("user_data_dir") and not staged_user_data_dir:
        return {
            "ok": False,
            "error": "protected browser profile cache missing for tmux worker; refresh cache outside tmux first",
            "error_type": "protected_profile_cache_missing",
        }

    payload = {
        "url": target_url,
        "allowed_domains": _resolve_allowed_domains(target_url, envelope),
        "auth_expected": bool(envelope.get("auth_expected", False)),
        "headless": bool(envelope.get("headless", True)),
        "artifact_dir": str(artifact_dir),
        "wait_ms": int(envelope.get("page_wait_ms", 1500) or 1500),
        "user_data_dir": str(staged_user_data_dir or ""),
        "profile_directory": str(envelope.get("profile_directory") or "Default"),
    }

    payload_json = json.dumps(payload, ensure_ascii=False)
    script = f"""
import asyncio, base64, json, re, sys
from pathlib import Path
from browser_use.browser.session import BrowserSession
from browser_use.browser.profile import BrowserProfile
from bs4 import BeautifulSoup

payload = json.loads({payload_json!r})
artifact_dir = Path(payload["artifact_dir"])
artifact_dir.mkdir(parents=True, exist_ok=True)

def clean_text(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\\n", strip=True)
    text = re.sub(r"\\n\\s*\\n+", "\\n\\n", text)
    return text[:50000]

def looks_like_login_wall(text: str) -> bool:
    lowered = (text or "").lower()
    cues = [
        "log in",
        "sign in",
        "login",
        "sign up",
        "continue with google",
        "continue with apple",
        "enter your password",
        "two-factor",
        "2fa",
        "captcha",
        "verify you are human",
        "登录",
        "注册",
        "开始使用",
        "使用 google 账户继续",
        "使用 apple 账户继续",
    ]
    return any(cue in lowered for cue in cues)

async def main() -> None:
    profile = BrowserProfile(
        headless=payload["headless"],
        allowed_domains=payload["allowed_domains"] or None,
        user_data_dir=payload["user_data_dir"] or None,
        profile_directory=payload["profile_directory"],
    )
    browser = BrowserSession(browser_profile=profile)
    await browser.start()
    try:
        page = await browser.new_page()
        await page.goto(payload["url"])
        await asyncio.sleep(max(payload["wait_ms"], 0) / 1000.0)
        title = await page.evaluate("() => document.title")
        final_url = await page.evaluate("() => location.href")
        html = await page.evaluate("() => document.documentElement.outerHTML")
        text = clean_text(html)
        screenshot_b64 = await page.screenshot(format="png")
        screenshot_path = artifact_dir / "screenshot.png"
        screenshot_path.write_bytes(base64.b64decode(screenshot_b64))
        html_path = artifact_dir / "page.html"
        html_path.write_text(html, encoding="utf-8")
        text_path = artifact_dir / "page.txt"
        text_path.write_text(text, encoding="utf-8")
        login_wall = payload["auth_expected"] and looks_like_login_wall(text)
        result = {{
            "ok": True,
            "state": "reauth_required" if login_wall else "done",
            "login_state": "reauth_required" if login_wall else "healthy",
            "title": title,
            "final_url": final_url,
            "text_excerpt": text[:1000],
            "artifacts": {{
                "screenshot_path": str(screenshot_path),
                "html_path": str(html_path),
                "text_path": str(text_path),
            }},
        }}
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({{"ok": False, "error": str(exc), "error_type": "runtime"}}, ensure_ascii=False))
        raise
    finally:
        await browser.stop()

asyncio.run(main())
"""

    with tempfile.NamedTemporaryFile("w", suffix="-browser-job.py", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        script_path = handle.name
    try:
        result = subprocess.run(
            [str(BROWSER_USE_PYTHON), script_path],
            cwd=str(BROWSER_USE_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"browser job timeout after {timeout}s", "error_type": "timeout"}
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)

    stdout_lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    stderr_tail = " | ".join((result.stderr or "").strip().splitlines()[-5:])
    payload_obj: Dict[str, Any] = {}
    if stdout_lines:
        try:
            payload_obj = json.loads(stdout_lines[-1])
        except json.JSONDecodeError:
            payload_obj = {
                "ok": False,
                "error": f"non-json stdout tail: {stdout_lines[-1][:300]}",
                "error_type": "protocol",
            }
    if result.returncode != 0 and payload_obj.get("ok") is not True:
        if stderr_tail:
            payload_obj["stderr_tail"] = stderr_tail
    return payload_obj


def execute_browser_job(job_id: str, timeout: Optional[int] = None) -> Dict[str, Any]:
    """Execute a submitted browser job via the local browser-use runtime."""
    state_data = _load_state(job_id)
    if state_data.get("state") in {"done", "failed", "timeout"}:
        return state_data
    if state_data.get("mock_sequence"):
        return state_data

    envelope = state_data.get("envelope") or {}
    state_data["state"] = "running"
    state_data["updated_at"] = _now()
    state_data["logs"] += f"[{_now()}] Browser execution daemon started.\n"
    _write_state(job_id, state_data)

    timeout = int(timeout or envelope.get("timeout_sec") or 90)
    probe = _run_real_browser_probe(job_id, envelope, timeout)

    state_data = _load_state(job_id)
    if probe.get("ok"):
        login_state = str(probe.get("login_state") or "healthy")
        state_data["state"] = "reauth_required" if login_state == "reauth_required" else str(probe.get("state") or "done")
        state_data["logs"] += f"[{_now()}] Real browser probe completed for {probe.get('final_url') or _resolve_target_url(envelope) or 'unknown-url'}.\n"
        metadata_dir = _job_dir(job_id) / "daemon-artifacts"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        artifacts = []
        paths = probe.get("artifacts") or {}
        for key, artifact_type in (("screenshot_path", "screenshot"), ("html_path", "html"), ("text_path", "text")):
            raw = paths.get(key)
            if raw:
                artifacts.append(_artifact_from_path(Path(raw), artifact_type))
        metadata = {
            "title": probe.get("title") or "",
            "final_url": probe.get("final_url") or _resolve_target_url(envelope) or "",
            "login_state": login_state,
            "text_excerpt": probe.get("text_excerpt") or "",
        }
        metadata_path = metadata_dir / "page.json"
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        artifacts.append(_artifact_from_path(metadata_path, "metadata"))
        state_data["artifacts"] = artifacts
        state_data["login_state"] = login_state
    else:
        err_type = str(probe.get("error_type") or "")
        state_data["state"] = "timeout" if err_type == "timeout" else "failed"
        state_data["logs"] += f"[{_now()}] Browser execution failed: {probe.get('error') or 'unknown error'}\n"
        if probe.get("stderr_tail"):
            state_data["logs"] += f"stderr: {probe['stderr_tail']}\n"
    state_data["updated_at"] = _now()
    _write_state(job_id, state_data)
    return state_data


def submit_browser_job(
    actor_id: str,
    envelope: Dict[str, Any],
    mock_sequence: Optional[List[str]] = None,
    capability_token: Optional[CapabilityToken] = None
) -> str:
    """Submits a browser job envelope and initializes state.json.

    Enforces capability-token policy checks and scrubs secrets.
    """
    # Enforce policy checks
    validate_browser_job_policy(envelope, capability_token)

    _ensure_jobs_dir()
    job_id = f"job-{uuid.uuid4()}"
    job_dir = BROWSER_JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Define initial state
    initial_state = "submitted"
    mock_index = 0
    if mock_sequence:
        mock_index = -1

    # Scrub envelope and initial logs of any secrets
    scrubbed_envelope = scrub_dict(envelope)
    initial_logs = scrub_secrets(f"Job {job_id} submitted for actor {actor_id} at {_now()}.\n")

    state_data = {
        "job_id": job_id,
        "actor_id": actor_id,
        "state": initial_state,
        "envelope": scrubbed_envelope,
        "execution_mode": "mock" if mock_sequence else "real_browser",
        "logs": initial_logs,
        "artifacts": [],
        "mock_sequence": mock_sequence,
        "mock_index": mock_index,
        "created_at": _now(),
        "updated_at": _now()
    }

    state_file = job_dir / "state.json"
    state_file.write_text(json.dumps(state_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return job_id


def poll_browser_job(job_id: str) -> Dict[str, Any]:
    """Polls the state of a browser job, simulating state transitions if mock_sequence is defined."""
    state_data = _load_state(job_id)

    # State transition logic for mock sequence
    mock_sequence = state_data.get("mock_sequence")
    if mock_sequence and isinstance(mock_sequence, list):
        current_state = state_data.get("state")
        terminal_states = {"done", "failed", "timeout"}
        if current_state not in terminal_states:
            idx = state_data.get("mock_index", -1)
            if idx + 1 < len(mock_sequence):
                idx += 1
                new_state = mock_sequence[idx]
                state_data["state"] = new_state
                state_data["mock_index"] = idx
                state_data["logs"] += f"[{_now()}] Transitioned to state: {new_state}\n"

                # Add mock artifacts on done/failed/timeout
                if new_state == "done":
                    state_data["artifacts"] = [
                        {"name": "screenshot.png", "type": "screenshot", "content": "mock_png_bytes"},
                        {"name": "logs.txt", "type": "logs", "content": state_data["logs"]}
                    ]
                elif new_state in {"failed", "timeout"}:
                    state_data["artifacts"] = [
                        {"name": "logs.txt", "type": "logs", "content": state_data["logs"] + "\nTerminal failure encountered."}
                    ]

                state_data["updated_at"] = _now()
    elif state_data.get("execution_mode") == "real_browser" and state_data.get("state") not in {"reauth_required", "done", "failed", "timeout"}:
        state_data = execute_browser_job(job_id)

    # Scrub logs & artifacts before saving/returning
    state_data["logs"] = scrub_secrets(state_data["logs"])
    for art in state_data.get("artifacts", []):
        if "content" in art and isinstance(art["content"], str):
            art["content"] = scrub_secrets(art["content"])

    # Surface WAITING_HUMAN when reauth_required is detected
    if state_data.get("state") == "reauth_required":
        state_data["projected_state"] = "WAITING_HUMAN"
    else:
        state_data["projected_state"] = state_data.get("state")

    _write_state(job_id, state_data)
    return state_data


def collect_browser_job(job_id: str, output_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Collects job results, writes structured result.json, and writes artifacts to output_dir."""
    job_dir = BROWSER_JOBS_DIR / job_id
    state_file = job_dir / "state.json"
    if not state_file.exists():
        raise ValueError(f"Job {job_id} not found")

    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    state = state_data.get("state")
    terminal_states = {"done", "failed", "timeout"}
    if state not in terminal_states:
        raise RuntimeError(f"Cannot collect job {job_id}: current state is '{state}', not terminal.")

    envelope = state_data.get("envelope") or {}
    operator_id = envelope.get("operator_id") or state_data.get("actor_id")
    task_id = envelope.get("task_id") or job_id
    sprint_id = envelope.get("sprint_id") or "sprint-unknown"
    node_id = envelope.get("node_id") or "node-unknown"

    # Determine exit code and final status
    status = "completed" if state == "done" else state
    exit_code = 0 if state == "done" else (1 if state == "failed" else 2)

    # Resolve output directory
    if output_dir is None:
        output_dir = OPERATOR_RESULTS_DIR / operator_id / task_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write artifacts to output_dir with secret scrubbing
    artifacts_written = []
    for artifact in state_data.get("artifacts", []):
        name = artifact.get("name")
        content = artifact.get("content", "")
        if name:
            art_file = output_dir / name
            artifact_path = artifact.get("path")
            artifact_type = str(artifact.get("type") or "")
            if artifact_path:
                src = Path(artifact_path)
                if src.exists():
                    if artifact_type in {"screenshot", "binary"} or src.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                        shutil.copyfile(src, art_file)
                    else:
                        art_file.write_text(scrub_secrets(src.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
                else:
                    art_file.write_text("", encoding="utf-8")
            elif isinstance(content, str):
                art_file.write_text(scrub_secrets(content), encoding="utf-8")
            else:
                art_file.write_bytes(content)
            artifacts_written.append(str(art_file))

    # Write structured result.json
    result = {
        "task_id": task_id,
        "operator_id": operator_id,
        "sprint_id": sprint_id,
        "node_id": node_id,
        "status": status,
        "exit_code": exit_code,
        "started_at": state_data.get("created_at"),
        "finished_at": state_data.get("updated_at"),
        "log_tail": scrub_secrets(state_data.get("logs")[-8000:]),
        "artifacts": artifacts_written
    }

    result_path = output_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return result


def cancel_browser_job(job_id: str) -> bool:
    """Cancels a browser job and marks it as failed."""
    job_dir = BROWSER_JOBS_DIR / job_id
    state_file = job_dir / "state.json"
    if not state_file.exists():
        return False

    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    state_data["state"] = "failed"
    state_data["logs"] += f"[{_now()}] Job cancelled by controller.\n"
    state_data["updated_at"] = _now()
    
    state_data["logs"] = scrub_secrets(state_data["logs"])
    state_file.write_text(json.dumps(state_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return True
