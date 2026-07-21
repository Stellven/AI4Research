"""Source workers for solar-harness refresh.

Each module exports a single function:
    fetch(deep: bool, deadline: float) -> dict
where `deadline` is a time.monotonic() absolute deadline and the returned dict
has shape {name, status, duration_ms, note}.
"""
