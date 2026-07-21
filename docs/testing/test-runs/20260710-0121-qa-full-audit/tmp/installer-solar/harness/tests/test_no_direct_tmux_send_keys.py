"""Lint gate: forbid direct ``tmux send-keys`` in normal DAG dispatch code.

Context
-------
The N2/N3 operatord work introduces a file-inbox dispatch model
(``lib/operator_runtime.submit`` + ``tools/operatord.py``) that replaces the
legacy "directly poke tmux send-keys at a worker pane" pattern.

New DAG-dispatch code must not use ``tmux send-keys`` at all.  Legacy
dispatchers, startup pane creation, the centralised prompt-quarantine
fix-keys helper, monitoring/recovery tools, and research-survey backends
are explicitly allowlisted.  Any other source file that adds
``tmux send-keys`` will fail this lint gate with a message explaining
how to extend the allowlist (and forcing the change through review).

Tests
-----
1. ``test_denylist_files_have_no_send_keys`` — operatord runtime + helper
   files must contain zero ``tmux send-keys`` references.
2. ``test_no_unexpected_send_keys_callsites`` — scan ``lib/``, ``tools/``
   and root ``*.sh`` files; any file outside the allowlist that contains
   ``tmux send-keys`` is a hard failure.
3. ``test_allowlist_paths_exist`` — guard against stale allowlist entries.
4. ``test_allowlist_entries_still_have_send_keys`` — if an allowlisted
   file no longer contains ``tmux send-keys`` it should be removed.
5. ``test_scanner_detects_synthetic_violation`` — self-test: a synthetic
   file with ``tmux send-keys`` must be flagged by the scanner.
6. ``test_scanner_ignores_comment_only_mention`` — self-test: a file
   that only mentions ``tmux send-keys`` inside comments should not
   trip the call-pattern detector (used in the synthetic check).

The lint is implemented in this file (no separate ``lib/`` helper) so
the gate has no production-side dependency: the only way to weaken it
is to edit this test, which is exactly what we want code review to
catch.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Scan configuration
# ---------------------------------------------------------------------------

HARNESS_DIR = Path(__file__).resolve().parent.parent

# Files allowed to contain ``tmux send-keys`` text.  Each entry must have
# a category and a one-line rationale.  Paths are relative to HARNESS_DIR.
ALLOWLIST: dict[str, str] = {
    # === LEGACY DAG DISPATCH (planned migration target for operatord) ===
    "lib/graph_node_dispatcher.py": (
        "legacy DAG node dispatcher; will be replaced by operator_runtime.submit"
    ),
    "lib/hands_runtime.py": (
        "legacy PaneHand class; superseded by operator_runtime.submit"
    ),
    "coordinator.sh": (
        "legacy DAG coordinator pane-pusher; migration target"
    ),

    # === APPROVED STARTUP / PANE LIFECYCLE ===
    "solar-harness.sh": (
        "harness startup: creates panes and launches pane-launcher.sh "
        "(not normal DAG dispatch)"
    ),
    "lib/prompt-quarantine.sh": (
        "centralised fix-keys helper (Escape / C-u); the ONLY approved "
        "location for prompt-clear keystrokes"
    ),

    # === RESEARCH TOOLING (non-DAG) ===
    "lib/research/cli.py": (
        "research survey CLI argparse definitions; --pane-send is an opt-in "
        "research flow, not DAG dispatch"
    ),
    "lib/research/survey/backends.py": (
        "research survey pane-packet backend; not a DAG dispatch path"
    ),

    # === MONITORING / RECOVERY (non-DAG) ===
    "tools/solar-autopilot-monitor.py": (
        "autopilot pane-recovery / prompt-clear; not a DAG dispatch path"
    ),
    "tools/solar-product-platform-nightwatch.sh": (
        "nightwatch monitor; sends prompts to monitoring panes"
    ),

    # === DOCUMENTATION / STRING LITERALS ONLY ===
    "lib/experience/patterns.py": (
        "string literal in PATTERN_CLASSES describing the 'c_u_storm' "
        "antipattern; no actual send-keys call"
    ),
}

# Files where ``tmux send-keys`` MUST NEVER appear (even in comments).
# These are the new control-plane modules — they dispatch via the file
# inbox, never by injecting keystrokes into tmux.
DENYLIST: tuple[str, ...] = (
    "lib/multi_task_status.py",
    "lib/operator_runtime.py",
    "tools/monitor_bridge.py",
    "tools/operatord.py",
    "tools/operator_naming.py",
    "tests/runtime/test_multi_task_runner_submit_path.py",
)

# Roots scanned for direct send-keys usage.
SCAN_ROOTS: tuple[str, ...] = ("lib", "tools")

# Top-level scripts also included in the scan.
ROOT_SCRIPTS: tuple[str, ...] = ("solar-harness.sh", "coordinator.sh")

# Suffixes scanned.
SCAN_SUFFIXES: tuple[str, ...] = (".py", ".sh")

# Substring matches that exclude a path from the scan.
SCAN_EXCLUDES: tuple[str, ...] = (
    "__pycache__",
    "/.git/",
    ".bak",  # historical backups: .bak-pre-pull-..., .bak-20260520T...
)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

# Shell-style invocation: ``tmux send-keys`` outside of a leading-# comment.
_RE_SHELL_CALL = re.compile(r"\btmux\s+send-keys\b")

# Python list-style invocation: ["tmux", "send-keys", ...] (allow whitespace
# and either quote style).
_RE_PY_LIST = re.compile(
    r"""["']tmux["']\s*,\s*["']send-keys["']"""
)


def _strip_inline_comment(line: str, suffix: str) -> str:
    """Return ``line`` with any trailing inline comment removed.

    Naive stripping: cut at the first ``#`` that is not inside an obvious
    single- or double-quoted string on the same line.  Good enough for
    shell and Python lint usage; we are not parsing a full grammar.
    """
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
    return line


def file_contains_send_keys_text(path: Path) -> bool:
    """Plain-text check: file contains the substring ``tmux send-keys``
    anywhere (including comments and string literals)."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "tmux send-keys" in text or '"tmux", "send-keys"' in text or "'tmux', 'send-keys'" in text


def find_send_keys_callsites(path: Path) -> list[tuple[int, str]]:
    """Return list of ``(line_no, line)`` that look like actual call sites.

    Comment-only mentions and obvious docstring blocks are ignored.  This
    is intentionally conservative — false negatives are caught by the
    plain-text allowlist scan in ``file_contains_send_keys_text``.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    suffix = path.suffix
    in_py_docstring = False
    docstring_delim: str | None = None
    hits: list[tuple[int, str]] = []

    for line_no, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()

        # Skip blank lines.
        if not stripped:
            continue

        # Skip pure-comment lines (shell or Python).
        if stripped.startswith("#"):
            continue

        # Best-effort Python docstring tracking.
        if suffix == ".py":
            if in_py_docstring:
                assert docstring_delim is not None
                if docstring_delim in raw:
                    in_py_docstring = False
                    docstring_delim = None
                continue
            saw_single_line_docstring = False
            for delim in ('"""', "'''"):
                if stripped.startswith(delim):
                    rest = stripped[3:]
                    if rest.endswith(delim) and len(rest) >= 3:
                        # Single-line docstring: skip the line entirely.
                        saw_single_line_docstring = True
                        break
                    in_py_docstring = True
                    docstring_delim = delim
                    break
            if saw_single_line_docstring or in_py_docstring:
                continue

        code = _strip_inline_comment(raw, suffix)

        if _RE_SHELL_CALL.search(code) or _RE_PY_LIST.search(code):
            hits.append((line_no, raw.rstrip()))

    return hits


def _iter_scan_files() -> list[Path]:
    """Enumerate every source file under SCAN_ROOTS + ROOT_SCRIPTS."""
    files: list[Path] = []

    for root_name in SCAN_ROOTS:
        root = HARNESS_DIR / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in SCAN_SUFFIXES:
                continue
            spath = str(path)
            if any(skip in spath for skip in SCAN_EXCLUDES):
                continue
            files.append(path)

    for script in ROOT_SCRIPTS:
        sp = HARNESS_DIR / script
        if sp.is_file():
            files.append(sp)

    return sorted(set(files))


def _rel(p: Path) -> str:
    return str(p.relative_to(HARNESS_DIR))


# ---------------------------------------------------------------------------
# Tests — the actual lint gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel_path", DENYLIST)
def test_denylist_files_have_no_send_keys(rel_path: str) -> None:
    """New control-plane modules must contain ZERO ``tmux send-keys``.

    The operatord runtime dispatches via a file-inbox; injecting
    keystrokes into tmux from this layer is a contract violation
    (see contract for sprint-20260522-operatord-runtime-submit, Required
    Safety: "Direct ``tmux send-keys`` is not used for normal DAG
    dispatch in new code.").
    """
    abs_path = HARNESS_DIR / rel_path
    assert abs_path.is_file(), (
        f"Denylisted path {rel_path} is missing — denylist is stale; "
        "remove the entry or restore the file."
    )
    text = abs_path.read_text(encoding="utf-8", errors="ignore")
    forbidden = [
        marker
        for marker in ("tmux send-keys", '"tmux", "send-keys"', "'tmux', 'send-keys'")
        if marker in text
    ]
    assert not forbidden, (
        f"Denylisted file {rel_path} must not reference 'tmux send-keys' "
        f"(found markers: {forbidden}). The operatord control plane "
        "dispatches via the operator inbox, not tmux keystrokes."
    )


def test_no_unexpected_send_keys_callsites() -> None:
    """Any file outside the allowlist that calls ``tmux send-keys`` fails."""
    allow_abs = {(HARNESS_DIR / k).resolve() for k in ALLOWLIST}
    offenders: list[tuple[str, list[tuple[int, str]]]] = []

    for path in _iter_scan_files():
        if path.resolve() in allow_abs:
            continue
        hits = find_send_keys_callsites(path)
        if hits:
            offenders.append((_rel(path), hits))

    if offenders:
        msg_lines = [
            "Found direct `tmux send-keys` calls outside the allowlist.",
            "",
            "New DAG-dispatch code must dispatch via operator_runtime.submit",
            "(file-inbox), not by injecting keystrokes into tmux.",
            "",
            "If this is intentional legacy/adapter code, add the file to",
            "ALLOWLIST in tests/test_no_direct_tmux_send_keys.py with a",
            "category and one-line rationale.",
            "",
            "Offending files:",
        ]
        for rel, hits in offenders:
            msg_lines.append(f"  {rel}:")
            for line_no, line in hits:
                msg_lines.append(f"    line {line_no}: {line}")
        pytest.fail("\n".join(msg_lines))


def test_allowlist_paths_exist() -> None:
    """Allowlist entries must point at real files."""
    missing = [
        rel for rel in ALLOWLIST
        if not (HARNESS_DIR / rel).is_file()
    ]
    assert not missing, (
        f"Allowlist contains stale entries (file missing): {missing}. "
        "Remove them from ALLOWLIST."
    )


def test_allowlist_entries_still_have_send_keys() -> None:
    """An allowlisted file that no longer references ``tmux send-keys``
    should be removed from the allowlist so the lint stays tight."""
    stale: list[str] = []
    for rel in ALLOWLIST:
        path = HARNESS_DIR / rel
        if not path.is_file():
            continue  # covered by test_allowlist_paths_exist
        if not file_contains_send_keys_text(path):
            stale.append(rel)
    assert not stale, (
        "Allowlist entries no longer contain 'tmux send-keys' — they "
        "should be removed so any future regression trips the gate: "
        f"{stale}"
    )


def test_scanner_detects_synthetic_violation(tmp_path: Path) -> None:
    """Self-test: scanner flags a file that calls ``tmux send-keys``."""
    bad_py = tmp_path / "fake_dispatcher.py"
    bad_py.write_text(
        "import subprocess\n"
        "def dispatch(pane, cmd):\n"
        "    subprocess.run(['tmux', 'send-keys', '-t', pane, cmd, 'Enter'])\n",
        encoding="utf-8",
    )
    hits = find_send_keys_callsites(bad_py)
    assert hits, "Scanner failed to detect a Python list-form send-keys call"
    assert any("send-keys" in line for _, line in hits)

    bad_sh = tmp_path / "fake_dispatch.sh"
    bad_sh.write_text(
        "#!/usr/bin/env bash\n"
        'pane="$1"\n'
        'tmux send-keys -t "$pane" "echo hi" Enter\n',
        encoding="utf-8",
    )
    hits_sh = find_send_keys_callsites(bad_sh)
    assert hits_sh, "Scanner failed to detect a shell-form send-keys call"


def test_scanner_ignores_comment_only_mention(tmp_path: Path) -> None:
    """Self-test: scanner does not flag pure-comment mentions.

    This guards the contract: comments that *document* the rule (e.g.
    ``# coordinator.sh must NOT call tmux send-keys directly``) should
    not be misclassified as real call sites.  The allowlist still
    governs whether the file is permitted to contain the text at all,
    but the call-pattern scanner must be precise enough to discriminate.
    """
    ok_py = tmp_path / "docs_only.py"
    ok_py.write_text(
        '"""This module describes the tmux send-keys antipattern."""\n'
        "# Do not call tmux send-keys directly from new code.\n"
        "VALUE = 1\n",
        encoding="utf-8",
    )
    assert find_send_keys_callsites(ok_py) == []

    ok_sh = tmp_path / "docs_only.sh"
    ok_sh.write_text(
        "#!/usr/bin/env bash\n"
        "# tmux send-keys is forbidden in DAG dispatch.\n"
        "echo ok\n",
        encoding="utf-8",
    )
    assert find_send_keys_callsites(ok_sh) == []


# ---------------------------------------------------------------------------
# Convenience: lets a human run `python tests/test_no_direct_tmux_send_keys.py`
# to print the current scan state.  Not used by pytest.
# ---------------------------------------------------------------------------


def _main() -> int:
    files = _iter_scan_files()
    with_send_keys = [p for p in files if file_contains_send_keys_text(p)]
    print(f"Scanned {len(files)} files, {len(with_send_keys)} contain 'tmux send-keys':")
    allow_abs = {(HARNESS_DIR / k).resolve() for k in ALLOWLIST}
    for p in with_send_keys:
        marker = "ALLOW" if p.resolve() in allow_abs else "DENY "
        print(f"  [{marker}] {_rel(p)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
