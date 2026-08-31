"""Offline regression: migration assets and scientific Evidence ABI closure."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HARNESS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "migration_closure_audit", HARNESS / "tools" / "migration_closure_audit.py")
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


class MigrationClosureTests(unittest.TestCase):
    def test_runtime_inventory_and_schema_references(self):
        result = audit_module.audit(audit_module.filesystem_reader(HARNESS), True)
        self.assertTrue(result["ok"], result["errors"])
        self.assertGreaterEqual(result["files"], 165)

    def test_absent_file_fails_closed(self):
        actual = audit_module.filesystem_reader(HARNESS)
        def read(path):
            if path == "schemas/evidence/research_paper.v1.schema.json":
                raise FileNotFoundError(path)
            return actual(path)
        result = audit_module.audit(read)
        self.assertFalse(result["ok"])
        self.assertTrue(any("research_paper.v1" in item for item in result["errors"]))

    def test_changed_contract_fails_closed(self):
        actual = audit_module.filesystem_reader(HARNESS)
        def read(path):
            return b"{}" if path == "schemas/evidence/scientific_report.v1.schema.json" else actual(path)
        self.assertFalse(audit_module.audit(read)["ok"])

    def test_crlf_and_lf_have_same_digest(self):
        self.assertEqual(audit_module.normalized_sha256(b"a\r\nb\r\n"),
                         audit_module.normalized_sha256(b"a\nb\n"))
        self.assertNotEqual(audit_module.normalized_sha256(b"a \n"),
                            audit_module.normalized_sha256(b"a\n"))

    def test_unsafe_paths_are_rejected(self):
        for path in ("../escape", "/absolute", "C:/absolute", "a\\escape"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                audit_module.safe_path(path)

    def test_missing_and_invalid_pointer_refs_are_detected_offline(self):
        docs = {"schemas/a.json": {"$ref": "b.json#/missing"},
                "schemas/b.json": {"$id": "https://example.invalid/b", "type": "object"}}
        self.assertEqual(len(audit_module.check_references(docs)), 1)
        docs["schemas/a.json"]["$ref"] = "https://example.invalid/b#/type"
        self.assertEqual(audit_module.check_references(docs), [])
        docs["schemas/a.json"]["$ref"] = "https://example.invalid/absent"
        self.assertEqual(len(audit_module.check_references(docs)), 1)

    def test_git_index_reader_does_not_fallback_to_worktree(self):
        with patch.object(audit_module.subprocess, "run") as run:
            run.return_value.returncode = 1
            read = audit_module.git_reader(Path("source"), ":")
            with self.assertRaises(FileNotFoundError):
                read("schemas/evidence/research_paper.v1.schema.json")
            self.assertEqual(run.call_args.args[0][-1],
                             ":harness/schemas/evidence/research_paper.v1.schema.json")

    def test_evidence_fixtures_pass_production_schema_validator(self):
        sys.path.insert(0, str(HARNESS))
        try:
            from evaluators.scientific.common import validate_schema
            fixtures = sorted((HARNESS / "schemas" / "evidence" / "fixtures").glob("*.json"))
            self.assertGreaterEqual(len(fixtures), 24)
            for path in fixtures:
                with self.subTest(fixture=path.name):
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    reasons, warnings = validate_schema(payload, payload["schema"])
                    self.assertEqual(reasons, [])
                    self.assertEqual(warnings, [])
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
