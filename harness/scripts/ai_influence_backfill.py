#!/usr/bin/env python3
"""
Backfill script for AI Influence data.
Runs the DOM scraper with multiple scrolls to gather ~30 days of data,
then organizes the JSON output by Week/Day/Handle.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

def run_backfill(handles: list[str], output_dir: str, days: int = 30):
    scraper_path = str(Path(__file__).resolve().parent.parent / "tools" / "playwright_twitter_scraper.py")
    python_bin = "~/.claude/mcp-servers/browser-use/.venv/bin/python"

    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(days=days)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    for handle in handles:
        handle = handle.strip()
        if not handle or handle.startswith("#"):
            continue

        print(f"Scraping @{handle} with 15 scrolls for {days} days of history...")
        try:
            proc = subprocess.run(
                [python_bin, scraper_path, handle, "--scrolls", "15"],
                capture_output=True, text=True, timeout=120
            )

            if proc.returncode != 0:
                print(f"Error scraping {handle}: {proc.stderr}")
                continue

            output = json.loads(proc.stdout)
            if "error" in output:
                print(f"Error from scraper for {handle}: {output['error']}")
                continue

            items = output.get("result", [])
            valid_items = []

            for item in items:
                pub_str = item.get("published_at")
                if not pub_str:
                    continue

                try:
                    pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except ValueError:
                    continue

                # Skip if older than 30 days
                if pub_dt < cutoff_date:
                    continue

                # Skip invalid links
                url = item.get("tweet_url", "")
                if not url or "/status/" not in url:
                    continue

                # Determine folder structure
                week_str = pub_dt.strftime("%G-W%V")
                day_str = pub_dt.strftime("%Y-%m-%d")

                valid_items.append({
                    "item": item,
                    "week": week_str,
                    "day": day_str,
                    "id": url.split("/")[-1]
                })

            print(f"Found {len(valid_items)} tweets for @{handle} in the last {days} days.")

            # Group by day to save into files
            day_groups = {}
            for v in valid_items:
                path_key = (v["week"], v["day"])
                if path_key not in day_groups:
                    day_groups[path_key] = []
                # Deduplicate by ID
                if not any(x["tweet_url"] == v["item"]["tweet_url"] for x in day_groups[path_key]):
                    day_groups[path_key].append(v["item"])

            for (week, day), daily_items in day_groups.items():
                target_dir = out_path / week / day
                target_dir.mkdir(parents=True, exist_ok=True)

                file_path = target_dir / f"{handle}.json"
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(daily_items, f, ensure_ascii=False, indent=2)

                print(f"  Saved {len(daily_items)} tweets to {file_path}")

        except Exception as e:
            print(f"Unexpected error for {handle}: {e}")

if __name__ == "__main__":
    accounts_file = Path(__file__).resolve().parent.parent / "ai-influence-digest" / "references" / "accounts_extended.txt"

    raw_lines = accounts_file.read_text().splitlines()
    handles = []
    for line in raw_lines:
        if not line.strip() or line.startswith("Tier"):
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            handle = parts[2].strip().lstrip("@")
            if handle:
                handles.append(handle)

    target_dir = str(Path.home() / "Knowledge" / "_raw" / "ai-influence-daily-digest" / "backfill")

    run_backfill(handles, target_dir)
    print("Backfill complete.")
