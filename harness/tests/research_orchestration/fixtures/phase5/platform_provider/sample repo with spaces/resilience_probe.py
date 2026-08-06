"""Tiny repository fixture for Phase 5 platform/provider smoke tests."""


def summarize_resilience_signal(events):
    """Return a deterministic status summary for provider resilience events."""

    completed = [event for event in events if event.get("status") == "completed"]
    failed = [event for event in events if event.get("status") == "failed"]
    return {
        "completed_count": len(completed),
        "failed_count": len(failed),
        "has_platform_path_check": any(
            "path" in str(event.get("kind", "")).lower() for event in events
        ),
    }
