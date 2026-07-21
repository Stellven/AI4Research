# N3: Output Format, Validator, Archive Layout, and 2026-W21 Fixture Spec

sprint: `sprint-20260528-p0-ai-influence-youtube-报告流默认流程固化与验收-s01-requirements`
node: `N3`
generated_at: `2026-05-29`
status: `reviewing`
package_boundary: `spec_only` — no code, no CLI invocation, no archive write

Scope:
- O5: reader-facing source mapping schema
- O6: SVG embedding rules
- O7: report validator (8 checks)
- O8: archive layout + ChatGPT 杂项 session archival metadata
- O9: 2026-W21 fixture smoke spec

Out of scope: implementation of `validate-report`, `plan-ai-influence-reports`, or `render-ai-influence-report`. This file specifies contracts only; the executable code is the responsibility of S02–S04 builder sprints.

---

## Part 1: Source Mapping (O5)

### 1.1 Reader-facing 5-field schema

Every claim that cites a YouTube video MUST surface exactly these five fields, in this order, to the reader:

| Field | Type | Required | Example |
|---|---|---|---|
| `channel` | string | yes | `OpenAI Developers` |
| `title` | string | yes | `GPT-5 Live: Multimodal Agent Demo` |
| `published_at` | ISO-8601 date | yes | `2026-05-21` |
| `trust_level` | enum {`T0`,`T1`,`T2`} | yes | `T1` |
| `cited_segment_snippet` | string, 1–2 sentences, ≤ 280 chars | yes | `"GPT-5 reads the screen and clicks the booking button in 12 seconds."` |

Notes:
- `trust_level` MUST be one of `T0` / `T1` / `T2`. `T3` is never present here because T3 videos are excluded upstream by the transcript gate (see N1 §1.2).
- `cited_segment_snippet` is a verbatim or near-verbatim quote with leading/trailing ellipsis allowed only at the boundary; no internal `...` truncation (the validator rejects it — see §3.1 Check 3).
- All five fields are reader-facing and persistent in both the markdown body and the HTML render.

### 1.2 Forbidden internal fields (must NOT appear in reader-facing output)

| # | Forbidden token / field | Rationale |
|---|------------------------|-----------|
| 1 | `video_id` (bare 11-char YouTube ID, e.g. `dQw4w9WgXcQ`) | Internal handle; leaks pipeline mechanics |
| 2 | `V00x` (synthetic internal numeric handle, e.g. `V001`, `V042`) | Internal sequence; not reader-facing |
| 3 | `raw_refs` | Internal evidence-resolver reference list |
| 4 | `pipeline_fields` (`ingest_ts`, `worker_id`, `retry_count`, `stage`, etc.) | Processing telemetry; not editorial |
| 5 | `transcript_status` (`pending`, `failed`, `requeued`, `t3_excluded`, etc.) | Internal gate state; not reader-facing |
| 6 | `processing_log` (any pipeline log line, debug trace, retry note) | Internal observability; never enters reader text |

Each token in the forbidden list is also a grep-blacklist entry for validator Check 1 (§3.1).

### 1.3 Rendering example

**Markdown form** (canonical):

```markdown
> *"GPT-5 reads the screen and clicks the booking button in 12 seconds."*
>
> — **OpenAI Developers**, *GPT-5 Live: Multimodal Agent Demo*, 2026-05-21 · trust: **T1**
```

**HTML form** (post-render, used by archive):

```html
<blockquote class="evidence" data-trust="T1">
  <p class="quote">GPT-5 reads the screen and clicks the booking button in 12 seconds.</p>
  <footer>
    <cite class="channel">OpenAI Developers</cite> ·
    <cite class="title">GPT-5 Live: Multimodal Agent Demo</cite> ·
    <time datetime="2026-05-21">2026-05-21</time> ·
    <span class="trust">trust: T1</span>
  </footer>
</blockquote>
```

Constraints:
- `data-trust` attribute MUST equal one of `T0`/`T1`/`T2`.
- No `data-video-id`, `data-internal-id`, `data-pipeline-*` attributes (validator Check 1).
- Markdown citation footer MUST contain exactly four `·`-separated segments: channel, title, date, trust.

---

## Part 2: SVG Embedding Rules (O6)

### 2.1 Mandatory inline SVG

Every architecture / trend / distribution / timeline chart in the final HTML output MUST be inline `<svg>` markup, NOT `<img src="...png">`, NOT base64-encoded `<img>`, NOT a remote URL reference.

Permitted:
```html
<figure class="chart">
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 320" role="img" aria-label="GPT-5 launch timeline">
    <!-- inline path / rect / text elements -->
  </svg>
  <figcaption>Figure 1 — GPT-5 launch timeline (2026-W21)</figcaption>
</figure>
```

Forbidden:
```html
<img src="figure-1.png">                                 <!-- raster ref -->
<img src="data:image/png;base64,iVBORw0KGgo...">         <!-- inline raster -->
<img src="https://cdn.example/figure-1.svg">             <!-- remote SVG -->
<object type="image/svg+xml" data="figure-1.svg">        <!-- external object -->
<iframe src="chart.html">                                <!-- nested doc -->
```

### 2.2 ASCII chart prohibition in final output

ASCII / text-art charts (box-drawing characters, `|---|`, `+---+`, `▇`, `█`, mermaid-as-codeblock) are permitted ONLY during the planning / sketching stage in scratch notes. They MUST NOT appear in the rendered markdown or HTML report.

Specifically, any of the following inside the report body fails Check 4 (§3.1):
- Code fences containing 3+ lines of `─│┌┐└┘├┤┬┴┼` or `─-=+|.` ratios > 50% per non-whitespace line.
- Mermaid code fences (\`\`\`mermaid ... \`\`\`) — the mermaid source must be rendered to SVG before archive.
- Box-drawn frames or histograms (`█`, `▇`, `▆`, `▅`, `▄`, `▃`, `▂`, `▁`) used as chart bars.

### 2.3 SVG source spec

SVG markup is produced through one of two paths, in priority order:

**Path A — high-model direct emission** (preferred for trend / distribution / unique charts):
- The chapter writer (Browser Agent ChatGPT 5.5 Thinking high) is prompted to emit SVG inline.
- Constraint: prompt MUST require `viewBox`, `role="img"`, and `aria-label`.
- Constraint: prompt MUST forbid `<image href>` raster embedding.
- Output is captured verbatim into the report HTML.

**Path B — template generation** (preferred for timeline / architecture / repeating layouts):
- Local templates under `templates/ai-influence-report/charts/*.svg.jinja` are rendered with the structured data from the plan JSON.
- Template MUST be self-contained: no external CSS, no external font (web-safe fallback stack), no JavaScript.
- Output is also captured verbatim into the report HTML.

Either path: SVG element MUST include `xmlns="http://www.w3.org/2000/svg"`, a `viewBox`, and an accessible label (`aria-label` or `<title>` child).

---

## Part 3: Report Validator (O7)

### 3.1 The 8 mandatory checks

`validate-report --report <path/to/report.md>` runs the checks below in order. Any FAIL rejects the report and blocks archive (see §3.2). Exit code policy: §3.3.

| # | Check | Method | Pass criterion |
|---|-------|--------|----------------|
| 1 | No internal-vocabulary leak | grep over blacklist (§3.4) on both `report.md` and `report.html` | 0 matches across blacklist |
| 2 | No bare video_id leak | regex `\b[A-Za-z0-9_-]{11}\b` scanned over reader-facing body; allow-list = nothing | 0 matches (allow-list never overrides) |
| 3 | No truncation tail | inspect last 100 characters of report.md body | No trailing `...`, `TBD`, `TODO`, `(continued)`, half-sentence break (ends without `.`, `。`, `!`, `?`, `”`, `」`) |
| 4 | SVG present | parse report.html, count `<svg ` elements | ≥ 1 inline `<svg>`; 0 `<img>` whose `src` ends in `.png`/`.jpg`/`.jpeg`/`.gif`/`.webp` |
| 5 | evidence_map.json intact | load evidence_map.json; for every chapter `evidence_ref` in plan, an entry exists with channel/title/published_at/trust_level/cited_segment_snippet (the 5 required fields from §1.1) | every plan evidence_ref resolvable; every entry has all 5 fields non-empty |
| 6 | No T3 in core evidence | scan evidence_map.json for `trust_level == "T3"` | 0 entries with `trust_level == "T3"` |
| 7 | group_type whitelist | scan plan.json `groups[].group_type` | every value ∈ `{event, conference, keynote, interview, tutorial, product_update, other}` (7 values) |
| 8 | Hierarchy intact | parse plan.json: every `chapter` has a parent `trend`; every `subsection` has a parent `chapter` | no orphan node; no skipped level |

Notes:
- Check 1 also runs against the HTML render (post-template processing), since some forbidden tokens may be re-introduced by templating.
- Check 2's 11-char regex is the YouTube video ID format. False positives (legitimate 11-char tokens like commit SHAs) are minimized by restricting the scan to reader-facing prose blocks (not code fences with language `bash`/`json`/`yaml`).
- Check 4 forbids `<img>` rasters but allows `<img>` to inline-data SVG ONLY IF the `src` starts with `data:image/svg+xml;` — strongly discouraged; the preferred form is `<svg>` element directly.
- Checks 5–8 operate against the plan + evidence_map JSON files alongside the report.

### 3.2 Any-FAIL rejects archive policy

`validate-report` is the gate before `archive-report`. The pipeline contract is:

```
plan → render → validate → (PASS) → archive
                       └── (FAIL) → halt; emit FAIL report to stderr; non-zero exit
```

If `validate-report` returns non-zero, `archive-report` MUST NOT be invoked. Any harness orchestrator that bypasses `validate-report` is a contract violation and itself fails the smoke suite (§5).

### 3.3 Exit code policy

| Exit | Meaning | stderr / stdout |
|------|---------|-----------------|
| `0` | PASS — all 8 checks succeed | stdout: JSON `{"ok": true, "checks": {1..8: "pass"}}` |
| `1` | FAIL — at least one check failed | stderr: JSON `{"ok": false, "failed_checks": [{"id": N, "reason": "...", "evidence": "..."}, ...]}` |
| `2` | Operator error — bad arguments, missing report file, malformed JSON | stderr: human-readable error; stdout: empty |

Exit code `1` is the only signal `archive-report` consumes for the gate; exit code `2` halts the pipeline upstream (operator must re-issue the command).

### 3.4 Grep blacklist — explicit token list

Used by Check 1. Stored at `lib/ai-influence-report/forbidden-tokens.txt`, one token per line. Each token is grep-fixed-string matched (case-insensitive) against the report.md body and the report.html body.

Initial list (S01 baseline):

```
video_id
raw_refs
pipeline_fields
transcript_status
processing_log
ingest_ts
worker_id
retry_count
stage_id
pipeline_stage
t3_excluded
asr_confidence
internal_handle
debug_trace
```

Also matched by regex (separate from fixed-string list):
- `V[0-9]{3}` (case-sensitive, matches `V001`–`V999` internal handles)
- `\b[A-Za-z0-9_-]{11}\b` in reader-facing prose only (Check 2)

The blacklist is intentionally conservative — additional tokens MAY be added by S02 sprint without breaking the contract; tokens MUST NOT be removed without an explicit planner sprint.

---

## Part 4: Archive Layout (O8)

### 4.1 Archive path template

```
~/Knowledge/_raw/tech-hotspot-radar/ai-influence-planned/<YYYY-MM-DD>/reports/<report_slug>/
```

Where:
- `<YYYY-MM-DD>` is the report's plan date (the Monday of the ISO week, e.g. `2026-05-18` for 2026-W21).
- `<report_slug>` is `<week>-<topic-kebab>` (e.g. `2026-W21-gpt5-multimodal-launches`).

### 4.2 4 archive artifact types per report

Every report produces exactly these four files inside the report-slug directory:

| File | Format | Purpose |
|------|--------|---------|
| `report.md` | markdown | Editorial source (reader-facing) |
| `report.html` | HTML | Rendered output (SVG inline; embedded styles) |
| `plan.json` | JSON | Plan from `plan-ai-influence-reports`; preserved verbatim |
| `evidence_map.json` | JSON | Per-claim → 5-field source map (§1.1); used by validator Check 5 |

No other files are written by the standard pipeline. Optional sibling files (e.g. `chatgpt-session.json` for the metadata in §4.3) may exist but are not required for the validator gate.

### 4.3 ChatGPT 杂项 archive metadata

When a report is produced via Browser Agent on ChatGPT 5.5 Thinking high, the session MUST be archived to the ChatGPT project named **`杂项`** (literally: "Miscellaneous"). The harness records the link in a sidecar file:

`chatgpt-session.json` (sibling of `report.md`):

```json
{
  "session_id": "chatgpt-conv-<uuid>",
  "url": "https://chat.openai.com/c/<conversation-id>",
  "project": "杂项",
  "archived_at": "2026-05-29T03:15:00Z",
  "model": "gpt-5.5-thinking-high",
  "phase_breakdown": {
    "plan": "chatgpt-conv-<uuid>#plan",
    "chapter_write": ["chatgpt-conv-<uuid>#ch1", "chatgpt-conv-<uuid>#ch2"],
    "summary": "chatgpt-conv-<uuid>#summary"
  }
}
```

Constraints:
- `session_id` and `url` are mandatory; both MUST be non-empty.
- `project` MUST equal the literal string `杂项`.
- `archived_at` is the UTC timestamp when the session was moved into the 杂项 project (not the timestamp of the original conversation).
- The session URL MUST be reachable from the operator's authenticated ChatGPT account; the URL itself is not validated by `validate-report` (no network call inside the validator).

`chatgpt-session.json` is NOT one of the four required artifact types in §4.2 because the validator gate cannot reach the ChatGPT API; absence does not FAIL Check 5. However, audit tooling outside the validator MAY enforce its presence.

---

## Part 5: 2026-W21 Fixture Smoke Spec (O9)

### 5.1 Fixture data range

ISO week: `2026-W21` → Monday `2026-05-18` to Sunday `2026-05-24` (inclusive).

The fixture set is the subset of videos in the tech-hotspot-radar YouTube ingest whose `published_at` falls in `[2026-05-18T00:00:00Z, 2026-05-24T23:59:59Z]` AND whose transcript gate result is `T0`, `T1`, or `T2`. T3 videos are excluded by the upstream gate (N1 §1.2); they MUST NOT appear in the fixture plan.

The fixture is read-only: the smoke MUST NOT mutate the upstream `tech-hotspot-radar.sqlite` or `~/Knowledge/_raw/...` outside its own `2026-05-18/reports/<slug>/` directory.

### 5.2 3-step smoke flow

```
Step 1: plan-ai-influence-reports --week 2026-W21
  → output: plan.json (path returned on stdout)
  → assertion: exit code 0; plan.json contains ≥ 1 trend with ≥ 1 chapter

Step 2: render-ai-influence-report --plan <plan.json path>
  → output: report.md + report.html + evidence_map.json (paths returned on stdout)
  → assertion: exit code 0; all three files non-empty

Step 3: validate-report --report <report.md path>
  → output: PASS JSON on stdout (§3.3)
  → assertion: exit code 0; all 8 checks PASS
```

Failure of any step halts the smoke; the failing step's stderr is captured into the smoke log.

### 5.3 PASS criterion — all 8 validator checks

The smoke is considered PASS only if Step 3 reports `{"ok": true, "checks": {1: "pass", 2: "pass", 3: "pass", 4: "pass", 5: "pass", 6: "pass", 7: "pass", 8: "pass"}}` exactly. Any partial pass (e.g. 7/8) is a FAIL.

### 5.4 Smoke exit code criterion

The overall smoke harness wrapper (the script that runs Steps 1→2→3) MUST return exit code `0` if and only if:
1. Step 1 returns exit code `0`, AND
2. Step 2 returns exit code `0`, AND
3. Step 3 returns exit code `0` (i.e. validator PASS per §5.3).

Any other combination MUST return exit code `1` (smoke FAIL) with a structured JSON line on stderr identifying which step failed.

The smoke is wired into CI as `make smoke-ai-influence-report-w21` (or equivalent); this `Makefile` target is the responsibility of S04, not this node.

---

## Part 6: Cross-references and Non-goals

### 6.1 Upstream nodes consumed

- **N1** (transcript gate + group_type classification): defines T0/T1/T2/T3 grading and the 7 group_type values. This spec references but does not redefine them.
- **N2** (Browser Agent ChatGPT 3-phase invocation): defines the model phases producing plan.json and chapter SVG. This spec references but does not redefine them.

### 6.2 Downstream sprints expected

- **S02 (planner)**: ratify the validator check list and grep blacklist as production contracts; write the executable spec for `validate-report` and `archive-report`.
- **S03 (builder, runtime)**: implement `validate-report`, `render-ai-influence-report` SVG path, and the archive writer; create the 2026-W21 fixture from the live ingest.
- **S04 (orchestration)**: wire the 3-step smoke into CI; create the `Makefile` target; surface FAIL output to the report dashboard.
- **S05 (verification & release)**: run the smoke on the 2026-W21 fixture; collect evidence; close the epic.

### 6.3 Explicit non-goals for N3

- Not implementing the validator script (delegated to S03).
- Not running the smoke (delegated to S05).
- Not authoring 2026-W21 plan content (delegated to S03 fixture).
- Not modifying `~/.claude/settings.json`, `tech-hotspot-radar.sqlite`, or any production code path.
- Not deciding the ChatGPT 杂项 project's archival retention policy (out of scope; operator decision).

---

## Part 7: Acceptance Matrix (Reverse-mapped to dispatch ACs)

| Dispatch AC | Section | Evidence |
|-------------|---------|----------|
| Source mapping 5-field template | §1.1 | 5-row table; field types and examples |
| 6 forbidden internal fields list | §1.2 | 6-row table; cross-linked to validator Check 1 |
| Source mapping rendering example (HTML+markdown) | §1.3 | Both renderings shown with constraints |
| SVG mandatory embedding rule (inline `<svg>` not `<img>`) | §2.1 | Permitted/forbidden examples |
| ASCII chart forbidden in final output rule | §2.2 | Explicit pattern list; mermaid-code-fence handling |
| SVG source spec (high model output or template generation) | §2.3 | Path A + Path B with constraints |
| 8 validator checks enumerated with grep blacklist + regex | §3.1 + §3.4 | 8-row table + explicit blacklist file |
| Validator any-FAIL rejects archive policy | §3.2 | Pipeline diagram + contract violation clause |
| Validator exit code 0 (PASS) / 1 (FAIL with reason) | §3.3 | 3-row exit-code table |
| Grep blacklist words list explicit | §3.4 | 14-entry initial list + extensibility clause |
| 4 archive file types | §4.2 | 4-row artifact table |
| Knowledge raw path template | §4.1 | Path template with placeholders |
| ChatGPT project 杂项 archive with session_id + URL metadata | §4.3 | JSON schema with mandatory fields |
| 2026-W21 fixture data range | §5.1 | ISO week + UTC bounds + T3-exclusion rule |
| 3-step smoke (plan → render → validate) | §5.2 | 3-step flow with per-step assertions |
| Validator 8 checks all PASS criterion | §5.3 | Exact JSON shape required |
| Smoke exit code 0 criterion | §5.4 | Tri-conditional exit code rule |

17 / 17 acceptance items addressed in this spec.

---

## Part 8: Risks and open questions for S02

1. **Grep blacklist drift** — the 14-entry initial list is the S01 baseline. S02 should treat this list as a versioned contract: any addition is backward-compatible; any removal requires a planner sprint.
2. **11-char regex false positives** — Check 2's `\b[A-Za-z0-9_-]{11}\b` can match legitimate tokens (git short SHAs are 7 chars, but other identifiers may be 11). The mitigation in §3.1 (scan only reader-facing prose blocks) is heuristic. S02 should formalize "reader-facing block" as a markdown AST predicate, not a regex over raw text.
3. **ChatGPT URL reachability** — the validator does NOT verify the ChatGPT URL is reachable; an offline operator could archive a stale or dead URL and still pass the gate. Out-of-band audit tooling (not part of S03 validator) is needed.
4. **Mermaid handling** — Mermaid source in code fences is forbidden in the final report (§2.2), but the planning notes upstream may legitimately use mermaid sketches. The boundary between "planning note" and "final report" is the `render-ai-influence-report` step; sketches MUST be rendered to SVG before reaching `report.md`.
5. **Multilingual snippet length** — `cited_segment_snippet` is capped at 280 chars (§1.1). For CJK content, 280 chars is roughly 1–2 paragraphs; this may need a per-language byte/character policy in S02.
6. **Archive directory collision** — if two reports for the same ISO week target the same `<report_slug>`, the second write would overwrite the first. S03 should either (a) reject duplicate slugs, or (b) suffix with a sequence number; the choice is deferred to S02.

---

## Part 9: Self-check (pre-handoff)

- §1.1 has exactly 5 fields and §1.2 has exactly 6 forbidden field rows.
- §2.1 forbids `<img>` raster and remote SVG; §2.2 prohibits ASCII charts in final output; §2.3 spells out Path A / Path B sources.
- §3.1 lists exactly 8 checks; §3.4 has an explicit fixed-string blacklist plus regex patterns.
- §4.1 path template, §4.2 4 artifact types, §4.3 ChatGPT 杂项 metadata schema all explicit.
- §5.1 ISO bounds for 2026-W21, §5.2 3 steps, §5.3 PASS JSON shape, §5.4 tri-conditional exit code.
- §7 reverse-maps all 17 dispatch ACs to sections.
- This file is markdown-only; no executable code, no CLI invocation.
- All language compliant with the parent DoD policy: no claims of finished implementation; this is a specification awaiting downstream code.
