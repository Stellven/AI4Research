"""Survey-grade DeepResearch package.

This package is intentionally separate from the legacy research CLI so survey
logic can evolve as a plug-in style package instead of bloating cli.py.
"""

from .planner import create_survey_plan
from .evidence_pack import build_evidence_packs
from .section_compiler import compile_section, compile_survey
from .evaluator import evaluate_survey

__all__ = [
    "build_evidence_packs",
    "compile_section",
    "compile_survey",
    "create_survey_plan",
    "evaluate_survey",
]
