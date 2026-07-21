from __future__ import annotations

import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.survey import schemas


def test_survey_dataclasses_have_schema_version():
    classes = [
        schemas.SurveyRun,
        schemas.SurveyQuestion,
        schemas.SourceMatrix,
        schemas.SurveyReportAST,
        schemas.ChapterSpec,
        schemas.SectionSpec,
        schemas.EvidencePack,
        schemas.SectionReview,
        schemas.SurveyScorecard,
    ]
    for cls in classes:
        assert "schema_version" in cls.__dataclass_fields__, cls.__name__


def test_to_dict_serializes_nested_dataclasses():
    chapter = schemas.ChapterSpec("ch01", "Intro", 1, 1000, "objective")
    section = schemas.SectionSpec("ch01/sec01", "ch01", "Section", 1, 500, "question", ["paper"], 2, 1)
    ast = schemas.SurveyReportAST("ast", "run", "Title", 50000, [chapter], [section])
    payload = schemas.to_dict(ast)
    assert payload["schema_version"] == schemas.SCHEMA_VERSION
    assert payload["chapters"][0]["chapter_id"] == "ch01"
    assert payload["sections"][0]["section_id"] == "ch01/sec01"
