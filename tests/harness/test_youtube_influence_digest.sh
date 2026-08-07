#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-${HOME}/Solar/harness}"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
PUBLISHED_AT="$(python3 - <<'PY'
import datetime as dt
print((dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S+00:00"))
PY
)"

cat > "$TMPDIR/config.yaml" <<YAML
version: 1
mac_mini_only: false
allowed_hostnames: []
output:
  raw_dir: "$TMPDIR/raw"
  state_dir: "$TMPDIR/state"
  max_videos_per_run: 10
  per_channel_limit: 2
  lookback_hours: 168
  keep_seen_days: 7
  transcript_max_chars: 20000
fetch:
  timeout_seconds: 1
  sleep_between_channels_seconds: 0
  sleep_between_videos_seconds: 0
channels:
  - channel_id: UC_x5XG1OV2P6uZZ5FSM9Ttw
    name: Google Developers
    category: 开发、工具与产品前沿
    priority: tier1
analysis_keywords:
  model_release: [model, launch, benchmark]
  agent: [agent, automation]
  tutorial: [tutorial, demo, build]
YAML

cat > "$TMPDIR/feed.xml" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
  <entry>
    <yt:videoId>abc123xyz00</yt:videoId>
    <title>Build an AI agent demo with tools</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=abc123xyz00"/>
    <published>${PUBLISHED_AT}</published>
  </entry>
</feed>
XML

cat > "$TMPDIR/transcript.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<transcript>
  <text start="0" dur="2">Today we build an AI agent demo with tools.</text>
  <text start="2" dur="2">The workflow shows automation and evaluation.</text>
</transcript>
XML

python3 "$ROOT/scripts/youtube_influence_digest.py" \
  --config "$TMPDIR/config.yaml" \
  --fixture-feed "$TMPDIR/feed.xml" \
  --fixture-transcript "$TMPDIR/transcript.xml" \
  --force-host >/tmp/youtube-digest-test.out

test -f "$TMPDIR/raw/latest.md"
grep -q "Classified Table" "$TMPDIR/raw/latest.md"
grep -q "Build an AI agent demo with tools" "$TMPDIR/raw/latest.md"
grep -q "transcripts_ok: 1" "$TMPDIR/raw/latest.md"
find "$TMPDIR/raw" -path '*/videos/*.md' -type f | grep -q .
grep -R "Today we build an AI agent demo" "$TMPDIR/raw" >/dev/null

echo "ok: youtube influence digest fixture test passed"
