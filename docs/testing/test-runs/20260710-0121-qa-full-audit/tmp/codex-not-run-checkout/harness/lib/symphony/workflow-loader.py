#!/usr/bin/env python3
"""Workflow Loader — parses WORKFLOW.solar.md YAML front matter."""

import os
import re
import sys


class WorkflowValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("Workflow validation failed:\n" + "\n".join(f"  - {e}" for e in errors))


_HOOK_LIFECYCLE_KEYS = {
    "pre_claim_workspace",
    "post_claim_workspace",
    "pre_release_workspace",
    "post_release_workspace",
}
_HOOK_ON_FAILURE = {"fail", "continue"}


def load_workflow(path=None):
    if path is None:
        harness_dir = os.path.expanduser("~/.solar/harness")
        path = os.path.join(harness_dir, "templates", "WORKFLOW.solar.md")

    if not os.path.isfile(path):
        return {}

    with open(path, "r") as f:
        content = f.read()

    # Extract YAML front matter between --- markers
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    yaml_str = match.group(1)
    config = _parse_simple_yaml(yaml_str)
    return config


def get_hooks(config):
    """Extract structured hooks config from flat dotted-key config dict."""
    hooks = {}
    global_timeout = config.get("hooks.global_timeout_ms")
    if global_timeout is not None:
        hooks["global_timeout_ms"] = global_timeout

    for lifecycle_key in _HOOK_LIFECYCLE_KEYS:
        prefix = f"hooks.{lifecycle_key}."
        hook_cfg = {}
        for k, v in config.items():
            if k.startswith(prefix):
                field = k[len(prefix):]
                hook_cfg[field] = v
        if hook_cfg:
            hooks[lifecycle_key] = hook_cfg

    return hooks


def validate_hooks(config):
    """Validate hooks section of config. Returns list of error strings (empty = valid)."""
    errors = []

    global_timeout = config.get("hooks.global_timeout_ms")
    if global_timeout is not None and not isinstance(global_timeout, int):
        errors.append("hooks.global_timeout_ms must be an integer")

    for lifecycle_key in _HOOK_LIFECYCLE_KEYS:
        cmd_key = f"hooks.{lifecycle_key}.command"
        on_fail_key = f"hooks.{lifecycle_key}.on_failure"
        timeout_key = f"hooks.{lifecycle_key}.timeout_ms"

        # If any sub-key exists for this hook, validate it
        hook_keys = [k for k in config if k.startswith(f"hooks.{lifecycle_key}.")]
        if not hook_keys:
            continue

        if cmd_key not in config:
            errors.append(f"hooks.{lifecycle_key}.command: required when hook is defined")

        on_fail = config.get(on_fail_key, "fail")
        if on_fail not in _HOOK_ON_FAILURE:
            errors.append(f"hooks.{lifecycle_key}.on_failure: must be 'fail' or 'continue', got '{on_fail}'")

        timeout_val = config.get(timeout_key)
        if timeout_val is not None and not isinstance(timeout_val, int):
            errors.append(f"hooks.{lifecycle_key}.timeout_ms: must be an integer")

    return errors


def _parse_list_value(value):
    """Parse inline YAML list: ["a","b"] or ['a','b'] → ["a","b"]. Returns None if not a list."""
    if not (value.startswith("[") and value.endswith("]")):
        return None
    inner = value[1:-1].strip()
    if not inner:
        return []
    items = []
    for item in inner.split(","):
        item = item.strip().strip('"').strip("'")
        if item:
            items.append(item)
    return items


def _parse_simple_yaml(text):
    """Minimal YAML parser for flat/nested key-value pairs and inline lists."""
    result = {}
    prefix_stack = []

    for line in text.split("\n"):
        stripped = line.rstrip()
        if not stripped or stripped.startswith("#"):
            continue

        key_match = re.match(r"(\s*)([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)", stripped)
        if not key_match:
            continue

        key = key_match.group(2)
        value = key_match.group(3).strip()

        key_indent = len(key_match.group(1))
        level = key_indent // 2

        # Build dotted path
        parts = []
        for i in range(level):
            if i < len(prefix_stack):
                parts.append(prefix_stack[i])
        parts.append(key)
        full_key = ".".join(parts)

        # Track nesting
        if level < len(prefix_stack):
            prefix_stack = prefix_stack[:level]
        if not value:
            prefix_stack.append(key)
            continue

        # Parse value — check list first, then scalar
        list_val = _parse_list_value(value)
        if list_val is not None:
            result[full_key] = list_val
        elif value.startswith('"') and value.endswith('"'):
            result[full_key] = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            result[full_key] = value[1:-1]
        elif value.startswith("${") and value.endswith("}"):
            result[full_key] = value
        elif value.isdigit():
            result[full_key] = int(value)
        else:
            result[full_key] = value

    return result


if __name__ == "__main__":
    args = sys.argv[1:]
    validate_mode = False
    path = None

    i = 0
    while i < len(args):
        if args[i] == "--validate":
            validate_mode = True
            i += 1
        else:
            path = args[i]
            i += 1

    config = load_workflow(path)

    if validate_mode:
        errors = validate_hooks(config)
        if errors:
            for e in errors:
                print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        hooks = get_hooks(config)
        hook_count = len([k for k in hooks if k != "global_timeout_ms"])
        print(f"hooks ok valid ({hook_count} lifecycle hooks defined)")
        sys.exit(0)

    for k, v in sorted(config.items()):
        print(f"  {k}: {v}")
