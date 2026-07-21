"""Solar DeepResearch core runtime library.

Sprint: sprint-20260513-solar-deepresearch-product-line-s03-core-runtime
Node: N1 (schemas + ids + hashing)
Schema Version: solar.deepresearch.schemas.v1

Exposes the three foundational submodules that downstream nodes (storage,
evidence, sources, cli) build on.
"""

from . import hashing, ids, schemas, seams

__all__ = ["schemas", "ids", "hashing", "seams"]
SCHEMA_VERSION = "solar.deepresearch.schemas.v1"
