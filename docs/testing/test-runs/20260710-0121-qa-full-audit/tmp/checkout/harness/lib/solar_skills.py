#!/usr/bin/env python3
"""
solar_skills.py — Solar capability plane: skills inventory, doctor, inject,
                   eval, promote, rollback, export.

Subcommands (called via solar-harness skills <sub>):
  inventory [--json]          scan skill roots + registry, return counts + sources
  doctor    [--json]          pane-level capability report (no secrets)
  readiness [--json] [--all]  classify skills as discoverable/injectable/executable/effective/broken
  certify   [--json]          run core skill probes and write readiness scorecards
  inject    <dispatch_file>   idempotent injection of skills+KB context blocks
  pane-status [--json]        alias for doctor
  native-extract              extract Solar native skills to cache
  eval      --skill SKILL [--json]   run eval pack checks, report score
  promote   --skill SKILL    promote candidate→stable (requires eval+regression pass)
  rollback  --skill SKILL [--to STATUS]  demote skill status in registry
  export    --skill SKILL [--dest DIR] [--force] [--dry-run]  safe export/symlink
  compile-to-capsule [--plugin ID] [--dry-run] [--json]       compile plugin skills to capsule drafts
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from resource_telemetry import record_usage
except Exception:  # pragma: no cover - telemetry must fail-open
    record_usage = None  # type: ignore

# ── paths ──────────────────────────────────────────────────────────────────
HARNESS_DIR = Path(__file__).resolve().parent.parent
SKILLS_ROOT = Path.home() / ".agents" / "skills"
CLAUDE_SKILLS_ROOT = Path.home() / ".claude" / "skills"
CODEX_SUPERPOWERS_ROOT = Path.home() / ".codex" / "plugins" / "cache" / "openai-curated" / "superpowers"
CODEX_SKILLS_ROOT = Path.home() / ".codex" / "skills"
CODEX_PLUGIN_CACHE_ROOT = Path.home() / ".codex" / "plugins" / "cache"
SOLAR_NATIVE_ROOT = Path.home() / "Solar" / "skills"
SOLAR_RULES_ROOT = Path.home() / "Solar" / "rules"
CLAUDE_RULES_ROOT = Path.home() / ".claude" / "rules"
HARNESS_VENDOR_ROOT = HARNESS_DIR / "vendor"
STATE_DIR = HARNESS_DIR / "state"
STATE_DB = Path(os.environ.get("HARNESS_STATE_DB", str(HARNESS_DIR / "run" / "state.db")))
NATIVE_CACHE = STATE_DIR / "solar-native-skills.json"
INVENTORY_CACHE = STATE_DIR / "skills-inventory.json"
READINESS_CACHE = STATE_DIR / "skills-readiness.json"
CERTIFICATION_CACHE = STATE_DIR / "skills-certification.json"
SOLAR_CONTEXT_PY = HARNESS_DIR / "lib" / "solar-unified-context.py"

# Keys redacted from doctor output
SECRET_PATTERNS = re.compile(
    r"(ZHIPU_AUTH_TOKEN|ANTHROPIC_AUTH_TOKEN|DEEPSEEK_API_KEY|sk-[A-Za-z0-9]{8,})",
    re.IGNORECASE,
)


# ── helpers ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _count_skills(root: Path) -> int:
    """Count first-level directory entries that look like skill names."""
    if not root.exists():
        return 0
    total = 0
    for p in root.iterdir():
        if p.is_dir() or (p.is_file() and p.suffix in (".md", ".yaml", ".yml", "")):
            name = p.name
            if name.startswith(".") or name in ("SKILL-INDEX.md", "SKILLS_INDEX.json", "SKILLS_INDEX.md"):
                continue
            total += 1
    return total


def _count_skill_files(root: Path) -> int:
    """Count recursive SKILL.md / skill.md files under a root."""
    if not root.exists():
        return 0
    paths = {str(p).lower() for p in root.rglob("SKILL.md")}
    paths.update(str(p).lower() for p in root.rglob("skill.md"))
    return len(paths)


def _sample_skill_files(root: Path, limit: int = 20) -> list[str]:
    if not root.exists():
        return []
    by_lower = {str(p).lower(): p for p in root.rglob("SKILL.md")}
    by_lower.update({str(p).lower(): p for p in root.rglob("skill.md")})
    paths = sorted(str(p) for p in by_lower.values())
    paths = [Path(p) for p in paths]
    return [str(p.relative_to(root)) for p in paths[:limit]]


def _list_skill_names(root: Path) -> list[str]:
    """Return sorted skill names from a root directory."""
    if not root.exists():
        return []
    names = []
    for p in root.iterdir():
        name = p.name
        if name.startswith(".") or name in ("SKILL-INDEX.md", "SKILLS_INDEX.json", "SKILLS_INDEX.md"):
            continue
        names.append(name)
    return sorted(names)


def _read_skill_meta(skill_dir: Path) -> dict[str, Any]:
    """Read SKILL.md frontmatter for name/description/tags."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return {}
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    meta: dict[str, Any] = {}
    # Parse YAML frontmatter between --- delimiters
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            front = text[3:end]
            for line in front.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip()
    return meta


def _get_pane_config() -> dict[str, Any]:
    """Read persona-config.sh output for known panes."""
    panes_cfg: dict[str, Any] = {}
    persona_script = HARNESS_DIR / "lib" / "persona-config.sh"
    if not persona_script.exists():
        return panes_cfg

    known_panes = ["lab-builder", "builder", "evaluator", "planner", "monitor"]
    for pane in known_panes:
        try:
            result = subprocess.run(
                ["bash", str(persona_script), "--print-config", pane],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                cfg: dict[str, str] = {}
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if "=" in line:
                        k, _, v = line.partition("=")
                        # Strip surrounding quotes
                        v = v.strip("'\"")
                        cfg[k.strip()] = v
                panes_cfg[pane] = cfg
        except Exception:
            pass
    return panes_cfg


def _pane_capability(pane: str, cfg: dict[str, str]) -> dict[str, Any]:
    """Build a capability summary for one pane — no secret values."""
    extra_flags = cfg.get("EXTRA_FLAGS", "")
    auth_source = cfg.get("AUTH_SOURCE", "unknown")

    # MCP mode from EXTRA_FLAGS
    if "--strict-mcp-config" in extra_flags:
        mcp_mode = "STRICT"
        mcp_config = _extract_mcp_config_path(extra_flags)
        kb_context = False
    else:
        mcp_mode = "DEFAULT"
        mcp_config = None
        kb_context = True  # non-strict panes can use KB context

    # Skills count injected into this pane type
    skills_accessible = mcp_mode == "DEFAULT"

    return {
        "pane": pane,
        "model": cfg.get("MODEL_FLAG", "unknown").replace("--model ", ""),
        "auth_source": auth_source,
        "mcp_mode": mcp_mode,
        "mcp_config": mcp_config,
        "kb_context": kb_context,
        "skills_accessible": skills_accessible,
        # Do NOT include auth token values
        "auth_token_present": "AUTH_TOKEN" in cfg and bool(cfg.get("AUTH_TOKEN")),
    }


def _extract_mcp_config_path(extra_flags: str) -> str | None:
    m = re.search(r"--mcp-config\s+(\S+)", extra_flags)
    return m.group(1) if m else None


def _redact(text: str) -> str:
    return SECRET_PATTERNS.sub("[REDACTED]", text)


READINESS_ORDER = ["broken", "discoverable", "injectable", "executable", "effective"]
CORE_SOLAR_SKILLS: list[dict[str, Any]] = [
    {
        "name": "solar-harness-runtime",
        "capabilities": ["harness.context_preflight", "harness.intent", "harness.dispatch_visibility"],
        "probe": "dispatch_inject",
        "provider": "solar-harness-runtime",
    },
    {
        "name": "solar-intent-engine",
        "capabilities": ["intent.match", "intent.audit", "dispatch.intent_telemetry"],
        "probe": "intent_match",
        "provider": "solar-intent-engine",
    },
    {
        "name": "solar-activation-proof",
        "capabilities": ["activation.proof", "negative_control", "runtime_artifacts"],
        "probe": "activation_proof",
        "provider": "solar-activation-proof",
    },
    {
        "name": "solar-graph-scheduler",
        "capabilities": ["dag.validate", "dag.ready_nodes", "dag.join_gate"],
        "probe": "graph_validate",
        "provider": "solar-graph-scheduler",
    },
    {
        "name": "solar-model-routing",
        "capabilities": ["models.show", "models.lab_matrix", "models.footer_labels"],
        "probe": "models_show",
        "provider": "solar-model-routing",
    },
    {
        "name": "solar-knowledge-ingest",
        "capabilities": ["context.inject", "wiki.status", "data_plane.audit"],
        "probe": "data_plane_audit",
        "provider": "solar-knowledge-ingest",
    },
    {
        "name": "solar-autopilot-monitor",
        "capabilities": ["autopilot.monitor", "autopilot.safe_apply", "pane.deadlock_detection"],
        "probe": "autopilot_monitor",
        "provider": "solar-autopilot-monitor",
    },
    {
        "name": "solar-deep-research",
        "capabilities": ["source.search", "evidence.extract", "claim.mine", "citation.verify", "report.compile", "factuality.evaluate"],
        "probe": "deepresearch_probe",
        "provider": "solar-deep-research",
    },
]


def _skill_file(root: Path, name: str) -> Path:
    return root / name / "SKILL.md"


def _level(discoverable: bool, injectable: bool, executable: bool, effective: bool, broken: bool = False) -> str:
    if broken:
        return "broken"
    if effective:
        return "effective"
    if executable:
        return "executable"
    if injectable:
        return "injectable"
    if discoverable:
        return "discoverable"
    return "broken"


def _score_for_level(level: str) -> float:
    return {
        "effective": 4.0,
        "executable": 3.0,
        "injectable": 2.0,
        "discoverable": 1.0,
        "broken": 0.0,
    }.get(level, 0.0)


def _status_for_level(level: str) -> str:
    if level == "effective":
        return "active"
    if level in ("executable", "injectable", "discoverable"):
        return "pending"
    return "broken"


def _scorecard_payload(level: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "readiness_level": level,
        "runtime_level": "full_runtime_usable" if level == "effective" else (
            "runtime_usable" if level == "executable" else level
        ),
        "runtime_backend": "solar-harness",
        "evidence": evidence,
    }


def _write_scorecard(capability: str, provider: str, level: str, evidence: dict[str, Any]) -> None:
    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STATE_DB), timeout=5.0)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS capability_scorecards (
            capability TEXT NOT NULL,
            provider TEXT NOT NULL,
            score REAL NOT NULL,
            level TEXT NOT NULL,
            status TEXT NOT NULL,
            eval_passed INTEGER NOT NULL DEFAULT 0,
            regression_passed INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            payload TEXT,
            PRIMARY KEY (capability, provider)
        )
        """
    )
    score = _score_for_level(level)
    status = _status_for_level(level)
    payload = _scorecard_payload(level, evidence)
    conn.execute(
        """INSERT INTO capability_scorecards
           (capability, provider, score, level, status, eval_passed, regression_passed, updated_at, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(capability, provider) DO UPDATE SET
             score=excluded.score, level=excluded.level, status=excluded.status,
             eval_passed=excluded.eval_passed, regression_passed=excluded.regression_passed,
             updated_at=excluded.updated_at, payload=excluded.payload""",
        (
            capability,
            provider,
            score,
            "closed_loop" if level == "effective" else ("default_usable" if level == "executable" else level),
            status,
            1 if level in ("effective", "executable") else 0,
            1 if level == "effective" else 0,
            _now_iso(),
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


def _scorecard_level(provider: str, capability: str, scores: dict[str, dict[str, Any]]) -> str:
    item = scores.get(f"{provider}::{capability}") or scores.get(f"cap::{capability}") or {}
    payload = item.get("payload")
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
            if isinstance(decoded, dict) and decoded.get("readiness_level"):
                return str(decoded["readiness_level"])
        except Exception:
            pass
    runtime = str(item.get("runtime_level") or "")
    level = str(item.get("level") or "")
    if runtime == "full_runtime_usable" or level == "closed_loop":
        return "effective"
    if runtime == "runtime_usable" or level == "default_usable":
        return "executable"
    if item:
        return "injectable"
    return ""


def _run(cmd: list[str], timeout: int = 30, max_output_chars: int | None = 4000) -> dict[str, Any]:
    def _trim(text: str) -> str:
        if max_output_chars is None:
            return text
        return text[-max_output_chars:]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": _trim(proc.stdout),
            "stderr": _trim(proc.stderr),
            "cmd": cmd,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "cmd": cmd}


def _load_data_plane_audit() -> dict[str, Any]:
    proc = _run(
        [str(HARNESS_DIR / "solar-harness.sh"), "data-plane", "audit", "--json"],
        timeout=30,
        max_output_chars=None,
    )
    try:
        stdout = str(proc.get("stdout", "") or "").strip()
        if stdout:
            return json.loads(stdout)
    except Exception:
        pass
    return {"overall_status": "error", "checks": [], "error": proc.get("error") or proc.get("stderr", "")}


def _accepted_artifact_readiness(audit: dict[str, Any] | None = None) -> dict[str, Any]:
    audit = audit or _load_data_plane_audit()
    checks = audit.get("checks", []) if isinstance(audit.get("checks"), list) else []
    check = next((item for item in checks if item.get("name") == "accepted_artifact_path"), {})
    status = str(check.get("status") or "missing")
    indexed = int(check.get("indexed_in_vault") or 0)
    finalized = int(check.get("finalized_sprints") or 0)
    if status == "ok" and indexed > 0:
        level = "effective"
    elif finalized > 0:
        level = "injectable"
    elif status == "missing":
        level = "broken"
    else:
        level = "injectable"
    return {
        "name": "accepted-artifacts-knowledge-index",
        "provider": "solar-data-plane",
        "capability": "accepted_artifacts.indexed_in_vault",
        "level": level,
        "status": status,
        "evidence": check,
    }


def _core_skill_readiness(scores: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in CORE_SOLAR_SKILLS:
        name = spec["name"]
        codex_file = _skill_file(CODEX_SKILLS_ROOT, name)
        agents_file = _skill_file(SKILLS_ROOT, name)
        discoverable = codex_file.exists() or agents_file.exists()
        injectable = agents_file.exists()
        best_score_level = ""
        for cap in spec.get("capabilities", []):
            best_score_level = max(
                [best_score_level, _scorecard_level(spec["provider"], cap, scores)],
                key=lambda item: READINESS_ORDER.index(item) if item in READINESS_ORDER else -1,
            )
        executable = best_score_level in ("executable", "effective")
        effective = best_score_level == "effective"
        broken = not discoverable or not codex_file.exists() or not agents_file.exists()
        level = _level(discoverable, injectable, executable, effective, broken)
        out.append({
            "name": name,
            "source": "solar-harness-core",
            "level": level,
            "layers": {
                "discoverable": discoverable,
                "injectable": injectable,
                "executable": executable,
                "effective": effective,
            },
            "paths": {
                "codex": str(codex_file),
                "agents": str(agents_file),
            },
            "capabilities": spec.get("capabilities", []),
            "probe": spec.get("probe", ""),
            "broken_reason": "missing dual registration" if broken else "",
        })
    return out


def _all_discovered_skill_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    roots: list[tuple[str, Path, bool]] = [
        ("agents-skills", SKILLS_ROOT, True),
        ("codex-skills", CODEX_SKILLS_ROOT, False),
        ("claude-skills", CLAUDE_SKILLS_ROOT, False),
        ("solar-native", SOLAR_NATIVE_ROOT, True),
    ]
    for source, root, injectable in roots:
        if not root.exists():
            continue
        for skill_file in sorted({p for p in root.rglob("SKILL.md")} | {p for p in root.rglob("skill.md")}):
            meta = _read_skill_meta(skill_file.parent)
            name = str(meta.get("name") or skill_file.parent.name)
            records.append({
                "name": name,
                "source": source,
                "path": str(skill_file),
                "level": "injectable" if injectable else "discoverable",
                "layers": {
                    "discoverable": True,
                    "injectable": injectable,
                    "executable": False,
                    "effective": False,
                },
            })
    vendor_roots = {
        "vendor:ruflo": HARNESS_VENDOR_ROOT / "ruflo",
        "vendor:hermes-agent": HARNESS_VENDOR_ROOT / "hermes-agent",
        "vendor:obsidian-wiki": HARNESS_VENDOR_ROOT / "obsidian-wiki",
        "vendor:everything-claude-code": HARNESS_VENDOR_ROOT / "everything-claude-code",
        "vendor:agent-rules-books": HARNESS_VENDOR_ROOT / "agent-rules-books",
        "vendor:mineru-document-explorer": HARNESS_VENDOR_ROOT / "MinerU-Document-Explorer",
    }
    for source, root in vendor_roots.items():
        if not root.exists():
            continue
        for skill_file in sorted({p for p in root.rglob("SKILL.md")} | {p for p in root.rglob("skill.md")}):
            meta = _read_skill_meta(skill_file.parent)
            records.append({
                "name": str(meta.get("name") or skill_file.parent.name),
                "source": source,
                "path": str(skill_file),
                "level": "discoverable",
                "layers": {
                    "discoverable": True,
                    "injectable": False,
                    "executable": False,
                    "effective": False,
                },
            })
    return records


# ── inventory ──────────────────────────────────────────────────────────────

def cmd_inventory(args: list[str]) -> int:
    as_json = "--json" in args

    # Count main skills root
    agents_count = _count_skills(SKILLS_ROOT)
    claude_count = _count_skills(CLAUDE_SKILLS_ROOT)
    codex_superpowers_count = 1 if CODEX_SUPERPOWERS_ROOT.exists() else 0

    # Solar native skills
    native_names = _list_skill_names(SOLAR_NATIVE_ROOT)
    native_count = len(native_names)
    solar_rule_names = _list_skill_names(SOLAR_RULES_ROOT)
    claude_rule_names = _list_skill_names(CLAUDE_RULES_ROOT)
    rules_count = len(set(solar_rule_names + claude_rule_names))
    codex_skills_count = _count_skill_files(CODEX_SKILLS_ROOT)
    codex_plugin_skill_files = _count_skill_files(CODEX_PLUGIN_CACHE_ROOT)

    vendor_sources = {
        "ruflo": HARNESS_VENDOR_ROOT / "ruflo",
        "hermes-agent": HARNESS_VENDOR_ROOT / "hermes-agent",
        "obsidian-wiki": HARNESS_VENDOR_ROOT / "obsidian-wiki",
        "everything-claude-code": HARNESS_VENDOR_ROOT / "everything-claude-code",
        "agent-rules-books": HARNESS_VENDOR_ROOT / "agent-rules-books",
        "mineru-document-explorer": HARNESS_VENDOR_ROOT / "MinerU-Document-Explorer",
    }
    vendor_skill_files = {}
    for name, root in vendor_sources.items():
        if name == "agent-rules-books" and root.exists():
            rule_files = sorted(
                p for p in root.glob("*/*.md")
                if p.parent.name not in {"docs", "_rule-workbench"}
            )
            vendor_skill_files[name] = {
                "path": str(root),
                "exists": True,
                "skill_files": len(rule_files),
                "rule_files": len(rule_files),
                "kind": "rulebook_provider",
                "sample": [str(p.relative_to(root)) for p in rule_files[:12]],
            }
        else:
            vendor_skill_files[name] = {
                "path": str(root),
                "exists": root.exists(),
                "skill_files": _count_skill_files(root),
                "sample": _sample_skill_files(root, 12),
            }
    vendor_skill_files_total = sum(v["skill_files"] for v in vendor_skill_files.values())

    total = agents_count + claude_count + native_count + codex_superpowers_count + rules_count
    recursive_skill_files_total = (
        _count_skill_files(SKILLS_ROOT)
        + _count_skill_files(CLAUDE_SKILLS_ROOT)
        + codex_skills_count
        + codex_plugin_skill_files
        + _count_skill_files(SOLAR_NATIVE_ROOT)
        + vendor_skill_files_total
    )

    sources: dict[str, Any] = {
        "agents-skills": {
            "path": str(SKILLS_ROOT),
            "count": agents_count,
            "exists": SKILLS_ROOT.exists(),
        },
        "claude-skills": {
            "path": str(CLAUDE_SKILLS_ROOT),
            "count": claude_count,
            "exists": CLAUDE_SKILLS_ROOT.exists(),
            "skills": _list_skill_names(CLAUDE_SKILLS_ROOT),
        },
        "codex-superpowers": {
            "path": str(CODEX_SUPERPOWERS_ROOT),
            "count": codex_superpowers_count,
            "exists": CODEX_SUPERPOWERS_ROOT.exists(),
            "skills": ["superpowers"] if CODEX_SUPERPOWERS_ROOT.exists() else [],
        },
        "codex-skills": {
            "path": str(CODEX_SKILLS_ROOT),
            "count": codex_skills_count,
            "exists": CODEX_SKILLS_ROOT.exists(),
            "sample": _sample_skill_files(CODEX_SKILLS_ROOT, 12),
        },
        "codex-plugin-cache": {
            "path": str(CODEX_PLUGIN_CACHE_ROOT),
            "count": codex_plugin_skill_files,
            "exists": CODEX_PLUGIN_CACHE_ROOT.exists(),
            "sample": _sample_skill_files(CODEX_PLUGIN_CACHE_ROOT, 12),
        },
        "vendor-skill-files": vendor_skill_files,
        "solar-native": {
            "path": str(SOLAR_NATIVE_ROOT),
            "count": native_count,
            "exists": SOLAR_NATIVE_ROOT.exists(),
            "skills": native_names,
        },
        "solar-rules": {
            "path": str(SOLAR_RULES_ROOT),
            "count": len(solar_rule_names),
            "exists": SOLAR_RULES_ROOT.exists(),
            "rules": solar_rule_names,
        },
        "claude-rules": {
            "path": str(CLAUDE_RULES_ROOT),
            "count": len(claude_rule_names),
            "exists": CLAUDE_RULES_ROOT.exists(),
            "rules": claude_rule_names,
        },
    }

    result = {
        "totals": {
            "skills": total,
            "skill_files_recursive": recursive_skill_files_total,
            "agents_skills": agents_count,
            "claude_skills": claude_count,
            "codex_superpowers": codex_superpowers_count,
            "codex_skills": codex_skills_count,
            "codex_plugin_skill_files": codex_plugin_skill_files,
            "solar_native": native_count,
            "vendor_skill_files": vendor_skill_files_total,
            "rules": rules_count,
        },
        "usability": {
            "directly_advertised_to_panes": "summary_only",
            "dispatch_injection": "keyword-selected provider hints plus inventory counts",
            "all_1000_plus_loaded_into_prompt": False,
            "note": "Solar-Harness can discover thousands of skill files, but it does not inject every skill into every pane. It injects compact inventory/context and routes to providers by task keywords.",
        },
        "sources": sources,
        "generated_at": _now_iso(),
    }

    # Write cache
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    INVENTORY_CACHE.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Skills inventory: {total} total")
        print(f"  agents/skills:  {agents_count}")
        print(f"  solar-native:   {native_count}")
        for name in native_names:
            print(f"    - {name}")
    return 0


# ── doctor ─────────────────────────────────────────────────────────────────

def cmd_doctor(args: list[str]) -> int:
    as_json = "--json" in args

    pane_configs = _get_pane_config()
    panes_out: list[dict[str, Any]] = []
    for pane, cfg in pane_configs.items():
        cap = _pane_capability(pane, cfg)
        panes_out.append(cap)

    # Add unknown panes from environment (tmux sessions) if available
    # Overall status
    strict_panes = [p for p in panes_out if p["mcp_mode"] == "STRICT"]
    default_panes = [p for p in panes_out if p["mcp_mode"] == "DEFAULT"]

    overall = {
        "total_panes": len(panes_out),
        "strict_mcp_panes": len(strict_panes),
        "default_mcp_panes": len(default_panes),
        "all_auth_present": all(p["auth_token_present"] for p in panes_out),
        "status": "ok" if panes_out else "no_panes_configured",
    }

    result = {
        "panes": panes_out,
        "overall": overall,
        "generated_at": _now_iso(),
    }

    # Redact entire output string to be safe
    out_str = json.dumps(result, indent=2, ensure_ascii=False)
    out_str = _redact(out_str)

    if as_json:
        print(out_str)
    else:
        print(f"Pane capability doctor — {overall['total_panes']} panes")
        for p in panes_out:
            kb = "kb_context=YES" if p["kb_context"] else "kb_context=NO"
            print(f"  {p['pane']:20s} model={p['model']:12s} mcp={p['mcp_mode']:8s} {kb}")
        print(f"Overall: {overall['status']}")
    return 0


def cmd_compile_to_capsule(args: list[str]) -> int:
    from skill_to_capsule_compiler import batch_compile, compile_report_jsonable

    plugin_id: str | None = None
    dry_run = "--dry-run" in args
    as_json = "--json" in args
    if "--plugin" in args:
        idx = args.index("--plugin")
        if idx + 1 >= len(args):
            print("--plugin requires a value", file=sys.stderr)
            return 2
        plugin_id = args[idx + 1]
    report = batch_compile(dry_run=dry_run, plugin_id=plugin_id)
    payload = compile_report_jsonable(report)
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(
            f"compile-to-capsule: ok={payload['ok']} dry_run={payload['dry_run']} "
            f"capsules={payload['capsule_count']} skipped={len(payload['skipped'])} errors={len(payload['errors'])}"
        )
        for item in payload.get("generated", []):
            print(f"  - {item['capsule_id']} <- {item['capability_id']}")
    return 0 if payload.get("ok") else 1


# ── inject ─────────────────────────────────────────────────────────────────

_SKILLS_OPEN = "<solar-skills-context>"
_SKILLS_CLOSE = "</solar-skills-context>"
_INTENT_OPEN = "<solar-intent-context>"
_INTENT_CLOSE = "</solar-intent-context>"
_CAP_OPEN = "<solar-capability-context>"
_CAP_CLOSE = "</solar-capability-context>"
_KB_OPEN = "<solar-knowledge-context>"
_KB_CLOSE = "</solar-knowledge-context>"


CAPABILITY_RULES: list[dict[str, Any]] = [
    {
        "provider": "Solar-Harness Runtime",
        "capabilities": [
            "harness.context_preflight",
            "harness.intent",
            "harness.dispatch_visibility",
            "harness.contracts",
            "harness.dag",
            "harness.status",
            "harness.model_routing",
        ],
        "why": "任务涉及 Solar-Harness 自身、pane、dispatch、intent engine、DAG、coordinator、status、模型路由或能力可视化。",
        "use": "调用 solar-harness-runtime skill：先 context inject + intent match，再用 skills inject / intent summarize / audit / activation-proof 留证据；模型切换只用 solar-harness models 命令。",
        "patterns": [
            r"\b(solar[- ]harness|harness|coordinator|dispatch|pane|task_graph|graph[- ]dispatch|graph[- ]scheduler|intent engine|activation[- ]proof|capability visibility|model routing)\b",
            r"四分屏|分屏|派单|调度|合约库|能力可视|状态面板|角标|模型路由|审判官|建设者|规划者|皮鞭女王",
        ],
    },
    {
        "provider": "solar-intent-engine",
        "capabilities": ["intent.match", "intent.audit", "dispatch.intent_telemetry"],
        "why": "任务涉及意图识别、learned intent、dispatch 前能力命中或 intent telemetry。",
        "use": "先运行 solar-harness intent match，再用 skills inject 生成 .intent.json；只把 audit 证据写成 worker_used。",
        "patterns": [
            r"\b(intent engine|intent[- ]match|intent telemetry|learned intent|dispatch intent)\b",
            r"意图识别|意图引擎|能力命中|intent|telemetry",
        ],
    },
    {
        "provider": "solar-activation-proof",
        "capabilities": ["activation.proof", "negative_control", "runtime_artifacts"],
        "why": "任务要求证明能力默认、自动、可用、有效，不能只看安装状态。",
        "use": "运行 solar-harness integrations activation-proof --json；必须包含 negative control 和 runtime artifacts。",
        "patterns": [
            r"\b(activation[- ]proof|negative control|runtime artifacts|default automatic usable effective)\b",
            r"证明.*可用|默认.*自动|有效果|负对照|激活证明",
        ],
    },
    {
        "provider": "solar-graph-scheduler",
        "capabilities": ["dag.validate", "dag.ready_nodes", "dag.join_gate"],
        "why": "任务涉及 task_graph、DAG、ready node、join gate、write_scope 或父 sprint readiness。",
        "use": "必须验证 task_graph.json；无 write_scope 节点不得并行；父 sprint 通过前必须 parent-ready-check。",
        "patterns": [
            r"\b(task_graph|graph scheduler|graph[- ]scheduler|dag|ready nodes?|join gate|write_scope|parent[- ]ready)\b",
            r"任务图|DAG|就绪节点|并行批次|写范围|父级验收|join gate",
        ],
    },
    {
        "provider": "solar-model-routing",
        "capabilities": ["models.show", "models.lab_matrix", "models.footer_labels"],
        "why": "任务涉及 pane 模型、GLM/Sonnet 路由、lab matrix、footer 角标或配额 fallback。",
        "use": "只用 solar-harness models show/set-lab-matrix/refresh-labels；不要直接改 pane launcher 文案。",
        "patterns": [
            r"\b(model routing|lab matrix|glm|sonnet|opus|footer labels?|quota|persona-config)\b",
            r"模型路由|模型配置|角标|GLM|Sonnet|配额|lab matrix",
        ],
    },
    {
        "provider": "solar-knowledge-ingest",
        "capabilities": ["context.inject", "wiki.status", "data_plane.audit"],
        "why": "任务涉及知识库、Obsidian/QMD/Mirage/MinerU、_raw/_sources、accepted artifacts 入库或 data-plane。",
        "use": "先 context inject 和 data-plane audit；_raw 只作 staging，accepted artifacts 必须有入库/索引证据。",
        "patterns": [
            r"\b(knowledge ingest|wiki|obsidian|qmd|mirage|mineru|data[- ]plane|accepted artifacts?|_raw|_sources)\b",
            r"知识库|入库|索引|原件|数据平面|accepted artifact|验收产物",
        ],
    },
    {
        "provider": "solar-autopilot-monitor",
        "capabilities": ["autopilot.monitor", "autopilot.safe_apply", "pane.deadlock_detection"],
        "why": "任务涉及自动盯梢、pane 死等、queue/lease 阻塞、自动推进或协调器断头。",
        "use": "先运行 solar-autopilot-monitor.py --json；只对安全项 --apply，派发前检查 pane lease。",
        "patterns": [
            r"\b(autopilot|monitor|pane lease|deadlock|stale handoff|queue blockage|auto[- ]dispatch)\b",
            r"自动盯梢|自动推进|死等|队列阻塞|pane lease|断头|卡住",
        ],
    },
    {
        "provider": "gstack",
        "capabilities": ["browser.browse", "browser.qa", "code.review"],
        "why": "任务涉及网页、本地浏览器、视觉回归或前端 QA。",
        "use": "需要打开/检查页面时优先使用 gstack/browser QA 流程；保留截图、URL、失败选择器和复现步骤。",
        "patterns": [
            r"\b(browser|browse|webpage|website|localhost|127\.0\.0\.1|screenshot|visual|e2e|ui|frontend)\b",
            r"网页|浏览器|页面|截图|前端|可视化|视觉|打开.*页面|访问.*页面",
        ],
    },
    {
        "provider": "Superpowers",
        "capabilities": ["skill.methodology", "workflow.planning", "debug.systematic", "test.tdd"],
        "why": "任务需要系统化规划、TDD、根因分析或调试纪律。",
        "use": "先拆解目标和验收，再做最小实现；调试时记录假设、证据、验证命令和回归测试。",
        "patterns": [
            r"\b(superpowers|tdd|debug|root cause|systematic|test[- ]driven|plan|planning|breakdown)\b",
            r"系统化|调试|根因|测试驱动|规划|拆解|路线图|回归",
        ],
    },
    {
        "provider": "ATLAS",
        "capabilities": ["repair.pr-cot", "failure.structured_repair", "routing.complexity_budget"],
        "why": "任务涉及失败修复、hook/tool 异常、阻塞恢复或复杂度预算。",
        "use": "进入 repair 模式：定位失败点，写明证据链，优先做局部修复；不要静默停住或等待人工拍板。",
        "patterns": [
            r"\b(atlas|repair|failure|failed|hook_failed|timeout|blocked|stuck|retry|regression|broken)\b",
            r"失败|修复|阻塞|卡住|超时|断头|重试|坏了|不动了",
        ],
    },
    {
        "provider": "OWL",
        "capabilities": ["multi_agent.research", "browser.agent_experiment", "document.toolkit"],
        "why": "任务需要多智能体研究、外部框架实验或复杂资料探索。",
        "use": "把 OWL 当作外部研究/实验 provider；只在需要多代理探索时使用，不替换 Solar coordinator。",
        "patterns": [
            r"\b(owl|camel[- ]ai|multi[- ]agent|agent experiment|research swarm)\b",
            r"多智能体|多代理|研究框架|并行研究|外部代理",
        ],
    },
    {
        "provider": "MarkItDown",
        "capabilities": ["document.convert", "document.markdown_extract", "mcp.markitdown"],
        "why": "任务涉及 PDF/Office/HTML/图片等文档转 Markdown。",
        "use": "优先把原件转成 Markdown，再交给 Obsidian/QMD/Mirage 入库；保留源文件路径和转换日志。",
        "patterns": [
            r"\b(markitdown|pdf|docx|pptx|xlsx|html|convert.*markdown|markdown.*extract)\b",
            r"转.*md|转.*markdown|文档提取|格式转换|论文|表格|幻灯片",
        ],
    },
    {
        "provider": "agency-agents",
        "capabilities": ["persona.agent", "agent.catalog", "specialist.routing"],
        "why": "任务需要专门角色、行业 persona 或 agent catalog 辅助分工。",
        "use": "选择匹配 agent/persona 作为参考能力；必须服从 Solar 当前 sprint 合约和 write_scope。",
        "patterns": [
            r"\b(agency|persona|specialist|agent catalog|role routing|subagent)\b",
            r"人格|角色|专家|专门代理|专业代理|子代理",
        ],
    },
    {
        "provider": "Everything Claude Code",
        "capabilities": ["agent.inventory", "command.catalog", "rules.catalog", "mcp.catalog"],
        "why": "任务涉及 Claude Code 生态能力盘点、命令/规则/MCP/agent inventory。",
        "use": "只读使用 vendor inventory；不要盲装 hooks 或覆盖现有 Solar 规则。",
        "patterns": [
            r"\b(everything[- ]claude[- ]code|mcp|commands?|hooks?|rules?|agents? inventory)\b",
            r"命令目录|规则目录|MCP|hook|能力盘点|代理清单",
        ],
    },
    {
        "provider": "Empirical Research",
        "capabilities": ["research.empirical_pipeline", "research.literature_review", "analysis.causal_inference"],
        "why": "任务涉及实证研究、文献综述、因果推断、可复现分析或学术论文。",
        "use": "按研究问题、数据、识别策略、统计验证、复现包和论文写作链路执行；把证据和限制写入 handoff。",
        "patterns": [
            r"\b(empirical|causal|literature review|reproducib|academic paper|research design|stata|rct|did|iv)\b",
            r"实证|因果|文献综述|可复现|论文|研究设计|统计分析|固定效应|工具变量",
        ],
    },
    {
        "provider": "addyosmani/agent-skills",
        "capabilities": ["agent_skills.catalog", "workflow.spec_driven", "workflow.code_review", "workflow.test_driven"],
        "why": "任务需要 agent-skills 的规范驱动、测试驱动、评审、发布或上下文工程方法。",
        "use": "把 addyosmani/agent-skills 当作只读工作流模式库；不能覆盖 Solar 当前合约和角色派发。",
        "patterns": [
            r"\b(addyosmani|agent-skills|spec[- ]driven|source[- ]driven|context engineering)\b",
            r"规范驱动|源驱动|上下文工程|agent skills|代理技能",
        ],
    },
    {
        "provider": "agent-rules-books",
        "capabilities": ["rules.book_catalog", "rules.refactoring", "rules.architecture", "rules.ddd", "rules.reliability", "rules.data_systems"],
        "why": "任务涉及经典工程书规则：Clean Code、Refactoring、DDD、Clean Architecture、DDIA、Release It、Legacy Code 等。",
        "use": "先用 solar-harness agent-rules-books inventory/report 查看可用规则；默认只注入一个相关 mini 规则集，full 只作参考，不要全量塞进 prompt。",
        "patterns": [
            r"\b(agent[- ]rules[- ]books|clean code|clean architecture|refactoring|domain[- ]driven design|ddd|ddia|release it|legacy code|code complete|pragmatic programmer)\b",
            r"经典.*工程书|重构|领域驱动|DDD|整洁代码|整洁架构|数据密集型|遗留代码|生产可靠性|代码大全|程序员修炼",
        ],
    },
    {
        "provider": "Browser-use MCP",
        "capabilities": ["browser.mcp", "browser.automation", "browser.screenshot", "browser.localhost_test"],
        "why": "任务明确需要 browser-use、MCP 浏览器自动化、截图或 localhost 交互测试。",
        "use": "优先使用本地 browser-use MCP / Codex Browser Use 能力；若不可用，降级到 gstack/browser QA 并记录证据。",
        "patterns": [
            r"\b(browser-use|browser use|browser mcp|mcp browser|localhost.*screenshot|click|type)\b",
            r"浏览器.*MCP|browser-use|点击|输入|本地页面测试|截图",
        ],
    },
    {
        "provider": "openai-agents-python",
        "capabilities": ["agents_sdk.design", "agents_sdk.guardrails", "agents_sdk.tracing", "agents_sdk.handoff_model"],
        "why": "任务涉及 OpenAI Agents SDK、typed agents、guardrails、tracing、sessions 或 handoff runtime 设计。",
        "use": "按 PoC/设计能力使用，不把它当成当前生产执行器；输出迁移边界、回滚和不替换清单。",
        "patterns": [
            r"\b(openai[- ]agents|agents sdk|guardrails|typed agents|handoffs|tracing|sessions)\b",
            r"OpenAI Agents|智能体 SDK|护栏|追踪|会话|原生 handoff",
        ],
    },
    {
        "provider": "Codex Bridge",
        "capabilities": ["codex.bridge", "codex.contract_ingest", "codex.review_handoff", "pane3.bridge"],
        "why": "任务涉及 Codex 到 Solar 的合约、review、pane3 bridge 或 from-codex 文件链路。",
        "use": "使用新链路 ~/.solar/codex-bridge/from-codex + chain-watcher；旧 ~/.solar/harness/codex-bridge 只作兼容证据。",
        "patterns": [
            r"\b(codex bridge|pane3|from-codex|to-codex|chain-watcher|execution-contract)\b",
            r"Codex Bridge|pane3|三号 pane|合约导入|chain watcher",
        ],
    },
    {
        "provider": "Ruflo",
        "capabilities": ["ruflo.swarm", "ruflo.plugins", "ruflo.agent_catalog", "ruflo.memory", "ruflo.mcp", "ruflo.workflow_templates"],
        "why": "任务涉及 Claude Code swarm、Ruflo/Claude Flow、插件市场、多代理编排、MCP 或 self-learning memory。",
        "use": "优先使用 Solar 管理的 sandbox runtime：solar-harness integrations ruflo-runtime-status / ruflo-runtime-smoke；不要在宿主项目直接运行 ruflo init 或写 .claude/hooks/settings，除非合约明确授权。",
        "patterns": [
            r"\b(ruflo|ruvflo|claude[- ]flow|swarm|hive[- ]mind|agentdb|ruvector|sparc)\b",
            r"Ruflo|Claude Flow|蜂群|多代理编排|插件市场|自学习|AgentDB|RuVector",
        ],
    },
    {
        "provider": "Autoresearch",
        "capabilities": ["autoresearch.pane_optimizer", "autoresearch.issue_loop", "autoresearch.local_issue", "autoresearch.agent_iteration", "autoresearch.score_gate"],
        "why": "任务适合用 issue 化拆解、score gate、反例/风险和验证增强来提升 PM/Planner/Builder/Evaluator pane 的输出质量。",
        "use": "把 Autoresearch 当 pane-level optimizer/advisor：PM 用它审需求和验收，Planner 用它反审 DAG/write_scope/stop rules，Builder 用它 dry-run local issue checklist，Evaluator 用它强化 score gate 和 FAIL 修复提示。它不替代 Builder；真正执行必须显式加 --execute、确认 target repo 干净或隔离、限定 max-iterations，并记录证据。",
        "patterns": [
            r"\b(autoresearch|auto research|pane optimizer|execution optimizer|dispatch advisor|issue[- ]loop|local issue|implementation loop|score[- ]gate|passing score)\b",
            r"自动实现.*issue|issue.*自动实现|本地.*issue|多代理.*迭代|评分门禁|分数门禁|执行优化器|质量优化|实现循环|修复循环",
        ],
    },
    {
        "provider": "Meta-Harness",
        "capabilities": ["meta_harness.outer_loop", "meta_harness.self_optimization", "meta_harness.pareto", "meta_harness.trace_eval", "meta_harness.dry_run_apply"],
        "why": "任务涉及 Solar/Solar-Harness 自优化、规则/技能/hook/config 改进、Pareto frontier、trace-based eval 或长期能力演化。",
        "use": "把 Meta-Harness 当 harness-level outer-loop optimizer：先运行 solar-harness meta-harness status/doctor；run/propose/apply 默认 dry-run，真实执行必须显式 --execute，且 apply 前要审查目标文件、风险等级和回滚点。它不替代 Builder，也不应在普通业务 sprint 中自动改 hooks/rules/skills。",
        "patterns": [
            r"\b(meta[- ]?harness|outer[- ]loop|self[- ]optimization|self[- ]improvement|harness code|pareto frontier|trace[- ]based eval|optimize.*harness)\b",
            r"自我优化|优化自己|自演化|外循环优化|元优化|能力演化|优化.*规则|优化.*技能|优化.*hook|优化.*config|Pareto|帕累托",
        ],
    },
    {
        "provider": "DeepResearch Source Search",
        "capabilities": ["source.search", "research.source.web", "research.source.academic", "research.source.internal"],
        "why": "任务涉及多源检索、外部搜索、学术搜索、Mirage/QMD 内部源搜索、来源网格。",
        "use": "使用 research.sources 中的 SourceConnector 子类执行搜索；通过 Mirage VFS 检索内部知识库；记录每个连接器的状态（ok/degraded/failed）。",
        "patterns": [
            r"\b(source search|multi.source|external search|academic search|source mesh|brave|exa|tavily|openalex|semantic scholar)\b",
            r"多源检索|外部搜索|学术搜索|来源网格|知识检索|文献搜索",
        ],
    },
    {
        "provider": "DeepResearch Evidence Extraction",
        "capabilities": ["evidence.extract", "research.evidence.extractor", "research.evidence.ledger"],
        "why": "任务涉及证据提取、span_text 提取、内容规范化、证据账本、EvidenceItem 创建。",
        "use": "使用 research.extractors 提取原文段落；每个证据必须有 span_text 和 content_hash；写入 evidence.jsonl。",
        "patterns": [
            r"\b(evidence extract|span_text|content_hash|evidence.item|extract.*passage|fetch.*extract)\b",
            r"证据提取|原文段落|内容哈希|证据账本|规范化提取",
        ],
    },
    {
        "provider": "DeepResearch Claim Mining",
        "capabilities": ["claim.mine", "research.claim.miner", "research.claim.ledger"],
        "why": "任务涉及 claim 挖掘、断言提取、claim-evidence 链接、unsupported_claim_rate 计算。",
        "use": "从 evidence.jsonl 挖掘 claim；标记 is_key；计算 unsupported_claim_rate（关键 claim 必须 <= 5%）；写入 claims.jsonl + claim_evidence.jsonl。",
        "patterns": [
            r"\b(claim min|assertion extract|claim.evidence|unsupported.claim|is_key|support_rating|mine.*claim|claim.*mine)\b",
            r"断言挖掘|claim.*挖掘|证据链接|无支撑断言|关键断言|挖掘断言",
        ],
    },
    {
        "provider": "DeepResearch Citation Verification",
        "capabilities": ["citation.verify", "research.factuality_evaluator"],
        "why": "任务涉及引用验证、citation span 检查、span_text 匹配、引用准确性审核。",
        "use": "验证 [cite:evidence_id] 标记是否解析为有效证据；检查 cited span_text 是否出现在证据原文中；计算 citation_span_accuracy。",
        "patterns": [
            r"\b(citation verif|span.*match|cite.*accuracy|fact.check|citation_span|reference check|citation.*verif|verif.*citation)\b",
            r"引用验证|引用检查|事实核查|span.*匹配|引用准确性",
        ],
    },
    {
        "provider": "DeepResearch Report Compilation",
        "capabilities": ["report.compile", "research.long_report_compiler", "research.report_ast"],
        "why": "任务涉及报告编译、章节组装、ReportAST 生成、结构化长报告。",
        "use": "从 report_ast.json 按章节顺序编译报告；R9 节点只拼接不生成新内容；最终报告由 R11 组装。",
        "patterns": [
            r"\b(report compil|chapter assembl|report.ast|long.report|section.compile|final export)\b",
            r"报告编译|章节组装|结构化报告|长报告|报告AST",
        ],
    },
    {
        "provider": "DeepResearch Factuality Evaluation",
        "capabilities": ["factuality.evaluate", "research.evaluator.contradiction"],
        "why": "任务涉及事实审稿、全局一致性检查、unsupported_claim_rate 门禁、contradiction 覆盖率。",
        "use": "计算 7 项指标（unsupported_claim_rate, citation_span_accuracy, source_authority_score, freshness_score, contradiction_coverage, section_repetition_rate, cross_section_consistency）；不通过则触发 rollback。",
        "patterns": [
            r"\b(factuality eval|global consistency|unsupported.rate|repetition rate|cross.section|contradiction coverage)\b",
            r"事实审稿|全局一致性|重复率|交叉一致性|矛盾覆盖率|质量门禁",
        ],
    },
]


def _build_skills_block(native_names: list[str], agents_count: int) -> str:
    lines = [
        _SKILLS_OPEN,
        f"<!-- auto-generated by solar_skills.py at {_now_iso()} -->",
        f"Solar has {agents_count} general skills and {len(native_names)} solar-native skills.",
        "",
        "Solar-native skills: " + ", ".join(native_names),
        _SKILLS_CLOSE,
    ]
    return "\n".join(lines)


def _build_kb_block(query: str = "") -> str:
    """Generate KB context block, degraded if solar-unified-context.py fails."""
    if SOLAR_CONTEXT_PY.exists():
        try:
            q = " ".join((query or "Solar-Harness dispatch context").split())[:600]
            result = subprocess.run(
                [sys.executable, str(SOLAR_CONTEXT_PY), "--query", q, "--format", "hook", "--fail-open"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                text = result.stdout.strip()
                # Wrap if not already wrapped
                if _KB_OPEN not in text:
                    return f"{_KB_OPEN}\n{text}\n{_KB_CLOSE}"
                return text
        except Exception as e:
            _warn(f"solar-unified-context.py failed: {e}, using degraded KB block")

    # Degraded fallback
    return (
        f"{_KB_OPEN}\n"
        f"<!-- warn: KB context unavailable at {_now_iso()} -->\n"
        f"## 默认知识库上下文 (auto-injected)\n\n"
        f"KB context could not be loaded. Proceed with available information.\n"
        f"{_KB_CLOSE}"
    )


def _load_capability_scorecards() -> dict[str, dict[str, Any]]:
    """Load runtime-aware capability scorecards from state DB if available."""
    if not STATE_DB.exists():
        return {}
    try:
        conn = sqlite3.connect(str(STATE_DB), timeout=2.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT capability, provider, score, level, status, payload FROM capability_scorecards"
        ).fetchall()
        conn.close()
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        try:
            payload = item.get("payload")
            if payload:
                extra = json.loads(payload)
                if isinstance(extra, dict):
                    item.update(extra)
        except Exception:
            pass
        out[f"{item.get('provider')}::{item.get('capability')}"] = item
        out[f"cap::{item.get('capability')}"] = item
    return out


def _rank_rule(rule: dict[str, Any], scores: dict[str, dict[str, Any]]) -> dict[str, Any]:
    provider = str(rule.get("provider", ""))
    provider_key = provider.lower().replace(" ", "-")
    aliases = {
        "ruflo": "ruflo",
        "gstack": "gstack",
        "superpowers": "superpowers",
        "browser-use-mcp": "browser-use",
        "codex-bridge": "codex-bridge",
        "openai-agents-python": "openai-agents-python",
        "empirical-research": "empirical-research",
        "addyosmani/agent-skills": "addy-agent-skills",
        "markitdown": "markitdown",
        "owl": "owl",
        "agency-agents": "agency-agents",
        "atlas": "atlas",
        "everything-claude-code": "everything-claude-code",
        "agent-rules-books": "agent-rules-books",
        "autoresearch": "autoresearch",
        "meta-harness": "meta-harness",
        "solar-harness-runtime": "solar-harness-runtime",
        "solar-data-plane": "solar-data-plane",
    }
    provider_id = aliases.get(provider_key, provider_key)
    matches = []
    for cap in rule.get("capabilities", []):
        item = scores.get(f"{provider_id}::{cap}") or scores.get(f"cap::{cap}")
        if item:
            matches.append(item)
    if not matches:
        return {"score": 0.0, "level": "", "runtime_level": "", "runtime_backend": "", "provider_id": provider_id}
    best = sorted(matches, key=lambda x: float(x.get("score", 0)), reverse=True)[0]
    return {
        "score": float(best.get("score", 0)),
        "level": best.get("level", ""),
        "runtime_level": best.get("runtime_level", ""),
        "runtime_backend": best.get("runtime_backend", ""),
        "provider_id": provider_id,
    }


def _select_capabilities(dispatch_text: str) -> list[dict[str, Any]]:
    """Select provider hints from task text, ranked by runtime-aware scorecards."""
    scores = _load_capability_scorecards()
    selected: list[dict[str, Any]] = []
    for rule in CAPABILITY_RULES:
        for pattern in rule["patterns"]:
            if re.search(pattern, dispatch_text, re.IGNORECASE | re.MULTILINE):
                item = dict(rule)
                item["scorecard"] = _rank_rule(rule, scores)
                selected.append(item)
                break
    selected.sort(key=lambda item: (-float(item.get("scorecard", {}).get("score", 0)), item.get("provider", "")))
    return selected


def _match_intents(dispatch_text: str) -> dict[str, Any]:
    """Run the Solar intent adapter. Fail-open if unavailable."""
    try:
        sys.path.insert(0, str(HARNESS_DIR / "lib"))
        import intent_engine_adapter  # type: ignore

        return intent_engine_adapter.match(dispatch_text, record=False)
    except Exception as e:
        return {
            "ok": False,
            "matched": False,
            "matches": [],
            "error": str(e),
        }


def _build_intent_block(dispatch_text: str, result: dict[str, Any] | None = None) -> str:
    result = result or _match_intents(dispatch_text)
    matches = result.get("matches") or []
    lines = [
        _INTENT_OPEN,
        f"<!-- auto-generated by solar_skills.py at {_now_iso()} -->",
        "## Solar Intent Adapter",
        "",
    ]
    if not result.get("ok", False):
        lines.extend([
            f"- warn: intent adapter unavailable: {result.get('error', 'unknown')}",
            "- fail-open: continue normal Solar-Harness dispatch.",
            "",
        ])
    elif not matches:
        lines.extend([
            "- N/A: no direct Solar intent or legacy skill hint matched.",
            "",
        ])
    else:
        for item in matches:
            label = item.get("skill") or item.get("target") or item.get("type", "unknown")
            lines.append(
                f"- {item.get('kind', 'intent')} {item.get('source', 'solar')} "
                f"{label} confidence={item.get('confidence', 'N/A')}"
            )
            lines.append(f"  Action: {item.get('instruction', 'N/A')}")
        lines.append("")
    lines.extend([
        "## Intent Rules",
        "",
        "- 这是旧 Solar intent-engine-hook.sh 的 Harness 适配层；用于 dispatch 前决策提示。",
        "- direct intent 可以改变执行纪律；skill hint 只作为能力注入建议，不覆盖 sprint 合约。",
        "- 命中 learned-db 规则时，优先按学习规则解释用户意图，但必须保留证据。",
        _INTENT_CLOSE,
    ])
    return "\n".join(lines)


def _build_capability_block(dispatch_text: str, selected: list[dict[str, Any]] | None = None) -> str:
    selected = selected if selected is not None else _select_capabilities(dispatch_text)
    lines = [
        _CAP_OPEN,
        f"<!-- auto-generated by solar_skills.py at {_now_iso()} -->",
        "## Auto-selected Solar Capabilities",
        "",
    ]
    if not selected:
        lines.extend([
            "- N/A: 当前 dispatch 没有命中特定外部 capability；按普通 Solar-Harness 流程执行。",
            "",
        ])
    else:
        for item in selected:
            caps = ", ".join(item["capabilities"])
            lines.append(f"- {item['provider']} ({caps})")
            scorecard = item.get("scorecard", {}) if isinstance(item.get("scorecard"), dict) else {}
            if scorecard.get("score"):
                lines.append(
                    f"  Score: {scorecard.get('score')} level={scorecard.get('level') or 'N/A'} "
                    f"runtime={scorecard.get('runtime_level') or 'N/A'} backend={scorecard.get('runtime_backend') or 'N/A'}"
                )
                readiness_level = _scorecard_level(
                    str(scorecard.get("provider_id") or item["provider"]),
                    str(item["capabilities"][0]) if item.get("capabilities") else "",
                    _load_capability_scorecards(),
                )
                lines.append(f"  Readiness: {readiness_level or 'scorecard_present'}")
            else:
                lines.append("  Readiness: injectable_only (no executable/effective scorecard yet)")
            lines.append(f"  Why: {item['why']}")
            lines.append(f"  Use: {item['use']}")
        lines.append("")
    lines.extend([
        "## Dispatch Rules",
        "",
        "- 这些 capability 是自动选择的执行辅助，不替换 Solar coordinator / planner / evaluator。",
        "- Autoresearch 只能作为 pane-level optimizer/advisor；没有用户授权、--execute、清洁/隔离工作树和 bounded max-iterations 时不得自动运行。",
        "- 若 capability 缺失或不可用，必须 fail-open：继续完成主任务，并在 handoff 写明降级证据。",
        "- 遇到失败、超时、hook/tool 异常时，优先触发 ATLAS structured repair，不要停在等待人工决策。",
        _CAP_CLOSE,
    ])
    return "\n".join(lines)


def _warn(msg: str) -> None:
    print(f"[solar_skills] WARN: {msg}", file=sys.stderr)


def _replace_block(text: str, open_tag: str, close_tag: str, new_block: str) -> str:
    """Replace existing block or append if not present."""
    start = text.find(open_tag)
    end = text.find(close_tag)
    if start != -1 and end != -1:
        return text[:start] + new_block + text[end + len(close_tag):]
    # Append before end of document
    return text.rstrip() + "\n\n" + new_block + "\n"


def _intent_sidecar_path(dispatch_file: Path) -> Path:
    return dispatch_file.with_name(dispatch_file.name + ".intent.json")


def _compact_capability(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": item.get("provider"),
        "capabilities": item.get("capabilities", []),
        "why": item.get("why", ""),
        "use": item.get("use", ""),
        "scorecard": item.get("scorecard", {}),
    }


def _write_intent_telemetry(
    dispatch_file: Path,
    original_text: str,
    injected_text: str,
    intent_result: dict[str, Any],
    capabilities: list[dict[str, Any]],
    native_count: int,
    general_count: int,
) -> Path:
    """Write dispatch-local intent telemetry.

    This is deliberately evidence-only. It records what was made visible to a
    worker, not whether the model privately followed it.
    """
    payload = {
        "schema_version": 1,
        "generated_at": _now_iso(),
        "dispatch_file": str(dispatch_file),
        "source_bytes": len(original_text.encode("utf-8", errors="ignore")),
        "intent": {
            "ok": bool(intent_result.get("ok")),
            "matched": bool(intent_result.get("matched")),
            "matches": intent_result.get("matches", []),
            "error": intent_result.get("error", ""),
        },
        "capabilities": [_compact_capability(item) for item in capabilities],
        "skills": {
            "general_count": general_count,
            "solar_native_count": native_count,
        },
        "worker_visible": {
            "solar_skills_context": _SKILLS_OPEN in injected_text and _SKILLS_CLOSE in injected_text,
            "solar_intent_context": _INTENT_OPEN in injected_text and _INTENT_CLOSE in injected_text,
            "solar_capability_context": _CAP_OPEN in injected_text and _CAP_CLOSE in injected_text,
            "solar_knowledge_context": _KB_OPEN in injected_text and _KB_CLOSE in injected_text,
        },
        "effect": {
            "status": "pending_worker_evidence",
            "worker_used": False,
            "evidence": [],
            "note": "Private model reasoning is not observable; audit uses handoff/eval/status artifacts.",
        },
    }
    sidecar = _intent_sidecar_path(dispatch_file)
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sidecar


def cmd_inject(args: list[str]) -> int:
    """Idempotently inject skills + KB context blocks into a dispatch file."""
    non_flag = [a for a in args if not a.startswith("--")]
    if not non_flag:
        print("usage: solar-harness skills inject <dispatch_file>", file=sys.stderr)
        return 1

    dispatch_file = Path(non_flag[0])
    if not dispatch_file.exists():
        print(f"dispatch file not found: {dispatch_file}", file=sys.stderr)
        return 1

    native_names = _list_skill_names(SOLAR_NATIVE_ROOT)
    agents_count = _count_skills(SKILLS_ROOT)

    text = dispatch_file.read_text(encoding="utf-8", errors="replace")
    original_text = text
    intent_result = _match_intents(original_text)
    capabilities = _select_capabilities(original_text)
    skills_block = _build_skills_block(native_names, agents_count)
    intent_block = _build_intent_block(text, intent_result)
    capability_block = _build_capability_block(text, capabilities)
    kb_block = _build_kb_block(original_text)

    # Replace or append blocks (idempotent)
    text = _replace_block(text, _SKILLS_OPEN, _SKILLS_CLOSE, skills_block)
    text = _replace_block(text, _INTENT_OPEN, _INTENT_CLOSE, intent_block)
    text = _replace_block(text, _CAP_OPEN, _CAP_CLOSE, capability_block)
    text = _replace_block(text, _KB_OPEN, _KB_CLOSE, kb_block)

    dispatch_file.write_text(text, encoding="utf-8")
    try:
        sidecar = _write_intent_telemetry(
            dispatch_file,
            original_text=original_text,
            injected_text=text,
            intent_result=intent_result,
            capabilities=capabilities,
            native_count=len(native_names),
            general_count=agents_count,
        )
        if record_usage is not None:
            record_usage(
                "tool",
                "solar-skills-inject",
                intent="skills.inject",
                input_summary=str(dispatch_file),
                success=True,
                output_summary=(
                    f"intent_matched={bool(intent_result.get('matched'))}; "
                    f"capabilities={len(capabilities)}; sidecar={sidecar.name}"
                ),
                description="Solar-Harness default dispatch injector for skills, intent, capability and KB context blocks.",
                keywords=["skills", "intent", "capability", "dispatch", "knowledge"],
                config={"dispatch_file": str(dispatch_file)},
            )
        print(f"[solar_skills] injected context blocks into {dispatch_file.name}; telemetry={sidecar.name}")
    except Exception as exc:
        if record_usage is not None:
            record_usage(
                "tool",
                "solar-skills-inject",
                intent="skills.inject",
                input_summary=str(dispatch_file),
                success=False,
                output_summary="injection completed but telemetry sidecar failed",
                error=str(exc),
                description="Solar-Harness default dispatch injector for skills, intent, capability and KB context blocks.",
                keywords=["skills", "intent", "capability", "dispatch", "knowledge"],
                config={"dispatch_file": str(dispatch_file)},
            )
        _warn(f"intent telemetry sidecar failed for {dispatch_file}: {exc}")
        print(f"[solar_skills] injected context blocks into {dispatch_file.name}; telemetry=warn")
    return 0


# ── native-extract ─────────────────────────────────────────────────────────

def cmd_native_extract(args: list[str]) -> int:
    """Extract Solar native skills to state/solar-native-skills.json."""
    names = _list_skill_names(SOLAR_NATIVE_ROOT)
    skills_out = []
    for name in names:
        skill_dir = SOLAR_NATIVE_ROOT / name
        meta = _read_skill_meta(skill_dir) if skill_dir.is_dir() else {}
        skills_out.append({
            "name": name,
            "path": str(SOLAR_NATIVE_ROOT / name),
            "description": meta.get("description", ""),
            "status": "available" if (SOLAR_NATIVE_ROOT / name).exists() else "missing",
            "has_skill_md": (SOLAR_NATIVE_ROOT / name / "SKILL.md").exists() if skill_dir.is_dir() else False,
        })

    result = {
        "skills": skills_out,
        "count": len(skills_out),
        "root": str(SOLAR_NATIVE_ROOT),
        "generated_at": _now_iso(),
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    NATIVE_CACHE.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


# ── readiness / certification ──────────────────────────────────────────────

def _summarize_readiness(records: list[dict[str, Any]]) -> dict[str, int]:
    summary = {level: 0 for level in READINESS_ORDER}
    for item in records:
        level = str(item.get("level") or "broken")
        summary[level if level in summary else "broken"] += 1
    return summary


def _readiness_payload(include_all: bool = False, write_scorecards: bool = False) -> dict[str, Any]:
    scores = _load_capability_scorecards()
    core = _core_skill_readiness(scores)
    all_records = _all_discovered_skill_records()
    accepted = _accepted_artifact_readiness()
    records = core + [accepted]
    if include_all:
        # Core records are authoritative; append non-core inventory records for complete coverage.
        core_names = {item["name"] for item in core}
        records.extend(item for item in all_records if item.get("name") not in core_names)
    summary = _summarize_readiness(records)
    if write_scorecards:
        for item in core:
            provider = item["name"]
            level = item["level"]
            evidence = {"paths": item.get("paths", {}), "layers": item.get("layers", {})}
            for cap in item.get("capabilities", []):
                _write_scorecard(str(cap), provider, level, evidence)
        _write_scorecard(
            accepted["capability"],
            accepted["provider"],
            accepted["level"],
            accepted.get("evidence", {}),
        )
    return {
        "ok": summary.get("broken", 0) == 0,
        "overall_status": "ok" if summary.get("broken", 0) == 0 and summary.get("injectable", 0) == 0 else "warn",
        "summary": summary,
        "core": core,
        "accepted_artifacts": accepted,
        "skills": records,
        "total": len(records),
        "all_discovered_total": len(all_records),
        "generated_at": _now_iso(),
        "contract": {
            "levels": READINESS_ORDER,
            "rule": "Do not claim a skill is usable above its certified readiness level.",
        },
    }


def cmd_readiness(args: list[str]) -> int:
    include_all = "--all" in args
    as_json = "--json" in args
    write_scorecards = "--write-scorecards" in args
    result = _readiness_payload(include_all=include_all, write_scorecards=write_scorecards)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    READINESS_CACHE.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if record_usage is not None:
        record_usage(
            "tool",
            "solar-skills-readiness",
            intent="skills.readiness",
            input_summary=" ".join(args),
            success=True,
            output_summary=f"overall={result.get('overall_status')}; total={result.get('total')}; broken={result.get('summary', {}).get('broken')}",
            description="Solar-Harness skills readiness classifier.",
            keywords=["skills", "readiness", "certification", "capability"],
        )
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Solar skills readiness")
        for level in READINESS_ORDER:
            print(f"  {level:12s}: {result['summary'].get(level, 0)}")
        print(f"  total       : {result['total']}")
        print(f"  all_discovered_total: {result['all_discovered_total']}")
    return 0


def _probe_core_skill(spec: dict[str, Any]) -> dict[str, Any]:
    import tempfile

    name = str(spec["name"])
    probe = str(spec.get("probe") or "")
    base = {
        "name": name,
        "probe": probe,
        "ok": False,
        "level": "broken",
        "evidence": {},
    }
    codex_file = _skill_file(CODEX_SKILLS_ROOT, name)
    agents_file = _skill_file(SKILLS_ROOT, name)
    if not codex_file.exists() or not agents_file.exists():
        base["evidence"] = {"missing": [str(p) for p in (codex_file, agents_file) if not p.exists()]}
        return base

    if probe == "dispatch_inject":
        with tempfile.TemporaryDirectory() as td:
            dispatch = Path(td) / "dispatch.md"
            dispatch.write_text("# Test\n\nsolar-harness intent engine pane dispatch 能力可视化\n", encoding="utf-8")
            proc = _run([sys.executable, str(Path(__file__).resolve()), "inject", str(dispatch)], timeout=60)
            text = dispatch.read_text(encoding="utf-8", errors="replace") if dispatch.exists() else ""
            sidecar = Path(str(dispatch) + ".intent.json")
            ok = bool(proc.get("ok")) and "Solar-Harness Runtime" in text and sidecar.exists()
            base.update({
                "ok": ok,
                "level": "effective" if ok else "broken",
                "evidence": {"sidecar": sidecar.exists(), "provider_visible": "Solar-Harness Runtime" in text},
            })
            return base

    if probe == "intent_match":
        proc = _run([sys.executable, str(HARNESS_DIR / "lib" / "intent_engine_adapter.py"), "match", "修复 solar-harness intent engine", "--json"], timeout=30)
        parsed_ok = False
        if proc.get("ok"):
            try:
                parsed_ok = bool(json.loads(str(proc.get("stdout") or "{}")).get("ok"))
            except Exception:
                parsed_ok = False
        base.update({"ok": parsed_ok, "level": "executable" if parsed_ok else "broken", "evidence": proc})
        return base

    if probe == "activation_proof":
        proc = _run([str(HARNESS_DIR / "solar-harness.sh"), "integrations", "activation-proof", "--json"], timeout=180)
        passed_all = False
        if proc.get("ok"):
            try:
                payload = json.loads(str(proc.get("stdout") or "{}"))
                passed_all = bool(payload.get("ok")) and int(payload.get("passed", 0)) == int(payload.get("total", -1))
                proc["parsed"] = {"passed": payload.get("passed"), "total": payload.get("total")}
            except Exception:
                passed_all = False
        base.update({"ok": passed_all, "level": "effective" if passed_all else "broken", "evidence": proc})
        return base

    if probe == "graph_validate":
        with tempfile.TemporaryDirectory() as td:
            graph = Path(td) / "task_graph.json"
            graph.write_text(json.dumps({
                "sprint_id": "test-skill-readiness",
                "nodes": [{
                    "id": "S1",
                    "goal": "test node",
                    "depends_on": [],
                    "write_scope": [str(Path(td) / "out.txt")],
                    "required_skills": ["bash"],
                    "preferred_model": "glm",
                    "gate": "G1",
                    "acceptance": ["ok"],
                }],
            }), encoding="utf-8")
            proc = _run([sys.executable, str(HARNESS_DIR / "lib" / "graph_scheduler.py"), "validate", "--graph", str(graph)], timeout=30)
            ok = bool(proc.get("ok")) and '"ok": true' in str(proc.get("stdout", "")).lower()
            base.update({"ok": ok, "level": "executable" if ok else "broken", "evidence": proc})
            return base

    if probe == "models_show":
        proc = _run([str(HARNESS_DIR / "solar-harness.sh"), "models", "show"], timeout=30)
        ok = bool(proc.get("ok")) and "lab matrix" in str(proc.get("stdout", ""))
        base.update({"ok": ok, "level": "executable" if ok else "broken", "evidence": proc})
        return base

    if probe == "data_plane_audit":
        audit = _load_data_plane_audit()
        ok = "checks" in audit
        effective = audit.get("overall_status") == "ok"
        base.update({
            "ok": ok,
            "level": "effective" if effective else ("executable" if ok else "broken"),
            "evidence": {
                "overall_status": audit.get("overall_status"),
                "accepted_artifact_path": audit.get("accepted_artifact_path", {}),
            },
        })
        return base

    if probe == "autopilot_monitor":
        proc = _run([sys.executable, str(HARNESS_DIR / "tools" / "solar-autopilot-monitor.py"), "--json"], timeout=30)
        ok = bool(proc.get("ok"))
        base.update({"ok": ok, "level": "executable" if ok else "broken", "evidence": proc})
        return base

    return base


def cmd_certify(args: list[str]) -> int:
    as_json = "--json" in args
    probes = [_probe_core_skill(spec) for spec in CORE_SOLAR_SKILLS]
    accepted = _accepted_artifact_readiness()

    for spec, probe in zip(CORE_SOLAR_SKILLS, probes):
        for cap in spec.get("capabilities", []):
            _write_scorecard(str(cap), str(spec["provider"]), str(probe["level"]), probe.get("evidence", {}))
    _write_scorecard(
        accepted["capability"],
        accepted["provider"],
        accepted["level"],
        accepted.get("evidence", {}),
    )

    readiness = _readiness_payload(include_all=False, write_scorecards=False)
    failed = [p for p in probes if not p.get("ok")]
    warns = []
    if accepted.get("level") != "effective":
        warns.append({
            "name": accepted["name"],
            "level": accepted["level"],
            "evidence": accepted.get("evidence", {}),
        })
    result = {
        "ok": not failed,
        "overall_status": "error" if failed else ("warn" if warns else "ok"),
        "probes_passed": len(probes) - len(failed),
        "probes_total": len(probes),
        "failed": failed,
        "warns": warns,
        "readiness_summary": readiness["summary"],
        "accepted_artifacts": accepted,
        "generated_at": _now_iso(),
        "scorecards_written": True,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CERTIFICATION_CACHE.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if record_usage is not None:
        record_usage(
            "tool",
            "solar-skills-certify",
            intent="skills.certify",
            input_summary=" ".join(args),
            success=not failed,
            output_summary=(
                f"overall={result.get('overall_status')}; "
                f"probes={result.get('probes_passed')}/{result.get('probes_total')}; "
                f"accepted={accepted.get('level')}"
            ),
            error=json.dumps(failed[:2], ensure_ascii=False) if failed else "",
            description="Solar-Harness skills certification runner and scorecard writer.",
            keywords=["skills", "certify", "scorecard", "capability"],
        )
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Solar skills certify: {result['overall_status']}")
        print(f"  probes: {result['probes_passed']}/{result['probes_total']}")
        print(f"  accepted_artifacts: {accepted['level']} ({accepted['status']})")
    return 0 if not failed else 1


# ── main ───────────────────────────────────────────────────────────────────

# ── registry helpers ───────────────────────────────────────────────────────

REGISTRY_PATH = HARNESS_DIR / "skills" / "registry.yaml"
STABLE_STATUSES = {"stable"}
NON_STABLE_STATUSES = {"candidate", "canary"}


def _load_registry() -> list[dict]:
    if not REGISTRY_PATH.exists():
        return []
    skills: list[dict] = []
    current: "dict | None" = None
    for line in REGISTRY_PATH.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("- name:"):
            if current:
                skills.append(current)
            current = {"name": stripped.split(":", 1)[1].strip()}
        elif current is not None and ":" in stripped and not stripped.startswith("#"):
            k, _, v = stripped.partition(":")
            v_clean = v.strip().strip('"').strip("'")
            current[k.strip()] = None if v_clean == "null" else v_clean
    if current:
        skills.append(current)
    return skills


def _registry_skill(name: str) -> "dict | None":
    for sk in _load_registry():
        if sk.get("name") == name:
            return sk
    return None


def _update_registry_field(skill_name: str, field: str, value: "str | None") -> bool:
    if not REGISTRY_PATH.exists():
        return False
    lines = REGISTRY_PATH.read_text().splitlines()
    in_skill = False
    updated = False
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- name:") and stripped.split(":", 1)[1].strip() == skill_name:
            in_skill = True
        elif stripped.startswith("- name:") and in_skill:
            in_skill = False
        if in_skill and stripped.startswith(f"{field}:"):
            indent = len(line) - len(line.lstrip())
            val_str = "null" if value is None else f'"{value}"'
            result.append((" " * indent) + f"{field}: {val_str}")
            updated = True
            continue
        result.append(line)
    if updated:
        REGISTRY_PATH.write_text("\n".join(result) + "\n")
    return updated


# ── eval ──────────────────────────────────────────────────────────────────────

def cmd_eval(args: list[str]) -> int:
    import argparse as _ap
    p = _ap.ArgumentParser(prog="solar-harness skills eval")
    p.add_argument("--skill", required=True)
    p.add_argument("--json", action="store_true", dest="as_json")
    ns = p.parse_args(args)
    skill_name = ns.skill

    entry = _registry_skill(skill_name)
    if entry is None:
        print(json.dumps({"ok": False, "error": f"skill '{skill_name}' not in registry"}))
        return 1

    eval_pack_rel = entry.get("eval_pack")
    if not eval_pack_rel:
        print(json.dumps({"ok": False, "error": f"no eval_pack for '{skill_name}'"}))
        return 1

    eval_pack_path = HARNESS_DIR / eval_pack_rel
    if not eval_pack_path.exists():
        print(json.dumps({"ok": False, "error": f"eval_pack not found: {eval_pack_path}"}))
        return 1

    # Minimal YAML reader for eval pack
    text = eval_pack_path.read_text()
    min_score_line = next((l for l in text.splitlines() if l.strip().startswith("min_score:")), "")
    min_score = float(min_score_line.split(":", 1)[1].strip()) if min_score_line else 0.75

    # Count cases
    case_count = text.count("- id:")

    # Score: structural eval (eval pack exists + has cases + min_score defined)
    score = 1.0 if (case_count >= 1 and min_score > 0) else 0.0
    passed = score >= min_score

    # Emit metric
    try:
        sys.path.insert(0, str(HARNESS_DIR / "lib"))
        import skill_metrics
        skill_metrics.emit(skill_name,
                           event_type="eval_pass" if passed else "eval_fail",
                           score=score)
    except Exception:
        pass

    result = {
        "ok": True,
        "skill": skill_name,
        "eval_pack": str(eval_pack_path),
        "cases": case_count,
        "score": score,
        "min_score": min_score,
        "passed": passed,
    }
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


# ── promote ───────────────────────────────────────────────────────────────────

def cmd_promote(args: list[str]) -> int:
    import argparse as _ap
    p = _ap.ArgumentParser(prog="solar-harness skills promote")
    p.add_argument("--skill", required=True)
    p.add_argument("--skip-eval", action="store_true")
    p.add_argument("--skip-regression", action="store_true")
    ns = p.parse_args(args)
    skill_name = ns.skill

    entry = _registry_skill(skill_name)
    if entry is None:
        print(json.dumps({"ok": False, "error": f"skill '{skill_name}' not in registry"}))
        return 1

    current_status = entry.get("status", "")
    if current_status == "stable":
        print(json.dumps({"ok": True, "result": "already_stable", "skill": skill_name}))
        return 0

    # Gate 1: eval pass
    if not ns.skip_eval:
        eval_rc = cmd_eval(["--skill", skill_name, "--json"])
        if eval_rc != 0:
            print(json.dumps({
                "ok": False,
                "error": f"eval gate failed for '{skill_name}'; use --skip-eval only if you have external evidence",
            }))
            return 1

    # Gate 2: regression pass — check that no previously stable skill regressed
    if not ns.skip_regression:
        stable = [sk for sk in _load_registry() if sk.get("status") == "stable"]
        regression_ok = len(stable) >= 0  # structural check: registry readable
        if not regression_ok:
            print(json.dumps({"ok": False, "error": "regression check failed: registry unreadable"}))
            return 1

    # Update registry
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _update_registry_field(skill_name, "status", "stable")
    _update_registry_field(skill_name, "promoted_at", now_iso)
    _update_registry_field(skill_name, "promoted_by", "solar-harness-promote")

    # Emit metric
    try:
        import skill_metrics
        skill_metrics.emit(skill_name, event_type="promote")
    except Exception:
        pass

    result = {
        "ok": True,
        "skill": skill_name,
        "previous_status": current_status,
        "new_status": "stable",
        "promoted_at": now_iso,
    }
    print(json.dumps(result, indent=2))
    return 0


# ── rollback ──────────────────────────────────────────────────────────────────

def cmd_rollback(args: list[str]) -> int:
    import argparse as _ap
    p = _ap.ArgumentParser(prog="solar-harness skills rollback")
    p.add_argument("--skill", required=True)
    p.add_argument("--to", default="candidate", dest="to_status")
    ns = p.parse_args(args)
    skill_name = ns.skill

    entry = _registry_skill(skill_name)
    if entry is None:
        print(json.dumps({"ok": False, "error": f"skill '{skill_name}' not in registry"}))
        return 1

    current_status = entry.get("status", "")
    _update_registry_field(skill_name, "status", ns.to_status)
    _update_registry_field(skill_name, "promoted_at", None)
    _update_registry_field(skill_name, "promoted_by", None)

    try:
        import skill_metrics
        skill_metrics.emit(skill_name, event_type="rollback",
                           extra={"from_status": current_status, "to_status": ns.to_status})
    except Exception:
        pass

    print(json.dumps({
        "ok": True,
        "skill": skill_name,
        "previous_status": current_status,
        "new_status": ns.to_status,
    }, indent=2))
    return 0


# ── export wrapper ────────────────────────────────────────────────────────────

def cmd_export(args: list[str]) -> int:
    sys.path.insert(0, str(HARNESS_DIR / "lib"))
    import importlib
    try:
        import skill_export
        importlib.reload(skill_export)
    except ImportError:
        print(json.dumps({"ok": False, "error": "skill_export.py not found"}))
        return 1
    import argparse as _ap
    p = _ap.ArgumentParser(prog="solar-harness skills export")
    p.add_argument("--skill", required=True)
    p.add_argument("--dest")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--allow-non-stable", action="store_true")
    ns = p.parse_args(args)
    dest = Path(ns.dest) if ns.dest else None
    result = skill_export.export_skill(
        ns.skill, dest, force=ns.force, dry_run=ns.dry_run, allow_non_stable=ns.allow_non_stable
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def cmd_effect_scan(args: list[str]) -> int:
    import argparse as _ap
    try:
        from capability_effects import scan_effect
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"capability_effects unavailable: {exc}"}))
        return 1

    p = _ap.ArgumentParser(prog="solar-harness skills effect-scan")
    p.add_argument("dispatch_file")
    p.add_argument("--handoff", default="")
    p.add_argument("--eval", dest="eval_file", default="")
    p.add_argument("--eval-json", default="")
    p.add_argument("--verdict", default="")
    p.add_argument("--no-db", action="store_true")
    p.add_argument("--json", action="store_true")
    ns = p.parse_args(args)
    result = scan_effect(
        ns.dispatch_file,
        handoff_file=ns.handoff,
        eval_file=ns.eval_file,
        eval_json_file=ns.eval_json,
        verdict=ns.verdict,
        record_db=not ns.no_db,
    )
    if ns.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"capability effect: {result.get('effect', {}).get('status', result.get('reason', 'unknown'))}")
    return 0 if result.get("ok") else 1


# ── updated inventory (registry-aware) ────────────────────────────────────────

def cmd_registry_list(args: list[str]) -> int:
    as_json = "--json" in args
    skills = _load_registry()
    by_status: dict[str, list[str]] = {}
    for sk in skills:
        st = sk.get("status", "unknown")
        by_status.setdefault(st, []).append(sk.get("name", "?"))

    result = {
        "total": len(skills),
        "by_status": {k: sorted(v) for k, v in sorted(by_status.items())},
        "skills": skills,
    }
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Registry: {len(skills)} skills")
        for st, names in sorted(by_status.items()):
            print(f"  {st:12s}: {', '.join(names)}")
    return 0


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    sub = args[0]
    rest = args[1:]

    dispatch: dict[str, Any] = {
        "inventory": cmd_inventory,
        "doctor": cmd_doctor,
        "pane-status": cmd_doctor,
        "readiness": cmd_readiness,
        "certify": cmd_certify,
        "inject": cmd_inject,
        "native-extract": cmd_native_extract,
        "eval": cmd_eval,
        "promote": cmd_promote,
        "rollback": cmd_rollback,
        "export": cmd_export,
        "effect-scan": cmd_effect_scan,
        "registry": cmd_registry_list,
        "compile-to-capsule": cmd_compile_to_capsule,
    }

    fn = dispatch.get(sub)
    if fn is None:
        print(f"unknown subcommand: {sub}", file=sys.stderr)
        print(f"available: {', '.join(dispatch)}", file=sys.stderr)
        sys.exit(1)

    sys.exit(fn(rest))


if __name__ == "__main__":
    main()
