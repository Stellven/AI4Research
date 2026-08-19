"""A reviser must be judged against the requirement it was actually given.

`report_revision` accumulates `limitations` as its loop runs: the writer's own,
then the reviewer's, then a note when writer and reviewer share a model. The
preservation check used to RECOMPUTE its expectation from that list instead of
comparing against the object that went into the prompt, so the target could move
between asking and checking.

Separately, the "every limitation must be rendered in the report" check ran
against the same accumulated list, which by then included limitations the
reviewer had written about its own review, after the report was generated. No
attempt can render a limitation that did not exist when it was prompted, and
each review adds more, so that condition could never converge -- which is why
this node burned both attempts on every run.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parents[2]
if str(HARNESS / "plugins" / "autosci") not in sys.path:
    sys.path.insert(0, str(HARNESS / "plugins" / "autosci"))

from operators.research_synthesis.base import ResearchOperatorError  # noqa: E402
from operators.research_synthesis.report_revision import (  # noqa: E402
    revision_preservation_requirements,
    verify_revision_response_preservation,
)

METHOD_BODY = (
    "## Evidence Method\n\n"
    "This report uses only the traceable claims in evidence_synthesis.\n"
)
LIMITATION_A = "Only five sources survived validation."
LIMITATION_B = "Coverage is limited to English-language venues."
REVIEWER_LIMITATION = "This review is bounded to the supplied revised report draft."


def _original() -> dict[str, Any]:
    return {
        "report": {
            "body": f"# Title\n\n{METHOD_BODY}\n## Limitations\n\n- {LIMITATION_A}\n- {LIMITATION_B}\n",
            "conclusions": [
                {"conclusion_id": "conclusion-001", "text": "RAG reduces hallucination.",
                 "evidence_ids": ["claim-001"]},
            ],
        },
        "limitations": [LIMITATION_A, LIMITATION_B],
    }


def _response(required: dict[str, Any], *, limitations: list[str]) -> dict[str, Any]:
    """A well-behaved reviser: it echoes exactly what it was handed."""
    body = (
        "# Title\n\n"
        f"{METHOD_BODY}\n"
        "## Limitations\n\n" + "".join(f"- {item}\n" for item in limitations)
    )
    return {
        "report": {
            "body": body,
            "conclusions": [
                {"conclusion_id": "conclusion-001", "text": "RAG reduces hallucination.",
                 "evidence_ids": ["claim-001"]},
            ],
        },
        "limitations": list(limitations),
        "preservation": {
            "preserved_conclusion_ids": required["preserved_conclusion_ids"],
            "preserved_method_sha256": required["preserved_method_sha256"],
            "preserved_limitations": required["preserved_limitations"],
        },
    }


def test_a_reviser_that_echoes_its_prompt_is_accepted() -> None:
    original = _original()
    required = revision_preservation_requirements(original)
    response = _response(required, limitations=required["preserved_limitations"])
    result = verify_revision_response_preservation(original, response, requirements=required)
    assert result


def test_the_target_may_not_move_between_prompting_and_checking() -> None:
    """The regression, stated directly.

    The reviser is prompted with two limitations and echoes both. The reviewer
    then appends one of its own. Checking against the prompt-time requirement
    accepts the revision; recomputing rejects it for omitting a limitation that
    did not exist when it was asked.
    """
    original = _original()
    accumulated = [LIMITATION_A, LIMITATION_B]
    prompt_requirements = revision_preservation_requirements(
        original, required_limitations=accumulated
    )
    response = _response(prompt_requirements,
                         limitations=prompt_requirements["preserved_limitations"])

    # The reviewer speaks after the reviser has already answered.
    accumulated.append(REVIEWER_LIMITATION)

    # Judged against what it was given: accepted.
    assert verify_revision_response_preservation(
        original, response, requirements=prompt_requirements
    )

    # Judged against the moved target: rejected, through no fault of the model.
    with pytest.raises(ResearchOperatorError) as excinfo:
        verify_revision_response_preservation(
            original, response, required_limitations=accumulated
        )
    assert "preservation set" in str(excinfo.value)


def test_recomputation_is_still_available_for_callers_without_a_prompt_object() -> None:
    original = _original()
    required = revision_preservation_requirements(original)
    response = _response(required, limitations=required["preserved_limitations"])
    assert verify_revision_response_preservation(
        original, response, required_limitations=[LIMITATION_A, LIMITATION_B]
    )


def test_preservation_still_rejects_a_genuinely_incomplete_declaration() -> None:
    """Judging against the prompt must not have weakened the check."""
    original = _original()
    required = revision_preservation_requirements(original)
    response = _response(required, limitations=required["preserved_limitations"])
    response["preservation"]["preserved_limitations"] = [LIMITATION_A]
    with pytest.raises(ResearchOperatorError):
        verify_revision_response_preservation(original, response, requirements=required)


def test_preservation_still_rejects_a_dropped_conclusion() -> None:
    original = _original()
    required = revision_preservation_requirements(original)
    response = _response(required, limitations=required["preserved_limitations"])
    response["report"]["conclusions"] = []
    with pytest.raises(ResearchOperatorError):
        verify_revision_response_preservation(original, response, requirements=required)


def test_preservation_still_rejects_a_dropped_method_section() -> None:
    original = _original()
    required = revision_preservation_requirements(original)
    response = _response(required, limitations=required["preserved_limitations"])
    response["report"]["body"] = "# Title\n\n## Limitations\n\n- " + LIMITATION_A + "\n"
    with pytest.raises(ResearchOperatorError):
        verify_revision_response_preservation(original, response, requirements=required)


def test_the_adapter_recompute_reproduces_the_operator_proof() -> None:
    """The published artifact must survive being re-verified downstream.

    `_verify_report_revision_artifact` in the adapter rebuilds the requirement
    from the artifact's own `limitations` field and refuses the node when the
    result differs from the stored proof. Publishing the running accumulator
    there, rather than the set the accepted attempt preserved, makes that
    recompute disagree with the proof on a revision that did everything asked.

    This reproduces the adapter's exact call, so a regression in what the
    operator publishes fails here instead of during a live run.
    """
    original = _original()
    accumulated = [LIMITATION_A, LIMITATION_B]
    prompt_requirements = revision_preservation_requirements(
        original, required_limitations=accumulated
    )
    response = _response(prompt_requirements,
                         limitations=prompt_requirements["preserved_limitations"])
    proof = verify_revision_response_preservation(
        original, response, requirements=prompt_requirements
    )

    # The reviewer speaks afterwards; the accumulator grows.
    accumulated.append(REVIEWER_LIMITATION)

    published_limitations = list(prompt_requirements["preserved_limitations"])
    recomputed = verify_revision_response_preservation(
        original,
        {
            "report": response["report"],
            "limitations": published_limitations,
            "preservation": proof["model_declaration"],
        },
        required_limitations=published_limitations,
    )
    assert recomputed == proof

    # And the failure mode being guarded against: publishing the accumulator.
    with pytest.raises(ResearchOperatorError):
        verify_revision_response_preservation(
            original,
            {
                "report": response["report"],
                "limitations": accumulated,
                "preservation": proof["model_declaration"],
            },
            required_limitations=accumulated,
        )
