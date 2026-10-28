"""Unsloth local 4-bit Qwen3-4B backend with greedy decoding and <think> suppression."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

from ghost_maintainer.backends.base import BackendUnavailableError
from ghost_maintainer.backends.openai_compat import strip_think_tags_stream

# Safe import guard for systems without CUDA/Unsloth
try:
    import torch  # type: ignore[import-not-found]
    from transformers import TextIteratorStreamer
    from unsloth import FastLanguageModel

    HAS_UNSLOTH = True
except ImportError:
    torch = None
    TextIteratorStreamer = None
    FastLanguageModel = None
    HAS_UNSLOTH = False


_CACHED_MODEL: Any = None
_CACHED_TOKENIZER: Any = None
_MODEL_LOCK = threading.Lock()


class UnslothBackend:
    """Local 4-bit quantized Qwen3-4B inference backend using Unsloth."""

    DEFAULT_MODEL = "unsloth/Qwen3-4B-Instruct-2507-bnb-4bit"

    def __init__(
        self,
        model_name: str | None = None,
        max_seq_length: int = 4096,
        load_in_4bit: bool = True,
    ) -> None:
        self.name: str = "unsloth"
        self.model_name = model_name or self.DEFAULT_MODEL
        self.max_seq_length = max_seq_length
        self.load_in_4bit = load_in_4bit

    @classmethod
    def is_available(cls) -> bool:
        """Check if unsloth and torch are importable in current environment."""
        return HAS_UNSLOTH

    def _ensure_loaded(self) -> tuple[Any, Any]:
        """Lazy load model and tokenizer singleton once per process."""
        global _CACHED_MODEL, _CACHED_TOKENIZER

        if not HAS_UNSLOTH:
            raise BackendUnavailableError(
                "Unsloth backend requires 'unsloth' and 'torch'. "
                "Install with: pip install ghost-maintainer[unsloth]"
            )

        if _CACHED_MODEL is not None and _CACHED_TOKENIZER is not None:
            return _CACHED_MODEL, _CACHED_TOKENIZER

        with _MODEL_LOCK:
            if _CACHED_MODEL is None or _CACHED_TOKENIZER is None:
                model, tokenizer = FastLanguageModel.from_pretrained(
                    model_name=self.model_name,
                    max_seq_length=self.max_seq_length,
                    load_in_4bit=self.load_in_4bit,
                )
                FastLanguageModel.for_inference(model)
                _CACHED_MODEL = model
                _CACHED_TOKENIZER = tokenizer

        return _CACHED_MODEL, _CACHED_TOKENIZER

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Stream generated response tokens with greedy decoding and <think> stripping."""
        model, tokenizer = self._ensure_loaded()

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer([prompt], return_tensors="pt")
        if hasattr(inputs, "to") and torch is not None and torch.cuda.is_available():
            inputs = inputs.to("cuda")

        streamer = TextIteratorStreamer(
            tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )
        generation_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=max_new_tokens,
            do_sample=(temperature != 0.0),
            temperature=temperature if temperature > 0.0 else None,
        )

        thread = threading.Thread(target=model.generate, kwargs=generation_kwargs)
        thread.start()

        raw_stream = (chunk for chunk in streamer)
        yield from strip_think_tags_stream(raw_stream)
        thread.join()

    def generate_stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Alias for generate to satisfy streaming interfaces."""
        return self.generate(messages, max_new_tokens=max_new_tokens, temperature=temperature)
