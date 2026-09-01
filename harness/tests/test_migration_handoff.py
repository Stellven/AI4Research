"""Offline handoff checks; no backend, install or model call."""
import importlib.util
from pathlib import Path
import re
import unittest
from unittest.mock import patch

HARNESS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "migration_portability_audit", HARNESS / "tools" / "migration_portability_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class MigrationHandoffTests(unittest.TestCase):
    def test_onboarding_links_exist(self):
        for name in ("NEW-MACHINE-START-HERE.md", "portability-audit-20260830.md"):
            path = HARNESS / "metadata" / name
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                with self.subTest(file=name, target=target):
                    self.assertTrue((path.parent / target).resolve().exists())

    def test_explicit_onboarding_harness_paths_exist(self):
        content = (HARNESS / "metadata" / "NEW-MACHINE-START-HERE.md").read_text(encoding="utf-8")
        paths = re.findall(r"`(harness/[^`]+)`", content)
        self.assertGreater(len(paths), 20)
        for value in paths:
            relative = value.split("::", 1)[0].removeprefix("harness/")
            with self.subTest(path=value):
                self.assertTrue((HARNESS / relative).exists())

    def test_patterns_find_old_paths_without_matching_relative_paths(self):
        self.assertIsNotNone(audit.PERSONAL_PATH.search("/home/previous-user/project"))
        self.assertIsNone(audit.PERSONAL_PATH.search("harness/lib/example.py"))
        self.assertIsNotNone(audit.HOST_ADDRESS.search("http://" + "localhost:8765"))

    def test_outgoing_scan_reports_location_not_token(self):
        oid = "a" * 40
        token = ("sk-" + "x" * 45).encode()
        def git(_repo, *args):
            if args[0] == "rev-list":
                return (oid + " config.py\n").encode()
            return token
        with patch.object(audit, "git", side_effect=git), patch.object(audit.subprocess, "run") as run:
            run.return_value.stdout = (oid + " blob 48\n").encode()
            result = audit.outgoing_secret_scan(Path("source"))
        self.assertEqual(result["findings"], [{"kind": "provider_token", "object": oid, "path": "config.py"}])
        self.assertNotIn(token.decode(), str(result))

    def test_shell_syntax_targets_only_approved_runtime(self):
        names = b"harness/tools/a.sh\0harness/tests/b.sh\0harness/vendor/c.sh\0"
        with patch.object(audit, "git", return_value=names), patch.object(audit.subprocess, "run") as run:
            run.return_value.returncode = 0
            result = audit.check_runtime_shells(Path("source"), Path("approved-runtime"))
        self.assertEqual(result, {"files": 1, "failures": []})
        self.assertEqual(run.call_args.args[0], ["bash", "-n", str(Path("approved-runtime/tools/a.sh"))])


if __name__ == "__main__":
    unittest.main()
