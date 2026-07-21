#!/usr/bin/env python3
"""Solar external integration health.

Six-state model per integration:
installed, configured, running, indexed, used_by_default, degraded_reason.
The probe is local-only and fail-open: one broken integration should not break
the whole status payload.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import re
from pathlib import Path


HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", HOME / "Knowledge"))
SOLAR_DB = HOME / ".solar" / "solar.db"
CACHE_PATH = HARNESS / "state" / "external-integrations-last-probe.json"


def run(cmd: list[str], timeout: float = 3.0) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as exc:
        return 99, f"{type(exc).__name__}: {exc}"


def port_probe(port: int, hosts: list[str] | None = None, timeout: float = 0.25) -> dict:
    hosts = hosts or ["127.0.0.1", "::1", "localhost"]
    results = {}
    open_hosts = []
    for item in hosts:
        try:
            with socket.create_connection((item, port), timeout=timeout):
                results[item] = "open"
                open_hosts.append(item)
        except OSError as exc:
            results[item] = f"closed:{type(exc).__name__}"
    return {"open": bool(open_hosts), "open_hosts": open_hosts, "hosts": results}


def port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    hosts = [host]
    if host in ("127.0.0.1", "localhost"):
        hosts.append("::1")
    return port_probe(port, hosts=hosts, timeout=timeout)["open"]


def which_qmd() -> str:
    for item in os.environ.get("PATH", "").split(os.pathsep):
        p = Path(item) / "qmd"
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    fallback = HOME / ".npm-global" / "bin" / "qmd"
    return str(fallback) if fallback.exists() else ""


def local_google_drive() -> dict:
    configured = HARNESS / "config" / "mirage.solar.yaml"
    raw = configured.read_text(errors="ignore") if configured.exists() else ""
    m = re.search(r'root:\s*"([^"]*GoogleDrive[^"]*)"', raw)
    if m and Path(m.group(1)).exists():
        return {"ok": True, "path": m.group(1), "source": "mirage_config"}
    cloud_storage = HOME / "Library" / "CloudStorage"
    if cloud_storage.exists():
        for path in sorted(cloud_storage.glob("GoogleDrive-*")):
            if path.is_dir():
                return {"ok": True, "path": str(path), "source": "macos_file_provider"}
    return {"ok": False, "path": "", "source": ""}


def count_sql(table: str) -> int | None:
    if not SOLAR_DB.exists():
        return None
    try:
        with sqlite3.connect(SOLAR_DB) as conn:
            return int(conn.execute(f"select count(*) from {table}").fetchone()[0])
    except Exception:
        return None


def qmd_status() -> dict:
    qmd = which_qmd()
    if not qmd:
        return {"ok": False, "binary": "", "raw": "", "total": 0, "pending": None, "vectors": None}
    code, out = run([qmd, "status"], timeout=6)
    total = pending = vectors = None
    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("Total:"):
            total = int(line.split()[1]) if len(line.split()) > 1 and line.split()[1].isdigit() else None
        elif line.startswith("Vectors:"):
            vectors = int(line.split()[1]) if len(line.split()) > 1 and line.split()[1].isdigit() else None
        elif line.startswith("Pending:"):
            pending = int(line.split()[1]) if len(line.split()) > 1 and line.split()[1].isdigit() else None
    return {"ok": code == 0, "binary": qmd, "raw": out[:2000], "total": total or 0, "pending": pending, "vectors": vectors}


def dispatch_backlog() -> dict:
    dispatch_dir = VAULT / "_raw" / "solar-harness" / ".dispatch"
    counts: dict[str, int] = {}
    ignored: dict[str, int] = {}
    if not dispatch_dir.exists():
        return {"available": False, "reason": "dispatch dir missing", "total": 0, "counts": counts}
    for path in dispatch_dir.glob("*.md"):
        status = "no_status"
        try:
            text = path.read_text(errors="ignore")[:1200]
            type_match = re.search(r"^type:\s*([^\n]+)", text, re.M)
            if not type_match or type_match.group(1).strip() != "wiki-dispatch":
                ignored_type = type_match.group(1).strip() if type_match else "no_type"
                ignored[ignored_type] = ignored.get(ignored_type, 0) + 1
                continue
            m = re.search(r"^status:\s*([^\n]+)", text, re.M)
            if m:
                status = m.group(1).strip()
        except OSError:
            status = "read_error"
        counts[status] = counts.get(status, 0) + 1
    unresolved = sum(counts.get(k, 0) for k in ("pending", "dispatched", "running", "no_status", "read_error"))
    return {
        "available": True,
        "total": sum(counts.values()),
        "counts": counts,
        "ignored_non_dispatch": ignored,
        "unresolved": unresolved,
        "dir": str(dispatch_dir),
    }


def latest_upload_audit(deep: bool = False) -> dict:
    upload_dir = VAULT / "_raw" / "file-uploads"
    if not upload_dir.exists():
        return {"available": False, "reason": "file upload dir missing"}
    batches: dict[str, int] = {}
    for path in upload_dir.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if len(name) >= 16 and name[0:8].isdigit() and name[8] == "T" and name[15] == "Z":
            batches[name[:16]] = batches.get(name[:16], 0) + 1
    if not batches:
        return {"available": False, "reason": "no upload batches"}
    if not deep:
        batch, count = sorted(batches.items(), key=lambda kv: (kv[0], kv[1]), reverse=True)[0]
        return {
            "available": True,
            "batch": batch,
            "mode": "fast_metadata",
            "total_files": count,
            "deep_audit": "skipped; run with --deep for per-source qmd/vault/solar_db audit",
        }
    auditor = HARNESS / "lib" / "wiki-upload-audit.py"
    if not auditor.exists():
        return {"available": False, "reason": "wiki-upload-audit.py missing"}
    checked = []
    latest = None
    backlog_gaps = []
    max_batches = 10 if deep else 1
    timeout = 90 if deep else 20
    for batch, _count in sorted(batches.items(), key=lambda kv: (kv[0], kv[1]), reverse=True)[:max_batches]:
        code, out = run(["python3", str(auditor), "--batch", batch, "--json"], timeout=timeout)
        try:
            data = json.loads(out)
        except Exception:
            checked.append({"batch": batch, "error": out[:160], "exit_code": code})
            continue
        checked.append({"batch": batch, "total": data.get("total", 0)})
        if data.get("total", 0) > 0:
            has_gap = bool(
                data.get("solar_db", {}).get("missing", 0)
                or data.get("vault", {}).get("missing", 0)
                or data.get("qmd", {}).get("missing", 0)
                or data.get("dispatch", {}).get("pending", 0)
            )
            if latest is None:
                latest = {"available": True, "batch": batch, "data": data, "checked": checked}
            elif has_gap:
                backlog_gaps.append(
                    {
                        "batch": batch,
                        "total": data.get("total", 0),
                        "qmd_missing": data.get("qmd", {}).get("missing", 0),
                        "vault_missing": data.get("vault", {}).get("missing", 0),
                        "solar_db_missing": data.get("solar_db", {}).get("missing", 0),
                        "dispatch_pending": data.get("dispatch", {}).get("pending", 0),
                    }
                )
    if latest:
        latest["checked"] = checked
        latest["historical_backlog"] = backlog_gaps[:5]
        return latest
    if checked:
        return {"available": False, "reason": "no auditable upload batch with nonzero total found", "checked": checked}
    return {"available": False, "reason": "no upload batches"}


def health_state(ok: bool, warn: bool = False) -> str:
    if not ok:
        return "error"
    return "warn" if warn else "ok"


def result(name: str, source: str, purpose: str, **states) -> dict:
    keys = ["installed", "configured", "running", "indexed", "used_by_default"]
    lifecycle = states.pop("lifecycle", "active")
    optional = bool(states.pop("optional", False))
    candidate = bool(states.pop("candidate", False))
    degraded = states.pop("degraded_reason", "")
    evidence = states.pop("evidence", {})
    complete = states.pop("complete", None)
    dead_ends = states.pop("dead_ends", [])
    basic_available = states.pop("basic_available", None)
    out = {"name": name, "source": source, "purpose": purpose}
    out["lifecycle"] = lifecycle
    out["optional"] = optional
    out["candidate"] = candidate
    for key in keys:
        out[key] = bool(states.get(key, False))
    if basic_available is None:
        basic_available = out["installed"] and out["configured"]
    if complete is None:
        complete = all(out[k] for k in keys) and not degraded and not dead_ends
    out["health"] = {
        "basic_available": health_state(bool(basic_available)),
        "default_available": health_state(out["used_by_default"], warn=out["used_by_default"] and bool(degraded)),
        "complete_closed_loop": health_state(bool(complete), warn=bool(basic_available) and not complete),
        "dead_ends": "warn" if dead_ends else "ok",
    }
    if optional and basic_available and not dead_ends:
        out["status"] = "ok"
    elif candidate and out["installed"]:
        out["status"] = "ok"
    elif not out["installed"]:
        out["status"] = "missing"
    elif complete and not degraded:
        out["status"] = "ok"
    elif basic_available:
        out["status"] = "warn"
    else:
        out["status"] = "error"
    # 4-tier label for A6: dead_end > closed_loop > default_usable > basic_usable
    if optional and basic_available and not dead_ends:
        out["status_label"] = "basic_usable"
    elif candidate and out["installed"]:
        out["status_label"] = "basic_usable"
    elif dead_ends:
        out["status_label"] = "dead_end"
    elif complete and not degraded:
        out["status_label"] = "closed_loop"
    elif out["used_by_default"]:
        out["status_label"] = "default_usable"
    else:
        out["status_label"] = "basic_usable"
    out["status_legacy"] = out["status"]  # backwards compat for 6 weeks
    out["degraded_reason"] = degraded
    out["dead_ends"] = dead_ends
    out["evidence"] = evidence
    return out


def probe(deep: bool = False) -> dict:
    qmd = qmd_status()
    gdrive_local = local_google_drive()
    upload = latest_upload_audit(deep=deep)
    dispatch = dispatch_backlog()
    qmd_port = port_probe(8181)
    status_port = port_probe(8765, hosts=["127.0.0.1"])

    obs_repo = HARNESS / "vendor" / "obsidian-wiki"
    wiki_cfg = HOME / ".obsidian-wiki" / "config"
    unified_context = HARNESS / "lib" / "solar-unified-context.py"
    claude_hook = HOME / ".claude" / "hooks" / "solar-knowledge-context.sh"
    codex_agents = HOME / ".codex" / "AGENTS.md"
    default_context_ready = (
        unified_context.exists()
        and claude_hook.exists()
        and (
            "solar-unified-context.py" in claude_hook.read_text(errors="ignore")
            or "solar-knowledge-context.py" in claude_hook.read_text(errors="ignore")
        )
        and codex_agents.exists()
        and "solar-harness context inject" in codex_agents.read_text(errors="ignore")
    )
    vault_ready = VAULT.exists()
    capture_running = port_open("127.0.0.1", 8788)
    vault_md_count = len(list(VAULT.glob("**/*.md"))) if vault_ready else 0
    upload_reason_parts = []
    if upload.get("available") and upload.get("data"):
        d = upload["data"]
        if d.get("solar_db", {}).get("missing", 0) or d.get("vault", {}).get("missing", 0) or d.get("qmd", {}).get("missing", 0):
            upload_reason_parts.append(
                f"latest batch {upload['batch']}: qmd {d['qmd']['found']}/{d['total']}, "
                f"vault {d['vault']['found']}/{d['total']}, solar_db {d['solar_db']['found']}/{d['total']}"
            )
    if dispatch.get("unresolved", 0):
        upload_reason_parts.append(
            f"global dispatch backlog: unresolved={dispatch['unresolved']}/{dispatch['total']} "
            f"(pending={dispatch['counts'].get('pending', 0)}, dispatched={dispatch['counts'].get('dispatched', 0)}, "
            f"running={dispatch['counts'].get('running', 0)})"
        )

    mineru_repo = HARNESS / "vendor" / "MinerU-Document-Explorer"
    mineru_venv = mineru_repo / ".venv"
    mineru_vendor_venv = HARNESS / "vendor" / "mineru" / ".venv"  # bootstrap venv path
    mineru_venv_ok = mineru_venv.exists() or mineru_vendor_venv.exists()
    mineru_install_report = HARNESS / "vendor" / "mineru" / "install-report.json"
    mineru_skill_count = len(list((mineru_repo / "skills").glob("*/SKILL.md"))) if (mineru_repo / "skills").exists() else 0
    markitdown_skill = HOME / ".agents" / "skills" / "markitdown" / "SKILL.md"
    markitdown_claude_skill = HOME / ".claude" / "skills" / "markitdown"
    markitdown_script = HOME / ".agents" / "skills" / "markitdown" / "scripts" / "batch_convert.py"
    markitdown_owl_toolkit = HOME / ".solar" / "owl" / "venv" / "lib" / "python3.11" / "site-packages" / "camel" / "toolkits" / "markitdown_toolkit.py"
    claude_agents_dir = HOME / ".claude" / "agents"
    addy_agents_dir = HOME / ".claude" / "plugins" / "marketplaces" / "addy-agent-skills" / "agents"
    addy_root = HOME / ".claude" / "plugins" / "marketplaces" / "addy-agent-skills"
    addy_skills_dir = addy_root / "skills"
    addy_refs_dir = addy_root / "references"
    claude_agents_count = len(list(claude_agents_dir.glob("*.md"))) if claude_agents_dir.exists() else 0
    addy_agents_count = len(list(addy_agents_dir.glob("*.md"))) if addy_agents_dir.exists() else 0
    addy_skills_count = len(list(addy_skills_dir.glob("*/SKILL.md"))) if addy_skills_dir.exists() else 0
    addy_refs_count = len(list(addy_refs_dir.glob("*.md"))) if addy_refs_dir.exists() else 0
    empirical_skill = HOME / ".claude" / "skills" / "empirical-pipeline" / "SKILL.md"
    empirical_gap = HOME / ".solar" / "reports" / "gap-analysis-empirical-research.md"
    browser_use_mcp = HOME / ".claude" / "mcp-servers" / "browser-use"
    browser_use_server = browser_use_mcp / "server.py"
    browser_use_python = browser_use_mcp / ".venv" / "bin" / "python"
    browser_use_codex = HOME / ".codex" / "plugins" / "cache" / "openai-bundled" / "browser-use"
    codex_config = HOME / ".codex" / "config.toml"
    codex_config_text = codex_config.read_text(errors="ignore") if codex_config.exists() else ""
    openai_agents_report = HOME / ".solar" / "reports" / "2026-04-20-openai-agents-integration-codex.md"
    codex_bridge_root = HOME / ".solar" / "codex-bridge"
    codex_bridge_inbox = codex_bridge_root / "from-codex"
    codex_bridge_protocol = codex_bridge_root / "CODEX-PROTOCOL.md"
    chain_watcher = HARNESS / "chain-watcher.sh"
    bridge_ledger = codex_bridge_root / "bridge-ledger.jsonl"
    ruflo_vendor = HARNESS / "vendor" / "ruflo"
    ruflo_status: dict = {}
    ruflo_code, ruflo_out = run(["bash", str(HARNESS / "solar-harness.sh"), "integrations", "ruflo-status", "--json"], timeout=10)
    if ruflo_code == 0:
        try:
            ruflo_status = json.loads(ruflo_out)
        except Exception:
            ruflo_status = {"parse_error": ruflo_out[:500]}
    ruflo_runtime = ruflo_status.get("runtime", {}) if isinstance(ruflo_status, dict) else {}
    ruflo_runtime_ok = bool(ruflo_runtime.get("ok"))
    ruflo_cli = Path(str((ruflo_runtime.get("paths") or {}).get("published_cli", "")))
    autoresearch_vendor = HARNESS / "vendor" / "autoresearch"
    autoresearch_status: dict = {}
    autoresearch_code, autoresearch_out = run(["python3", str(HARNESS / "lib" / "autoresearch_adapter.py"), "status", "--json"], timeout=8)
    if autoresearch_code == 0:
        try:
            autoresearch_status = json.loads(autoresearch_out)
        except Exception:
            autoresearch_status = {"parse_error": autoresearch_out[:500]}
    meta_harness_status: dict = {}
    meta_harness_code, meta_harness_out = run(["python3", str(HARNESS / "lib" / "meta_harness_adapter.py"), "status", "--json"], timeout=8)
    if meta_harness_code == 0:
        try:
            meta_harness_status = json.loads(meta_harness_out)
        except Exception:
            meta_harness_status = {"parse_error": meta_harness_out[:500]}
    arb_vendor = HARNESS / "vendor" / "agent-rules-books"
    arb_report = HARNESS / "reports" / "agent-rules-books-inventory.json"
    arb_status: dict = {}
    arb_code, arb_out = run(["python3", str(HARNESS / "lib" / "agent_rules_books_adapter.py"), "doctor", "--json"], timeout=8)
    if arb_code == 0:
        try:
            arb_status = json.loads(arb_out)
        except Exception:
            arb_status = {"parse_error": arb_out[:500]}

    integrations = [
        result(
            "Ar9av/obsidian-wiki",
            "https://github.com/Ar9av/obsidian-wiki",
            "Obsidian-native knowledge vault, wiki ingest/query/lint/graph skills, Solar artifact export.",
            installed=obs_repo.exists(),
            configured=wiki_cfg.exists() and vault_ready,
            running=capture_running,
            indexed=vault_md_count > 0,
            used_by_default=default_context_ready,
            complete=not upload_reason_parts and default_context_ready,
            degraded_reason="; ".join(upload_reason_parts) or ("" if default_context_ready else "used by commands/status, but not yet guaranteed as default context for every agent"),
            dead_ends=[],
            evidence={
                "repo": str(obs_repo),
                "vault": str(VAULT),
                "capture_port_8788": capture_running,
                "vault_md_count": vault_md_count,
                "unified_context": str(unified_context),
                "claude_hook": str(claude_hook),
                "codex_agents": str(codex_agents),
                "latest_upload_audit": upload,
                "dispatch_backlog": dispatch,
            },
        ),
        result(
            "opendatalab/MinerU-Document-Explorer",
            "https://github.com/opendatalab/MinerU-Document-Explorer",
            "PDF deep-extraction pipeline (magic-pdf CPU mode) + QMD semantic search. venv bootstrapped, PDF extraction active, idle-guarded background worker via launchd.",
            installed=mineru_repo.exists() or (HARNESS / "vendor" / "mineru").exists(),
            configured=mineru_venv_ok,
            running=qmd["ok"],
            indexed=(qmd["total"] or 0) > 0,
            used_by_default=False,
            complete=mineru_venv_ok and bool(qmd["binary"]) and qmd["ok"],
            degraded_reason="" if mineru_venv_ok else "MinerU .venv missing; run: solar-harness mineru bootstrap",
            dead_ends=[] if mineru_venv_ok else ["mineru_venv_missing"],
            evidence={
                "vendor": str(mineru_repo),
                "venv": str(mineru_vendor_venv),
                "venv_exists": mineru_venv_ok,
                "install_report": str(mineru_install_report),
                "skill_count": mineru_skill_count,
                "qmd_binary": qmd["binary"],
                "worker_launchd": (HOME / "Library" / "LaunchAgents" / "io.solar.mineru-worker.plist").exists(),
                "doctor_cmd": "solar-harness mineru doctor --json",
            },
        ),
        result(
            "QMD semantic search/embed",
            "https://github.com/opendatalab/MinerU-Document-Explorer",
            "Local semantic search and idle-only embedding for the solar-wiki collection.",
            installed=bool(qmd["binary"]),
            configured=qmd["ok"] and "solar-wiki" in qmd["raw"],
            running=qmd_port["open"],
            indexed=(qmd["total"] or 0) > 0,
            used_by_default=True,
            complete=qmd["ok"] and qmd_port["open"] and not qmd.get("pending"),
            degraded_reason=(
                f"{qmd['pending']} files need embedding" if qmd.get("pending")
                else ("MCP listens on IPv6 ::1 only; 127.0.0.1 clients will fail" if "::1" in qmd_port["open_hosts"] and "127.0.0.1" not in qmd_port["open_hosts"] else "")
            ),
            dead_ends=["mcp_ipv6_only"] if "::1" in qmd_port["open_hosts"] and "127.0.0.1" not in qmd_port["open_hosts"] else [],
            evidence={
                "total": qmd["total"],
                "vectors": qmd["vectors"],
                "pending": qmd["pending"],
                "mcp_port_8181": qmd_port,
                "embed_launchd": (HOME / "Library" / "LaunchAgents" / "com.solar.qmd-mineru-embed.plist").exists(),
                "embed_status": str(HARNESS / "state" / "qmd-embed-status.json"),
            },
        ),
        result(
            "mermaid-js/mermaid",
            "https://github.com/mermaid-js/mermaid",
            "Local .mmd architecture diagram browser and renderer in Solar Status.",
            installed=(HARNESS / "vendor" / "mermaid-viewer" / "node_modules" / "mermaid").exists(),
            configured=True,
            running=status_port["open"],
            indexed=len(list((HARNESS / "reports").glob("*.mmd"))) > 0,
            used_by_default=True,
            complete=status_port["open"] and len(list((HARNESS / "reports").glob("*.mmd"))) > 0,
            evidence={"viewer": "http://127.0.0.1:8765/mermaid", "mmd_count": len(list((HARNESS / "reports").glob("*.mmd"))), "status_port": status_port},
        ),
        result(
            "openai/symphony",
            "https://github.com/openai/symphony",
            "Adopted SPEC patterns (WORKFLOW, isolated workspace, hooks, scheduler events) as local dry-run sidecar — coordinator/tmux is the real executor; Symphony does not run builders.",
            installed=(HARNESS / "lib" / "symphony").exists(),
            configured=(HARNESS / "lib" / "symphony" / "workflow-loader.py").exists(),
            running=False,
            indexed=(HARNESS / "state" / "symphony").exists(),
            used_by_default=False,
            basic_available=True,
            complete=True,
            degraded_reason="",
            evidence={
                "lib": str(HARNESS / "lib" / "symphony"),
                "mode": "dry_run_sidecar",
                "executes_builders": False,
            },
        ),
        result(
            "strukto-ai/mirage",
            "https://github.com/strukto-ai/mirage",
            "Solar logical VFS wrapper over Knowledge, Raw, Sprints, Solar DB, QMD. SDK/FUSE decision ADR filed: wrapper_only (SIP blocks macFUSE, reboot required). Drive is logical mount requiring credentials.",
            installed=(HARNESS / "lib" / "solar_mirage.py").exists(),
            configured=(HARNESS / "config" / "mirage.solar.yaml").exists(),
            running=True,
            indexed=(qmd["total"] or 0) > 0 and SOLAR_DB.exists(),
            used_by_default=True,
            complete=True,
            degraded_reason="",
            dead_ends=[],
            evidence={
                "wrapper": str(HARNESS / "lib" / "solar_mirage.py"),
                "sdk": {
                    "kind": "solar-logical",
                    "mode": "wrapper_only",
                },
                "sdk_decision": "wrapper_only",
                "sdk_decision_doc": str(HOME / ".solar" / "reports" / "mirage-sdk-fuse-decision-2026-05-09.md"),
                "drive": {
                    "state": "local_mount" if gdrive_local["ok"] else "credentials_missing",
                    "local_root": gdrive_local["path"],
                    "unblock_env_var": "GOOGLE_DRIVE_REFRESH_TOKEN",
                    "ui_path": "/integrations#drive",
                },
                "doctor_cmd": "solar-harness mirage doctor --json",
                "last_check": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        ),
        result(
            "gstack",
            "https://github.com/graydotdev/gstack",
            "Solar browser/QA/review workflow skills installed under ~/.claude/skills/gstack. Used by Solar rules for browse, qa, review, investigate, ship and visual testing flows.",
            installed=(HOME / ".claude" / "skills" / "gstack" / "SKILL.md").exists(),
            configured=(HOME / ".claude" / "skills" / "gstack" / "bin").exists(),
            running=True,
            indexed=True,
            used_by_default=True,
            complete=(HOME / ".claude" / "skills" / "gstack" / "SKILL.md").exists(),
            evidence={
                "skill": str(HOME / ".claude" / "skills" / "gstack" / "SKILL.md"),
                "solar_rule": str(HOME / "Solar" / "CLAUDE.md"),
                "commands": ["/browse", "/qa", "/review", "/investigate", "/ship"],
            },
        ),
        result(
            "Superpowers",
            "openai-curated/superpowers",
            "Codex and multi-agent skill framework. Installed as Codex plugin plus using-superpowers skills for Claude/agents.",
            installed=(HOME / ".codex" / "plugins" / "cache" / "openai-curated" / "superpowers").exists()
            or (HOME / ".agents" / "skills" / "using-superpowers" / "SKILL.md").exists(),
            configured=(HOME / ".codex" / "config.toml").exists()
            and "superpowers@openai-curated" in (HOME / ".codex" / "config.toml").read_text(errors="ignore"),
            running=True,
            indexed=True,
            used_by_default=True,
            complete=True,
            evidence={
                "codex_plugin": str(HOME / ".codex" / "plugins" / "cache" / "openai-curated" / "superpowers"),
                "agents_skill": str(HOME / ".agents" / "skills" / "using-superpowers" / "SKILL.md"),
                "codex_config": str(HOME / ".codex" / "config.toml"),
            },
        ),
        result(
            "Empirical Research skills",
            "https://github.com/brycewang-stanford/Awesome-Agent-Skills-for-Empirical-Research",
            "Empirical research pipeline registered as Solar dispatch capability for literature review, causal/statistical analysis, reproducibility and academic paper workflows.",
            lifecycle="active",
            installed=empirical_skill.exists(),
            configured=empirical_gap.exists(),
            running=True,
            indexed=True,
            used_by_default=True,
            complete=empirical_skill.exists(),
            degraded_reason="" if empirical_skill.exists() else "empirical-pipeline skill missing",
            evidence={
                "skill": str(empirical_skill),
                "gap_analysis": str(empirical_gap),
                "dispatch_capability": "research.empirical_pipeline",
            },
        ),
        result(
            "addyosmani/agent-skills",
            "https://github.com/addyosmani/agent-skills",
            "Agent skills marketplace installed locally. Solar consumes it as a read-only workflow and specialist-routing catalog through capability injection.",
            lifecycle="active",
            installed=addy_root.exists(),
            configured=addy_agents_count > 0 and addy_refs_count > 0,
            running=True,
            indexed=True,
            used_by_default=True,
            complete=addy_root.exists() and addy_agents_count > 0 and addy_refs_count > 0,
            degraded_reason="" if (addy_root.exists() and addy_agents_count > 0 and addy_refs_count > 0) else "agent-skills marketplace incomplete",
            evidence={
                "root": str(addy_root),
                "agents_count": addy_agents_count,
                "skills_count": addy_skills_count,
                "references_count": addy_refs_count,
                "dispatch_capability": "agent_skills.catalog",
            },
        ),
        result(
            "ATLAS repair protocol",
            "Solar local rules",
            "ATLAS-derived repair protocol and PR-CoT failure-repair rules absorbed into Solar rules. Provides structured repair behavior for hook/tool failures.",
            installed=(HOME / "Solar" / "rules" / "atlas-repair-protocol.md").exists()
            or (HOME / ".claude" / "rules" / "atlas-repair-protocol.md").exists(),
            configured=(HOME / ".solar" / "plans" / "atlas-solar-integration.md").exists(),
            running=True,
            indexed=True,
            used_by_default=True,
            complete=True,
            evidence={
                "solar_rule": str(HOME / "Solar" / "rules" / "atlas-repair-protocol.md"),
                "claude_rule": str(HOME / ".claude" / "rules" / "atlas-repair-protocol.md"),
                "plan": str(HOME / ".solar" / "plans" / "atlas-solar-integration.md"),
            },
        ),
        result(
            "Browser-use MCP",
            "https://github.com/browser-use/browser-use",
            "Local browser-use MCP server and Codex Browser Use plugin. Registered for browser.mcp/browser.automation dispatches; gstack remains the broader browser QA fallback.",
            lifecycle="active",
            installed=browser_use_server.exists() or browser_use_codex.exists(),
            configured=browser_use_python.exists() and browser_use_server.exists(),
            running=True,
            indexed=True,
            used_by_default="browser-use@openai-bundled" in codex_config_text,
            complete=browser_use_python.exists() and browser_use_server.exists() and browser_use_codex.exists(),
            degraded_reason="" if (browser_use_python.exists() and browser_use_server.exists() and browser_use_codex.exists()) else "browser-use local MCP/plugin incomplete",
            evidence={
                "mcp_server": str(browser_use_server),
                "venv_python": str(browser_use_python),
                "codex_plugin": str(browser_use_codex),
                "codex_config": str(codex_config),
                "dispatch_capability": "browser.mcp",
            },
        ),
        result(
            "camel-ai/owl",
            "https://github.com/camel-ai/owl",
            "External multi-agent/browser execution framework installed locally. Registered as a Solar capability provider for multi-agent research/browser experimentation; not the default coordinator.",
            lifecycle="active",
            installed=(HOME / ".solar" / "owl").exists(),
            configured=(HOME / ".solar" / "owl" / "pyproject.toml").exists(),
            running=(HOME / ".solar" / "owl" / ".owl-service.pid").exists(),
            indexed=True,
            used_by_default=False,
            complete=True,
            degraded_reason="",
            evidence={
                "repo": str(HOME / ".solar" / "owl"),
                "venv": str(HOME / ".solar" / "owl" / "venv"),
                "service_pid_file": str(HOME / ".solar" / "owl" / ".owl-service.pid"),
                "connection_status": "active_capability_provider_not_default_coordinator",
            },
        ),
        result(
            "openai-agents-python PoC",
            "https://github.com/openai/openai-agents-python",
            "Design-level PoC for future typed runtime/guardrails/tracing/handoff migration. Explicitly not the current Solar production executor.",
            lifecycle="candidate",
            candidate=True,
            installed=openai_agents_report.exists(),
            configured=openai_agents_report.exists(),
            running=False,
            indexed=True,
            used_by_default=False,
            basic_available=openai_agents_report.exists(),
            complete=False,
            degraded_reason="",
            evidence={
                "report": str(openai_agents_report),
                "mode": "design_poc_not_production_runtime",
                "dispatch_capability": "agents_sdk.design",
            },
        ),
        result(
            "Microsoft MarkItDown MCP",
            "https://github.com/microsoft/markitdown",
            "Document conversion provider for PDF/Office/HTML/image-to-Markdown. Solar dispatch injects MarkItDown for document extraction; MCP runtime is optional and detected separately.",
            lifecycle="active",
            installed=markitdown_skill.exists() or markitdown_claude_skill.exists() or markitdown_owl_toolkit.exists(),
            configured=markitdown_script.exists() or markitdown_owl_toolkit.exists(),
            running=True,
            indexed=True,
            used_by_default=True,
            complete=markitdown_skill.exists() and (markitdown_script.exists() or markitdown_owl_toolkit.exists()),
            degraded_reason="" if (markitdown_skill.exists() and (markitdown_script.exists() or markitdown_owl_toolkit.exists())) else "MarkItDown skill or conversion script/toolkit missing",
            evidence={
                "agents_skill": str(markitdown_skill),
                "claude_skill": str(markitdown_claude_skill),
                "batch_convert": str(markitdown_script),
                "owl_toolkit": str(markitdown_owl_toolkit),
                "dispatch_capability": "document.convert",
                "mcp_runtime": "optional_not_required_for_solar_dispatch",
            },
        ),
        result(
            "Codex Bridge / pane3 bridge",
            "Solar local bridge",
            "Active bridge path is ~/.solar/codex-bridge/from-codex plus chain-watcher ingestion. Legacy ~/.solar/harness/codex-bridge is deprecated and not counted as the active runtime.",
            lifecycle="active",
            installed=codex_bridge_root.exists() and chain_watcher.exists(),
            configured=codex_bridge_inbox.exists() and codex_bridge_protocol.exists(),
            running=True,
            indexed=bridge_ledger.exists(),
            used_by_default=True,
            complete=codex_bridge_inbox.exists() and codex_bridge_protocol.exists() and chain_watcher.exists(),
            degraded_reason="" if (codex_bridge_inbox.exists() and codex_bridge_protocol.exists() and chain_watcher.exists()) else "active codex bridge chain missing",
            evidence={
                "active_root": str(codex_bridge_root),
                "from_codex": str(codex_bridge_inbox),
                "protocol": str(codex_bridge_protocol),
                "chain_watcher": str(chain_watcher),
                "ledger": str(bridge_ledger),
                "legacy_harness_bridge": str(HARNESS / "codex-bridge"),
                "dispatch_capability": "codex.bridge",
            },
        ),
        result(
            "agency-agents persona",
            "local Claude agents + addy-agent-skills",
            "Specialist persona/agent catalog used as Solar routing context. Provides role hints for PM/planner/builder/evaluator without replacing the Harness pane model.",
            lifecycle="active",
            installed=claude_agents_dir.exists() or addy_agents_dir.exists(),
            configured=(claude_agents_count + addy_agents_count) > 0,
            running=True,
            indexed=True,
            used_by_default=True,
            complete=(claude_agents_count + addy_agents_count) > 0,
            degraded_reason="" if (claude_agents_count + addy_agents_count) > 0 else "no agent catalog markdown files found",
            evidence={
                "claude_agents_dir": str(claude_agents_dir),
                "claude_agents_count": claude_agents_count,
                "addy_agents_dir": str(addy_agents_dir),
                "addy_agents_count": addy_agents_count,
                "dispatch_capability": "persona.agent",
            },
        ),
        result(
            "Google Drive mount",
            "external service",
            "Optional Mirage /drive data source. Uses local macOS Google Drive File Provider when installed; service-account credentials are only needed for headless/API mode.",
            lifecycle="optional",
            optional=True,
            installed=True,
            configured=gdrive_local["ok"] or bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
            running=gdrive_local["ok"],
            indexed=gdrive_local["ok"],
            used_by_default=False,
            basic_available=True,
            complete=gdrive_local["ok"],
            degraded_reason="" if gdrive_local["ok"] else "Google Drive local mount not found and GOOGLE_APPLICATION_CREDENTIALS not configured",
            evidence={
                "credential_env": "GOOGLE_APPLICATION_CREDENTIALS",
                "state": "local_mount" if gdrive_local["ok"] else "logical_mount",
                "local_root": gdrive_local["path"],
                "local_source": gdrive_local["source"],
            },
        ),
        result(
            "affaan-m/everything-claude-code",
            "https://github.com/affaan-m/everything-claude-code",
            "Claude Code agents, commands, skills, hooks, rules, MCP configs, contexts, scripts, and tests. Registered as a Solar capability provider in safe read-only/vendor mode.",
            lifecycle="active",
            installed=(HARNESS / "vendor" / "everything-claude-code").exists(),
            configured=(HARNESS / "vendor" / "everything-claude-code" / "agent.yaml").exists(),
            running=False,
            indexed=(HARNESS / "reports" / "everything-claude-code-audit-20260508.md").exists(),
            used_by_default=False,
            complete=True,
            degraded_reason="",
            evidence={
                "canonical_source": "https://github.com/affaan-m/everything-claude-code",
                "mirror_or_fork_seen": "https://github.com/WorldFlowAI/everything-claude-code",
                "contract": str(HARNESS / "sprints" / "sprint-20260508-everything-claude-code-integration.contract.md"),
                "mode": "safe_read_only_vendor_provider",
                "related_systems": {
                    "gstack": str(HOME / "Solar" / "CLAUDE.md"),
                    "superpowers": str(HOME / ".codex" / "config.toml"),
                },
            },
        ),
        result(
            "ciembor/agent-rules-books",
            "https://github.com/ciembor/agent-rules-books",
            "MIT rule/skill catalog distilled from classic software engineering books. Solar uses it as a safe read-only book-rules provider: mini for task-specific pressure, full as retrieval/reference.",
            lifecycle="active",
            installed=arb_vendor.exists(),
            configured=(arb_status.get("counts", {}) or {}).get("mini", 0) >= 10,
            running=True,
            indexed=arb_report.exists(),
            used_by_default=False,
            complete=bool(arb_status.get("ok")),
            degraded_reason="" if arb_status.get("ok") else "agent-rules-books vendor/report incomplete; run solar-harness agent-rules-books vendor && report",
            evidence={
                "vendor": str(arb_vendor),
                "report": str(HARNESS / "reports" / "agent-rules-books-inventory.md"),
                "counts": arb_status.get("counts", {}),
                "mode": "safe_read_only_vendor_provider",
                "default_version": "mini",
                "dispatch_capability": "rules.book_catalog",
            },
        ),
        result(
            "smallnest/autoresearch",
            "https://github.com/smallnest/autoresearch",
            "Pane-level execution optimizer plus external issue-to-implementation loop for local/GitHub issues, multi-agent iterations and score-gated fixes. Solar exposes it as advisor/dry-run by default; it improves pane output quality but does not replace Builder, and execution requires --execute.",
            lifecycle="active",
            installed=autoresearch_vendor.exists(),
            configured=bool((autoresearch_status.get("interface", {}) or {}).get("run_sh_exists")),
            running=False,
            indexed=True,
            used_by_default=False,
            complete=bool(autoresearch_status.get("ok")),
            degraded_reason="" if autoresearch_status.get("ok") else "autoresearch not vendored or run.sh missing; run solar-harness integrations autoresearch-vendor --json",
            dead_ends=[],
            evidence={
                "vendor": str(autoresearch_vendor),
                "source_commit": (autoresearch_status.get("source", {}) or {}).get("commit", ""),
                "mode": autoresearch_status.get("mode", "pane_optimizer_advisor_and_explicit_local_issue_runner"),
                "interface": autoresearch_status.get("interface", {}),
                "dispatch_capability": "autoresearch.pane_optimizer",
                "issue_loop_capability": "autoresearch.issue_loop",
                "dry_run_cmd": "solar-harness integrations autoresearch-run-local --project <repo> --issue-title <title> --issue-body <body> --json",
                "execute_requires": "--execute",
            },
        ),
        result(
            "Solar Meta-Harness",
            "local ~/.claude/core/solar-farm/meta-harness.ts",
            "Harness-level outer-loop optimizer for Solar rules, hooks, skills, config and personality knobs. Solar exposes it as a controlled dry-run-first capability provider; it is not coordinator autorun and real run/apply requires --execute.",
            lifecycle="active",
            installed=bool((meta_harness_status.get("tool", {}) or {}).get("exists")),
            configured=(meta_harness_status.get("store", {}) or {}).get("evaluation_count", 0) > 0,
            running=False,
            indexed=bool((meta_harness_status.get("pareto", {}) or {}).get("exists")),
            used_by_default=False,
            complete=bool(meta_harness_status.get("ok")),
            degraded_reason="" if meta_harness_status.get("ok") else "meta-harness tool/store incomplete; run solar-harness meta-harness doctor --json",
            dead_ends=[],
            evidence={
                "tool": (meta_harness_status.get("tool", {}) or {}).get("path", ""),
                "store": (meta_harness_status.get("store", {}) or {}).get("path", ""),
                "evaluation_count": (meta_harness_status.get("store", {}) or {}).get("evaluation_count", 0),
                "pareto_count": (meta_harness_status.get("pareto", {}) or {}).get("pareto_count", 0),
                "all_runs_count": (meta_harness_status.get("pareto", {}) or {}).get("all_runs_count", 0),
                "dispatch_capability": "meta_harness.outer_loop",
                "self_optimization_capability": "meta_harness.self_optimization",
                "dry_run_cmd": "solar-harness meta-harness run 3 hooks --json",
                "apply_dry_run_cmd": "solar-harness meta-harness apply <run_id> --json",
                "execute_requires": "--execute",
                "coordinator_autorun": False,
            },
        ),
        result(
            "ruflo / Claude Flow",
            "https://github.com/ruvnet/ruflo",
            "Sandboxed Ruflo / Claude Flow runtime provider for swarm orchestration, agent catalog, memory, workflow templates and MCP command surface. Host-level ruflo init remains gated; Solar uses the managed sandbox runtime.",
            lifecycle="active",
            installed=ruflo_vendor.exists(),
            configured=bool(ruflo_runtime.get("cli_exists")),
            running=ruflo_runtime_ok,
            indexed=(ruflo_status.get("inventory", {}) or {}).get("skill_files", 0) > 0,
            used_by_default=True,
            complete=ruflo_runtime_ok,
            degraded_reason="" if ruflo_runtime_ok else "Ruflo sandbox runtime not smoked; run solar-harness integrations ruflo-runtime-smoke --json",
            dead_ends=[] if ruflo_runtime_ok else ["ruflo_runtime_not_smoked"],
            evidence={
                "vendor": str(ruflo_vendor),
                "source_commit": (ruflo_status.get("source", {}) or {}).get("commit", ""),
                "runtime_backend": ruflo_runtime.get("backend", ""),
                "runtime_level": ruflo_runtime.get("integration_level", ""),
                "runtime_package": ruflo_runtime.get("runtime_package", ""),
                "runtime_version": (ruflo_runtime.get("published_package", {}) or {}).get("version", ""),
                "published_cli": str(ruflo_cli),
                "evidence": ruflo_runtime.get("evidence", ""),
                "dispatch_capability": "ruflo.swarm",
            },
        ),
    ]

    summary = {
        "ok": sum(1 for x in integrations if x["status"] == "ok"),
        "warn": sum(1 for x in integrations if x["status"] == "warn"),
        "error": sum(1 for x in integrations if x["status"] == "error"),
        "missing": sum(1 for x in integrations if x["status"] == "missing"),
        "total": len(integrations),
        "dead_ends": sum(1 for x in integrations if x.get("dead_ends")),
        "optional": sum(1 for x in integrations if x.get("optional")),
        "candidate": sum(1 for x in integrations if x.get("candidate")),
    }
    levels = {level: 0 for level in ("dead_end", "basic_usable", "default_usable", "closed_loop")}
    for item in integrations:
        label = item.get("status_label", "dead_end")
        if label in levels:
            levels[label] += 1
    summary["integration_levels"] = levels
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "summary": summary, "integrations": integrations}


def text_report(data: dict) -> str:
    rows = []
    for x in data["integrations"]:
        rows.append(
            f"{x['status']:7} {x['name']:<38} installed={int(x['installed'])} configured={int(x['configured'])} "
            f"running={int(x['running'])} indexed={int(x['indexed'])} default={int(x['used_by_default'])} "
            f"{x['degraded_reason']}"
        )
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="ignore cache and run all probes")
    ap.add_argument("--deep", action="store_true", help="run slower historical upload audits")
    ap.add_argument("--max-age", type=int, default=120, help="cache max age in seconds")
    args = ap.parse_args()
    data = None
    if not args.refresh and CACHE_PATH.exists():
        try:
            cached = json.loads(CACHE_PATH.read_text())
            age = time.time() - float(cached.get("_cached_at", 0))
            if age <= args.max_age:
                data = cached
                data["_cache"] = {"hit": True, "age_sec": round(age, 1), "path": str(CACHE_PATH)}
        except Exception:
            data = None
    if data is None:
        data = probe(deep=args.deep)
        data["_cached_at"] = time.time()
        data["_cache"] = {"hit": False, "path": str(CACHE_PATH)}
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except OSError:
            pass
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(text_report(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
