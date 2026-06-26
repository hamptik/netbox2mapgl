"""Payload builders for the MapGL map data endpoints."""

from __future__ import annotations

import json
from typing import Any

from app.builders.links import build_links, build_location_markers
from app.builders.paths import build_paths
from app.cache import BuiltResult, CacheSnapshot

__all__ = [
    "build_links",
    "build_location_markers",
    "build_paths",
    "build_all",
    "format_paths_json",
]


def format_paths_json(objects: list[dict[str, Any]], blank_lines: int) -> str:
    """Serialize path objects with configurable blank-line separators."""
    lines: list[str] = ["["]
    last = len(objects) - 1
    for i, obj in enumerate(objects):
        obj_json = json.dumps(obj, ensure_ascii=False, indent=4)
        if i != last:
            lines.append(obj_json + ",")
            lines.extend([""] * blank_lines)
        else:
            lines.append(obj_json)
    lines.append("]")
    return "\n".join(lines)


def build_all(
    snapshot: CacheSnapshot,
    blank_lines: int,
    *,
    main_tag: str = "mapgl-main",
    target_roles: frozenset[str] = frozenset({"router", "switch"}),
    lat_field: str = "lat",
    lon_field: str = "lon",
) -> BuiltResult:
    """Build all API responses from a snapshot and pre-serialize the JSON.

    Paths are built **per-location** so the BFS graph is isolated within each
    location.  This prevents devices from routing through — or reaching — main
    nodes in other locations.
    """
    links = build_links(
        snapshot,
        target_roles=target_roles,
        lat_field=lat_field,
        lon_field=lon_field,
    )
    markers = build_location_markers(
        snapshot,
        lat_field=lat_field,
        lon_field=lon_field,
    )

    location_slugs = sorted(
        {
            slug
            for dev in snapshot.devices.values()
            if isinstance(dev.get("location"), dict)
            and (slug := dev["location"].get("slug"))
        }
    )
    paths: list[dict[str, Any]] = []
    for slug in location_slugs:
        paths.extend(build_paths(snapshot, location_filter=slug, main_tag=main_tag))

    links_json = json.dumps(links + markers, ensure_ascii=False, indent=4)
    paths_json = format_paths_json(paths, blank_lines)

    return BuiltResult(
        links=links,
        markers=markers,
        paths=paths,
        links_json=links_json,
        paths_json=paths_json,
    )
