#!/usr/bin/env python3
"""Solar Sprint Issue Adapter — normalizes Solar sprint status to Symphony Issue model."""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
SPRINTS_DIR = os.path.join(HARNESS_DIR, "sprints")

STATE_MAP = {
    "drafting": "draft",
    "approved": "active",
    "active": "active",
    "planning": "planning",
    "reviewing": "in_review",
    "ready_for_review": "in_review",
    "passed": "completed",
    "done": "completed",
    "eval_pass": "completed",
    "failed_review": "failed_review",
    "failed": "failed_review",
    "cancelled": "cancelled",
    "interrupted": "interrupted",
    "superseded": "cancelled",
    "needs_human_review": "in_review",
    "blocked": "blocked",
}

PRIORITY_MAP = {
    "P0": "P0",
    "P1": "P1",
    "P2": "P2",
    "P3": "P3",
}


def sanitize_key(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", key)


def sprint_to_issue(status: dict) -> dict:
    sid = status.get("id", "unknown")
    identifier = "SYM-" + re.sub(r"^sprint-\d{8}-", "", sid).upper()[:6]

    title = status.get("title", "")
    solar_state = status.get("status", "drafting")
    symphony_state = STATE_MAP.get(solar_state, "unknown")

    priority = "P0"
    contract_path = os.path.join(SPRINTS_DIR, f"{sid}.contract.md")

    # Try to extract priority from contract
    if os.path.isfile(contract_path):
        try:
            with open(contract_path, "r") as f:
                content = f.read(2000)
            for line in content.split("\n"):
                low = line.lower().strip()
                if low.startswith("priority"):
                    for p in ["P0", "P1", "P2", "P3"]:
                        if p in line:
                            priority = p
                            break
                    break
        except Exception:
            pass

    # Labels from contract keywords
    labels = []
    if os.path.isfile(contract_path):
        try:
            with open(contract_path, "r") as f:
                content = f.read(2000).lower()
            if "symphony" in content:
                labels.append("symphony")
            if "integration" in content:
                labels.append("integration")
            if "security" in content:
                labels.append("security")
        except Exception:
            pass

    return {
        "id": sid,
        "identifier": identifier,
        "title": title,
        "description": status.get("phase", ""),
        "priority": priority,
        "state": symphony_state,
        "labels": labels,
        "blocked_by": [],
        "created_at": status.get("created_at", ""),
        "updated_at": status.get("updated_at", status.get("created_at", "")),
        "contract_path": contract_path,
    }


def list_issues(states: list = None) -> list:
    issues = []
    pattern = os.path.join(SPRINTS_DIR, "*.status.json")
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, "r") as f:
                status = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        issue = sprint_to_issue(status)

        if states:
            if issue["state"] not in states:
                # Also check raw Solar state
                raw = status.get("status", "")
                if raw not in states:
                    continue

        issues.append(issue)

    # Sort by priority then created_at
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    issues.sort(key=lambda i: (priority_order.get(i["priority"], 9), i["created_at"]))
    return issues


def get_one(sprint_id: str) -> dict:
    path = os.path.join(SPRINTS_DIR, f"{sprint_id}.status.json")
    if not os.path.isfile(path):
        print(f"Error: sprint not found: {sprint_id}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r") as f:
        status = json.load(f)
    return sprint_to_issue(status)


def main():
    parser = argparse.ArgumentParser(description="Solar Sprint Issue Adapter")
    parser.add_argument("--list", action="store_true", help="List all issues as JSON")
    parser.add_argument("--one", metavar="SPRINT_ID", help="Get single issue by sprint ID")
    parser.add_argument("--states", default="", help="Comma-separated state filter")
    args = parser.parse_args()

    if args.one:
        issue = get_one(args.one)
        print(json.dumps(issue, indent=2, ensure_ascii=False))
        return

    states = [s.strip() for s in args.states.split(",") if s.strip()] if args.states else None
    issues = list_issues(states)
    print(json.dumps(issues, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
