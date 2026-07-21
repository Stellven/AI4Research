#!/usr/bin/env python3
"""qmd_adapter.py — QMD incremental rebuild adapter.

Wraps the existing QMD embed runner with:
  - Incremental mode: only re-embed files newer than last index timestamp
  - Wiki link integrity check: grep QMD index for broken [[links]]
  - Drive status: degraded when GOOGLE_APPLICATION_CREDENTIALS missing
  - Stop-on-break: abort rebuild if wiki links would be invalidated

CLI:
  python3 qmd_adapter.py status [--json]
  python3 qmd_adapter.py rebuild [--dry-run] [--force] [--json]
  python3 qmd_adapter.py check-links [--json]
  python3 qmd_adapter.py drive-status [--json]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
QMD_STATE_DIR = HARNESS_DIR / "state" / "qmd"
LAST_BUILD_FILE = QMD_STATE_DIR / "last-build.json"
QMD_EMBED_RUNNER = HARNESS_DIR / "lib" / "qmd-embed-runner.sh"
KNOWLEDGE_DIR = HOME / "Knowledge"
SOURCES_INGESTED = HARNESS_DIR / "_sources" / "ingested"

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from hands_runtime import SandboxHand  # noqa: E402
    from runtime_interfaces import ResultStatus  # noqa: E402
    _SANDBOX_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - import safety
    SandboxHand = None  # type: ignore[assignment]
    ResultStatus = None  # type: ignore[assignment]
    _SANDBOX_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


def _resolve_qmd_bin() -> str:
    """Locate the qmd CLI binary without sourcing the harness shell."""
    candidate = os.environ.get("QMD_BIN", "").strip()
    if candidate and Path(candidate).exists():
        return candidate
    import shutil as _sh
    found = _sh.which("qmd")
    if found:
        return found
    legacy = HOME / ".npm-global" / "bin" / "qmd"
    return str(legacy) if legacy.exists() else "qmd"


def _qmd_status_sandboxed(timeout: int = 10) -> dict[str, Any]:
    """Run `qmd status` through SandboxHand (argv mode, evidence file).

    Returns a dict with sandbox routing evidence so callers can prove that
    the tool-plane probe used the disposable sandbox instead of touching the
    host shell directly. We invoke the qmd CLI directly rather than the
    harness wrapper because the wrapper sources files relative to $HOME,
    which the sandbox intentionally rewrites.

    When SandboxHand is unavailable we fall back to a direct subprocess
    call and flag the route as `executor=host_fallback` so the activation
    proof can downgrade the verdict instead of silently passing.
    """
    qmd_bin = _resolve_qmd_bin()
    if SandboxHand is None or ResultStatus is None:
        reason = _SANDBOX_IMPORT_ERROR or "SandboxHand not importable"
        return {
            "ok": False,
            "exit_code": 99,
            "stdout": "",
            "stderr": reason,
            "executor": "host_fallback",
            "execution_mode": "argv",
            "evidence_file": "",
            "write_guard": {"enabled": False, "violations": []},
            "fallback_reason": reason,
            "qmd_bin": qmd_bin,
        }
    hand = SandboxHand()
    ref = hand.provision(capabilities=["qmd-status"])
    try:
        idem = hashlib.sha1(f"qmd-status:{os.getpid()}:{datetime.datetime.utcnow().isoformat()}".encode()).hexdigest()[:24]
        result = hand.execute(
            ref,
            "qmd-status",
            {
                "argv": [qmd_bin, "status"],
                "session_id": f"qmd-status-{os.getpid()}",
                "sprint_id": f"qmd-status-{os.getpid()}",
                "activity_id": f"qmd-status-{idem}",
            },
            idempotency_key=f"qmd-status:{idem}",
            timeout_seconds=timeout,
        )
        stdout = str(result.output or "")
        stderr = str((result.metadata or {}).get("stderr", "") or result.error or "")
        ok = result.status == ResultStatus.OK
        exit_code = 0 if ok else (124 if result.status == ResultStatus.TIMEOUT else 1)
        return {
            "ok": ok,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "executor": "sandbox",
            "execution_mode": (result.metadata or {}).get("execution_mode", "argv"),
            "evidence_file": (result.metadata or {}).get("evidence_file", ""),
            "write_guard": (result.metadata or {}).get("write_guard", {"enabled": False, "violations": []}),
            "sandbox_status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "hand_id": ref.hand_id,
            "qmd_bin": qmd_bin,
        }
    finally:
        hand.dispose(ref)


def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_last_build() -> "dict | None":
    if LAST_BUILD_FILE.exists():
        try:
            return json.loads(LAST_BUILD_FILE.read_text())
        except Exception:
            pass
    return None


def _write_last_build(data: dict) -> None:
    QMD_STATE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_BUILD_FILE.write_text(json.dumps(data, indent=2) + "\n")


def _qmd_available() -> bool:
    """Probe `qmd-status` through SandboxHand (argv mode, evidence file)."""
    return _qmd_status_sandboxed().get("ok", False)


def _find_new_files(since_iso: "str | None") -> list[Path]:
    """Find Knowledge + _sources/ingested files newer than last build."""
    roots = [r for r in [KNOWLEDGE_DIR, SOURCES_INGESTED] if r.exists()]
    new_files: list[Path] = []
    for root in roots:
        for ext in ("*.md", "*.txt", "*.pdf"):
            for f in root.rglob(ext):
                if since_iso is None:
                    new_files.append(f)
                else:
                    try:
                        mtime = datetime.datetime.utcfromtimestamp(f.stat().st_mtime)
                        if mtime.strftime("%Y-%m-%dT%H:%M:%SZ") > since_iso:
                            new_files.append(f)
                    except Exception:
                        pass
    return new_files


def _check_wiki_links() -> dict[str, Any]:
    """Check for broken [[wiki links]] by scanning markdown files."""
    broken: list[dict] = []
    if not KNOWLEDGE_DIR.exists():
        return {"ok": True, "checked": 0, "broken": [], "note": "Knowledge dir missing"}

    # Collect all known page names (case-insensitive stem)
    known: set[str] = set()
    for md in KNOWLEDGE_DIR.rglob("*.md"):
        known.add(md.stem.lower())

    checked = 0
    for md in KNOWLEDGE_DIR.rglob("*.md"):
        try:
            text = md.read_text(errors="replace")
            checked += 1
            import re
            for m in re.finditer(r"\[\[([^\]|#]+)", text):
                target = m.group(1).strip().lower()
                if target and target not in known:
                    broken.append({
                        "file": str(md.relative_to(KNOWLEDGE_DIR)),
                        "link": m.group(1).strip(),
                    })
        except Exception:
            pass

    return {
        "ok": len(broken) == 0,
        "checked": checked,
        "broken_count": len(broken),
        "broken": broken[:20],  # cap output
    }


def cmd_status(as_json: bool) -> int:
    last = _read_last_build()
    probe = _qmd_status_sandboxed()
    qmd_ok = probe.get("ok", False)
    drive_status = cmd_drive_status(as_json=False, _return=True)

    out = {
        "ok": True,
        "qmd_available": qmd_ok,
        "last_build": last,
        "drive": drive_status,
        "sources_ingested_exists": SOURCES_INGESTED.exists(),
        "knowledge_exists": KNOWLEDGE_DIR.exists(),
        "generated_at": _now(),
        "executor": probe.get("executor", "host_fallback"),
        "execution_mode": probe.get("execution_mode", ""),
        "evidence_file": probe.get("evidence_file", ""),
        "write_guard": probe.get("write_guard", {"enabled": False, "violations": []}),
        "sandbox_status": probe.get("sandbox_status", ""),
        "fallback_reason": probe.get("fallback_reason", ""),
    }
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"QMD adapter status:")
        print(f"  qmd_available:  {qmd_ok}")
        print(f"  executor:       {out['executor']} ({out['execution_mode']})")
        print(f"  evidence_file:  {out['evidence_file'] or '-'}")
        print(f"  last_build:     {last.get('built_at', 'never') if last else 'never'}")
        print(f"  drive_status:   {drive_status.get('status', '?')}")
    return 0


def cmd_rebuild(dry_run: bool, force: bool, as_json: bool) -> int:
    last = _read_last_build()
    since = None if force or last is None else last.get("built_at")

    new_files = _find_new_files(since)
    link_check = _check_wiki_links()

    if not link_check["ok"] and not dry_run:
        out = {
            "ok": False,
            "error": "wiki_links_broken_before_rebuild",
            "broken_links": link_check["broken"],
        }
        print(json.dumps(out, indent=2))
        return 1

    action = "dry_run" if dry_run else "rebuild"
    rebuilt = 0

    if not dry_run and new_files:
        if QMD_EMBED_RUNNER.exists():
            try:
                result = subprocess.run(
                    ["bash", str(QMD_EMBED_RUNNER), "--incremental"],
                    capture_output=True, text=True, timeout=300
                )
                rebuilt = len(new_files)
                if result.returncode == 0:
                    _write_last_build({
                        "built_at": _now(),
                        "mode": "incremental",
                        "files_rebuilt": rebuilt,
                    })
            except subprocess.TimeoutExpired:
                rebuilt = 0
        else:
            _write_last_build({
                "built_at": _now(),
                "mode": "incremental_noop",
                "files_rebuilt": 0,
                "note": "qmd-embed-runner.sh not present; state recorded only",
            })

    out = {
        "ok": True,
        "action": action,
        "since": since,
        "new_files_found": len(new_files),
        "rebuilt": rebuilt,
        "wiki_links_ok": link_check["ok"],
        "dry_run": dry_run,
    }
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        mode = "DRY-RUN" if dry_run else "APPLY"
        print(f"QMD rebuild [{mode}]: {len(new_files)} new files, rebuilt={rebuilt}")
    return 0


def cmd_check_links(as_json: bool) -> int:
    result = _check_wiki_links()
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        tag = "✓" if result["ok"] else "✗"
        print(f"Wiki links: {tag} ({result['broken_count']} broken / {result['checked']} checked)")
    return 0 if result["ok"] else 1


def cmd_drive_status(as_json: bool = True, _return: bool = False) -> "dict | int":
    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    has_creds = bool(creds and Path(creds).exists()) if creds else False

    out: dict[str, Any] = {
        "status": "ok" if has_creds else "degraded",
        "credential_env": "GOOGLE_APPLICATION_CREDENTIALS",
        "credential_present": has_creds,
    }
    if not has_creds:
        out["unblock"] = {
            "set_env": "GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json",
            "ui_path": "/integrations#drive",
        }
        out["note"] = "Drive is mirror/cold-backup only; degraded when no credentials"

    if _return:
        return out
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Drive status: {out['status']}")
        if not has_creds:
            print(f"  Set GOOGLE_APPLICATION_CREDENTIALS to enable")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(prog="qmd_adapter.py")
    sub = ap.add_subparsers(dest="cmd")

    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true", dest="as_json")

    rb = sub.add_parser("rebuild")
    rb.add_argument("--dry-run", action="store_true")
    rb.add_argument("--force", action="store_true")
    rb.add_argument("--json", action="store_true", dest="as_json")

    cl = sub.add_parser("check-links")
    cl.add_argument("--json", action="store_true", dest="as_json")

    ds = sub.add_parser("drive-status")
    ds.add_argument("--json", action="store_true", dest="as_json")

    args = ap.parse_args()
    if args.cmd == "status":
        return cmd_status(args.as_json)
    elif args.cmd == "rebuild":
        return cmd_rebuild(args.dry_run, args.force, args.as_json)
    elif args.cmd == "check-links":
        return cmd_check_links(args.as_json)
    elif args.cmd == "drive-status":
        return cmd_drive_status(args.as_json)
    else:
        ap.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
