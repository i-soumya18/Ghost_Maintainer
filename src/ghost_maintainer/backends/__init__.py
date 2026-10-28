"""Polymorphic streaming LLM backends for The Ghost Maintainer."""

from __future__ import annotations

from typing import Any

from ghost_maintainer.backends.base import (
    Backend,
    BackendConfigError,
    BackendError,
    BackendUnavailableError,
    ContextLengthExceededError,
    ModelNotFoundError,
)
from ghost_maintainer.backends.mock import MockBackend, MockMode
from ghost_maintainer.backends.openai_compat import OpenAICompatBackend, strip_think_tags_stream
from ghost_maintainer.backends.unsloth_backend import UnslothBackend
from ghost_maintainer.config import settings

__all__ = [
    "Backend",
    "BackendConfigError",
    "BackendError",
    "BackendUnavailableError",
    "ContextLengthExceededError",
    "MockBackend",
    "MockMode",
    "ModelNotFoundError",
    "OpenAICompatBackend",
    "UnslothBackend",
    "get_backend",
    "strip_think_tags_stream",
]


def get_backend(name: str | None = None, **kwargs: Any) -> Backend:
    """Instantiate and return a configured Backend implementation.

    Args:
        name: Name of backend ('mock', 'openai_compat', 'openai', 'unsloth').
            If None, defaults to settings.backend (from GHOST_BACKEND or config).
        **kwargs: Backend-specific constructor arguments.

    Returns:
        An instance conforming to Backend protocol.

    Raises:
        ValueError: If name is unrecognized.
    """
    raw_name = name if name is not None else settings.backend
    normalized = raw_name.strip().lower().replace("-", "_")

    if normalized == "mock":
        return MockBackend(**kwargs)
    if normalized in ("openai_compat", "openai"):
        return OpenAICompatBackend(**kwargs)
    if normalized == "unsloth":
        return UnslothBackend(**kwargs)

    raise ValueError(
        f"Unknown backend '{name}'. Available backends: 'mock', 'openai_compat', 'unsloth'."
    )
