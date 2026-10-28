"""OpenAI-compatible streaming backend for OpenAI API and local Ollama/llama.cpp/vLLM."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from ghost_maintainer.backends.base import (
    BackendConfigError,
    BackendError,
    BackendUnavailableError,
)
from ghost_maintainer.config import settings


def strip_think_tags_stream(stream: Iterator[str]) -> Iterator[str]:
    """Filter out <think>...</think> reasoning traces from an incremental token stream.

    Handles split tokens and partial tags across stream boundaries.
    """
    buffer = ""
    in_think = False
    start_checked = False

    for chunk in stream:
        buffer += chunk

        if not start_checked:
            if buffer.startswith("<think>"):
                in_think = True
                start_checked = True
                buffer = buffer[7:]  # discard <think>
            elif "<think>".startswith(buffer) and len(buffer) < 7:
                # Buffer could still become "<think>", wait for more chunks
                continue
            else:
                # Does not start with <think>, flush and exit special start mode
                start_checked = True
                if buffer:
                    yield buffer
                    buffer = ""
                continue

        if in_think:
            if "</think>" in buffer:
                _, _, remainder = buffer.partition("</think>")
                in_think = False
                remainder = remainder.lstrip("\r\n ")
                if remainder:
                    yield remainder
                buffer = ""
            continue

        # Normal streaming outside think tags
        if buffer:
            yield buffer
            buffer = ""

    # If stream ended while buffered outside think mode
    if buffer and not in_think:
        yield buffer


class OpenAICompatBackend:
    """Client for OpenAI and local OpenAI-compatible endpoints with SSE streaming."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        *,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.name: str = "openai_compat"
        self.model: str = model or settings.openai_model
        self.base_url: str = base_url or settings.base_url or "https://api.openai.com/v1"
        self.timeout: float = timeout
        self._custom_client: httpx.Client | None = client

        # Resolve API key
        resolved_key = api_key or settings.openai_api_key
        is_official_openai = "api.openai.com" in self.base_url.lower()

        if is_official_openai and not resolved_key:
            raise BackendConfigError(
                "OPENAI_API_KEY is required when using official OpenAI API. "
                "Set OPENAI_API_KEY in environment or configure GHOST_BASE_URL for local Ollama/llama.cpp."
            )

        # Local servers (Ollama, llama.cpp, vLLM) generally accept any non-empty or empty key
        self.api_key: str = resolved_key or ("local" if not is_official_openai else "")

    def _stream_raw(
        self,
        messages: list[dict[str, str]],
        max_new_tokens: int,
        temperature: float,
    ) -> Iterator[str]:
        """Internal generator yielding raw tokens from SSE stream."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": temperature,
            "stream": True,
        }

        client_cm = (
            self._custom_client
            if self._custom_client is not None
            else httpx.Client(timeout=self.timeout)
        )
        should_close_client = self._custom_client is None

        try:
            with client_cm.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code == 401:
                    raise BackendConfigError(
                        f"Authentication failed (401 Unauthorized) at {self.base_url}. "
                        "Check your OPENAI_API_KEY."
                    )
                if response.status_code != 200:
                    err_body = response.read().decode("utf-8", errors="replace")
                    raise BackendError(
                        f"OpenAICompatBackend HTTP {response.status_code} error from {self.base_url}: {err_body}"
                    )

                for line in response.iter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line == "data: [DONE]":
                        break
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content

        except httpx.ConnectError as exc:
            raise BackendUnavailableError(
                f"Failed to connect to OpenAI-compatible server at {self.base_url}. "
                "Ensure local server (Ollama/llama.cpp) is running."
            ) from exc
        except httpx.TimeoutException as exc:
            raise BackendError(
                f"Request to backend at {self.base_url} timed out after {self.timeout}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendError(
                f"HTTP communication error with backend at {self.base_url}: {exc}"
            ) from exc
        finally:
            if should_close_client:
                client_cm.close()

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Stream chat completions incrementally via Server-Sent Events (SSE)."""
        raw_stream = self._stream_raw(messages, max_new_tokens, temperature)
        yield from strip_think_tags_stream(raw_stream)

    def generate_stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Alias for generate to satisfy streaming interfaces."""
        return self.generate(messages, max_new_tokens=max_new_tokens, temperature=temperature)
