"""RC9 watchdog pane recovery must preserve the selected runtime.

The normal pane launcher supports both Claude and Codex, but the watchdog's
legacy restart path called ``start-incarnation.sh`` unconditionally.  That
script is Claude-only, so a Codex session could unexpectedly open Claude OAuth
after a pane exited.  These source-contract checks pin the recovery wiring;
the installed live rung supplies the real tmux/runtime proof.
"""

from __future__ import annotations

from pathlib import Path


_HARNESS = Path(__file__).resolve().parents[2]
_WATCHDOG = _HARNESS / "coordinator-watchdog.sh"


def _source() -> str:
    return _WATCHDOG.read_text(encoding="utf-8")


def _restart_block(source: str) -> str:
    start = source.index("    # 重启 pane")
    end = source.index("    # 更新 rate-limit", start)
    return source[start:end]


def test_watchdog_resolves_runtime_from_the_owning_tmux_session() -> None:
    source = _source()

    assert "resolve_pane_restart_runtime()" in source
    assert 'tmux show-environment -t "$session" SOLAR_PANE_RUNTIME' in source
    assert 'case "$runtime" in' in source
    assert "claude|codex" in source


def test_codex_restart_uses_runtime_aware_launcher_and_explicit_runtime() -> None:
    block = _restart_block(_source())

    assert '_restart_runtime=$(resolve_pane_restart_runtime "$session")' in block
    assert 'if [[ "$_restart_runtime" == "codex" ]]' in block
    assert '_restart_launcher="pane-launcher.sh"' in block
    assert '_restart_launcher="start-incarnation.sh"' in block
    assert "SOLAR_PANE_RUNTIME='${_restart_runtime}'" in block
    assert "${_esc_h}/${_restart_launcher}" in block
    assert "${_esc_h}/start-incarnation.sh" not in block
