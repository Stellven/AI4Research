# Mermaid Viewer Integration

Status: implemented  
Source: https://github.com/mermaid-js/mermaid  
Local package: `~/.solar/harness/vendor/mermaid-viewer/node_modules/mermaid`

## What It Does

Solar status-server can now browse and render `.mmd` files directly:

```bash
solar-harness mermaid --open
solar-harness mermaid ~/.solar/harness/reports/solar-system-architecture-20260508.mmd --open
```

URLs:

```text
http://127.0.0.1:8765/mermaid
http://127.0.0.1:8765/mermaid/view?file=<absolute-or-allowed-relative-mmd-path>
http://127.0.0.1:8765/mermaid/raw?file=<absolute-or-allowed-relative-mmd-path>
```

The main Solar Status page also has an `架构图` tab with an embedded viewer.

## Security Boundary

The server only reads `.mmd` files under:

- `~/.solar/harness`
- `~/Knowledge`

Mermaid static assets are served from:

```text
~/.solar/harness/vendor/mermaid-viewer/node_modules/mermaid/dist
```

No arbitrary local file read is exposed.

## Runtime

The browser imports Mermaid from the local vendored ESM bundle:

```text
/mermaid/assets/mermaid.esm.min.mjs
```

This keeps rendering local and avoids a CDN dependency.
