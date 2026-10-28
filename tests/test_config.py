"""Tests for configuration settings and cache resolution."""

from __future__ import annotations

import tempfile
from pathlib import Path

from conftest import safe_rmtree

from ghost_maintainer.config import (
    GHOST_DISCLAIMER,
    GHOST_REFUSAL_MESSAGE,
    Settings,
    get_default_cache_dir,
    get_repo_cache_key,
)


def test_protocol_constants() -> None:
    """Protocol constants match exact specification strings."""
    assert GHOST_REFUSAL_MESSAGE == "The dead do not remember."
    assert GHOST_DISCLAIMER == "Voices are fiction. Evidence is real."


def test_default_cache_dir() -> None:
    """Default cache dir resolves to a Path."""
    p = get_default_cache_dir()
    assert isinstance(p, Path)


def test_get_repo_cache_key() -> None:
    """Cache key produces 12-char hex string and normalizes slashes."""
    k1 = get_repo_cache_key("c:/test/repo")
    k2 = get_repo_cache_key("c:\\test\\repo")
    assert len(k1) == 12
    assert k1 == k2


def test_settings_cache_dir_and_expansion() -> None:
    """Settings cache directory expands tilde and derives repo cache dir."""
    temp_dir = Path(tempfile.mkdtemp(prefix="ghost_test_conf_"))
    try:
        s = Settings(cache_dir=temp_dir, min_score=0.85)
        assert s.min_score == 0.85
        repo_cache = s.get_repo_cache_dir(temp_dir)
        assert repo_cache.exists()
        assert repo_cache.parent == temp_dir
    finally:
        safe_rmtree(temp_dir)
