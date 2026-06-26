"""Shared helpers for the links/paths builders."""

from __future__ import annotations

import re
from typing import Any

#: Device roles that are physical infrastructure we trace links through.
VALID_TARGET_ROLES = frozenset({"router", "switch"})

_SPEED_RE = re.compile(r"(\d+(?:\.\d+)?)(g|m)?base")


def get_role_slug(device: dict[str, Any]) -> str:
    """Return the role slug of a device, tolerating NetBox API differences."""
    role = device.get("role") or device.get("device_role") or {}
    if isinstance(role, dict):
        return role.get("slug") or ""
    return ""


def get_location_slug(device: dict[str, Any]) -> str:
    """Return the location slug of a device, or ``""`` if unknown."""
    loc = device.get("location")
    if isinstance(loc, dict):
        return loc.get("slug") or ""
    return ""


def parse_speed_bps(if_name: str | None, cable_type: str = "") -> int:
    """Parse an interface/cable description into a bits-per-second value.

    Recognizes patterns like ``10gbase``, ``1gbase``, ``1000base``, ``10base``.
    Returns 0 when no speed can be determined. Only ``cable_type`` is type
    guarded: ``if_name`` is always considered because the original code dropped
    it entirely whenever the cable type was not a string.
    """
    parts = [if_name or ""]
    if isinstance(cable_type, str):
        parts.append(cable_type)
    text = " ".join(parts).lower()

    match = _SPEED_RE.search(text)
    if not match:
        return 0

    value = float(match.group(1))
    unit = match.group(2)
    if unit == "g":
        return int(value * 10**9)
    if unit == "m":
        return int(value * 10**6)
    return int(value * 10**6)


def extract_geo(location: dict[str, Any]) -> tuple[float, float]:
    """Return ``(lon, lat)`` for a NetBox location.

    Latitude is read from the ``lat`` custom field and longitude from ``lon``.
    ``(0.0, 0.0)`` is returned when the location has no coordinates.
    """
    cf = location.get("custom_fields") or {}
    try:
        lat = float(cf.get("lat") or 0)
        lon = float(cf.get("lon") or 0)
    except (TypeError, ValueError):
        return 0.0, 0.0
    return lon, lat


def rack_namespace(location_slug: str | None, rack: Any) -> str:
    """Build a namespace string from a location slug and a (optional) rack.

    The rack name is reduced to digits/dots and dots are turned into dashes so
    ``Rack-2.3`` becomes ``2-3`` and the namespace ``dc1.2-3``. When the device
    has no usable rack the bare location slug is returned.
    """
    slug = location_slug or ""
    rack_name = rack.get("name") if isinstance(rack, dict) else None
    if not rack_name:
        return slug
    cleaned = re.sub(r"[^0-9.]", "", rack_name).replace(".", "-")
    return f"{slug}.{cleaned}" if cleaned else slug
