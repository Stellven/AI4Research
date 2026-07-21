"""compiler_profile — Schema, validation, registry, and loader for compiler profiles.

Public API::

    from lib.compiler_profile import validate_profile
"""
from __future__ import annotations

from .schema import validate_profile

__all__ = ["validate_profile"]
