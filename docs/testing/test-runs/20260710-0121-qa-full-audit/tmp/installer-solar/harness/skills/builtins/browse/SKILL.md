---
name: browse
namespace: builtin
status: stable
version: "1.0"
description: "Web browsing — navigate URLs, extract content, screenshot via playwright MCP"
tags: [web, browser, playwright]
min_score: 0.75
author: solar-harness
created_at: "2026-05-09T00:00:00Z"
---

# Skill: browse

Navigate to URLs, extract text content, and capture screenshots using playwright MCP.

## Trigger

User says: `浏览`, `打开网页`, `browse`, `/browse`

## Steps

1. **Navigate** — `mcp__playwright__browser_navigate` to target URL
2. **Snapshot** — `mcp__playwright__browser_snapshot` to get page structure
3. **Extract** — locate relevant content sections
4. **Screenshot** (if needed) — `mcp__playwright__browser_take_screenshot`
5. **Summarize** — structured output of findings

## Rules

- Primary tool: playwright MCP (`mcp__playwright__*`)
- Fallback: browser-use MCP (`mcp__browser-use__*`) if playwright unavailable
- Never use WebSearch / WebFetch as substitutes for actual page rendering
- Respect robots.txt and rate limits

## Done when

Target content extracted and summarized; screenshot saved to /tmp if requested.
