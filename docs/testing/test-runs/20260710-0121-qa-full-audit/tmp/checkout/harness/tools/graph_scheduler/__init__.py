"""graph_scheduler package — pluggable scheduling strategy extensions.

This package provides scheduling strategy plugins that connect domain-specific
intelligence systems (GitHub, HuggingFace, etc.) with the core
graph_scheduler.py interface contract without modifying core files.

Usage:
    from tools.graph_scheduler import GitHubIntelligenceStrategy
    strategy = GitHubIntelligenceStrategy()
    batches = strategy.make_concurrent_batches(graph)
"""
from __future__ import annotations

from tools.graph_scheduler.github_strategy import GitHubIntelligenceStrategy

__all__ = ["GitHubIntelligenceStrategy"]
