# OpenJiuwen Solar pipx Wrapper

This package is named `openjiuwen-solar` and installs a thin `openjiuwen-solar`
console command. It does not bundle the OpenSolar repository payload into the
wheel. `openjiuwen-solar install` delegates to the canonical shell path:

```text
get-solar.sh -> clone selected channel into $SOLAR_SRC -> install.sh
```

## Install

This package requires Python 3.11+. It installs only the `openjiuwen-solar`
wrapper. The real runtime bootstrap happens when you run
`openjiuwen-solar install`, which delegates to the shell installer.

Local checkout:

```bash
pipx install ./distribution/pipx
```

From the rc.9 tag:

```bash
pipx install "git+https://github.com/suraj-subrahmanyan/OpenSolar.git@v1.0.0-rc.9#subdirectory=distribution/pipx"
```

## Commands

```bash
openjiuwen-solar install --yes --components kernel,harness
openjiuwen-solar install --yes --components kernel,harness --bootstrap-system-deps
openjiuwen-solar status
openjiuwen-solar doctor --json
openjiuwen-solar harness preflight
openjiuwen-solar update
openjiuwen-solar uninstall --yes
openjiuwen-solar source
```

`openjiuwen-solar install` forwards every argument after `install` to `get-solar.sh`
unchanged. These environment variables are preserved:

```text
SOLAR_REPO
SOLAR_CHANNEL
SOLAR_SRC
SOLAR_COMPONENTS
OPENJIUWEN_SOLAR_GET_SOLAR_URL
```

Use `OPENJIUWEN_SOLAR_GET_SOLAR_URL=/path/to/get-solar.sh` or a `file://` URL
for offline/local tests. Without that override, the wrapper downloads the
`v1.0.0-rc.9` tag `get-solar.sh`. The older `OPENSOLAR_GET_SOLAR_URL` override
is still accepted for local compatibility.

Pip/pipx cannot install system binaries. For a first-time machine, run the
install command with `--bootstrap-system-deps` or install the shell
dependencies yourself:

```text
macOS: brew install tmux jq bash
Ubuntu/Debian: sudo apt-get update && sudo apt-get install -y tmux jq bash
Fedora: sudo dnf install -y tmux jq bash
Arch: sudo pacman -S --needed tmux jq bash
```

`openjiuwen-solar source` prints `$SOLAR_SRC/OpenSolar` when present, or the
default `~/.solar-src/OpenSolar`. If no checkout exists it prints a not-found
message and exits `1`.

## Warnings

`pipx uninstall openjiuwen-solar` removes only this wrapper. It does not
uninstall the OpenSolar runtime. Run this first:

```bash
openjiuwen-solar uninstall --yes
```

Native Windows is not supported by this wrapper. Use WSL and the repository
`install.ps1` bootstrapper instead.

## Local Smoke

The smoke uses a sandbox `HOME`, the local `get-solar.sh`, and a `file://`
clone of the current repository. It does not install system packages.

```bash
bash distribution/pipx/smoke.sh
```

The smoke runs:

```bash
openjiuwen-solar install --yes --components kernel,harness --fake-keys --skip-llm-cli --skip-py-deps
openjiuwen-solar status
openjiuwen-solar doctor --json
openjiuwen-solar harness preflight
openjiuwen-solar update --fake-keys --skip-llm-cli --skip-py-deps
openjiuwen-solar uninstall --yes
```

Then it verifies:

```text
~/.solar removed
~/.claude/solar removed
$SOLAR_SRC retained
```

If `pipx` is installed, the smoke installs the wrapper with pipx. If `pipx` is
absent, it uses a venv fallback and prints that the pipx leg is unverified.

## Self-contained Linux runtime deliverable

`distribution/runtime_deliverable.py` constructs the supported WSL/Linux
x86_64 CPython 3.12 target. The output replay archive contains the wrapper,
the exact Git source snapshot, JSON schema and verifier, jq, an offline harness
wheelhouse, bootstrap/replay scripts, and a hash inventory. Construction takes
the already-downloaded wheelhouse and jq binary as explicit inputs:

```bash
python distribution/runtime_deliverable.py build \
  --repo-root . \
  --output-dir /tmp/opensolar-runtime-deliverable \
  --wheelhouse /path/to/cp312-linux-wheelhouse \
  --jq-binary /path/to/jq-linux-amd64
```

Extract the emitted `.tar.gz`, then replay without a network connection,
external checkout, or injected runtime environment:

```bash
tar -xzf openjiuwen-solar-runtime-deliverable-<commit>.tar.gz -C /tmp/replay
bash /tmp/replay/runtime-deliverable/replay.sh /tmp/new-empty-sandbox
```

The replay writes atomic command, exit-code, output-hash, doctor, HTTP health,
and rollback evidence to `<sandbox>/product/smoke-evidence.json`. When pipx is
unavailable, the evidence reports the pipx leg as `NOT_TESTED` and records the
isolated venv fallback separately.
