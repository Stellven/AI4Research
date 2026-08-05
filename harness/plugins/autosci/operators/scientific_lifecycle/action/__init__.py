"""Bounded action and delivery physical operators for scientific lifecycle workflows."""

from .registry import execute_operator, get_operator, registration_entries

__all__ = ["execute_operator", "get_operator", "registration_entries"]
