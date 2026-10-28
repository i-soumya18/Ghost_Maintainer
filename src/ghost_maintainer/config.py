"""Configuration management and environment settings for The Ghost Maintainer."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal

import platformdirs
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Core protocol constants
GHOST_REFUSAL_MESSAGE: str = "The dead do not remember."
GHOST_DISCLAIMER: str = "Voices are fiction. Evidence is real."


def get_default_cache_dir() -> Path:
    """Resolve the default cache directory.

    Checks if ~/.ghost exists; otherwise falls back to the standard
    OS cache directory resolved via platformdirs.
    """
    dot_ghost = Path.home() / ".ghost"
    if dot_ghost.exists():
        return dot_ghost
    try:
        return Path(platformdirs.user_cache_dir("ghost-maintainer", appauthor=False))
    except Exception:
        return dot_ghost


def get_repo_cache_key(repo_path: Path | str) -> str:
    """Generate deterministic 12-char hex cache key for a repository path."""
    canonical = Path(repo_path).resolve()
    path_str = str(canonical).replace("\\", "/")
    if os.name == "nt":
        path_str = path_str.lower()
    return hashlib.sha256(path_str.encode("utf-8")).hexdigest()[:12]


class Settings(BaseSettings):
    """Global configuration settings for The Ghost Maintainer."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cache_dir: Path = Field(
        default_factory=get_default_cache_dir,
        validation_alias=AliasChoices("GHOST_CACHE_DIR", "cache_dir"),
        description="Root directory where BM25 indices and commit caches are stored.",
    )
    min_score: float = Field(
        default=0.8,
        validation_alias=AliasChoices("GHOST_MIN_SCORE", "min_score"),
        description="BM25 score threshold below which query triggers immediate refusal.",
    )
    base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GHOST_BASE_URL", "base_url"),
        description="Base URL for OpenAI-compatible endpoint (e.g. local Ollama or llama.cpp).",
    )
    openai_model: str = Field(
        default="gpt-6-luna",
        validation_alias=AliasChoices("GHOST_OPENAI_MODEL", "openai_model"),
        description="Default model ID for OpenAI backend.",
    )
    backend: Literal["unsloth", "openai_compat", "mock"] = Field(
        default="unsloth",
        validation_alias=AliasChoices("GHOST_BACKEND", "backend"),
        description="Default LLM backend to use for generation.",
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"),
        description="API key for OpenAI backend.",
    )
    host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("GHOST_HOST", "host"),
        description="Host address to bind FastAPI server.",
    )
    port: int = Field(
        default=6660,
        validation_alias=AliasChoices("GHOST_PORT", "port"),
        description="Port to bind FastAPI server.",
    )
    static_dir: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("GHOST_STATIC_DIR", "static_dir"),
        description="Optional directory override containing built static Web UI assets.",
    )
    default_k: int = Field(
        default=8,
        validation_alias=AliasChoices("GHOST_DEFAULT_K", "default_k"),
        description="Default number of evidence commits to retrieve.",
    )
    max_hunks_per_commit: int = Field(
        default=20,
        validation_alias=AliasChoices("GHOST_MAX_HUNKS", "max_hunks_per_commit"),
        description="Maximum hunk context signatures to retain per commit in gitlog pass.",
    )

    @field_validator("cache_dir", mode="after")
    @classmethod
    def expand_cache_dir(cls, v: Path) -> Path:
        """Expand user home directory tilde if present in cache_dir."""
        return v.expanduser()

    def get_repo_cache_dir(self, repo_path: Path | str) -> Path:
        """Derive an isolated cache directory for a given target repository.

        Computes the first 12 characters of the SHA-256 hash of the canonical
        repository path, ensuring zero pollution of the target repository.
        """
        key = get_repo_cache_key(repo_path)
        target = self.cache_dir / key
        target.mkdir(parents=True, exist_ok=True)
        return target


# Exported singleton instance
settings = Settings()
