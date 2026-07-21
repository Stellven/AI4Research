"""
adapter.py — GEPA optimize_anything adapter for Solar Harness.

Design principles
-----------------
* Real namespace: ``from gepa.optimize_anything import …`` (per I0 gate result).
* Zero side effects at import time: no I/O, no GEPA calls, no config reads.
* Graceful degradation: if ``gepa`` is not installed the try/except at module
  top sets ``_GEPA_AVAILABLE = False``; constructing ``GEPAAdapter`` then
  raises ``AdapterError("gepa unavailable")`` instead of crashing the harness.
* Unit-testable without gepa: ``GEPAConfig`` and ``AdapterError`` are plain
  Python and carry no gepa dependency.  Tests can instantiate configs, assert
  on validation errors, and verify that ``GEPAAdapter`` raises the right error
  when gepa is absent—all without the package installed.

Public symbols (re-exported from ``integrations.gepa_optimizer.__init__``)
---------------------------------------------------------------------------
* ``AdapterError``   — adapter-level failure (gepa absent, config invalid, …)
* ``GEPAConfig``     — adapter-level config dataclass (no gepa dependency)
* ``GEPAAdapter``    — thin wrapper around ``optimize_anything``
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional GEPA import – graceful fallback when the package is not installed
# ---------------------------------------------------------------------------

try:
    from gepa.optimize_anything import (  # real namespace confirmed by I0 gate
        optimize_anything as _gepa_optimize_anything,
        GEPAConfig as _GepaInternalConfig,
        EngineConfig as _EngineConfig,
        ReflectionConfig as _ReflectionConfig,
        TrackingConfig as _TrackingConfig,
        MergeConfig as _MergeConfig,
        RefinerConfig as _RefinerConfig,
    )
    _GEPA_AVAILABLE: bool = True
except ImportError:
    _GEPA_AVAILABLE = False
    _gepa_optimize_anything = None       # type: ignore[assignment]
    _GepaInternalConfig = None           # type: ignore[assignment]
    _EngineConfig = None                 # type: ignore[assignment]
    _ReflectionConfig = None             # type: ignore[assignment]
    _TrackingConfig = None               # type: ignore[assignment]
    _MergeConfig = None                  # type: ignore[assignment]
    _RefinerConfig = None                # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------

class AdapterError(RuntimeError):
    """Raised for adapter-level failures.

    Typical causes:
    * ``gepa`` package not installed.
    * Invalid ``GEPAConfig`` fields.
    * ``optimize_anything`` raised an unexpected exception.
    """


# ---------------------------------------------------------------------------
# Adapter-level config (importable without gepa)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class GEPAConfig:
    """Adapter-level configuration for ``GEPAAdapter``.

    All fields use plain Python types so this class is fully instantiable
    without the ``gepa`` package installed.  ``GEPAAdapter._build_gepa_config``
    maps these fields onto gepa's internal config hierarchy at run time.

    Extra kwargs
    ------------
    The ``extra`` dict accepts prefixed keys that are forwarded to the
    corresponding gepa sub-config constructors:

    * ``engine_*``     → ``EngineConfig``
    * ``reflection_*`` → ``ReflectionConfig``
    * ``tracking_*``   → ``TrackingConfig``
    * ``merge_*``      → ``MergeConfig``
    * ``refiner_*``    → ``RefinerConfig``
    """

    # Engine / model settings
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4096

    # Optimization loop settings
    max_iterations: int = 3

    # Reflection settings
    reflection_enabled: bool = True
    reflection_depth: int = 2

    # Tracking / observability
    tracking_enabled: bool = True
    run_id: str | None = None

    # Candidate merge strategy
    merge_strategy: str = "best_of_n"

    # Refiner settings
    refiner_enabled: bool = True
    refiner_rounds: int = 1

    # Arbitrary extra kwargs, prefixed per sub-config (see class docstring)
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1, got {self.max_iterations}")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError(
                f"temperature must be in [0.0, 2.0], got {self.temperature}"
            )
        if self.refiner_rounds < 0:
            raise ValueError(
                f"refiner_rounds must be >= 0, got {self.refiner_rounds}"
            )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class GEPAAdapter:
    """Thin wrapper around ``gepa.optimize_anything``.

    Raises ``AdapterError`` at construction time if the ``gepa`` package is
    not installed so callers learn about the missing dependency before doing
    any other work.

    Actual optimization is deferred to :meth:`run` so ``__init__`` is safe to
    call in test environments and in import-time code paths.

    Example
    -------
    ::

        cfg = GEPAConfig(model="gpt-4o", max_iterations=5)
        adapter = GEPAAdapter(cfg)
        result = adapter.run(prompt="Improve this prompt:", seed="You are …")
    """

    def __init__(self, config: GEPAConfig) -> None:
        if not _GEPA_AVAILABLE:
            raise AdapterError(
                "The 'gepa' package is not installed. "
                "Install it in an isolated venv with:  pip install gepa"
            )
        if not isinstance(config, GEPAConfig):
            raise TypeError(
                f"config must be a GEPAConfig instance, got {type(config).__name__!r}"
            )
        self._adapter_config: GEPAConfig = config
        self._gepa_config: Any = None  # lazily built on first run()

    # ------------------------------------------------------------------
    # Internal config builder
    # ------------------------------------------------------------------

    def _build_gepa_config(self) -> Any:
        """Construct the gepa-internal config hierarchy from adapter config.

        Called once on the first :meth:`run` call; result is cached.
        """
        cfg = self._adapter_config
        extra: dict[str, Any] = cfg.extra or {}

        def _sub(prefix: str) -> dict[str, Any]:
            """Strip *prefix* from matching keys and return the sub-dict."""
            return {k[len(prefix):]: v for k, v in extra.items() if k.startswith(prefix)}

        engine = _EngineConfig(
            model=cfg.model,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            **_sub("engine_"),
        )
        reflection = _ReflectionConfig(
            enabled=cfg.reflection_enabled,
            depth=cfg.reflection_depth,
            **_sub("reflection_"),
        )
        tracking_kwargs: dict[str, Any] = {
            "enabled": cfg.tracking_enabled,
            **_sub("tracking_"),
        }
        if cfg.run_id is not None:
            tracking_kwargs["run_id"] = cfg.run_id
        tracking = _TrackingConfig(**tracking_kwargs)

        merge = _MergeConfig(
            strategy=cfg.merge_strategy,
            **_sub("merge_"),
        )
        refiner = _RefinerConfig(
            enabled=cfg.refiner_enabled,
            rounds=cfg.refiner_rounds,
            **_sub("refiner_"),
        )

        return _GepaInternalConfig(
            max_iterations=cfg.max_iterations,
            engine=engine,
            reflection=reflection,
            tracking=tracking,
            merge=merge,
            refiner=refiner,
        )

    def _ensure_gepa_config(self) -> Any:
        """Build and cache the gepa-internal config (idempotent)."""
        if self._gepa_config is None:
            try:
                self._gepa_config = self._build_gepa_config()
            except Exception as exc:
                raise AdapterError(f"Failed to build GEPA config: {exc}") from exc
        return self._gepa_config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, **kwargs: Any) -> Any:
        """Run GEPA optimization.

        All *kwargs* are forwarded verbatim to ``gepa.optimize_anything``
        alongside the config object built from :class:`GEPAConfig`.

        Parameters
        ----------
        **kwargs:
            Forwarded to ``optimize_anything(config=…, **kwargs)``.
            Typical keys: ``prompt``, ``seed``, ``dataset``, ``evaluator``.

        Returns
        -------
        Any
            Whatever ``optimize_anything`` returns (typically a result object
            with a ``.best_candidate`` attribute).

        Raises
        ------
        AdapterError
            Wraps any exception raised by ``optimize_anything``.
        """
        gepa_config = self._ensure_gepa_config()
        try:
            return _gepa_optimize_anything(config=gepa_config, **kwargs)
        except AdapterError:
            raise
        except Exception as exc:
            logger.exception("gepa.optimize_anything raised an exception")
            raise AdapterError(f"GEPA optimization failed: {exc}") from exc

    def wrap_evaluator(self, evaluator: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a callable evaluator for use with ``optimize_anything``.

        The default implementation is a transparent pass-through: GEPA
        accepts plain callables directly, so no wrapping is needed.  This
        method exists as an extension point so callers can inject GEPA-
        specific adapters (e.g. type adapters for structured evaluator
        results) without changing call sites.

        Parameters
        ----------
        evaluator:
            Any callable ``(candidate: str, **ctx) -> float | dict``.

        Returns
        -------
        Callable
            The same callable (or a wrapped version, if gepa requires one).
        """
        if not callable(evaluator):
            raise TypeError(
                f"evaluator must be callable, got {type(evaluator).__name__!r}"
            )
        return evaluator

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> GEPAConfig:
        """Return the adapter-level config (read-only)."""
        return self._adapter_config

    @property
    def gepa_available(self) -> bool:
        """True when the ``gepa`` package was successfully imported."""
        return _GEPA_AVAILABLE
