# OpenJiuwen Solar pipx Wrapper

This package is named `openjiuwen-solar` and installs a thin `opensolar`
console command. It does not bundle the OpenSolar repository payload into the
wheel. `opensolar install` delegates to the canonical shell path:

```text
get-solar.sh -> clone selected channel into $SOLAR_SRC -> install.sh
```

## Install

Local checkout:

```bash
pipx install ./distribution/pipx
```

From the stable branch:

```bash
pipx install "git+https://github.com/suraj-subrahmanyan/OpenSolar.git@stable#subdirectory=distribution/pipx"
```

## Commands

```bash
opensolar install --yes --components kernel,harness
opensolar doctor --json
opensolar update
opensolar uninstall --yes
opensolar source
```

`opensolar install` forwards every argument after `install` to `get-solar.sh`
unchanged. These environment variables are preserved:

```text
SOLAR_REPO
SOLAR_CHANNEL
SOLAR_SRC
SOLAR_COMPONENTS
OPENSOLAR_GET_SOLAR_URL
```

Use `OPENSOLAR_GET_SOLAR_URL=/path/to/get-solar.sh` or a `file://` URL for
offline/local tests. Without that override, the wrapper downloads the
`stable` branch `get-solar.sh`.

`opensolar source` prints `$SOLAR_SRC/OpenSolar` when present, or the default
`~/.solar-src/OpenSolar`. If no checkout exists it prints a not-found message
and exits `1`.

## Warnings

`pipx uninstall openjiuwen-solar` removes only this wrapper. It does not
uninstall the OpenSolar runtime. Run this first:

```bash
opensolar uninstall --yes
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
opensolar install --yes --components kernel,harness --fake-keys --skip-llm-cli --skip-py-deps
opensolar doctor --json
opensolar update --fake-keys --skip-llm-cli --skip-py-deps
opensolar uninstall --yes
```

Then it verifies:

```text
~/.solar removed
~/.claude/solar removed
$SOLAR_SRC retained
```

If `pipx` is installed, the smoke installs the wrapper with pipx. If `pipx` is
absent, it uses a venv fallback and prints that the pipx leg is unverified.
