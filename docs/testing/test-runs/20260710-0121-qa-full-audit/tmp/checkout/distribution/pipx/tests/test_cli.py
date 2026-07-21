import contextlib
import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opensolar_cli import cli  # noqa: E402


def write_executable(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    path.chmod(0o755)


class OpenSolarCliTests(unittest.TestCase):
    def test_install_forwards_arguments_exactly_and_preserves_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            capture = tmp_path / "capture.json"
            get_solar = tmp_path / "get-solar.sh"
            write_executable(
                get_solar,
                """\
                #!/usr/bin/env bash
                set -eu
                python3 - "$@" <<'PY'
                import json
                import os
                import sys

                keys = [
                    "SOLAR_REPO",
                    "SOLAR_CHANNEL",
                    "SOLAR_SRC",
                    "SOLAR_COMPONENTS",
                    "OPENJIUWEN_SOLAR_GET_SOLAR_URL",
                    "OPENSOLAR_GET_SOLAR_URL",
                ]
                with open(os.environ["CAPTURE"], "w", encoding="utf-8") as f:
                    json.dump({
                        "args": sys.argv[1:],
                        "env": {key: os.environ.get(key) for key in keys},
                    }, f, sort_keys=True)
                PY
                """,
            )
            env = {
                "CAPTURE": str(capture),
                "OPENJIUWEN_SOLAR_GET_SOLAR_URL": str(get_solar),
                "SOLAR_REPO": "file:///repo.git",
                "SOLAR_CHANNEL": "demo/pipx-wrapper",
                "SOLAR_SRC": str(tmp_path / "src"),
                "SOLAR_COMPONENTS": "kernel,harness",
                "OPENSOLAR_GET_SOLAR_URL": "unused-legacy-value",
            }
            args = [
                "install",
                "--yes",
                "--components",
                "kernel,harness",
                "--set",
                "GREETING=hello world",
            ]

            with mock.patch.dict(os.environ, env, clear=False):
                self.assertEqual(cli.main(args), 0)

            data = json.loads(capture.read_text(encoding="utf-8"))
            self.assertEqual(data["args"], args[1:])
            for key in cli.PASSTHROUGH_ENV:
                self.assertEqual(data["env"][key], env[key])

    def test_install_accepts_file_url_get_solar_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            capture = tmp_path / "capture.json"
            get_solar = tmp_path / "get-solar.sh"
            write_executable(
                get_solar,
                """\
                #!/usr/bin/env bash
                set -eu
                python3 - "$@" <<'PY'
                import json
                import os
                import sys

                with open(os.environ["CAPTURE"], "w", encoding="utf-8") as f:
                    json.dump(sys.argv[1:], f)
                PY
                """,
            )

            with mock.patch.dict(
                os.environ,
                {
                    "CAPTURE": str(capture),
                    "OPENJIUWEN_SOLAR_GET_SOLAR_URL": get_solar.as_uri(),
                },
                clear=False,
            ):
                self.assertEqual(cli.main(["install", "--dry-run"]), 0)

            self.assertEqual(json.loads(capture.read_text(encoding="utf-8")), ["--dry-run"])

    def test_install_accepts_legacy_get_solar_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            capture = tmp_path / "capture.json"
            get_solar = tmp_path / "get-solar.sh"
            write_executable(
                get_solar,
                """\
                #!/usr/bin/env bash
                set -eu
                python3 - "$@" <<'PY'
                import json
                import os
                import sys

                with open(os.environ["CAPTURE"], "w", encoding="utf-8") as f:
                    json.dump(sys.argv[1:], f)
                PY
                """,
            )

            with mock.patch.dict(
                os.environ,
                {
                    "CAPTURE": str(capture),
                    "OPENSOLAR_GET_SOLAR_URL": get_solar.as_uri(),
                },
                clear=False,
            ):
                os.environ.pop("OPENJIUWEN_SOLAR_GET_SOLAR_URL", None)
                self.assertEqual(cli.main(["install", "--dry-run"]), 0)

            self.assertEqual(json.loads(capture.read_text(encoding="utf-8")), ["--dry-run"])

    def test_installed_solar_commands_delegate_to_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            solar_bin = home / ".solar" / "bin" / "solar"
            solar_bin.parent.mkdir(parents=True)
            capture = Path(tmp) / "delegated.json"
            write_executable(
                solar_bin,
                """\
                #!/usr/bin/env bash
                set -eu
                python3 - "$@" <<'PY'
                import json
                import os
                import sys
                from pathlib import Path

                path = Path(os.environ["CAPTURE"])
                rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
                rows.append(sys.argv[1:])
                path.write_text(json.dumps(rows), encoding="utf-8")
                PY
                """,
            )

            with mock.patch.dict(os.environ, {"HOME": str(home), "CAPTURE": str(capture)}, clear=False):
                self.assertEqual(cli.main(["status", "--json"]), 0)
                self.assertEqual(cli.main(["doctor", "--json"]), 0)
                self.assertEqual(cli.main(["harness", "preflight"]), 0)
                self.assertEqual(cli.main(["components", "list"]), 0)
                self.assertEqual(cli.main(["update"]), 0)
                self.assertEqual(cli.main(["uninstall", "--yes"]), 0)

            self.assertEqual(
                json.loads(capture.read_text(encoding="utf-8")),
                [
                    ["status", "--json"],
                    ["doctor", "--json"],
                    ["harness", "preflight"],
                    ["components", "list"],
                    ["update"],
                    ["uninstall", "--yes"],
                ],
            )

    def test_missing_installed_solar_has_clear_error_for_lifecycle_commands(self) -> None:
        for command in ("status", "doctor", "harness", "components", "update", "uninstall"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp) / "home"
                stderr = io.StringIO()
                with mock.patch.dict(os.environ, {"HOME": str(home)}, clear=False):
                    with contextlib.redirect_stderr(stderr):
                        code = cli.main([command])
                self.assertNotEqual(code, 0)
                text = stderr.getvalue()
                self.assertIn(str(home / ".solar" / "bin" / "solar"), text)
                self.assertIn("openjiuwen-solar install --yes", text)

    def test_source_prints_env_checkout_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_parent = Path(tmp) / "source-parent"
            checkout = source_parent / "OpenSolar"
            checkout.mkdir(parents=True)
            stdout = io.StringIO()
            with mock.patch.dict(os.environ, {"SOLAR_SRC": str(source_parent)}, clear=False):
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(cli.main(["source"]), 0)
            self.assertEqual(stdout.getvalue(), f"{checkout}\n")

    def test_source_not_found_is_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stderr = io.StringIO()
            with mock.patch.dict(os.environ, {"HOME": str(Path(tmp) / "home")}, clear=False):
                os.environ.pop("SOLAR_SRC", None)
                with contextlib.redirect_stderr(stderr):
                    code = cli.main(["source"])
            self.assertEqual(code, 1)
            self.assertIn("source checkout not found", stderr.getvalue())

    def test_help_contains_install_commands_examples_and_warnings(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(cli.main(["--help"]), 0)
        text = stdout.getvalue()
        self.assertIn("Commands:", text)
        self.assertIn("pipx install ./distribution/pipx", text)
        self.assertIn("git+https://github.com/Stellven/OpenSolar.git@v1.0.0-rc.3#subdirectory=distribution/pipx", text)
        self.assertIn("raw.githubusercontent.com/Stellven/OpenSolar/v1.0.0-rc.3/get-solar.sh", text)
        self.assertIn("openjiuwen-solar install --yes --components kernel,harness", text)
        self.assertIn("openjiuwen-solar status", text)
        self.assertIn("openjiuwen-solar doctor --json", text)
        self.assertIn("openjiuwen-solar harness preflight", text)
        self.assertIn("openjiuwen-solar update", text)
        self.assertIn("openjiuwen-solar uninstall --yes", text)
        self.assertIn("OPENJIUWEN_SOLAR_GET_SOLAR_URL", text)
        self.assertIn("pipx uninstalling this wrapper does NOT uninstall OpenSolar", text)
        self.assertIn("Native Windows is not supported", text)

    def test_native_windows_guard_fails_loud(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(cli.platform, "system", return_value="Windows"):
            with contextlib.redirect_stderr(stderr):
                code = cli.main(["install", "--yes"])
        self.assertNotEqual(code, 0)
        text = stderr.getvalue()
        self.assertIn("native Windows is not supported", text)
        self.assertIn("WSL", text)
        self.assertIn("install.ps1", text)


if __name__ == "__main__":
    unittest.main()
