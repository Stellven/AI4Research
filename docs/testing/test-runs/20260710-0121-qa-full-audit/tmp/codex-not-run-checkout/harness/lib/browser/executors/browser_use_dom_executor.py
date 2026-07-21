"""Descriptor for browser-use DOM/evaluate auth execution."""
from __future__ import annotations


def executor_descriptor() -> dict[str, object]:
    return {
        "kind": "browser_use_dom_executor",
        "runtime_owner": "browser_use",
        "capabilities": ["login_clicks", "dom_evaluate", "account_selection"],
    }
