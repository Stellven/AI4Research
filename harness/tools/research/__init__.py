"""Compatibility route to the single DeepResearch implementation.

Some historical tool entrypoints put ``harness/tools`` before ``harness/lib``
on ``sys.path``.  The old duplicate package then shadowed newer product code.
Keep this package name for compatibility, but resolve every submodule from the
authoritative ``harness/lib/research`` tree.
"""

from pathlib import Path


_LIB_RESEARCH = Path(__file__).resolve().parents[2] / "lib" / "research"
if not _LIB_RESEARCH.is_dir():
    raise ImportError(f"authoritative research package missing: {_LIB_RESEARCH}")

# Python consults package.__path__ for every ``research.<submodule>`` import.
# Excluding this retired directory makes its historical copies unreachable
# without breaking callers that still begin resolution from harness/tools.
__path__ = [str(_LIB_RESEARCH)]

from . import hashing, ids, schemas, seams

__all__ = ["schemas", "ids", "hashing", "seams"]
SCHEMA_VERSION = "solar.deepresearch.schemas.v1"
