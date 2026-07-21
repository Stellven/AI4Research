# Solar Knowledge Capture Chrome Extension

Click the extension icon to capture the current page into the Solar knowledge ingest pipeline.

- ChatGPT pages are captured from the rendered DOM as structured `user` / `assistant` messages and imported through `/chatgpt-import`.
- If ChatGPT changes its primary DOM marker, the extension falls back to conversation-turn/article selectors instead of silently failing.
- Other JS-heavy pages are captured from `article` / `main` / `body` readable text through `/capture`.
- The local server must be running: `solar-harness wiki capture-server start --port 8788`.

Recommended unpacked install path:

- MacBook: `~/Solar/harness/extensions/chatgpt-knowledge-capture`
- Mac mini: `~/Solar/harness/extensions/chatgpt-knowledge-capture`
