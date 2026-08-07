# HTML Renderer Migration

## Default Path

Solar Harness now routes human-readable sprint HTML through `html_anything_adapter.py` by default.

Covered surfaces:
- `prd.html`
- `planning.html`
- `design.html`

The adapter preserves single-file, self-contained HTML and adds explicit renderer markers:
- `meta[name="x-solar-renderer"][content="html-anything"]`
- `meta[name="x-html-anything-profile"]`

## Upstream Pin

- Repo: `https://github.com/nexu-io/html-anything.git`
- Commit: `145a40ebd79624bbd6a28ec379148a895896573c`
- Local checkout target: `~/.solar/harness/vendor/html-anything-upstream`

The integration uses html-anything's profile family and editorial surface language as the default reader-facing HTML shell. Solar keeps the semantic section assembly in Python so existing DAG/coverage/export behavior remains stable.

## Fallback

Set:

```bash
export SOLAR_USE_LEGACY_RENDERER=1
```

This forces `render_sprint_html.py` to use the old inline template path instead of the html-anything adapter.

## Rollback

1. Set `SOLAR_USE_LEGACY_RENDERER=1`.
2. Re-render `prd.html`, `planning.html`, or `design.html`.
3. Keep canonical Markdown/JSON artifacts unchanged.
4. Remove the env var after adapter issues are fixed.

## Self-Contained Guarantee

The adapter strips external `<script src>`, stylesheet `<link>`, and CSS `@import` references before writing the final document. Rendered files must not depend on CDN assets.

## Validation

Run:

```bash
bash ~/Solar/tests/harness/test_html_anything_adapter.sh
bash ~/Solar/tests/harness/test_html_artifact_helper.sh
bash ~/Solar/tests/harness/test_pm_planner_html_artifacts.sh
bash ~/Solar/tests/harness/test_accepted_artifact_knowledge_sync.sh
```
