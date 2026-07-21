"""
budgets.py — Budget caps and StopperProtocol implementations.

Five stoppers are provided; any one of them can short-circuit the
optimization loop with a structured ``StopReason``:

* ``SpendStopper``    — USD spend exceeds the cap.
* ``EvalStopper``     — number of candidate evaluations exceeds the cap.
* ``WalltimeStopper`` — wall-clock seconds since start exceeds the cap.
* ``PlateauStopper``  — best score has not improved by ``epsilon`` for
                        ``patience`` consecutive evaluations.
* ``StopFileStopper`` — a sentinel file exists on disk (ops emergency
                        kill switch). Default name: ``STOP``.

``Budget`` packages the three required CLI caps
(``max_evals``, ``max_spend_usd``, ``max_walltime_seconds``) and exposes
``Budget.default_stoppers()`` to build the corresponding three stoppers
plus a ``StopFileStopper`` watching ``<run_dir>/STOP``.

All stoppers return ``None`` while the run can continue, or a
``StopReason`` once their condition trips. The reason carries a stable
string code and a serialisable ``details`` dict so the summary writer
can record exactly which stopper fired and why.
"""

from __future__ import annotations

import dataclasses
import os
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "Budget",
    "BudgetError",
    "StopReason",
    "StopperProtocol",
    "SpendStopper",
    "EvalStopper",
    "WalltimeStopper",
    "PlateauStopper",
    "StopFileStopper",
]


class BudgetError(ValueError):
    """Raised for malformed budget configurations."""


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class StopReason:
    """Structured reason a stopper has tripped.

    The ``code`` is a short stable string suitable for branching in the
    summary writer (e.g. ``"budget.spend"``, ``"plateau.no_improvement"``);
    ``details`` carries the numbers that triggered the decision so a
    human-readable summary can be reconstructed.
    """

    code: str
    message: str
    details: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Budget:
    """The three mandatory budget caps enforced by the CLI."""

    max_evals: int
    max_spend_usd: float
    max_walltime_seconds: float

    def __post_init__(self) -> None:
        if self.max_evals <= 0:
            raise BudgetError(f"max_evals must be > 0, got {self.max_evals}")
        if self.max_spend_usd <= 0:
            raise BudgetError(f"max_spend_usd must be > 0, got {self.max_spend_usd}")
        if self.max_walltime_seconds <= 0:
            raise BudgetError(
                f"max_walltime_seconds must be > 0, got {self.max_walltime_seconds}"
            )

    def default_stoppers(
        self,
        *,
        run_dir: str | os.PathLike | None = None,
        time_source: "TimeSource | None" = None,
    ) -> list["StopperProtocol"]:
        """Build the spend / eval / walltime trio plus an optional STOP file watcher."""
        ts: TimeSource = time_source or _RealTime()
        stoppers: list[StopperProtocol] = [
            SpendStopper(max_spend_usd=self.max_spend_usd),
            EvalStopper(max_evals=self.max_evals),
            WalltimeStopper(max_seconds=self.max_walltime_seconds, time_source=ts),
        ]
        if run_dir is not None:
            stoppers.append(StopFileStopper(run_dir=run_dir))
        return stoppers


# ---------------------------------------------------------------------------
# StopperProtocol + monotonic clock seam (for unit tests)
# ---------------------------------------------------------------------------


@runtime_checkable
class StopperProtocol(Protocol):
    """Protocol every stopper implements."""

    def check(self, state: "RunState") -> StopReason | None:  # pragma: no cover
        ...


class TimeSource(Protocol):
    """Monotonic time source for testability."""

    def now(self) -> float:  # pragma: no cover
        ...


class _RealTime:
    def now(self) -> float:
        return time.monotonic()


@dataclasses.dataclass(frozen=True)
class RunState:
    """Snapshot of the optimizer state passed to every stopper on each tick."""

    evaluations: int
    spend_usd: float
    started_at_monotonic: float
    best_score: float | None
    history: tuple[float, ...] = ()


# ---------------------------------------------------------------------------
# Concrete stoppers
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class SpendStopper:
    max_spend_usd: float

    def check(self, state: RunState) -> StopReason | None:
        if state.spend_usd >= self.max_spend_usd:
            return StopReason(
                code="budget.spend",
                message=(
                    f"spend ${state.spend_usd:.4f} exceeds cap ${self.max_spend_usd:.4f}"
                ),
                details={
                    "spend_usd": state.spend_usd,
                    "max_spend_usd": self.max_spend_usd,
                },
            )
        return None


@dataclasses.dataclass
class EvalStopper:
    max_evals: int

    def check(self, state: RunState) -> StopReason | None:
        if state.evaluations >= self.max_evals:
            return StopReason(
                code="budget.evals",
                message=(
                    f"evaluations {state.evaluations} reached cap {self.max_evals}"
                ),
                details={
                    "evaluations": state.evaluations,
                    "max_evals": self.max_evals,
                },
            )
        return None


@dataclasses.dataclass
class WalltimeStopper:
    max_seconds: float
    time_source: TimeSource = dataclasses.field(default_factory=_RealTime)

    def check(self, state: RunState) -> StopReason | None:
        elapsed = self.time_source.now() - state.started_at_monotonic
        if elapsed >= self.max_seconds:
            return StopReason(
                code="budget.walltime",
                message=(
                    f"wall-time {elapsed:.2f}s reached cap {self.max_seconds:.2f}s"
                ),
                details={
                    "elapsed_seconds": elapsed,
                    "max_seconds": self.max_seconds,
                },
            )
        return None


@dataclasses.dataclass
class PlateauStopper:
    """Trip after ``patience`` evaluations without an improvement > ``epsilon``."""

    patience: int = 10
    epsilon: float = 1e-3

    def __post_init__(self) -> None:
        if self.patience <= 0:
            raise BudgetError(f"patience must be > 0, got {self.patience}")
        if self.epsilon < 0:
            raise BudgetError(f"epsilon must be >= 0, got {self.epsilon}")

    def check(self, state: RunState) -> StopReason | None:
        if len(state.history) <= self.patience:
            return None
        window = state.history[-(self.patience + 1):]
        baseline = window[0]
        current_best = max(window)
        if current_best - baseline <= self.epsilon:
            return StopReason(
                code="plateau.no_improvement",
                message=(
                    f"best score {current_best:.6f} did not improve more than "
                    f"{self.epsilon:.6f} over the last {self.patience} evaluations"
                ),
                details={
                    "baseline": baseline,
                    "current_best": current_best,
                    "epsilon": self.epsilon,
                    "patience": self.patience,
                },
            )
        return None


@dataclasses.dataclass
class StopFileStopper:
    """Trip when a sentinel file appears in the run directory.

    Default file name is ``STOP``; ops can ``touch <run_dir>/STOP`` to
    request a graceful stop without sending signals.
    """

    run_dir: str | os.PathLike
    filename: str = "STOP"

    def check(self, state: RunState) -> StopReason | None:
        sentinel = Path(self.run_dir) / self.filename
        if sentinel.exists():
            return StopReason(
                code="explicit.stop_file",
                message=f"sentinel file {sentinel} exists",
                details={"path": str(sentinel)},
            )
        return None
