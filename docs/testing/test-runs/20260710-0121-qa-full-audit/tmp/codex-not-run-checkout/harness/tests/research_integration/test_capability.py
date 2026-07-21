"""test_capability — Verify 6 research.* capabilities are registered and functional."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from capability_inference import infer_capabilities, infer_node_capabilities
from solar_skills import CAPABILITY_RULES, CORE_SOLAR_SKILLS


class TestResearchCapabilityRegistration:
    """Verify all 6 research.* capabilities exist in CAPABILITY_RULES."""

    def test_capability_rules_has_research_entries(self):
        research_rules = [
            r for r in CAPABILITY_RULES
            if any(c.startswith("research.") or c in ("source.search", "evidence.extract", "claim.mine", "citation.verify", "report.compile", "factuality.evaluate")
                   for c in r.get("capabilities", []))
        ]
        assert len(research_rules) >= 6, f"Expected >= 6 research rules, got {len(research_rules)}"

    def test_source_search_registered(self):
        caps = _all_research_caps()
        assert any("source.search" in c or "research.source" in c for c in caps), f"source.search not found in {caps}"

    def test_evidence_extract_registered(self):
        caps = _all_research_caps()
        assert any("evidence.extract" in c or "research.evidence" in c for c in caps), f"evidence.extract not found in {caps}"

    def test_claim_mine_registered(self):
        caps = _all_research_caps()
        assert any("claim.mine" in c or "research.claim" in c for c in caps), f"claim.mine not found in {caps}"

    def test_citation_verify_registered(self):
        caps = _all_research_caps()
        assert any("citation.verify" in c or "research.factuality" in c for c in caps), f"citation.verify not found in {caps}"

    def test_report_compile_registered(self):
        caps = _all_research_caps()
        assert any("report.compile" in c or "research.report" in c for c in caps), f"report.compile not found in {caps}"

    def test_factuality_evaluate_registered(self):
        caps = _all_research_caps()
        assert any("factuality.evaluate" in c or "research.evaluator" in c for c in caps), f"factuality.evaluate not found in {caps}"

    def test_deep_research_skill_in_core_skills(self):
        names = [s["name"] for s in CORE_SOLAR_SKILLS]
        assert "solar-deep-research" in names, f"solar-deep-research not found in core skills: {names}"

    def test_infer_capabilities_matches_source_search(self):
        matches = infer_capabilities("multi-source search across web and academic sources")
        caps = [c for m in matches for c in m.get("capabilities", [])]
        assert any("source.search" in c for c in caps), f"source.search not matched: {caps}"

    def test_infer_capabilities_matches_evidence_extract(self):
        matches = infer_capabilities("extract evidence with span_text and content_hash from passages")
        caps = [c for m in matches for c in m.get("capabilities", [])]
        assert any("evidence.extract" in c for c in caps), f"evidence.extract not matched: {caps}"

    def test_infer_capabilities_matches_claim_mine(self):
        matches = infer_capabilities("assertion extract and mine claim.evidence from documents")
        caps = [c for m in matches for c in m.get("capabilities", [])]
        assert any("claim.mine" in c for c in caps), f"claim.mine not matched: {caps}"

    def test_infer_capabilities_matches_citation_verify(self):
        matches = infer_capabilities("verify citation spans and check span_text accuracy")
        caps = [c for m in matches for c in m.get("capabilities", [])]
        assert any("citation.verify" in c for c in caps), f"citation.verify not matched: {caps}"

    def test_infer_capabilities_matches_report_compile(self):
        matches = infer_capabilities("compile report chapters from report_ast sections")
        caps = [c for m in matches for c in m.get("capabilities", [])]
        assert any("report.compile" in c for c in caps), f"report.compile not matched: {caps}"

    def test_infer_capabilities_matches_factuality_evaluate(self):
        matches = infer_capabilities("evaluate factuality and global consistency unsupported_claim_rate")
        caps = [c for m in matches for c in m.get("capabilities", [])]
        assert any("factuality.evaluate" in c for c in caps), f"factuality.evaluate not matched: {caps}"

    def test_infer_node_capabilities_works(self):
        node = {
            "id": "R3",
            "goal": "multi-source search across web and academic sources",
            "acceptance": ["source.search returns results", "evidence.extract works"],
        }
        result = infer_node_capabilities(node)
        assert "capabilities" in result
        assert "providers" in result
        assert len(result["capabilities"]) >= 2, f"Expected >= 2 caps, got {result['capabilities']}"

    def test_existing_capabilities_unchanged(self):
        """Non-research capabilities still match."""
        matches = infer_capabilities("use tmux and coordinator for sprint management")
        caps = [c for m in matches for c in m.get("capabilities", [])]
        assert any("harness" in c.lower() for c in caps), f"Expected harness capabilities: {caps}"

    def test_no_mock_in_tests(self):
        """Verify zero @mock.patch in this test file."""
        import subprocess
        result = subprocess.run(
            ["grep", "-rc", "@mock.patch|mock.patch|Mock\\(",
             str(Path(__file__).resolve())],
            capture_output=True, text=True,
        )
        lines = [l for l in result.stdout.strip().split("\n") if l and not l.endswith(":0")]
        assert lines == [], f"Mock usage found: {lines}"


def _all_research_caps():
    """Collect all research-related capabilities from CAPABILITY_RULES."""
    caps = set()
    for rule in CAPABILITY_RULES:
        for c in rule.get("capabilities", []):
            if c.startswith("research.") or c in (
                "source.search", "evidence.extract", "claim.mine",
                "citation.verify", "report.compile", "factuality.evaluate",
            ):
                caps.add(c)
    return caps
