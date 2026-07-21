#!/usr/bin/env python3
"""Safe adapter for ciembor/agent-rules-books.

The upstream project is a rules/skills catalog distilled from engineering
books. Solar consumes it as a read-only provider by default:

- vendor keeps the upstream git repository.
- inventory/report describe available rule sets and local collisions.
- install --dry-run shows what would be staged; it never overwrites live rules.
- sync copies selected mini/nano/full files into a Solar-owned staging folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", str(HOME / ".solar" / "harness")))
VENDOR = HARNESS / "vendor" / "agent-rules-books"
STAGING = HARNESS / "vendor" / "agent-rules-books-staging"
REPORT_JSON = HARNESS / "reports" / "agent-rules-books-inventory.json"
REPORT_MD = HARNESS / "reports" / "agent-rules-books-inventory.md"
EFFECT_JSON = HARNESS / "reports" / "agent-rules-books-effect-proof.json"
EFFECT_MD = HARNESS / "reports" / "agent-rules-books-effect-proof.md"
STATE_DB = HARNESS / "run" / "state.db"
SOURCE_URL = "https://github.com/ciembor/agent-rules-books"

BOOK_DIRS = [
    "a-philosophy-of-software-design",
    "clean-architecture",
    "clean-code",
    "code-complete",
    "designing-data-intensive-applications",
    "domain-driven-design",
    "domain-driven-design-distilled",
    "implementing-domain-driven-design",
    "patterns-of-enterprise-application-architecture",
    "refactoring",
    "refactoring-guru",
    "release-it",
    "the-pragmatic-programmer",
    "working-effectively-with-legacy-code",
]

LOCAL_RULE_TARGETS = [
    HOME / "Solar" / "rules",
    HOME / ".claude" / "rules",
    HOME / ".cursor" / "rules",
]
LOCAL_SKILL_TARGETS = [
    HOME / ".agents" / "skills",
    HOME / ".codex" / "skills",
    HOME / ".claude" / "skills",
]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd: list[str], cwd: Path | None = None, timeout: float = 20.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except Exception as exc:
        return 99, f"{type(exc).__name__}: {exc}"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(VENDOR))
    except ValueError:
        return str(path)


def sha16(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def line_count(path: Path) -> int:
    try:
        return len(path.read_text(errors="ignore").splitlines())
    except OSError:
        return 0


def read_text(path: Path, max_chars: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars]
    return text


def version_for(path: Path) -> str:
    name = path.name
    if name.endswith(".mini.md"):
        return "mini"
    if name.endswith(".nano.md"):
        return "nano"
    if name.endswith(".md"):
        return "full"
    return "unknown"


def rule_files() -> list[Path]:
    if not VENDOR.exists():
        return []
    files: list[Path] = []
    for book in BOOK_DIRS:
        root = VENDOR / book
        if root.exists():
            files.extend(sorted(root.glob("*.md")))
    return files


def local_names(roots: list[Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.iterdir():
            if path.name.startswith("."):
                continue
            key = path.stem if path.is_file() else path.name
            out[key] = str(path)
    return out


def inventory() -> dict:
    code, commit = run(["git", "rev-parse", "HEAD"], cwd=VENDOR)
    code2, remote = run(["git", "remote", "get-url", "origin"], cwd=VENDOR)
    files = rule_files()
    rules = []
    by_book: dict[str, dict] = {}
    for path in files:
        book = path.parent.name
        version = version_for(path)
        item = {
            "book": book,
            "version": version,
            "path": rel(path),
            "bytes": path.stat().st_size,
            "lines": line_count(path),
            "sha16": sha16(path),
        }
        rules.append(item)
        by_book.setdefault(book, {"full": False, "mini": False, "nano": False, "files": []})
        by_book[book][version] = True
        by_book[book]["files"].append(item["path"])

    local_rule_names = local_names(LOCAL_RULE_TARGETS)
    local_skill_names = local_names(LOCAL_SKILL_TARGETS)
    collisions = []
    for book in by_book:
        candidates = {book, book.replace("-", "_"), f"agent-rules-books-{book}"}
        for name in candidates:
            if name in local_rule_names:
                collisions.append({"surface": "rules", "key": name, "local": local_rule_names[name], "action": "defer"})
            if name in local_skill_names:
                collisions.append({"surface": "skills", "key": name, "local": local_skill_names[name], "action": "defer"})

    counts = {
        "books": len(by_book),
        "rules_total": len(rules),
        "full": sum(1 for r in rules if r["version"] == "full"),
        "mini": sum(1 for r in rules if r["version"] == "mini"),
        "nano": sum(1 for r in rules if r["version"] == "nano"),
    }
    return {
        "generated_at": now(),
        "source_url": remote if code2 == 0 else SOURCE_URL,
        "commit": commit if code == 0 else "",
        "vendor": str(VENDOR),
        "staging": str(STAGING),
        "installed": VENDOR.exists(),
        "counts": counts,
        "books": by_book,
        "rules": rules,
        "collisions": collisions,
        "mode": "safe_read_only_vendor_provider",
        "default_version": "mini",
        "recommendation": "Use mini as on-demand skill/rule pressure; keep full as retrieval/reference.",
    }


def write_reports(data: dict) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# agent-rules-books Inventory",
        "",
        f"- generated_at: {data.get('generated_at')}",
        f"- source: {data.get('source_url')}",
        f"- commit: `{data.get('commit')}`",
        f"- mode: {data.get('mode')}",
        f"- vendor: `{data.get('vendor')}`",
        f"- staging: `{data.get('staging')}`",
        "",
        "## Counts",
        "",
        "| metric | count |",
        "| --- | ---: |",
    ]
    for k, v in data.get("counts", {}).items():
        lines.append(f"| {k} | {v} |")
    lines.extend(["", "## Books", "", "| book | full | mini | nano |", "| --- | --- | --- | --- |"])
    for book, meta in sorted(data.get("books", {}).items()):
        lines.append(f"| {book} | {bool(meta.get('full'))} | {bool(meta.get('mini'))} | {bool(meta.get('nano'))} |")
    lines.extend(["", "## Collision Report", ""])
    if data.get("collisions"):
        lines.extend(["| surface | key | local | action |", "| --- | --- | --- | --- |"])
        for item in data["collisions"]:
            lines.append(f"| {item.get('surface')} | {item.get('key')} | `{item.get('local')}` | {item.get('action')} |")
    else:
        lines.append("No local name collisions detected for rule/skill roots.")
    lines.extend([
        "",
        "## Solar Policy",
        "",
        "- Do not globally inject all rule books into every pane.",
        "- Dispatch should select one or two relevant books by intent.",
        "- `mini` is the default active rule body; `full` stays reference/retrieval evidence.",
    ])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def doctor() -> dict:
    data = inventory() if VENDOR.exists() else {
        "installed": False,
        "counts": {"books": 0, "rules_total": 0, "full": 0, "mini": 0, "nano": 0},
        "collisions": [],
        "vendor": str(VENDOR),
        "staging": str(STAGING),
        "source_url": SOURCE_URL,
        "commit": "",
    }
    ok = bool(data.get("installed")) and data.get("counts", {}).get("mini", 0) >= 10
    return {
        "ok": ok,
        "installed": bool(data.get("installed")),
        "configured": bool(REPORT_JSON.exists() or data.get("counts", {}).get("rules_total", 0)),
        "indexed": REPORT_JSON.exists(),
        "used_by_default": False,
        "integration_level": "safe_read_only_vendor_provider" if ok else "missing_or_incomplete",
        "vendor": str(VENDOR),
        "staging": str(STAGING),
        "report_json": str(REPORT_JSON),
        "report_md": str(REPORT_MD),
        "counts": data.get("counts", {}),
        "collisions": data.get("collisions", []),
    }


def clone_or_update() -> dict:
    VENDOR.parent.mkdir(parents=True, exist_ok=True)
    if (VENDOR / ".git").exists():
        run(["git", "fetch", "--quiet", "--depth=1", "origin", "main"], cwd=VENDOR, timeout=60)
        run(["git", "checkout", "--quiet", "main"], cwd=VENDOR, timeout=20)
        code, out = run(["git", "pull", "--ff-only", "--quiet"], cwd=VENDOR, timeout=60)
    else:
        if VENDOR.exists():
            shutil.rmtree(VENDOR)
        code, out = run(["git", "clone", "--depth=1", SOURCE_URL, str(VENDOR)], timeout=120)
    data = inventory() if VENDOR.exists() else {"installed": False, "error": out}
    if VENDOR.exists():
        write_reports(data)
    return {"ok": code == 0 and VENDOR.exists(), "git": out, "inventory": data}


def sync(version: str, dry_run: bool) -> dict:
    if version not in {"mini", "nano", "full"}:
        raise SystemExit(f"invalid version: {version}")
    if not VENDOR.exists():
        return {"ok": False, "error": "vendor_missing", "vendor": str(VENDOR)}
    selected = [p for p in rule_files() if version_for(p) == version]
    actions = []
    for src in selected:
        dst = STAGING / version / src.parent.name / src.name
        actions.append({"src": rel(src), "dst": str(dst), "bytes": src.stat().st_size})
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    data = inventory()
    write_reports(data)
    return {"ok": True, "dry_run": dry_run, "version": version, "count": len(actions), "actions": actions[:80], "staging": str(STAGING)}


def score_for_level(level: str) -> float:
    return {
        "effective": 4.0,
        "executable": 3.0,
        "injectable": 2.0,
        "discoverable": 1.0,
        "broken": 0.0,
    }.get(level, 0.0)


def write_scorecard(capability: str, level: str, evidence: dict) -> None:
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
    payload = {
        "readiness_level": level,
        "runtime_level": "full_runtime_usable" if level == "effective" else level,
        "runtime_backend": "solar-harness",
        "evidence": evidence,
    }
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
            "agent-rules-books",
            score_for_level(level),
            "closed_loop" if level == "effective" else level,
            "active" if level == "effective" else "pending",
            1 if level in {"effective", "executable"} else 0,
            1 if level == "effective" else 0,
            now(),
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


def parse_sidecar(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}


def mini_rule_path(book: str) -> Path:
    return VENDOR / book / f"{book}.mini.md"


def rule_excerpt(path: Path) -> dict:
    text = read_text(path, max_chars=5000)
    rules = [line.strip() for line in text.splitlines() if line.strip().startswith("- ")]
    headings = [line.strip("# ").strip() for line in text.splitlines() if line.startswith("## ")]
    return {
        "path": str(path),
        "exists": path.exists(),
        "sha16": sha16(path),
        "headings": headings[:8],
        "sample_rules": rules[:8],
    }


def run_dispatch_inject(dispatch: Path) -> dict:
    skills_py = HARNESS / "lib" / "solar_skills.py"
    code, out = run([sys.executable, str(skills_py), "inject", str(dispatch)], timeout=90)
    sidecar = Path(str(dispatch) + ".intent.json")
    return {
        "ok": code == 0 and dispatch.exists() and sidecar.exists(),
        "returncode": code,
        "output": out[-1200:],
        "dispatch": str(dispatch),
        "sidecar": str(sidecar),
        "sidecar_payload": parse_sidecar(sidecar) if sidecar.exists() else {},
        "dispatch_text": read_text(dispatch, max_chars=12000),
    }


def prove(query: str, negative_query: str, write_scorecards: bool) -> dict:
    import tempfile

    inv = inventory() if VENDOR.exists() else {"installed": False, "counts": {}}
    clean_rule = mini_rule_path("clean-code")
    refactor_rule = mini_rule_path("refactoring")
    with tempfile.TemporaryDirectory(prefix="solar-arb-proof-") as td:
        root = Path(td)
        positive_dispatch = root / "agent-rules-books-positive.dispatch.md"
        negative_dispatch = root / "agent-rules-books-negative.dispatch.md"
        positive_dispatch.write_text(
            "# Dispatch\n\n"
            f"{query}\n\n"
            "验收：输出必须包含行为保护测试、最小安全重构步骤、风险清单。\n",
            encoding="utf-8",
        )
        negative_dispatch.write_text(f"# Dispatch\n\n{negative_query}\n", encoding="utf-8")

        positive = run_dispatch_inject(positive_dispatch)
        negative = run_dispatch_inject(negative_dispatch)

    sidecar = positive.get("sidecar_payload", {})
    intent_matches = sidecar.get("intent", {}).get("matches", []) if isinstance(sidecar, dict) else []
    capabilities = sidecar.get("capabilities", []) if isinstance(sidecar, dict) else []
    visible = sidecar.get("worker_visible", {}) if isinstance(sidecar, dict) else {}
    negative_sidecar = negative.get("sidecar_payload", {})
    negative_matches = negative_sidecar.get("intent", {}).get("matches", []) if isinstance(negative_sidecar, dict) else []
    negative_caps = negative_sidecar.get("capabilities", []) if isinstance(negative_sidecar, dict) else []

    dispatch_text = str(positive.get("dispatch_text", ""))
    positive_ok = (
        bool(inv.get("installed"))
        and clean_rule.exists()
        and refactor_rule.exists()
        and any(m.get("source") == "agent-rules-books" for m in intent_matches)
        and any(c.get("provider") == "agent-rules-books" for c in capabilities)
        and bool(visible.get("solar_capability_context"))
        and bool(visible.get("solar_intent_context"))
        and "agent-rules-books" in dispatch_text
        and ("Clean Code" in dispatch_text or "clean-code" in dispatch_text)
    )
    negative_ok = (
        not any(m.get("source") == "agent-rules-books" for m in negative_matches)
        and not any(c.get("provider") == "agent-rules-books" for c in negative_caps)
    )
    ok = positive_ok and negative_ok
    level = "effective" if ok else ("injectable" if positive.get("ok") else "broken")

    evidence = {
        "query": query,
        "negative_query": negative_query,
        "vendor": str(VENDOR),
        "commit": inv.get("commit", ""),
        "counts": inv.get("counts", {}),
        "positive": {
            "ok": positive.get("ok"),
            "intent_sources": sorted({m.get("source", "") for m in intent_matches if m.get("source")}),
            "intent_skills": sorted({m.get("skill", "") for m in intent_matches if m.get("skill")}),
            "capability_providers": sorted({c.get("provider", "") for c in capabilities if c.get("provider")}),
            "worker_visible": visible,
            "dispatch_contains_agent_rules_books": "agent-rules-books" in dispatch_text,
            "dispatch_contains_rulebook_reference": ("Clean Code" in dispatch_text or "clean-code" in dispatch_text),
        },
        "negative": {
            "ok": negative.get("ok"),
            "intent_sources": sorted({m.get("source", "") for m in negative_matches if m.get("source")}),
            "capability_providers": sorted({c.get("provider", "") for c in negative_caps if c.get("provider")}),
            "agent_rules_books_absent": negative_ok,
        },
        "rulebooks": {
            "clean-code": rule_excerpt(clean_rule),
            "refactoring": rule_excerpt(refactor_rule),
        },
        "effect_contract": [
            "positive task routes to agent-rules-books via intent adapter",
            "positive dispatch makes rulebook use visible to worker",
            "positive sidecar records worker-visible context blocks",
            "negative control does not select agent-rules-books",
            "scorecard is written only when positive and negative controls pass",
        ],
    }

    if ok and write_scorecards:
        for capability in [
            "rules.book_catalog",
            "rules.refactoring",
            "rules.architecture",
            "rules.ddd",
            "rules.reliability",
            "rules.data_systems",
        ]:
            write_scorecard(capability, "effective", evidence)

    result = {
        "ok": ok,
        "level": level,
        "scorecards_written": bool(ok and write_scorecards),
        "report_json": str(EFFECT_JSON),
        "report_md": str(EFFECT_MD),
        "evidence": evidence,
        "generated_at": now(),
    }
    write_effect_reports(result)
    return result


def write_effect_reports(result: dict) -> None:
    EFFECT_JSON.parent.mkdir(parents=True, exist_ok=True)
    EFFECT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence = result.get("evidence", {})
    positive = evidence.get("positive", {})
    negative = evidence.get("negative", {})
    lines = [
        "# agent-rules-books Effect Proof",
        "",
        f"- generated_at: {result.get('generated_at')}",
        f"- ok: {result.get('ok')}",
        f"- level: {result.get('level')}",
        f"- scorecards_written: {result.get('scorecards_written')}",
        f"- query: {evidence.get('query')}",
        f"- negative_query: {evidence.get('negative_query')}",
        "",
        "## Evidence",
        "",
        "| check | status | detail |",
        "| --- | --- | --- |",
        f"| positive intent | {'ok' if 'agent-rules-books' in positive.get('intent_sources', []) else 'error'} | {positive.get('intent_sources')} / {positive.get('intent_skills')} |",
        f"| positive capability | {'ok' if 'agent-rules-books' in positive.get('capability_providers', []) else 'error'} | {positive.get('capability_providers')} |",
        f"| worker visible | {'ok' if positive.get('worker_visible', {}).get('solar_capability_context') else 'error'} | {positive.get('worker_visible')} |",
        f"| negative control | {'ok' if negative.get('agent_rules_books_absent') else 'error'} | {negative.get('intent_sources')} / {negative.get('capability_providers')} |",
        "",
        "## Rulebook Samples",
        "",
    ]
    for name, item in (evidence.get("rulebooks") or {}).items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"- path: `{item.get('path')}`")
        lines.append(f"- sha16: `{item.get('sha16')}`")
        for rule in item.get("sample_rules", [])[:5]:
            lines.append(rule)
        lines.append("")
    EFFECT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    argv = list(sys.argv[1:])
    json_requested = "--json" in argv
    argv = [x for x in argv if x != "--json"]
    parser = argparse.ArgumentParser(description="agent-rules-books adapter")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("doctor")
    sub.add_parser("inventory")
    sub.add_parser("report")
    sub.add_parser("vendor")
    p_sync = sub.add_parser("sync")
    p_sync.add_argument("--version", choices=["mini", "nano", "full"], default="mini")
    p_sync.add_argument("--dry-run", action="store_true")
    p_install = sub.add_parser("install")
    p_install.add_argument("--dry-run", action="store_true")
    p_install.add_argument("--version", choices=["mini", "nano", "full"], default="mini")
    p_prove = sub.add_parser("prove")
    p_prove.add_argument("--query", default="请重构这个遗留代码，按 Clean Code 和 Refactoring 方法处理；减少 code smell，补 characterization test。")
    p_prove.add_argument("--negative-query", default="把这段会议纪要整理成三条待办。")
    p_prove.add_argument("--no-scorecard", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    args.json = json_requested or bool(args.json)

    cmd = args.cmd or "doctor"
    if cmd == "vendor":
        result = clone_or_update()
    elif cmd == "doctor":
        result = doctor()
    elif cmd == "inventory":
        result = inventory()
        write_reports(result)
    elif cmd == "report":
        result = inventory()
        write_reports(result)
        result = {"ok": True, "report_json": str(REPORT_JSON), "report_md": str(REPORT_MD), "counts": result.get("counts", {})}
    elif cmd == "sync":
        result = sync(args.version, args.dry_run)
    elif cmd == "install":
        # Product policy: install is a staging sync. Live activation must be a
        # separate explicit allowlist operation after reviewing collisions.
        result = sync(args.version, True if args.dry_run else False)
        result["live_activation"] = "not_performed"
    elif cmd == "prove":
        result = prove(args.query, args.negative_query, write_scorecards=not args.no_scorecard)
    else:
        raise SystemExit(f"unknown command: {cmd}")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if cmd in {"doctor", "inventory", "report"}:
            print(f"agent-rules-books: {'ok' if result.get('ok', True) else 'warn'}")
            print(f"vendor: {result.get('vendor', VENDOR)}")
            print(f"counts: {result.get('counts', {})}")
            print(f"report: {REPORT_MD}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
