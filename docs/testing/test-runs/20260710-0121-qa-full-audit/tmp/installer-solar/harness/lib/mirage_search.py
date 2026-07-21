#!/usr/bin/env python3
"""
mirage_search.py — Unified search across Mirage paths, QMD, and Solar DB.

Sources:
  1. mirage_path — bounded grep/rg over allowed mount directories
  2. qmd — call `solar-harness wiki qmd-search "<query>" --json`
  3. solar_db — call `solar-knowledge-context.py --query ... --json`

Output:
  Normalized hits with mount, path, source_type, snippet, provenance, score_or_rank.
  Defaults: max 10 hits, max 4000 chars.
  Degraded sources are tracked in `degraded_sources`.

Used by:
  solar_mirage.py (S1 wrapper) → its search subcommand → this module
  solar-harness mirage search <query> --json

Sprint: sprint-20260508-mirage-unified-vfs
Slice:  S2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Optional SandboxHand routing for QMD search (tool-plane default).
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from hands_runtime import SandboxHand  # noqa: E402
    from runtime_interfaces import ResultStatus  # noqa: E402
    _SANDBOX_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - import safety
    SandboxHand = None  # type: ignore[assignment]
    ResultStatus = None  # type: ignore[assignment]
    _SANDBOX_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

try:
    import cocoindex_adapter  # type: ignore  # noqa: E402
except Exception as exc:  # pragma: no cover - optional adapter
    cocoindex_adapter = None  # type: ignore[assignment]
    _COCO_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    _COCO_IMPORT_ERROR = ""

try:
    import understand_anything_adapter  # type: ignore  # noqa: E402
except Exception as exc:  # pragma: no cover - optional adapter
    understand_anything_adapter = None  # type: ignore[assignment]
    _UA_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    _UA_IMPORT_ERROR = ""

# Last-route telemetry for callers/tests to assert sandbox routing.
LAST_QMD_ROUTE: dict[str, Any] = {}

# ─── Default allowed mounts for path search ───────────────────────────
# These are the safe, read-only mounts defined in the design.
# If mirage.solar.yaml exists (S1 deliverable), it overrides these.
DEFAULT_MOUNTS: list[dict[str, str]] = [
    {"path": "/knowledge", "root": os.path.expanduser("~/Knowledge")},
    {"path": "/sprints",  "root": os.path.expanduser("~/.solar/harness/sprints")},
    {"path": "/cortex",   "root": os.path.expanduser("~/.claude/core/cortex")},
]

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
QMD_BIN = "qmd"
QMD_COLLECTION = os.environ.get("QMD_WIKI_COLLECTION", "solar-wiki")
SOLAR_KB_SCRIPT = os.path.join(HARNESS_DIR, "lib", "solar-knowledge-context.py")
MIRAGE_CONFIG_YAML = os.path.join(HARNESS_DIR, "config", "mirage.solar.yaml")
HOST_QMD_CACHE_HOME = str(Path.home() / ".cache")
HOST_QMD_CONFIG_HOME = str(Path.home() / ".config")

# Budgets (contract A4)
DEFAULT_MAX_HITS = 10
DEFAULT_MAX_CHARS = 4000
ADAPTER_TIMEOUT_S = 3  # per source adapter


def _extract_cjk_keywords(query: str) -> str:
    """Return the strongest CJK topical phrase from a multilingual query."""
    cleaned = re.sub(
        r'帮我|请你|请问|帮忙|告诉我|给我|分析一下|分析下|解释一下|介绍一下|讲解|'
        r'详细说明|总结|简单|怎么|如何|基于|关于|是什么|有哪些|有什么|什么是|'
        r'做了什么|负责什么|解决了什么问题|当前是否|当前|现在|是否',
        ' ',
        query,
    )
    cleaned = re.sub(
        r'分析|研究|探讨|优化|改进|实现|设计|解决|处理|应用|使用|部署|集成|'
        r'配置|与.*关系|和.*关系',
        ' ',
        cleaned,
    )
    cleaned = re.sub(r'[的了在里与和及/？?，,。:：()（）]', ' ', cleaned)
    segments = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]{4,}', cleaned)
    if segments:
        return max(segments, key=len)
    cjk_any = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]{2,}', cleaned)
    if cjk_any:
        return max(cjk_any, key=len)
    return ""


def _query_variants(query: str) -> list[str]:
    """Search original query plus precise topical variants.

    Agents often expand a Chinese user query into bilingual terms. Exact vault
    titles are frequently Chinese, so searching only the expanded string can
    dilute results. Keep the original query but also search the extracted topic.
    """
    variants: list[str] = []
    stripped = query.strip()
    ascii_tokens = re.findall(r'[A-Za-z][A-Za-z0-9_.-]*', stripped)
    ascii_phrase = " ".join(ascii_tokens[:6])
    extra_ascii: list[str] = []
    lowered_tokens = {t.lower() for t in ascii_tokens}
    if "mia" in lowered_tokens and any(t.lower() == "solar-harness" for t in ascii_tokens):
        extra_ascii.extend(["Solar MIA", "solar-mia", "MIA"])
    if "apple" in lowered_tokens and "notes" in lowered_tokens:
        extra_ascii.extend(["Apple Notes", "微信文章进入知识库链路"])
    cjk_topic = _extract_cjk_keywords(query)
    cjk_segments = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]{4,}', cjk_topic)
    cjk_subphrases: list[str] = []
    for seg in cjk_segments:
        cjk_subphrases.append(seg)
        if len(seg) > 6:
            cjk_subphrases.append(seg[:6])
            cjk_subphrases.append(seg[-4:])

    for candidate in (stripped, cjk_topic, *cjk_subphrases, ascii_phrase, *extra_ascii):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants or [query]


# ─── Mount resolution ─────────────────────────────────────────────────

def _load_mounts_from_yaml() -> list[dict[str, str]] | None:
    """Try to load mount definitions from mirage.solar.yaml (S1 deliverable)."""
    if not os.path.exists(MIRAGE_CONFIG_YAML):
        return None
    try:
        with open(MIRAGE_CONFIG_YAML) as f:
            content = f.read()
    except Exception:
        return None
    mounts: list[dict[str, str]] = []
    in_mounts = False
    in_policy = False  # stop parsing mounts at policy:
    current: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        # Stop at policy section
        if stripped.startswith("policy:"):
            in_policy = True
            in_mounts = False
            continue
        if in_policy:
            continue
        if stripped.startswith("mounts:"):
            in_mounts = True
            continue
        if not in_mounts:
            continue
        # New mount entry
        if stripped.startswith("- path:"):
            if current:
                mounts.append(current)
                current = {}
            current["path"] = stripped.split(":", 1)[1].strip().strip('"')
        elif stripped.startswith("root:") and "path" in current:
            root_val = stripped.split(":", 1)[1].strip().strip('"')
            if root_val:
                current["root"] = os.path.expanduser(root_val)
        elif stripped.startswith("mode:"):
            current["mode"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("source_type:"):
            current["source_type"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("optional:") and "root" not in current:
            # End of current mount (gdrive/virtual, no root)
            if current and "path" in current:
                # Only keep disk mounts with roots for path search
                pass
            current = {}
        elif stripped.startswith("adapter:") or stripped.startswith("credential_env:"):
            # Skip these — not disk mounts
            pass
        elif stripped == "" and current:
            # End of current mount block
            if "root" in current and current["root"]:
                pass  # keep it
            elif "root" not in current:
                # virtual or gdrive mount, skip for path search
                current = {}
    if current and "path" in current and "root" in current and current["root"]:
        mounts.append(current)
    # Filter: only keep disk mounts with valid roots
    disk_mounts = [m for m in mounts
                   if m.get("source_type") in (None, "disk")
                   and m.get("root") and os.path.isdir(m.get("root", ""))]
    if disk_mounts:
        return disk_mounts
    return None


def get_mounts() -> list[dict[str, str]]:
    """Return mount definitions: config if available, else defaults."""
    loaded = _load_mounts_from_yaml()
    if loaded:
        return loaded
    return DEFAULT_MOUNTS


# ─── Source adapter: mirage_path ──────────────────────────────────────

def _rg_available() -> bool:
    """Check if ripgrep is on PATH."""
    try:
        subprocess.run(["rg", "--version"], capture_output=True, timeout=1)
        return True
    except Exception:
        return False


def search_mirage_path(query: str, mounts: list[dict[str, str]],
                       max_hits: int = 6) -> list[dict[str, Any]]:
    """Grep allowed mount directories for query matches.

    Uses rg (ripgrep) if available; falls back to grep -r.
    Returns up to max_hits normalized hits.
    """
    hits: list[dict[str, Any]] = []
    use_rg = _rg_available()

    for mount in mounts:
        root = mount.get("root", "")
        if not os.path.isdir(root):
            continue
        mount_path = mount.get("path", root)
        root = os.path.realpath(root)

        try:
            if use_rg:
                cmd = [
                    "rg", "--json", "--no-heading", "--ignore-case",
                    "--max-count", str(max_hits),
                    "--max-filesize", "1M",
                    "--follow",
                    "-g", "!*.png", "-g", "!*.jpg", "-g", "!*.gif",
                    "-g", "!*.pdf", "-g", "!*.zip", "-g", "!*.tar",
                    "-g", "!*.gz", "-g", "!*.db", "-g", "!*.sqlite",
                    "-g", "!.git/*", "-g", "!.obsidian/*",
                    "--", query, root,
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=ADAPTER_TIMEOUT_S,
                )
                if result.returncode not in (0, 1):
                    continue
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("type") != "match":
                        continue
                    data = entry.get("data", {})
                    file_path = data.get("path", {}).get("text", "")
                    line_text = data.get("lines", {}).get("text", "").strip()
                    line_no = data.get("line_number", 0)
                    snippet = line_text[:300]
                    if file_path:
                        hits.append({
                            "mount": mount_path,
                            "path": "/" + os.path.relpath(file_path, root),
                            "source_type": "mirage_path",
                            "snippet": snippet,
                            "provenance": f"rg:{mount_path}:{line_no}",
                            "score_or_rank": 1.0,
                        })
            else:
                cmd = ["grep", "-rin", "--max-count=1", "-I"]
                cmd += ["--", query, root]
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=ADAPTER_TIMEOUT_S,
                )
                if result.returncode not in (0, 1):
                    continue
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split(":", 2)
                    if len(parts) < 3:
                        continue
                    fpath, lineno_str, text = parts
                    try:
                        lineno = int(lineno_str)
                    except ValueError:
                        continue
                    rel = "/" + os.path.relpath(fpath, root)
                    hits.append({
                        "mount": mount_path,
                        "path": rel,
                        "source_type": "mirage_path",
                        "snippet": text.strip()[:300],
                        "provenance": f"grep:{mount_path}:{lineno}",
                        "score_or_rank": 1.0,
                    })
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue

        if len(hits) >= max_hits:
            break

    return hits[:max_hits]


# ─── Source adapter: qmd ──────────────────────────────────────────────

def _qmd_search_sandboxed(query: str, max_hits: int) -> dict[str, Any]:
    """Run `qmd search <query>` through SandboxHand (argv mode, evidence file).

    Returns a routing record with stdout/stderr/exit_code, plus executor /
    execution_mode / evidence_file so callers and tests can assert that the
    tool-plane QMD search path lands inside the disposable sandbox by default.

    If SandboxHand is unavailable (e.g. pruned install), reports
    `executor=host_fallback` with `fallback_reason` so activation proof can
    downgrade the verdict instead of silently passing.
    """
    base_payload = {
        "executor": "host_fallback",
        "execution_mode": "argv",
        "evidence_file": "",
        "write_guard": {"enabled": False, "violations": []},
        "fallback_reason": "",
        "stdout": "",
        "stderr": "",
        "exit_code": 99,
        "ok": False,
        "qmd_bin": QMD_BIN,
        "collection": QMD_COLLECTION,
        "argv": [QMD_BIN, "search", query, "-c", QMD_COLLECTION, "--json", "-n", str(max_hits)],
    }
    if SandboxHand is None or ResultStatus is None:
        base_payload["fallback_reason"] = _SANDBOX_IMPORT_ERROR or "SandboxHand not importable"
        return base_payload
    hand = SandboxHand()
    ref = hand.provision(capabilities=["qmd-search"])
    qmd_env_overrides = {
        "XDG_CACHE_HOME": HOST_QMD_CACHE_HOME,
        "XDG_CONFIG_HOME": HOST_QMD_CONFIG_HOME,
    }
    previous_env = {k: os.environ.get(k) for k in qmd_env_overrides}
    os.environ.update(qmd_env_overrides)
    try:
        idem = hashlib.sha1(
            f"qmd-search:{query}:{os.getpid()}:{time.monotonic_ns()}".encode("utf-8")
        ).hexdigest()[:24]
        result = hand.execute(
            ref,
            "qmd-search",
            {
                "argv": base_payload["argv"],
                "env_allow": ["XDG_CACHE_HOME", "XDG_CONFIG_HOME", "NODE_LLAMA_CPP_GPU"],
                "session_id": f"qmd-search-{os.getpid()}",
                "sprint_id": f"qmd-search-{os.getpid()}",
                "activity_id": f"qmd-search-{idem}",
            },
            idempotency_key=f"qmd-search:{idem}",
            timeout_seconds=ADAPTER_TIMEOUT_S,
        )
        stdout = str(result.output or "")
        stderr = str((result.metadata or {}).get("stderr", "") or "")
        ok = result.status == ResultStatus.OK
        exit_code = 0 if ok else (124 if result.status == ResultStatus.TIMEOUT else 1)
        base_payload.update({
            "executor": "sandbox",
            "execution_mode": (result.metadata or {}).get("execution_mode", "argv"),
            "evidence_file": (result.metadata or {}).get("evidence_file", ""),
            "write_guard": (result.metadata or {}).get("write_guard", {"enabled": False, "violations": []}),
            "sandbox_status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "hand_id": ref.hand_id,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "ok": ok,
        })
        return base_payload
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        hand.dispose(ref)


def _qmd_search_host_fallback(query: str, max_hits: int, reason: str) -> dict[str, Any]:
    route = {
        "executor": "host_fallback",
        "execution_mode": "argv",
        "evidence_file": "",
        "write_guard": {"enabled": False, "violations": []},
        "fallback_reason": reason,
        "stdout": "",
        "stderr": "",
        "exit_code": 99,
        "ok": False,
        "qmd_bin": QMD_BIN,
        "collection": QMD_COLLECTION,
        "argv": [QMD_BIN, "search", query, "-c", QMD_COLLECTION, "--json", "-n", str(max_hits)],
    }
    try:
        proc = subprocess.run(
            route["argv"],
            capture_output=True,
            text=True,
            timeout=ADAPTER_TIMEOUT_S,
            env={
                **os.environ,
                "XDG_CACHE_HOME": HOST_QMD_CACHE_HOME,
                "XDG_CONFIG_HOME": HOST_QMD_CONFIG_HOME,
            },
        )
    except subprocess.TimeoutExpired as exc:
        route.update({"stderr": f"timeout after {ADAPTER_TIMEOUT_S}s", "exit_code": 124, "ok": False})
        return route
    except Exception as exc:
        route.update({"stderr": f"{type(exc).__name__}: {exc}", "exit_code": 1, "ok": False})
        return route
    route.update({
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "exit_code": proc.returncode,
        "ok": proc.returncode == 0,
    })
    return route


def search_qmd(query: str, max_hits: int = 5) -> tuple[list[dict[str, Any]], bool]:
    """Call qmd search through SandboxHand and normalize results.

    Returns (hits, available).  available=False means qmd is not installed
    or search failed; hits will be empty.
    The most recent sandbox route record is also stored in module global
    `LAST_QMD_ROUTE` for tests and activation-proof callers.
    """
    global LAST_QMD_ROUTE
    hits: list[dict[str, Any]] = []
    route = _qmd_search_sandboxed(query, max_hits)
    LAST_QMD_ROUTE = route

    if not route.get("ok"):
        fallback = _qmd_search_host_fallback(query, max_hits, reason=str(route.get("stderr") or route.get("fallback_reason") or "sandbox_qmd_failed")[:500])
        fallback["sandbox_route"] = route
        LAST_QMD_ROUTE = fallback
        route = fallback
        if not route.get("ok"):
            # `qmd` binary may be absent or both sandbox and fallback failed.
            # Treat as available=False so the unified-search caller marks the
            # source as degraded rather than asserting hits.
            return hits, False

    try:
        data = json.loads(route.get("stdout") or "")
    except json.JSONDecodeError:
        return hits, True
    except Exception:
        return hits, True

    if not isinstance(data, list):
        return hits, True

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        file_ref = item.get("file", "") or item.get("path", "") or ""
        title = item.get("title", "")
        snippet = item.get("snippet", "") or item.get("context", "") or ""
        score = float(item.get("score", 0.5))

        hits.append({
            "mount": "/qmd",
            "path": file_ref,
            "source_type": "qmd",
            "snippet": (snippet or title or "")[:300],
            "provenance": f"qmd:{QMD_COLLECTION}:{item.get('docid', i)}",
            "score_or_rank": score,
        })

    return hits[:max_hits], True


# ─── Source adapter: solar_db ─────────────────────────────────────────

def search_solar_db(query: str, max_hits: int = 5) -> tuple[list[dict[str, Any]], bool]:
    """Call solar-knowledge-context.py and normalize results.

    Returns (hits, available).  available=False means the script is missing;
    hits will be empty.
    """
    hits: list[dict[str, Any]] = []
    if not os.path.exists(SOLAR_KB_SCRIPT):
        return hits, False

    try:
        result = subprocess.run(
            ["python3", SOLAR_KB_SCRIPT,
             "--query", query,
             "--json",
             "--max-hits", str(max_hits),
             "--fail-open"],
            capture_output=True, text=True,
            timeout=ADAPTER_TIMEOUT_S + 1,
        )
        if result.returncode != 0:
            return hits, True
        data = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return hits, True
    except (json.JSONDecodeError, Exception):
        return hits, True

    raw_hits = data.get("hits", [])
    if not isinstance(raw_hits, list):
        return hits, True

    for item in raw_hits:
        if not isinstance(item, dict):
            continue
        source = item.get("source", "") or item.get("table", "")
        hit_id = item.get("id", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")[:300]
        score = float(item.get("score", 0.5))
        item_path = item.get("path", "") or hit_id or title or ""

        hits.append({
            "mount": "/solar_db",
            "path": item_path,
            "source_type": "solar_db",
            "snippet": snippet,
            "provenance": f"solar_db:{source}:{hit_id}" if hit_id else f"solar_db:{source}",
            "score_or_rank": score,
        })

    return hits[:max_hits], True


# ─── Source adapters: cocoindex / understanding ───────────────────────

def search_cocoindex(query: str, max_hits: int = 5) -> tuple[list[dict[str, Any]], bool, str | None]:
    if cocoindex_adapter is None:
        return [], False, f"cocoindex:import_error:{_COCO_IMPORT_ERROR}"
    try:
        return cocoindex_adapter.search(query, limit=max_hits)
    except Exception as exc:
        return [], False, f"cocoindex:error:{type(exc).__name__}"


def search_understanding(query: str, max_hits: int = 5) -> tuple[list[dict[str, Any]], bool, str | None]:
    if understand_anything_adapter is None:
        return [], False, f"understanding:import_error:{_UA_IMPORT_ERROR}"
    try:
        return understand_anything_adapter.search(query, limit=max_hits)
    except Exception as exc:
        return [], False, f"understanding:error:{type(exc).__name__}"


# ─── Aggregation ──────────────────────────────────────────────────────

def _dedup_key(hit: dict[str, Any]) -> str:
    """Create a dedupe key that preserves distinct semantic layers."""
    source_hash = hit.get("source_hash") or hit.get("path") or ""
    layer = hit.get("layer") or _assign_layer(hit)
    return f"{source_hash}||{layer}"


def _hit_text(hit: dict[str, Any]) -> str:
    return " ".join(
        str(hit.get(k, "") or "").lower()
        for k in ("path", "mount", "source_type", "provenance", "snippet")
    )


def _topic_relevance(hit: dict[str, Any], query: str) -> float:
    topic = _extract_cjk_keywords(query) or query.strip()
    if not topic:
        return 0.0
    hay = _hit_text(hit)
    topic_l = topic.lower()
    boost = 0.0
    if topic_l in hay:
        boost += 2.0
    if query.strip().lower() and query.strip().lower() in hay:
        boost += 0.5
    if "solar-harness-pm-1210-context-inject-fix" in hay:
        boost -= 1.5
    ascii_tokens = [t.lower() for t in re.findall(r'[A-Za-z][A-Za-z0-9_.-]*', query) if len(t) >= 3]
    if ascii_tokens:
        matched = sum(1 for t in ascii_tokens if t in hay)
        if matched == len(ascii_tokens):
            boost += 2.5
        else:
            boost += 0.4 * matched
    return boost


def _assign_layer(hit: dict[str, Any]) -> str:
    source_type = str(hit.get("source_type", ""))
    if source_type == "cocoindex":
        return str(hit.get("layer") or "code-symbol")
    if source_type == "understanding":
        return str(hit.get("layer") or "understanding-summary")
    if source_type == "qmd":
        return "synthesis"
    if source_type == "solar_db":
        return "references"
    text = _hit_text(hit)
    if "qmd://solar-wiki/synthesis/" in text or "/knowledge/synthesis/" in text or "/synthesis/" in text:
        return "synthesis"
    if "qmd://solar-wiki/concepts/" in text or "/knowledge/concepts/" in text or "/concepts/" in text:
        return "concepts"
    if "qmd://solar-wiki/references/" in text or "/knowledge/references/" in text or "/references/" in text:
        return "references"
    if "qmd://solar-wiki/raw/" in text or "/knowledge/_raw/" in text or "/_raw/" in text or "/raw/" in text:
        return "raw-evidence"
    return "retrieval-evidence" if source_type == "mirage_path" else "raw-evidence"


def _layer_priority(hit: dict[str, Any]) -> int:
    layer = _assign_layer(hit)
    priorities = {
        "synthesis": 0,
        "concepts": 1,
        "references": 2,
        "code-symbol": 3,
        "code-callgraph": 4,
        "code-chunk": 5,
        "understanding-summary": 6,
        "understanding-claim": 7,
        "understanding-entity": 8,
        "retrieval-evidence": 9,
        "raw-evidence": 10,
    }
    if layer in priorities:
        return priorities[layer]
    text = _hit_text(hit)
    if "qmd://solar-wiki/synthesis/" in text or "/knowledge/synthesis/" in text or "/synthesis/" in text:
        return 0
    if "qmd://solar-wiki/concepts/" in text or "/knowledge/concepts/" in text or "/concepts/" in text:
        return 1
    if "qmd://solar-wiki/references/" in text or "/knowledge/references/" in text or "/references/" in text:
        return 2
    if any(f"qmd://solar-wiki/{bucket}/" in text or f"/knowledge/{bucket}/" in text or f"/{bucket}/" in text
           for bucket in ("entities", "projects", "skills", "theses", "timelines", "contradictions", "indexes")):
        return 3
    if "qmd://solar-wiki/raw/" in text or "/knowledge/_raw/" in text or "/_raw/" in text or "/raw/" in text:
        return 80
    return 40


def _source_priority(hit: dict[str, Any]) -> int:
    return {
        "qmd": 0,
        "solar_db": 1,
        "cocoindex": 2,
        "understanding": 3,
        "mirage_path": 4,
    }.get(str(hit.get("source_type", "")), 9)


def _rank_score(hit: dict[str, Any], query: str) -> float:
    layer_weights = {
        "synthesis": 1.0,
        "concepts": 0.95,
        "references": 0.9,
        "code-symbol": 0.85,
        "code-callgraph": 0.82,
        "code-chunk": 0.78,
        "understanding-summary": 0.75,
        "understanding-claim": 0.70,
        "understanding-entity": 0.65,
        "retrieval-evidence": 0.55,
        "raw-evidence": 0.40,
    }
    layer_weight = layer_weights.get(_assign_layer(hit), 0.5)
    semantic = float(hit.get("score_or_rank", 0.5) or 0.5)
    degraded_penalty = 0.3 if hit.get("degraded") else 0.0
    return layer_weight * 0.6 + semantic * 0.4 + _topic_relevance(hit, query) - degraded_penalty


def unified_search(query: str,
                   max_hits: int = DEFAULT_MAX_HITS,
                   max_chars: int = DEFAULT_MAX_CHARS,
                   sources: list[str] | None = None,
                   mounts: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Run unified search across all available sources.

    Args:
        query: Search query string.
        max_hits: Maximum number of hits to return (default 10).
        max_chars: Maximum total characters in hit snippets (default 4000).
        sources: Which source types to query. None = all.
        mounts: Mount definitions for path search. None = auto-detect.

    Returns:
        Dict with keys: hits, degraded_sources, total_chars, truncated, query, elapsed_ms.
    """
    t0 = time.monotonic()
    if sources is None:
        sources = ["mirage_path", "qmd", "solar_db", "cocoindex", "understanding"]
    if mounts is None:
        mounts = get_mounts()

    all_hits: list[dict[str, Any]] = []
    degraded: list[str] = []

    # Distribute hit budget across active sources
    active_count = len(sources)
    per_source = max(3, max_hits // max(1, active_count))

    query_variants = _query_variants(query)

    # --- mirage_path ---
    if "mirage_path" in sources:
        path_hits: list[dict[str, Any]] = []
        for q in query_variants:
            path_hits.extend(search_mirage_path(q, mounts, per_source))
        all_hits.extend(path_hits)
        if not path_hits:
            degraded.append("mirage_path:no_results")

    # --- qmd ---
    if "qmd" in sources:
        qmd_any_ok = False
        for q in query_variants:
            qmd_hits, qmd_ok = search_qmd(q, per_source)
            qmd_any_ok = qmd_any_ok or qmd_ok
            all_hits.extend(qmd_hits)
        if not qmd_any_ok:
            degraded.append("qmd:unavailable")

    # --- solar_db ---
    if "solar_db" in sources:
        db_any_ok = False
        for q in query_variants:
            db_hits, db_ok = search_solar_db(q, per_source)
            db_any_ok = db_any_ok or db_ok
            all_hits.extend(db_hits)
        if not db_any_ok:
            degraded.append("solar_db:unavailable")

    # --- cocoindex ---
    if "cocoindex" in sources:
        coco_any_ok = False
        coco_reasons: list[str] = []
        for q in query_variants:
            coco_hits, coco_ok, reason = search_cocoindex(q, per_source)
            coco_any_ok = coco_any_ok or coco_ok
            if reason:
                coco_reasons.append(reason)
            all_hits.extend(coco_hits)
        if not coco_any_ok:
            degraded.append(coco_reasons[0] if coco_reasons else "cocoindex:unavailable")
        elif coco_reasons:
            degraded.extend(sorted(set(coco_reasons))[:2])

    # --- understanding ---
    if "understanding" in sources:
        ua_any_ok = False
        ua_reasons: list[str] = []
        for q in query_variants:
            ua_hits, ua_ok, reason = search_understanding(q, per_source)
            ua_any_ok = ua_any_ok or ua_ok
            if reason:
                ua_reasons.append(reason)
            all_hits.extend(ua_hits)
        if not ua_any_ok:
            degraded.append(ua_reasons[0] if ua_reasons else "understanding:unavailable")
        elif ua_reasons:
            degraded.extend(sorted(set(ua_reasons))[:2])

    for hit in all_hits:
        hit["layer"] = _assign_layer(hit)
        hit.setdefault("source_hash", hashlib.sha256(
            f"{hit.get('source_type')}:{hit.get('path')}:{hit.get('snippet', '')[:120]}".encode("utf-8", errors="replace")
        ).hexdigest())
        hit.setdefault("lineage", [hit.get("path", "")])
        hit.setdefault("degraded", False)

    # Deduplicate by path+snippet key
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for h in all_hits:
        key = _dedup_key(h)
        if key not in seen:
            seen.add(key)
            unique.append(h)

    # Prefer compiled knowledge layers; keep raw material as evidence, not the
    # default synthesis context when both are available.
    unique.sort(key=lambda h: (
        -_rank_score(h, query),
        _layer_priority(h),
        _source_priority(h),
        -float(h.get("score_or_rank", 0.0) or 0.0),
    ))

    # Enforce hit budget
    hits = unique[:max_hits]

    # Enforce character budget
    total_chars = 0
    kept: list[dict[str, Any]] = []
    truncated = False
    for h in hits:
        snippet = h.get("snippet", "")
        snip_len = len(snippet)
        if total_chars + snip_len > max_chars:
            remaining = max(0, max_chars - total_chars)
            if remaining > 40:
                h["snippet"] = snippet[:remaining]
                kept.append(h)
                total_chars += remaining
            truncated = True
            break
        kept.append(h)
        total_chars += snip_len

    return {
        "hits": kept,
        "degraded_sources": degraded,
        "source_counts": {
            source: sum(1 for h in kept if h.get("source_type") == source)
            for source in sorted({str(h.get("source_type", "")) for h in kept if h.get("source_type")})
        },
        "lineage_refs": sorted({str(x) for h in kept for x in (h.get("lineage") or []) if x})[:50],
        "source_hash_refs": sorted({str(h.get("source_hash")) for h in kept if h.get("source_hash")})[:50],
        "total_chars": total_chars,
        "truncated": truncated,
        "query": query,
        "query_variants": query_variants,
        "elapsed_ms": (time.monotonic() - t0) * 1000,
    }


# ─── CLI ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mirage unified search — query across Mirage paths, QMD, Solar DB, CocoIndex, and understanding artifacts",
    )
    parser.add_argument("query", help="Search query string")
    parser.add_argument("--json", dest="json_out", action="store_true",
                        default=True, help="Output as JSON (default)")
    parser.add_argument("--max-hits", type=int, default=DEFAULT_MAX_HITS,
                        help=f"Max hits to return (default: {DEFAULT_MAX_HITS})")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                        help=f"Max total snippet chars (default: {DEFAULT_MAX_CHARS})")
    parser.add_argument("--sources", type=str, default="mirage_path,qmd,solar_db,cocoindex,understanding",
                        help="Comma-separated source types (default: mirage_path,qmd,solar_db,cocoindex,understanding)")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to mirage.solar.yaml (optional)")
    args = parser.parse_args()

    sources_list = [s.strip() for s in args.sources.split(",") if s.strip()]

    mounts: list[dict[str, str]] | None = None
    if args.config and os.path.exists(args.config):
        global MIRAGE_CONFIG_YAML
        MIRAGE_CONFIG_YAML = args.config
        mounts = _load_mounts_from_yaml()
    if mounts is None:
        mounts = get_mounts()

    result = unified_search(
        query=args.query,
        max_hits=args.max_hits,
        max_chars=args.max_chars,
        sources=sources_list,
        mounts=mounts,
    )

    if args.json_out:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        hits = result.get("hits", [])
        if not hits:
            print(f"No results found for: {args.query}")
            if result.get("degraded_sources"):
                print(f"Degraded sources: {', '.join(result['degraded_sources'])}")
            return
        print(f"Search results for: {args.query}")
        print(f"Sources: {args.sources}  |  Hits: {len(hits)}  |  "
              f"Chars: {result.get('total_chars', 0)}")
        print("-" * 60)
        for i, h in enumerate(hits, 1):
            st = h.get("source_type", "?")
            mount = h.get("mount", "?")
            path = h.get("path", "?")
            score = h.get("score_or_rank", 0)
            snippet = h.get("snippet", "")
            print(f"[{i}] [{st}] {mount}{path} (score={score:.2f})")
            print(f"    {snippet[:200]}")
        if result.get("truncated"):
            print("... (results truncated due to char budget)")
        if result.get("degraded_sources"):
            print(f"\n⚠ Degraded sources: {', '.join(result['degraded_sources'])}")


if __name__ == "__main__":
    main()
