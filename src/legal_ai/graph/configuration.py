"""Graph configuration -- now a thin alias over legal_ai.config.

The settings themselves live in legal_ai.config.settings so that caps,
models and retrieval limits are answerable from one file rather than six.
This module stays because the graph and its tests import GraphConfig.
"""

from __future__ import annotations

from legal_ai.config import DEFAULT_CONFIG, Configuration

GraphConfig = Configuration

__all__ = ["Configuration", "GraphConfig", "DEFAULT_CONFIG"]
