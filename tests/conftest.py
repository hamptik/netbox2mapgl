"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from app.cache import CacheSnapshot


@pytest.fixture
def empty_snapshot() -> CacheSnapshot:
    return CacheSnapshot.empty()
