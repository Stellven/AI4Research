"""compile_eval — Evaluation dimensions, hard validators, golden cases, ASI trace, and GEPA harness.

Public API::

    from lib.compile_eval import evaluate
    from lib.compile_eval.hard_validators import run_hard_validators
    from lib.compile_eval.golden_cases import load_golden_cases
    from lib.compile_eval.asi_trace import init_trace_db, write_trace, query_traces
    from lib.compile_eval.harness import CompileGEPAAdapter
"""
from __future__ import annotations

from .dimensions import evaluate

__all__ = ["evaluate"]
