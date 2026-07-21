"""Descriptor for Playwright CDP auth execution."""
from __future__ import annotations


def executor_descriptor() -> dict[str, object]:
    return {
        "kind": "playwright_cdp_executor",
        "runtime_owner": "browser_use",
        "capabilities": ["cdp_attach", "precise_page_control", "complex_dialogs"],
    }
