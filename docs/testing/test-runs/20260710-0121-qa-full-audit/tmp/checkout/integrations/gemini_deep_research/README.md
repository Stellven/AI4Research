# Gemini Deep Research Browser Integration

This integration provides browser automation to trigger, monitor, and retrieve reports from Gemini's Deep Research mode.

## CLI Usage

Run the operator script directly:
```bash
./harness/tools/gemini_deep_research_operator.py
```

## Environment Variables

- `BROWSER_AGENT_USER_DATA_DIR`: Path to the user data directory for Chrome profile persistence.
- `BROWSER_AGENT_PROFILE_DIRECTORY`: Name of the profile folder (default: `Profile 1`).
- `BROWSER_AGENT_GEMINI_URL`: Endpoint for Gemini UI (default: `https://gemini.google.com/app`).
- `BROWSER_AGENT_GEMINI_TIMEOUT`: Max timeout for execution in seconds (default: `1800`).

## Failover Retry Logic

In case of network issues or browser session timeouts, the operator automatically performs a configurable number of retries (up to 3 by default) with stability checkpoints.
