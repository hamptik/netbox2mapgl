"""Cache snapshot type and pre-built response store.

``CacheSnapshot`` is an immutable view consumed by the builders.
``ResponseStore`` holds the pre-built API payloads produced by the build step
so the request handlers can return them instantly.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

#: Object-valued cache kinds (devices, locations, cables, vms, interfaces).
ObjectKind = dict[int, dict[str, Any]]
#: Trace results are JSON arrays, not objects.
TraceKind = dict[int, list[Any]]


@dataclass(frozen=True, slots=True)
class CacheSnapshot:
    """Immutable point-in-time copy of the cache consumed by the builders."""

    devices: ObjectKind
    locations: ObjectKind
    cables: ObjectKind
    vms: ObjectKind
    traces: TraceKind
    interfaces: ObjectKind
    last_cache_time: float = 0.0

    @classmethod
    def empty(cls) -> CacheSnapshot:
        return cls(devices={}, locations={}, cables={}, vms={}, traces={}, interfaces={})


@dataclass(frozen=True, slots=True)
class BuiltResult:
    """Pre-built API response data with pre-serialized JSON for the common path."""

    links: list[dict[str, Any]]
    markers: list[dict[str, Any]]
    paths: list[dict[str, Any]]
    links_json: str
    paths_json: str


class ResponseStore:
    """Thread-safe holder for the latest build result.

    ``is_ready()`` returns ``True`` only after at least one successful build.
    Until then the API endpoints return 503.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._result: BuiltResult | None = None
        self._ready = threading.Event()

    def is_ready(self) -> bool:
        return self._ready.is_set()

    def update(self, result: BuiltResult) -> None:
        with self._lock:
            self._result = result
            self._ready.set()

    def result(self) -> BuiltResult | None:
        with self._lock:
            return self._result
