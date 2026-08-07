#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
GATE="$HARNESS_DIR/lib/wiki-quality-gate.py"

tmp="$(mktemp -d /tmp/wiki-quality-gate-page-dump.XXXXXX)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/references/paper-a"
cat > "$tmp/references/paper-a/page-008.md" <<'EOF'
---
source_pdf: /tmp/paper.pdf
source_page: 8
extraction_method: pymupdf
---

num_xcds = 8
pid_m = tl.program_id(0)
pid_n = tl.program_id(1)
pid = pid_m * (N // BLOCK_SIZE_N) + pid_n
Figure 10: SwizzlePerf-generated swizzling pattern for transpose kernel.
EOF

cat > "$tmp/references/paper-a/index.md" <<'EOF'
---
source_pdf: /tmp/paper.pdf
source_pages: 1
extraction_method: pymupdf
---

# paper.pdf

> Extracted by MinerU (pymupdf)

Abstract
This is raw paper text.

---
*Full content split into 1 page file(s) in this directory.*
EOF

cat > "$tmp/references/paper-a-deep.md" <<'EOF'
---
title: "Paper A"
---

# Paper A

## 论点

This is a structured note.

## 问题

It has knowledge structure.

## 方法

It is not a page dump.

## 来源

Source tracked.
EOF

out="$(python3 "$GATE" --vault "$tmp" --json || true)"
printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["low_quality_count"] == 2; reasons=[set(x["reasons"]) for x in d["findings"]]; assert any("raw_pdf_page_dump" in r for r in reasons); assert any("raw_pdf_index_dump" in r for r in reasons); assert d["graph"]["doc_count"] == 1'

python3 "$GATE" --vault "$tmp" --apply --json >/tmp/wiki-quality-gate-page-dump-apply.json
test ! -e "$tmp/references/paper-a/page-008.md"
test ! -e "$tmp/references/paper-a/index.md"
test -e "$tmp/references/paper-a-deep.md"

printf 'ok\n'
