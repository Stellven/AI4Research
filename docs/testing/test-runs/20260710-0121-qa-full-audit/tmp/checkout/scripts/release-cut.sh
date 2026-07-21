#!/usr/bin/env bash
# release-cut.sh — PREPARE / verify (and, with --execute, create) the public
# orphan-branch release of Solar: a single squashed commit of the current
# tracked tree with NO prior history ("show day 100, not the history").
#
# DEFAULT IS DRY-RUN. It builds the orphan in a scratch clone, applies the
# exclude list, runs the full release-gate verification, prints a report, and
# discards the scratch. It NEVER touches this repo's refs and NEVER pushes.
#
#   --execute       create the local orphan branch in THIS repo (run only with
#                   owner go-ahead). It still does NOT push and does NOT create
#                   any public repo or GitHub Release — those remain manual
#                   owner steps performed after this succeeds.
#
# RELEASE GATE (all must pass for a clean cut):
#   1. WORKLOG.md / MIGRATION_PLAN.md absent from the public tree AND from the
#      new (single-commit) history. (The dev history range ec07779..0e2b431
#      carried them tracked; the orphan cut drops all that history.)
#   2. Personal tokens ZERO in the public tree — owner-identifying + persona
#      proper nouns: /Users/lisihao, haogege1977, private IPs, lisihao@/sihaoli@,
#      小爱, 昊哥, xiaoai, sihaoli, "Li Sihao", "Sihao Li". (LICENSE is
#      allowlisted for the author's copyright name; the scanner scripts are
#      allowlisted for carrying the patterns themselves.)
#   3. Forbidden architectural tokens — REPORTED, allowlist-aware (solar-farm /
#      gstack inside harness/core internals are the tolerated out-of-scope
#      residue, per the ratified WS7 decision).
#   4. gitleaks over the full history is clean (uses harness/gitleaks.toml).
#
# Options:
#   --execute              create the local orphan branch (owner; no push)
#   --source REF           tree to cut from (default: HEAD)
#   --branch NAME          orphan branch name (default: release/v1)
#   --exclude-file FILE    newline-separated paths/globs (git pathspecs) to drop
#                          from the public tree before committing — the owner's
#                          cut-time exclude list (e.g. parked dev content)
#   --keep-scratch         do not delete the scratch dir (inspect the report)
#   --help
#
# Style: functions only, main at the end, bash-3.2-safe.
set -eu

SRC_REF="HEAD"
ORPHAN_BRANCH="release/v1"
EXCLUDE_FILE=""
DO_EXECUTE="false"
KEEP_SCRATCH="false"
GITLEAKS_CONFIG="harness/gitleaks.toml"

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"

log()  { printf '[release-cut] %s\n' "$*" >&2; }
die()  { printf '[release-cut] error: %s\n' "$*" >&2; exit 1; }
rule() { printf -- '----------------------------------------------------------------\n'; }

usage() { sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; }

parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --execute)       DO_EXECUTE="true"; shift ;;
            --source)        SRC_REF="$2"; shift 2 ;;
            --branch)        ORPHAN_BRANCH="$2"; shift 2 ;;
            --exclude-file)  EXCLUDE_FILE="$2"; shift 2 ;;
            --keep-scratch)  KEEP_SCRATCH="true"; shift ;;
            --help|-h)       usage; exit 0 ;;
            *) die "unknown option: $1" ;;
        esac
    done
}

exclude_entry() {
    printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

apply_excludes() {
    work="$1"
    [ -n "$EXCLUDE_FILE" ] && [ -f "$EXCLUDE_FILE" ] || return 0
    ( cd "$work"
      while IFS= read -r raw || [ -n "$raw" ]; do
          pat="$(exclude_entry "$raw")"
          case "$pat" in ''|'#'*) continue ;; esac
          git rm -rfq --ignore-unmatch -- "$pat" 2>/dev/null || true
          rm -rf -- "$pat" 2>/dev/null || true
      done < "$EXCLUDE_FILE"
    )
}

# Build the orphan branch (single commit of SRC_REF's tracked tree, minus the
# exclude list) inside the given git working directory.
build_orphan() {
    work="$1"
    ( cd "$work"
      git checkout -q --orphan "$ORPHAN_BRANCH" "$SRC_REF"
      apply_excludes "$work"
      git add -A
      git commit -q -m "Solar — public release

A clean, single-commit snapshot of Solar (no development history)." )
}

# ---- verification checks (run inside the scratch orphan repo) ----

check_excluded_paths_absent() {
    work="$1"; fail=0
    [ -n "$EXCLUDE_FILE" ] && [ -f "$EXCLUDE_FILE" ] || return 0
    log "check 0: exclude-file entries absent from the public tree"
    while IFS= read -r raw || [ -n "$raw" ]; do
        pat="$(exclude_entry "$raw")"
        case "$pat" in ''|'#'*) continue ;; esac
        hits="$(cd "$work" && git ls-tree -r --name-only "$ORPHAN_BRANCH" -- "$pat" 2>/dev/null || true)"
        if [ -n "$hits" ]; then
            printf '  FAIL: exclude entry still present in orphan tree: %s\n' "$pat" >&2
            printf '%s\n' "$hits" | sed 's/^/    /' | head -20 >&2
            fail=1
        fi
    done < "$EXCLUDE_FILE"
    if [ "$fail" -eq 0 ]; then
        log "  ok: all exclude-file entries absent"
    fi
    return $fail
}

check_working_files() {
    work="$1"; fail=0
    log "check 1: WORKLOG.md / MIGRATION_PLAN.md absent (tree + history)"
    intree="$(cd "$work" && git ls-tree -r --name-only "$ORPHAN_BRANCH" \
        | grep -E '^(WORKLOG|MIGRATION_PLAN)\.md$' || true)"
    inhist="$(cd "$work" && git log "$ORPHAN_BRANCH" --name-only --pretty=format: \
        | grep -E '^(WORKLOG|MIGRATION_PLAN)\.md$' | sort -u || true)"
    if [ -n "$intree" ] || [ -n "$inhist" ]; then
        printf '  FAIL: local-only working files present:\n%s\n%s\n' "$intree" "$inhist" >&2
        fail=1
    else
        log "  ok: neither file in the public tree or its history"
    fi
    return $fail
}

check_personal_tokens() {
    work="$1"; fail=0
    log "check 2: personal/persona tokens ZERO in the public tree"
    # Author-identifying + persona proper nouns. NOT architectural names.
    personal='/Users/lisihao|lisihao@|sihaoli@|haogege1977|192\.168\.|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.|小爱|昊哥|xiaoai|sihaoli|Li Sihao|Sihao Li'
    # Allowlist: LICENSE (author copyright name) + the scanner scripts that
    # legitimately embed the token patterns.
    hits="$(cd "$work" && git grep -nIE "$personal" "$ORPHAN_BRANCH" -- . \
        ':(exclude)LICENSE' \
        ':(exclude)scripts/release-cut.sh' \
        ':(exclude)scripts/check-privacy.sh' \
        ':(exclude)scripts/check-installed-clean.sh' \
        ':(exclude)scripts/check-kernel-gen.sh' \
        ':(exclude)scripts/check-daemons-render.sh' 2>/dev/null || true)"
    if [ -n "$hits" ]; then
        n="$(printf '%s\n' "$hits" | wc -l | tr -d ' ')"
        printf '  FAIL: %s personal/persona token hit(s) in the public tree:\n' "$n" >&2
        printf '%s\n' "$hits" | sed 's/^/    /' | head -60 >&2
        [ "$n" -gt 60 ] && printf '    ... (%s more)\n' "$((n - 60))" >&2
        fail=1
    else
        log "  ok: no personal/persona tokens (LICENSE copyright name allowlisted)"
    fi
    return $fail
}

report_architectural_tokens() {
    work="$1"
    log "check 3 (report): architectural names, allowlist-aware"
    arch='brain-router|brain_router|skill_retriever|skill-retriever|plan-act|plan_act|ml-intern|ml_intern|solar-farm|solar_farm|gstack'
    # Allowlist-aware: solar-farm/gstack inside harness/core internals are the
    # tolerated out-of-scope residue (WS7 decision). Report everything else.
    outside="$(cd "$work" && git grep -lIE "$arch" "$ORPHAN_BRANCH" -- . \
        ':(exclude)harness' ':(exclude)core' \
        ':(exclude)scripts/release-cut.sh' \
        ':(exclude)scripts/check-kernel-gen.sh' \
        ':(exclude)scripts/check-daemons-render.sh' 2>/dev/null | sed "s#^$ORPHAN_BRANCH:##" || true)"
    tolerated="$(cd "$work" && git grep -lIE "solar-farm|solar_farm|gstack" "$ORPHAN_BRANCH" -- harness core 2>/dev/null | wc -l | tr -d ' ')"
    log "  tolerated (solar-farm/gstack in harness+core): $tolerated file(s)"
    if [ -n "$outside" ]; then
        cnt="$(printf '%s\n' "$outside" | wc -l | tr -d ' ')"
        printf '  REPORT: %s file(s) carry architectural names OUTSIDE the allowlist\n' "$cnt" >&2
        printf '  (owner decides at cut: exclude or scrub these for a "day 100" tree)\n' >&2
        printf '%s\n' "$outside" | sed 's/^/    /' | head -60 >&2
        [ "$cnt" -gt 60 ] && printf '    ... (%s more)\n' "$((cnt - 60))" >&2
    else
        log "  ok: no architectural names outside the harness/core allowlist"
    fi
    return 0
}

check_gitleaks_history() {
    work="$1"
    log "check 4: gitleaks over full history"
    if ! command -v gitleaks >/dev/null 2>&1; then
        printf '  FAIL: gitleaks not found on PATH; release privacy validation requires it.\n' >&2
        printf '        Remedy: install gitleaks and confirm `gitleaks --version` works.\n' >&2
        printf '        Local pinned example: PATH="/tmp/solar-gitleaks-8.18.4:$PATH" bash scripts/release-cut.sh ...\n' >&2
        return 1
    fi
    if ( cd "$work" && gitleaks detect --config "$repo_dir/$GITLEAKS_CONFIG" --redact --log-opts="$ORPHAN_BRANCH" >/dev/null 2>&1 ); then
        log "  ok: gitleaks found no leaks across the orphan history"
        return 0
    fi
    printf '  FAIL: gitleaks found leaks in the orphan history (run gitleaks detect to see)\n' >&2
    return 1
}

run_verification() {
    work="$1"; rc=0
    rule
    check_excluded_paths_absent "$work" || rc=1
    rule
    check_working_files "$work"        || rc=1
    rule
    check_personal_tokens "$work"      || rc=1
    rule
    report_architectural_tokens "$work" || true
    rule
    check_gitleaks_history "$work"     || rc=1
    rule
    return $rc
}

main() {
    parse_args "$@"
    # Resolve the exclude file to an absolute path NOW (before any cd). It is
    # copied into scratch below so executed cuts can still verify excludes even
    # when the exclude file excludes itself from the orphan worktree.
    if [ -n "$EXCLUDE_FILE" ]; then
        case "$EXCLUDE_FILE" in /*) : ;; *) EXCLUDE_FILE="$PWD/$EXCLUDE_FILE" ;; esac
        [ -f "$EXCLUDE_FILE" ] || die "exclude file not found: $EXCLUDE_FILE"
    fi
    cd "$repo_dir"
    command -v git >/dev/null 2>&1 || die "git is required"
    git rev-parse --verify -q "$SRC_REF" >/dev/null || die "source ref not found: $SRC_REF"

    scratch="$(mktemp -d "${TMPDIR:-/tmp}/solar-release-cut.XXXXXX")"
    if [ "$KEEP_SCRATCH" != "true" ]; then
        trap 'rm -rf "$scratch"' EXIT
    fi
    if [ -n "$EXCLUDE_FILE" ]; then
        cp "$EXCLUDE_FILE" "$scratch/exclude-file"
        EXCLUDE_FILE="$scratch/exclude-file"
    fi
    log "scratch: $scratch"
    log "cutting orphan '$ORPHAN_BRANCH' from '$SRC_REF' (clone is local; refs untouched)"
    git clone -q --no-local --branch "$(git rev-parse --abbrev-ref "$SRC_REF" 2>/dev/null || echo HEAD)" . "$scratch/repo" 2>/dev/null \
        || git clone -q . "$scratch/repo"
    build_orphan "$scratch/repo"

    log "verifying the public tree + history"
    if run_verification "$scratch/repo"; then
        verdict="PASS"
    else
        verdict="FAIL"
    fi

    if [ "$DO_EXECUTE" = "true" ]; then
        [ "$verdict" = "PASS" ] || die "verification FAILED — refusing to create the orphan branch. Resolve the findings (exclude/scrub) and re-run."
        log "creating local orphan branch '$ORPHAN_BRANCH' in this repo (NO push)"
        git rev-parse --verify -q "$ORPHAN_BRANCH" >/dev/null && die "branch '$ORPHAN_BRANCH' already exists; delete it first"
        previous_ref="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || git rev-parse --short HEAD)"
        # Recreate the verified orphan in the real repo using the same path as
        # the dry-run scratch build, then verify the created local branch too.
        build_orphan "$repo_dir"
        log "verifying the executed local orphan branch"
        if ! run_verification "$repo_dir"; then
            git checkout -q "$previous_ref" 2>/dev/null || true
            die "executed orphan verification FAILED — branch '$ORPHAN_BRANCH' was created locally but is not release-ready"
        fi
        log "DONE (local only): orphan branch '$ORPHAN_BRANCH' created. NOTHING pushed."
        log "Next (manual, owner): review, then push to the public repo and cut the GitHub Release."
        git checkout -q "$previous_ref"
    fi

    rule
    log "RELEASE-GATE VERDICT: $verdict  (source=$SRC_REF branch=$ORPHAN_BRANCH execute=$DO_EXECUTE)"
    [ "$verdict" = "PASS" ] || exit 1
}

main "$@"
