---
name: review
namespace: builtin
status: stable
version: "1.0"
description: "Code review — structural, security, and style analysis of a diff or file"
tags: [code-review, quality, security]
min_score: 0.8
author: solar-harness
created_at: "2026-05-09T00:00:00Z"
---

# Skill: review

Systematic code review covering correctness, security, style, and test coverage.

## Trigger

User says: `审查代码`, `code review`, `/review`

## Steps

1. **Scope** — identify changed files or diff range
2. **Correctness** — logic errors, off-by-ones, null safety, error paths
3. **Security** — OWASP Top 10, secret leakage, injection, path traversal
4. **Style** — naming, comment quality, dead code
5. **Tests** — coverage gaps, missing edge cases
6. **Output** — structured findings with severity (BLOCKER/WARN/NIT)

## Output format

```
## Findings
### BLOCKER
- [file:line] description

### WARN
- [file:line] description

### NIT
- [file:line] description

## Verdict
APPROVE / REQUEST_CHANGES
```

## Done when

- All BLOCKER findings addressed or explicitly accepted
- Verdict is APPROVE
