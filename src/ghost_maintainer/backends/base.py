"""Base protocol and exceptions for polymorphic LLM backends."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable


class BackendError(Exception):
    """Base exception for all LLM backend failures."""


class BackendUnavailableError(BackendError):
    """Raised when a backend or its hardware/service dependencies are unavailable."""


class BackendConfigError(BackendError):
    """Raised when a backend is misconfigured or missing required settings."""


class ModelNotFoundError(BackendError):
    """Raised when a requested model cannot be found or loaded."""


class ContextLengthExceededError(BackendError):
    """Raised when conversation context exceeds the model's maximum sequence length."""


@runtime_checkable
class Backend(Protocol):
    """Polymorphic streaming interface for LLM generation backends."""

    name: str

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Stream generated text chunks incrementally for given conversation messages.

        Args:
            messages: List of chat messages in standard format:
                [{"role": "system"|"user"|"assistant", "content": "..."}].
            max_new_tokens: Upper bound on generated tokens (default: 512).
            temperature: Sampling temperature (default: 0.0 for greedy reproducibility).

        Returns:
            An iterator yielding incremental string chunks (tokens or text deltas).

        Raises:
            BackendError: On generation or connection failure.
            BackendUnavailableError: If required backend resources are missing.
            BackendConfigError: If backend settings are invalid.
            ModelNotFoundError: If requested model is not found.
            ContextLengthExceededError: If context length is exceeded.
        """
        ...
