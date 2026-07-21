"""Shared TUI pane overlay classification.

The key rule: tmux capture includes scrollback. A permissions/survey/proceed
prompt is only actionable when it is still after the latest live Claude prompt.
If a clean prompt/footer appears after it, the text is stale history and must
not block scheduling or recovery decisions.
"""

from __future__ import annotations

import re


FOOTER_RE = re.compile(
    r"⏵.*(auto|accept edits|edit|bypass permissions).*mode on|shift\+tab|esc to interrupt|/effort",
    re.I,
)
SURVEY_RE = re.compile(
    r"How is Claude doing this session\?|1:\s*Bad\s+2:\s*Fine\s+3:\s*Good\s+0:\s*Dismiss|survey_blocked",
    re.I,
)
PERMISSION_RE = re.compile(
    r"permissions?_prompt_blocked|pane_permissions_prompt_blocked|Do you want to make this edit|"
    r"allow all edits during this session|allow this command|approval required",
    re.I,
)
PROCEED_RE = re.compile(r"Do you want to proceed\?|Would you like to proceed\?|Enter to confirm|Esc to cancel", re.I)
QUEUED_RE = re.compile(r"Press up to edit queued messages|ready_for_builder|ready_for_evaluator|graph_node_idle_assigned", re.I)

OVERLAY_PATTERNS = {
    "survey": SURVEY_RE,
    "permission": PERMISSION_RE,
    "proceed": PROCEED_RE,
    "queued_input": QUEUED_RE,
}


def live_prompt_index(lines: list[str], footer_at: int | None = None) -> int:
    footer_at = len(lines) if footer_at is None else footer_at
    for idx in reversed([i for i, line in enumerate(lines) if "❯" in line]):
        if idx <= footer_at and footer_at - idx <= 8:
            return idx
    return -1


def tail_has_idle_prompt_footer(text: str) -> bool:
    lines = [line.rstrip() for line in str(text or "").splitlines()]
    saw_footer = False
    for line in reversed(lines[-12:]):
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if stripped.startswith("────────────────") or stripped.isdigit():
            continue
        if stripped.startswith("❯"):
            remainder = stripped[1:].strip()
            return remainder.startswith("Try ") or (not remainder and saw_footer)
        if FOOTER_RE.search(stripped) or lowered.startswith(("esc ", "tab ", "interrupt")) or "tokens" in lowered:
            saw_footer = True
            continue
        return False
    return False


def prompt_match_is_stale(text: str, match: re.Match[str] | None) -> bool:
    if match is None:
        return False
    after = str(text or "")[match.end():]
    return bool(re.search(r"❯[\s\u00a0]+Try\s+\"", after)) or tail_has_idle_prompt_footer(after)


def pane_overlay_detail(tail: str) -> dict:
    lines = str(tail or "").splitlines()
    if not lines:
        return {"state": "none", "type": "", "detail": ""}
    footer_indexes = [idx for idx, line in enumerate(lines) if FOOTER_RE.search(line)]
    footer_at = footer_indexes[-1] if footer_indexes else len(lines)
    live_prompt_at = live_prompt_index(lines, footer_at)
    newest_match: tuple[int, str, str] | None = None
    for idx, line in enumerate(lines):
        for kind, pattern in OVERLAY_PATTERNS.items():
            if pattern.search(line):
                newest_match = (idx, kind, line.strip())
    if newest_match is None:
        return {"state": "none", "type": "", "detail": ""}
    match_at, kind, detail = newest_match
    if live_prompt_at >= 0 and live_prompt_at > match_at:
        return {"state": "stale_scrollback_ignored", "type": kind, "detail": detail[:240]}
    return {"state": "pane_overlay_blocked", "type": kind, "detail": detail[:240]}


def pane_overlay_blocked(tail: str, *kinds: str) -> bool:
    detail = pane_overlay_detail(tail)
    if detail.get("state") != "pane_overlay_blocked":
        return False
    return not kinds or str(detail.get("type") or "") in set(kinds)
