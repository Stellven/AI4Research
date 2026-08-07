"""Tests for argument_density gate — S03 N4.

≥ 12 tests: each dimension ≥ 2 (present / absent) + applicability + edge cases.
"""

from __future__ import annotations

import pytest

from lib.research.survey.schemas import (
    ArgumentDensityProfile,
    DimensionIndicator,
    NotApplicableEntry,
    SectionReview,
    SectionSpec,
)
from lib.research.survey.gates import GateRegistry
from lib.research.survey.gates.argument_density import (
    detect_engineering_implication,
    detect_evaluation_protocol,
    detect_failure_negative_evidence,
    detect_mechanism_comparison,
    detect_method_taxonomy,
    map_dimension_applicability,
    measure_argument_density,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _review(section_id: str = "s1", **kw) -> SectionReview:
    defaults = dict(
        section_id=section_id,
        verdict="pass",
        unsupported_claim_rate=0.0,
        citation_span_accuracy=1.0,
        source_diversity_score=1.0,
        repetition_score=0.0,
        issues=[],
    )
    defaults.update(kw)
    return SectionReview(**defaults)


def _spec(
    section_id: str = "s1",
    title: str = "Test Section",
    rq: str = "How does X work?",
) -> SectionSpec:
    return SectionSpec(
        section_id=section_id,
        chapter_id="ch1",
        title=title,
        order=1,
        target_chars=5000,
        research_question=rq,
        required_source_types=["paper"],
        min_evidence=3,
        min_claims=2,
    )


# ---------------------------------------------------------------------------
# Dimension: mechanism_comparison (present / absent)
# ---------------------------------------------------------------------------


class TestMechanismComparison:
    def test_present(self) -> None:
        text = "Transformer versus RNN architectures. The attention mechanism outperforms recurrent approaches on long sequences."
        detected, spans = detect_mechanism_comparison(text)
        assert detected is True
        assert len(spans) >= 1

    def test_absent(self) -> None:
        text = "This section provides a general overview of the topic with no specific comparisons between methods."
        detected, spans = detect_mechanism_comparison(text)
        assert detected is False
        assert spans == []


# ---------------------------------------------------------------------------
# Dimension: method_taxonomy (present / absent)
# ---------------------------------------------------------------------------


class TestMethodTaxonomy:
    def test_present(self) -> None:
        text = "We organize the methods into the following category: (1) supervised approaches, (2) unsupervised methods, and (3) hybrid strategies."
        detected, spans = detect_method_taxonomy(text)
        assert detected is True
        assert any("category" in s.lower() for s in spans)

    def test_absent(self) -> None:
        text = "The results showed improvement across all tested configurations."
        detected, spans = detect_method_taxonomy(text)
        assert detected is False


# ---------------------------------------------------------------------------
# Dimension: evaluation_protocol (present / absent)
# ---------------------------------------------------------------------------


class TestEvaluationProtocol:
    def test_present(self) -> None:
        text = "We evaluate the models using standard benchmark datasets. The evaluation metric is BLEU score."
        detected, spans = detect_evaluation_protocol(text)
        assert detected is True
        assert len(spans) >= 1

    def test_absent(self) -> None:
        text = "The historical development of this field traces back to early computational models."
        detected, spans = detect_evaluation_protocol(text)
        assert detected is False


# ---------------------------------------------------------------------------
# Dimension: failure_negative_evidence (present / absent)
# ---------------------------------------------------------------------------


class TestFailureNegativeEvidence:
    def test_present(self) -> None:
        text = "A key limitation of this approach is its failure to generalize. We also found negative results on small datasets."
        detected, spans = detect_failure_negative_evidence(text)
        assert detected is True
        assert len(spans) >= 1

    def test_absent(self) -> None:
        text = "The approach works well and achieves state-of-the-art performance on all benchmarks."
        detected, spans = detect_failure_negative_evidence(text)
        assert detected is False


# ---------------------------------------------------------------------------
# Dimension: engineering_implication (present / absent)
# ---------------------------------------------------------------------------


class TestEngineeringImplication:
    def test_present(self) -> None:
        text = "The engineering implication of this finding is significant for production deployment. We discuss practical implications for real-world systems."
        detected, spans = detect_engineering_implication(text)
        assert detected is True
        assert len(spans) >= 1

    def test_absent(self) -> None:
        text = "The theoretical framework establishes connections between information theory and learning."
        detected, spans = detect_engineering_implication(text)
        assert detected is False


# ---------------------------------------------------------------------------
# measure_argument_density integration
# ---------------------------------------------------------------------------


class TestMeasureArgumentDensity:
    def test_all_dimensions_present(self) -> None:
        text = (
            "We compare Transformer versus RNN architectures. "
            "Methods fall into three category types: supervised, unsupervised, and hybrid. "
            "We use benchmark evaluation with standard metric scores. "
            "A key limitation is the failure to handle edge cases. "
            "The engineering implication for production deployment is discussed."
        )
        profile = measure_argument_density(_review(), text)
        assert isinstance(profile, ArgumentDensityProfile)
        assert profile.section_id == "s1"
        present_count = sum(1 for v in profile.dimension_coverages.values() if v == "present")
        assert present_count == 5
        assert profile.density_score == 1.0

    def test_no_dimensions_present(self) -> None:
        text = "Some general text without any technical depth."
        profile = measure_argument_density(_review("s2"), text)
        assert profile.density_score == 0.0
        assert all(v == "absent" for v in profile.dimension_coverages.values())
        assert len(profile.issues) >= 1
        assert "low_density_dimensions" in profile.issues[0]

    def test_partial_density(self) -> None:
        text = "We evaluate using standard benchmark metrics. A limitation is the failure on small data."
        profile = measure_argument_density(_review("s3"), text)
        assert 0.0 < profile.density_score < 1.0
        assert profile.dimension_coverages["evaluation_protocol"] == "present"
        assert profile.dimension_coverages["failure_negative_evidence"] == "present"

    def test_empty_text(self) -> None:
        profile = measure_argument_density(_review("s4"), "")
        assert profile.density_score == 0.0
        assert len(profile.detected_indicators) == 0


# ---------------------------------------------------------------------------
# map_dimension_applicability
# ---------------------------------------------------------------------------


class TestMapDimensionApplicability:
    def test_background_section_excludes_dims(self) -> None:
        text = "General overview of the historical context and key terminology."
        profile = measure_argument_density(_review("bg1"), text)
        spec = _spec("bg1", title="Background", rq="背景: what is the history of X?")
        result = map_dimension_applicability(spec, profile)
        dims = result.dimension_coverages
        assert dims.get("engineering_implication") == "not_applicable"
        assert dims.get("failure_negative_evidence") == "not_applicable"
        assert len(result.not_applicable_entries) == 2
        for entry in result.not_applicable_entries:
            assert entry.reason  # non-empty per AC2.2

    def test_normal_section_no_override(self) -> None:
        text = "We benchmark the approach and discuss limitations."
        profile = measure_argument_density(_review("n1"), text)
        spec = _spec("n1", rq="How does method X compare to method Y?")
        result = map_dimension_applicability(spec, profile)
        not_app = [e.dimension for e in result.not_applicable_entries]
        assert "engineering_implication" not in not_app
        assert "failure_negative_evidence" not in not_app

    def test_background_does_not_override_present(self) -> None:
        text = "We deploy in production environments and discuss engineering implications."
        profile = measure_argument_density(_review("bg2"), text)
        spec = _spec("bg2", rq="Background overview of deployment")
        result = map_dimension_applicability(spec, profile)
        # engineering_implication was detected as "present" — should NOT be overridden
        assert result.dimension_coverages["engineering_implication"] == "present"


# ---------------------------------------------------------------------------
# Gate registration
# ---------------------------------------------------------------------------


class TestGateRegistration:
    def test_registered_in_registry(self) -> None:
        fn = GateRegistry.get("argument_density")
        assert callable(fn)

    def test_gate_returns_profile(self) -> None:
        fn = GateRegistry.get("argument_density")
        result = fn(_review("g1"), "We benchmark the model using standard evaluation.")
        assert isinstance(result, ArgumentDensityProfile)
        assert result.section_id == "g1"
