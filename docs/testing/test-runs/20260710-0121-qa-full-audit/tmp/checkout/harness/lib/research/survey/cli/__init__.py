"""Survey gate CLI view package.

Exports 5 view function pairs + VIEW_REGISTRY for downstream consumption.
"""

from __future__ import annotations

from .source_quality_view import format_source_quality, to_dict_source_quality
from .argument_density_view import format_argument_density, to_dict_argument_density
from .contradiction_matrix_view import format_contradiction_matrix, to_dict_contradiction_matrix
from .exploration_view import format_exploration, to_dict_exploration
from .gate_report_view import format_gate_report, to_dict_gate_report
from ._views_registry import VIEW_REGISTRY, register_view

# Auto-register all 5 views into VIEW_REGISTRY
register_view("source_quality")(lambda: {"format": format_source_quality, "to_dict": to_dict_source_quality})
register_view("argument_density")(lambda: {"format": format_argument_density, "to_dict": to_dict_argument_density})
register_view("contradiction_matrix")(lambda: {"format": format_contradiction_matrix, "to_dict": to_dict_contradiction_matrix})
register_view("exploration")(lambda: {"format": format_exploration, "to_dict": to_dict_exploration})
register_view("gate_report")(lambda: {"format": format_gate_report, "to_dict": to_dict_gate_report})

__all__ = [
    "VIEW_REGISTRY",
    "register_view",
    "format_source_quality",
    "to_dict_source_quality",
    "format_argument_density",
    "to_dict_argument_density",
    "format_contradiction_matrix",
    "to_dict_contradiction_matrix",
    "format_exploration",
    "to_dict_exploration",
    "format_gate_report",
    "to_dict_gate_report",
]
