"""Unit tests for C5 — CLI + StatusSurface.

Acceptance map:
  - A-C5-1 CLI supports 5 backend choices (browser/rss/manual/x_api/auto)
            and --limit-accounts N flag
  - A-C5-2 Exit codes 0 / 1 / 2 / 3 (success / fallback / rate-limit / config-error)
  - A-C5-3 StatusSurface emits JSON with all 7 indicators
  - A-C5-4 Unit tests cover CLI arg parse + all 4 exit codes + status JSON shape
"""
from __future__ import annotations

import io
import json
import re
import unittest
from typing import Callable

from .cli import (
    BACKEND_CHOICES,
    CLI_TO_SCHEMA_BACKEND,
    EXIT_CODES,
    EXIT_CONFIG_ERROR,
    EXIT_LEASE_FALLBACK,
    EXIT_OK,
    EXIT_RATE_LIMIT,
    CliArgs,
    CliRunResult,
    main,
    parse_args,
)
from .status_surface import (
    DEFAULT_BACKEND_KEYS,
    PRIMARY_BACKEND,
    STATUS_INDICATORS,
    VALID_SCAN_STATES,
    StatusInput,
    StatusSurface,
)


def _ok_status() -> StatusInput:
    return StatusInput(
        total_accounts=10,
        enabled_accounts=8,
        scanned_today=5,
        browser_ready=True,
        scan_state="running",
        parse_fail_count=1,
        by_backend_count={"browser_agent": 4, "rss_public": 1, "manual_curated": 0},
    )


def _run(argv, callback=None) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, run_callback=callback, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# 1. CLI argument surface (A-C5-1)
# ---------------------------------------------------------------------------


class TestCliArgs(unittest.TestCase):
    def test_five_backend_choices_present(self):
        self.assertEqual(
            BACKEND_CHOICES, ("browser", "rss", "manual", "x_api", "auto")
        )
        self.assertEqual(len(BACKEND_CHOICES), 5)

    def test_cli_backend_maps_to_schema_backend(self):
        # 4 concrete backends map; `auto` is resolved by C4, not the CLI.
        self.assertEqual(set(CLI_TO_SCHEMA_BACKEND.keys()), set(BACKEND_CHOICES) - {"auto"})
        self.assertEqual(CLI_TO_SCHEMA_BACKEND["browser"], "browser_agent")
        self.assertEqual(CLI_TO_SCHEMA_BACKEND["rss"], "rss_public")
        self.assertEqual(CLI_TO_SCHEMA_BACKEND["manual"], "manual_curated")
        self.assertEqual(CLI_TO_SCHEMA_BACKEND["x_api"], "x_api")

    def test_parse_args_minimum(self):
        args = parse_args(["--backend", "browser"])
        self.assertEqual(args.backend, "browser")
        self.assertIsNone(args.limit_accounts)
        self.assertFalse(args.json_only)

    def test_parse_args_with_limit(self):
        args = parse_args(["--backend", "rss", "--limit-accounts", "3"])
        self.assertEqual(args.backend, "rss")
        self.assertEqual(args.limit_accounts, 3)

    def test_parse_args_json_only_flag(self):
        args = parse_args(["--backend", "auto", "--json-only"])
        self.assertTrue(args.json_only)

    def test_parse_args_each_backend(self):
        for backend in BACKEND_CHOICES:
            with self.subTest(backend=backend):
                args = parse_args(["--backend", backend])
                self.assertEqual(args.backend, backend)


# ---------------------------------------------------------------------------
# 2. Exit codes (A-C5-2)
# ---------------------------------------------------------------------------


class TestCliExitCodes(unittest.TestCase):
    def test_exit_code_set(self):
        self.assertEqual(EXIT_CODES, (0, 1, 2, 3))
        self.assertEqual(EXIT_OK, 0)
        self.assertEqual(EXIT_LEASE_FALLBACK, 1)
        self.assertEqual(EXIT_RATE_LIMIT, 2)
        self.assertEqual(EXIT_CONFIG_ERROR, 3)

    def test_exit_zero_on_success(self):
        def cb(args: CliArgs) -> CliRunResult:
            return CliRunResult(exit_code=EXIT_OK, status=_ok_status(), message="ok")

        code, stdout, _ = _run(["--backend", "browser"], callback=cb)
        self.assertEqual(code, EXIT_OK)
        envelope = json.loads(stdout)
        self.assertEqual(envelope["exit_code"], 0)
        self.assertEqual(envelope["backend"], "browser")
        self.assertEqual(envelope["message"], "ok")

    def test_exit_one_on_lease_fallback(self):
        def cb(args: CliArgs) -> CliRunResult:
            return CliRunResult(
                exit_code=EXIT_LEASE_FALLBACK,
                status=_ok_status(),
                message="browser lease unavailable",
            )

        code, _, _ = _run(["--backend", "browser"], callback=cb)
        self.assertEqual(code, EXIT_LEASE_FALLBACK)

    def test_exit_two_on_rate_limit(self):
        def cb(args: CliArgs) -> CliRunResult:
            return CliRunResult(
                exit_code=EXIT_RATE_LIMIT,
                status=_ok_status(),
                message="per-account cooldown breached",
            )

        code, _, _ = _run(["--backend", "auto"], callback=cb)
        self.assertEqual(code, EXIT_RATE_LIMIT)

    def test_exit_three_on_unknown_backend(self):
        code, _, stderr = _run(["--backend", "ftp"])
        self.assertEqual(code, EXIT_CONFIG_ERROR)
        self.assertIn("config error", stderr)

    def test_exit_three_on_missing_required_arg(self):
        code, _, _ = _run([])
        self.assertEqual(code, EXIT_CONFIG_ERROR)

    def test_exit_three_on_negative_limit(self):
        code, _, stderr = _run(["--backend", "auto", "--limit-accounts", "0"])
        self.assertEqual(code, EXIT_CONFIG_ERROR)
        self.assertIn("--limit-accounts", stderr)

    def test_exit_three_when_pipeline_raises(self):
        def cb(args: CliArgs) -> CliRunResult:
            raise RuntimeError("boom")

        code, _, stderr = _run(["--backend", "auto"], callback=cb)
        self.assertEqual(code, EXIT_CONFIG_ERROR)
        self.assertIn("pipeline error", stderr)

    def test_default_callback_returns_lease_fallback(self):
        # When no run_callback is wired (pre-C4 integration), the CLI
        # must surface EXIT_LEASE_FALLBACK rather than crashing.
        code, stdout, _ = _run(["--backend", "browser"])
        self.assertEqual(code, EXIT_LEASE_FALLBACK)
        envelope = json.loads(stdout)
        self.assertEqual(envelope["status"]["scan_state"], "idle")
        self.assertEqual(envelope["status"]["browser_ready"], 0)

    def test_invalid_exit_code_from_callback_maps_to_config_error(self):
        def cb(args: CliArgs) -> CliRunResult:
            return CliRunResult(exit_code=99, status=_ok_status())

        code, _, stderr = _run(["--backend", "auto"], callback=cb)
        self.assertEqual(code, EXIT_CONFIG_ERROR)
        self.assertIn("invalid exit_code", stderr)


# ---------------------------------------------------------------------------
# 3. StatusSurface JSON shape (A-C5-3)
# ---------------------------------------------------------------------------


class TestStatusSurface(unittest.TestCase):
    def test_seven_indicators(self):
        self.assertEqual(len(STATUS_INDICATORS), 7)
        expected = {
            "total",
            "enabled",
            "scanned_today",
            "browser_ready",
            "scan_state",
            "parse_fail",
            "fallback_count",
        }
        self.assertEqual(set(STATUS_INDICATORS), expected)

    def test_render_emits_all_seven_keys(self):
        surface = StatusSurface()
        payload = surface.render(_ok_status())
        for name in STATUS_INDICATORS:
            self.assertIn(name, payload, f"missing indicator {name}")

    def test_render_concrete_values(self):
        surface = StatusSurface()
        p = surface.render(_ok_status())
        self.assertEqual(p["total"], 10)
        self.assertEqual(p["enabled"], 8)
        self.assertEqual(p["scanned_today"], 5)
        self.assertEqual(p["browser_ready"], 1)
        self.assertEqual(p["scan_state"], "running")
        self.assertEqual(p["parse_fail"], 1)
        # fallback_count = sum of all non-browser_agent counts.
        # browser_agent=4, rss=1, manual=0 → fallback = 1
        self.assertEqual(p["fallback_count"], 1)

    def test_render_includes_by_backend_count_map(self):
        surface = StatusSurface()
        p = surface.render(_ok_status())
        backend_map = p["by_backend_count"]
        self.assertEqual(set(DEFAULT_BACKEND_KEYS), set(backend_map.keys()))
        self.assertEqual(backend_map["browser_agent"], 4)
        self.assertEqual(backend_map["rss_public"], 1)
        self.assertEqual(backend_map["manual_curated"], 0)
        self.assertEqual(backend_map["x_api"], 0)

    def test_fallback_count_excludes_primary(self):
        surface = StatusSurface()
        all_browser = StatusInput(
            total_accounts=3,
            enabled_accounts=3,
            scanned_today=3,
            browser_ready=True,
            scan_state="running",
            parse_fail_count=0,
            by_backend_count={"browser_agent": 5},
        )
        self.assertEqual(surface.render(all_browser)["fallback_count"], 0)

    def test_render_json_round_trip(self):
        surface = StatusSurface()
        json_str = surface.render_json(_ok_status())
        decoded = json.loads(json_str)
        for name in STATUS_INDICATORS:
            self.assertIn(name, decoded)

    def test_browser_ready_zero_when_not_ready(self):
        surface = StatusSurface()
        not_ready = _ok_status()
        not_ready.browser_ready = False
        self.assertEqual(surface.render(not_ready)["browser_ready"], 0)

    def test_invalid_scan_state_raises(self):
        bad = StatusInput(
            total_accounts=1,
            enabled_accounts=1,
            scanned_today=0,
            browser_ready=True,
            scan_state="exploding",
            parse_fail_count=0,
        )
        with self.assertRaises(ValueError):
            StatusSurface().render(bad)

    def test_enabled_exceeds_total_raises(self):
        bad = StatusInput(
            total_accounts=2,
            enabled_accounts=3,
            scanned_today=0,
            browser_ready=True,
            scan_state="running",
            parse_fail_count=0,
        )
        with self.assertRaises(ValueError):
            StatusSurface().render(bad)

    def test_negative_parse_fail_raises(self):
        bad = StatusInput(
            total_accounts=1,
            enabled_accounts=1,
            scanned_today=0,
            browser_ready=True,
            scan_state="running",
            parse_fail_count=-1,
        )
        with self.assertRaises(ValueError):
            StatusSurface().render(bad)

    def test_primary_backend_constant(self):
        self.assertEqual(PRIMARY_BACKEND, "browser_agent")

    def test_valid_scan_states_inventory(self):
        self.assertEqual(VALID_SCAN_STATES, ("running", "paused", "failed", "idle"))


# ---------------------------------------------------------------------------
# 4. End-to-end CLI shape (A-C5-4 join)
# ---------------------------------------------------------------------------


class TestCliEndToEnd(unittest.TestCase):
    def test_full_envelope_shape_ok_path(self):
        def cb(args: CliArgs) -> CliRunResult:
            return CliRunResult(
                exit_code=EXIT_OK,
                status=_ok_status(),
                message=f"scanned backend={args.backend} limit={args.limit_accounts}",
            )

        code, stdout, _ = _run(
            ["--backend", "rss", "--limit-accounts", "2"], callback=cb
        )
        self.assertEqual(code, EXIT_OK)
        envelope = json.loads(stdout)
        self.assertEqual(envelope["backend"], "rss")
        self.assertEqual(envelope["limit_accounts"], 2)
        self.assertEqual(envelope["exit_code"], 0)
        for name in STATUS_INDICATORS:
            self.assertIn(name, envelope["status"])
        # All 7 indicator keys + 1 aux by_backend_count + 0 surprises.
        self.assertEqual(
            set(envelope["status"].keys()),
            set(STATUS_INDICATORS) | {"by_backend_count"},
        )


# ---------------------------------------------------------------------------
# 5. Secret-scan parity (CLI / Surface modules)
# ---------------------------------------------------------------------------


class TestNoSecretLeaksC5(unittest.TestCase):
    SECRET_RX = re.compile(
        "(" + "set-" + "cookie:|bearer" + r"\s+[a-z0-9]|x-csrf-" + "token:|" + "session=" + r"[a-z0-9]+|auth-" + "token=" + ")",
        re.IGNORECASE,
    )

    def test_no_forbidden_tokens_in_module_sources(self):
        import importlib.resources as resources

        pkg = "social_browser_backend_x"
        for name in ("cli", "status_surface"):
            with self.subTest(module=name):
                source = resources.files(pkg).joinpath(f"{name}.py").read_text()
                self.assertEqual(
                    list(self.SECRET_RX.finditer(source)), [], f"secret hit in {name}"
                )


if __name__ == "__main__":
    unittest.main()
