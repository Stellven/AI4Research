# Solar Harness Complete Source Package

**Package date:** 2026-07-16  
**Scope:** Solar Harness, Solar-native AutoSci integration, OpenSolar, BetterSolar/AI4Research, architecture, parity analysis, raw evidence, technical reports, and feature/QA workbooks.

This package preserves every Solar Harness source file available in the established project source set, including versioned duplicates and historical intermediate artifacts. It also includes the current feature-list workbook used for the Capability Capsule Level 2 discussion.

## Contents

- `files/` — 83 original source files, preserving their original filenames and Library-relative paths.
- `INCLUDED_FILES.csv` — one row per included file with category, size, and SHA-256 checksum.
- `ARCHIVE_MANIFEST.json` — machine-readable archive manifest and verification totals.
- `REFERENCE_ONLY_SOURCES.md` — repositories, branches, commits, papers, conversations, code paths, and historical local paths that were referenced but were not separate stored file objects.

## Completeness rules

- Original `.md`, `.txt`, `.yaml`, `.html`, `.docx`, `.xlsx`, `.pptx`, `.png`, `.zip`, and `.tgz` bytes are retained.
- Historical versions and apparent duplicates are intentionally retained because they are distinct source artifacts.
- Existing `.zip` and `.tgz` inputs remain nested and unexpanded so their original bytes and checksums are preserved.
- Repository and paper URLs are recorded as references rather than replaced by newly downloaded material. This avoids silently substituting a newer repository head for the historical source state used in earlier work.
- Unrelated user files and unrelated projects are excluded.

The original source inventory is included at:

`files/AI4Research/solar_harness_source_inventory_2026-07-16.md`

