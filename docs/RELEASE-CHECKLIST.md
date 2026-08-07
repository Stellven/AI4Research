# OpenSolar Release Checklist

This is the owner-only checklist for publishing `openjiuwen-solar` and the
public OpenSolar release. Implementers may run the build, local checks, and
sandbox install verification. Implementers must not upload to PyPI, push tags,
push release branches, or create a GitHub Release.

Target release (the tree remains rc.8 until the dedicated version-bump commit):

```bash
VERSION=1.0.0-rc.9
PYPI_VERSION=1.0.0rc9
TAG=v1.0.0-rc.9
RELEASE_BRANCH=release/v1.0.0-rc.9
RELEASE_TITLE="OpenJiuwen Solar v1.0.0-rc.9"
```

## 1. Start From The Reviewed Candidate

Run from the owner-reviewed release candidate commit after all implementation
branches are merged locally:

```bash
git switch pkg/migration
git status --short
test "$(cat VERSION)" = "$VERSION"
```

`git status --short` must show no tracked release changes. Do not delete or
stage unrelated untracked owner files. The release tool imports the exact
verified scratch commit and must leave the development worktree unchanged.

## 2. Local Gates

First update every public version-bearing surface in one dedicated commit:
`VERSION`, `get-solar.sh`, `install.ps1`, `README.md`, `INSTALL.md`,
`docs/FIRST-SESSION.md`, desktop package metadata, and the pipx package,
documentation, CLI constants, and tests. Do not use an unrestricted repository
search-and-replace. `check-release-coherence.sh` is the authoritative drift
gate for this set.

Then run the repository checks before building artifacts:

```bash
bash scripts/check-privacy.sh
bash scripts/check-release-coherence.sh
bash tests/repository/release/test_release_cut_safety.sh
bash tests/repository/release/test_release_public_tree.sh
bash tests/repository/release/test_release_checklist.sh
bash scripts/check-installed-clean.sh
bash scripts/check-kernel-gen.sh
bash scripts/check-daemons-render.sh
bash scripts/check-daemons-lifecycle.sh
bash scripts/check-core-imports.sh
bash scripts/check-harness-plumbing.sh
bash scripts/check-update.sh
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
distribution/pipx/dist/openjiuwen_solar-1.0.0rc9-py3-none-any.whl
distribution/pipx/dist/openjiuwen_solar-1.0.0rc9.tar.gz
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
runtime.selected == codex or claude
runtime.cli == present
runtime.auth == ok or unauthenticated
runtime.guidance
runtime.login_command
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

`--execute` imports the exact verified scratch commit as a local ref. It does
not switch branches, stage files, or modify the development worktree. Review
the generated orphan through a disposable clone:

```bash
test "$(git rev-list --count "$RELEASE_BRANCH")" = "1"
review_dir="$(mktemp -d /tmp/solar-release-review.XXXXXX)"
git clone --no-local --branch "$RELEASE_BRANCH" . "$review_dir/repo"
(
  cd "$review_dir/repo"
  git log --oneline --decorate -3
  git status --short
  bash scripts/check-release-coherence.sh
  bash scripts/check-privacy.sh
  bash scripts/check-installed-clean.sh
  bash scripts/smoke-install-matrix.sh minimal
)
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
OpenJiuwen Solar v1.0.0-rc.9

Release candidate for the public OpenJiuwen Solar package.

Verified scope: Linux/WSL2 CLI, local dashboard, and ordinary Codex prompt
execution through governed planning, implementation, evaluation, and output
publication.

Research synthesis remains experimental. Native Windows install.ps1 and the
packaged macOS/Windows desktop applications are not yet runtime-proven.

See README.md for install paths and docs/FIRST-SESSION.md for the first-session walkthrough.
EOF
```

Create the tag on the verified orphan branch explicitly. Never rely on the
currently checked-out branch. Push only to `origin`:

```bash
case "$(git remote get-url origin)" in
  git@github.com:suraj-subrahmanyan/OpenSolar.git|https://github.com/suraj-subrahmanyan/OpenSolar.git) ;;
  *) echo "refusing unexpected origin" >&2; exit 1 ;;
esac
test -z "$(git ls-remote --tags origin "refs/tags/$TAG")"
git tag -a "$TAG" "$RELEASE_BRANCH" -m "$RELEASE_TITLE"
git push origin "$RELEASE_BRANCH"
git push origin "$TAG"
```

PyPI upload is a separate owner decision. Run it only after `twine check`, the
sandbox install, and explicit upload approval:

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

Do not attach or advertise `.dmg` or `.exe` desktop artifacts until each has
been launched and exercised on its native target OS. Building an artifact in CI
is not runtime proof.

If `get-solar.sh` default-channel cutover is still pending, perform it only
after the owner confirms the final tag and release asset URLs.

## 8. Published-Tag Installation Proof

After the origin tag is visible, install from the public tag into a throwaway
home. Never use the real `$HOME` for release verification:

```bash
published="$(git ls-remote --tags origin "refs/tags/$TAG")"
test -n "$published"
published_tmp="$(mktemp -d /tmp/solar-published-tag.XXXXXX)"
mkdir -p "$published_tmp/home"
curl -fsSL \
  "https://raw.githubusercontent.com/suraj-subrahmanyan/OpenSolar/$TAG/get-solar.sh" \
  -o "$published_tmp/get-solar.sh"
HOME="$published_tmp/home" SOLAR_CHANNEL="$TAG" \
  bash "$published_tmp/get-solar.sh" --yes --components kernel,harness
HOME="$published_tmp/home" "$published_tmp/home/.solar/bin/solar" doctor --json
python3 - "$published_tmp/home/.solar/install-receipt.json" "$TAG" <<'PY'
import json, sys
receipt = json.load(open(sys.argv[1], encoding="utf-8"))
assert receipt["channel"] == sys.argv[2], receipt
print(receipt["channel"])
PY
HOME="$published_tmp/home" "$published_tmp/home/.solar/bin/solar" uninstall --yes
```

The printed receipt channel must be exactly `v1.0.0-rc.9`. A different value
is an update-channel regression and must be reported immediately.

## 9. Manual Checks

Manual checks that still require a real user environment:

| Check | Required confirmation |
|---|---|
| Codex ordinary prompt | Select Codex, submit a bounded prompt through the installed dashboard, require a certified plan, terminal PASS, published user output, independent tests, and zero-survivor teardown. |
| Claude mode | Only when Claude is deliberately selected, authenticate Claude Code and confirm one real delegation result. Claude authorization appearing in Codex mode is a failure. |
| Daemon start | On real macOS launchd and systemd-user Linux/WSL2, confirm the daemon starts and stays up. |
| Windows WSL2 | Run `install.ps1` end to end on Win11 if this release claims WSL2 support. |
| Native desktop packages | Launch the `.dmg` on macOS and `.exe` on Windows, complete first-run setup, submit a prompt, and inspect the produced output before advertising either artifact. |
