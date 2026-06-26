"""Build the ``/links`` payload from cached traces."""

from __future__ import annotations

from typing import Any

from app.builders.utils import (
    extract_geo,
    get_location_slug,
    get_role_slug,
    parse_speed_bps,
)
from app.cache import CacheSnapshot

_DEFAULT_TARGET_ROLES: frozenset[str] = frozenset({"router", "switch"})


def build_links(
    snapshot: CacheSnapshot,
    location_filter: str | None = None,
    *,
    target_roles: frozenset[str] = _DEFAULT_TARGET_ROLES,
    lat_field: str = "lat",
    lon_field: str = "lon",
) -> list[dict[str, Any]]:
    """Produce link records connecting routers/switches across locations.

    Each record describes one end of a traced cable: the local location
    (``vertexA``), the remote location (``vertexB``), the devices on each side,
    the interface/cable capacity and the local coordinates.
    """
    devices = snapshot.devices
    locations = snapshot.locations
    traces = snapshot.traces
    interfaces = snapshot.interfaces

    results: list[dict[str, Any]] = []

    for iface_id, trace in traces.items():
        if not trace:
            continue
        try:
            first_iface_obj = trace[0][0][0]
            last_segment = trace[-1][2]
            if not last_segment:
                continue
            last_iface_obj = last_segment[-1]
        except (IndexError, TypeError):
            continue

        dev_a_info = first_iface_obj.get("device")
        dev_b_info = last_iface_obj.get("device")
        if not dev_a_info or not dev_b_info:
            continue

        dev_a = devices.get(dev_a_info.get("id"))
        dev_b = devices.get(dev_b_info.get("id"))
        if not dev_a or not dev_b:
            continue

        role_a = get_role_slug(dev_a)
        role_b = get_role_slug(dev_b)
        if role_a not in target_roles or role_b not in target_roles:
            continue

        loc_slug_a = get_location_slug(dev_a)
        loc_slug_b = get_location_slug(dev_b)
        if location_filter and (loc_slug_a != location_filter or loc_slug_b != location_filter):
            continue
        if loc_slug_a == loc_slug_b:
            continue

        link_iface_id = first_iface_obj.get("id")
        iface_obj = interfaces.get(link_iface_id, {})
        if not iface_obj:
            continue

        if_descr = iface_obj.get("name") or ""
        type_field = iface_obj.get("type")
        cable_type = type_field.get("value", "") if isinstance(type_field, dict) else ""
        capacity = parse_speed_bps(if_descr, cable_type)

        loc_field = dev_a.get("location")
        if not isinstance(loc_field, dict):
            continue
        loc_id = loc_field.get("id")
        if loc_id is None:
            continue
        loc_obj = locations.get(loc_id)
        if not isinstance(loc_obj, dict):
            continue
        lon, lat = extract_geo(loc_obj, lat_field, lon_field)
        if lon == 0.0 or lat == 0.0:
            continue

        results.append(
            {
                "vertexA": loc_slug_a,
                "vertexB": loc_slug_b,
                "instance": dev_a.get("_display_name"),
                "remote_instance": dev_b.get("_display_name"),
                "edgeId": str(iface_id),
                "lon": lon,
                "lat": lat,
                "capacity": capacity,
                "mapgl_node_ifc_name": f"{if_descr}@{dev_a.get('_display_name')}",
                "ifDescr": if_descr,
            }
        )

    return results


def build_location_markers(
    snapshot: CacheSnapshot,
    location_filter: str | None = None,
    *,
    lat_field: str = "lat",
    lon_field: str = "lon",
) -> list[dict[str, Any]]:
    """Produce one coordinate marker per geo-tagged location."""
    markers: list[dict[str, Any]] = []
    for loc in snapshot.locations.values():
        slug = loc.get("slug")
        if location_filter and slug != location_filter:
            continue
        lon, lat = extract_geo(loc, lat_field, lon_field)
        if lon == 0.0 or lat == 0.0:
            continue
        markers.append(
            {
                "vertexA": slug,
                "lon": lon,
                "lat": lat,
                "mapgl_node_ifc_name": slug,
            }
        )
    return markers
