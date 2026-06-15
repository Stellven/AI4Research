# OpenSolar Release Checklist

This is the owner-only checklist for publishing `openjiuwen-solar` and the
public OpenSolar release. Implementers may run the build, local checks, and
sandbox install verification. Implementers must not upload to PyPI, push tags,
push release branches, or create a GitHub Release.

Current release candidate:

```bash
VERSION=1.0.0-rc.3
PYPI_VERSION=1.0.0rc3
TAG=v1.0.0-rc.3
RELEASE_BRANCH=release/v1.0.0-rc.3
RELEASE_TITLE="OpenJiuwen Solar v1.0.0-rc.3"
```

## 1. Start From The Reviewed Candidate

Run from the owner-reviewed release candidate commit after all implementation
branches are merged locally:

```bash
git switch pkg/migration
git status --short
test "$(cat VERSION)" = "$VERSION"
```

`git status --short` must show no tracked release changes except any local
owner-only files that are intentionally untracked or ignored.

## 2. Local Gates

Run the repository checks before building artifacts:

```bash
bash scripts/check-privacy.sh
bash scripts/check-installed-clean.sh
bash scripts/check-kernel-gen.sh
bash scripts/check-daemons-render.sh
bash scripts/check-daemons-lifecycle.sh
bash scripts/check-core-imports.sh
bash scripts/check-harness-plumbing.sh
bash scripts/check-solar-version.sh
bash scripts/check-solar-update.sh
bash scripts/check-solar-status.sh
bash scripts/check-solar-harness-front-door.sh
bash scripts/smoke-install-matrix.sh minimal
```

If a WSL2/local runner cannot execute a gate, record the exact command and
failure. Do not mark that gate verified.

Before building the PyPI wrapper, confirm the installer bootstrap contract:

```bash
python3 - <<'PY'
import sys
assert sys.version_info >= (3, 11), sys.version
PY
bash install.sh --help | grep -- --bootstrap-system-deps
```

The shell installer, not pip, owns OS package bootstrap. On a first-time
machine the owner may run:

```bash
./install.sh --yes --components kernel,harness --bootstrap-system-deps
```

For local release verification, use a sandbox `HOME` and do not pass
`--bootstrap-system-deps` unless you intentionally want the package manager
prompt/command path exercised.

## 3. Build The PyPI Package

Build from a clean package worktree:

```bash
cd distribution/pipx
rm -rf dist build openjiuwen_solar.egg-info
python3 -m build --sdist --wheel
python3 -m twine check dist/*
cd ../..
```

Expected artifacts:

```text
distribution/pipx/dist/openjiuwen_solar-1.0.0rc3-py3-none-any.whl
distribution/pipx/dist/openjiuwen_solar-1.0.0rc3.tar.gz
```

## 4. Verify The Built Wheel In A Sandbox

Install only into throwaway directories:

```bash
tmp="$(mktemp -d /tmp/openjiuwen-solar-release.XXXXXX)"
python3 -m venv "$tmp/venv"
"$tmp/venv/bin/python" -m pip install --no-index \
  --find-links "$PWD/distribution/pipx/dist" "openjiuwen-solar==$PYPI_VERSION"
"$tmp/venv/bin/openjiuwen-solar" --help
METADATA="$("$tmp/venv/bin/python" - <<'PY'
from importlib.metadata import metadata
print(metadata("openjiuwen-solar")["Requires-Python"])
PY
)"
test "$METADATA" = ">=3.11"
```

Then verify the installed wrapper can install and delegate to the local Solar
lifecycle without touching the real home directory:

```bash
sandbox_home="$tmp/home"
mkdir -p "$sandbox_home"
HOME="$sandbox_home" \
SOLAR_REPO="file://$PWD" \
SOLAR_CHANNEL="$(git branch --show-current)" \
SOLAR_SRC="$tmp/src" \
OPENJIUWEN_SOLAR_GET_SOLAR_URL="$PWD/get-solar.sh" \
"$tmp/venv/bin/openjiuwen-solar" install --yes \
  --components kernel,harness --fake-keys --skip-llm-cli

HOME="$sandbox_home" "$tmp/venv/bin/openjiuwen-solar" status
HOME="$sandbox_home" "$tmp/venv/bin/openjiuwen-solar" doctor --json
HOME="$sandbox_home" "$tmp/venv/bin/openjiuwen-solar" harness preflight
HOME="$sandbox_home" "$tmp/venv/bin/openjiuwen-solar" uninstall --yes
```

`doctor --json` must include:

```text
python.version >= 3.11
python.harness_imports.yaml == ok
system.tmux / system.jq / system["bash>=4"]
models.guidance
models.claude_auth_note
```

## 5. Verify The Public Orphan Cut

Dry-run the public release tree. This does not change refs:

```bash
bash scripts/release-cut.sh --source HEAD --exclude-file release-exclude.txt
```

Expected result:

```text
RELEASE-GATE VERDICT: PASS
```

`gitleaks` must be installed and must actually run. If `gitleaks` is missing,
install it and rerun the gate; do not treat a skipped secret scan as verified.

## 6. Owner-Only Public Cut

Only the owner runs this after reviewing the dry-run output:

```bash
bash scripts/release-cut.sh --source HEAD \
  --branch "$RELEASE_BRANCH" \
  --exclude-file release-exclude.txt \
  --execute
```

Review the generated orphan branch before pushing:

```bash
git switch "$RELEASE_BRANCH"
git log --oneline --decorate -3
git status --short
bash scripts/check-privacy.sh
bash scripts/check-installed-clean.sh
```

## 7. Owner-Only Checksums, Tag, Upload, Release

Create checksums for the exact files that will be attached:

```bash
mkdir -p release-artifacts
cp get-solar.sh install.ps1 distribution/pipx/dist/openjiuwen_solar-"$PYPI_VERSION"* release-artifacts/
(cd release-artifacts && sha256sum * > SHA256SUMS)
```

Create release notes for the GitHub Release:

```bash
cat > release-artifacts/RELEASE_NOTES.md <<'EOF'
OpenJiuwen Solar v1.0.0-rc.3

Release candidate for the public OpenJiuwen Solar package.

See README.md for install paths and docs/FIRST-SESSION.md for the first-session walkthrough.
EOF
```

Create and push the release tag only after the public cut is reviewed:

```bash
git tag -a "$TAG" -m "$RELEASE_TITLE"
git push origin "$RELEASE_BRANCH"
git push origin "$TAG"
```

Upload the package to PyPI only after `twine check` and sandbox install pass:

```bash
python3 -m twine upload distribution/pipx/dist/openjiuwen_solar-"$PYPI_VERSION"*
```

Create the GitHub Release and upload assets:

```bash
gh release create "$TAG" \
  --repo suraj-subrahmanyan/OpenSolar \
  --target "$RELEASE_BRANCH" \
  --title "$RELEASE_TITLE" \
  --notes-file release-artifacts/RELEASE_NOTES.md \
  release-artifacts/*
```

If `get-solar.sh` stable/default-channel cutover is still pending, perform it
only after the owner confirms the final tag and release asset URLs.

## 8. Manual Checks

Manual checks that still require a real user environment:

| Check | Required confirmation |
|---|---|
| Kernel load | Open `claude`, approve the one-time `@~/.claude/solar/SOLAR.md` import, and confirm the kernel loads. |
| Harness cockpit | Run `solar harness start <workdir>`, confirm the tmux session opens, start/trust Claude in each pane, and confirm one real delegation result. |
| Claude quota/auth | If Claude is rate-limited or unauthenticated, record manual-blocked/auth-quota-blocked. |
| Daemon start | On real macOS launchd and systemd-user Linux/WSL2, confirm the daemon starts and stays up. |
| Windows WSL2 | Run `install.ps1` end to end on Win11 if this release claims WSL2 support. |
