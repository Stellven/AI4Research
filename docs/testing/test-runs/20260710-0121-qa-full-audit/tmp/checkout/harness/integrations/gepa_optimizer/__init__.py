"""
gepa_optimizer — GEPA optimisation integration package for Solar Harness.

Stable public API; importing this package has **zero side effects**.
All submodule symbols are loaded lazily on first attribute access so that
``import integrations.gepa_optimizer`` never touches the file system,
spawns processes, reads configs, or calls any LLM.

Usage::

    from integrations.gepa_optimizer import GEPAAdapter, Budget, ArtifactStore
"""

from __future__ import annotations

__version__: str = "0.1.0"
__author__: str = "Solar Harness"

# ---------------------------------------------------------------------------
# Public API declaration
# ---------------------------------------------------------------------------
# Symbols are resolved lazily (see __getattr__ below).  Listing them here
# lets tools like mypy, pyright, and ``help()`` discover the API without
# triggering any imports.
__all__: list[str] = [
    "__version__",
    # adapter
    "GEPAAdapter",
    "GEPAConfig",
    "AdapterError",
    # evaluator
    "SubprocessEvaluator",
    "EvaluatorResult",
    "EvaluatorError",
    # artifact_store
    "ArtifactStore",
    "RunRecord",
    "CandidateRecord",
    # operator_router
    "OperatorRouter",
    "OperatorSpec",
    # budgets
    "Budget",
    "SpendStopper",
    "EvalStopper",
    "WalltimeStopper",
    "PlateauStopper",
    "StopFileStopper",
    # promote
    "Promoter",
    "PromotionTarget",
    "RollbackError",
]

# ---------------------------------------------------------------------------
# Lazy-load map: public name → (relative_module, attribute)
# ---------------------------------------------------------------------------
# All keys that appear in __all__ (except __version__) must be present here.
_LAZY: dict[str, tuple[str, str]] = {
    # adapter.py — GEPA import wrapper, config builder, evaluator wrapper
    "GEPAAdapter":         (".adapter",         "GEPAAdapter"),
    "GEPAConfig":          (".adapter",         "GEPAConfig"),
    "AdapterError":        (".adapter",         "AdapterError"),
    # evaluator.py — subprocess JSON evaluator sandbox
    "SubprocessEvaluator": (".evaluator",       "SubprocessEvaluator"),
    "EvaluatorResult":     (".evaluator",       "EvaluatorResult"),
    "EvaluatorError":      (".evaluator",       "EvaluatorError"),
    # artifact_store.py — run dirs, candidates, pareto, summary, audit, cache
    "ArtifactStore":       (".artifact_store",  "ArtifactStore"),
    "RunRecord":           (".artifact_store",  "RunRecord"),
    "CandidateRecord":     (".artifact_store",  "CandidateRecord"),
    # operator_router.py — physical operator selection and multimodal gate
    "OperatorRouter":      (".operator_router", "OperatorRouter"),
    "OperatorSpec":        (".operator_router", "OperatorSpec"),
    # budgets.py — budget and stopper protocols
    "Budget":              (".budgets",         "Budget"),
    "SpendStopper":        (".budgets",         "SpendStopper"),
    "EvalStopper":         (".budgets",         "EvalStopper"),
    "WalltimeStopper":     (".budgets",         "WalltimeStopper"),
    "PlateauStopper":      (".budgets",         "PlateauStopper"),
    "StopFileStopper":     (".budgets",         "StopFileStopper"),
    # promote.py — promote, backup, diff, atomic replace, rollback
    "Promoter":            (".promote",         "Promoter"),
    "PromotionTarget":     (".promote",         "PromotionTarget"),
    "RollbackError":       (".promote",         "RollbackError"),
}


def __getattr__(name: str) -> object:
    """Resolve lazy-loaded public symbols from submodules.

    Caches the resolved value in the module's globals so subsequent accesses
    are O(1) dict lookups rather than repeated ``importlib`` calls.
    """
    if name in _LAZY:
        import importlib

        relative_path, attr = _LAZY[name]
        # __package__ is the fully-qualified package name of this __init__.py,
        # e.g. "integrations.gepa_optimizer".  importlib.import_module resolves
        # the relative path against it.
        mod = importlib.import_module(relative_path, package=__package__)
        value = getattr(mod, attr)
        # Cache to avoid repeated importlib lookups.
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
