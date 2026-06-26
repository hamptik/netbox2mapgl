"""Build the ``/paths`` payload: shortest path from each node to a main node."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from app.builders.utils import get_location_slug, rack_namespace
from app.cache import CacheSnapshot


def _trace_endpoints(
    trace: list[Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    """Extract ``(first_iface, cable_meta, last_iface)`` from a trace.

    Returns ``None`` for malformed/incomplete traces.
    """
    if not trace:
        return None
    try:
        first_iface_obj = trace[0][0][0]
        cable_meta = trace[0][1] or {}
        last_segment = trace[-1][2]
        if not last_segment:
            return None
        last_iface_obj = last_segment[-1]
    except (IndexError, TypeError):
        return None
    return first_iface_obj, cable_meta, last_iface_obj


def build_paths(
    snapshot: CacheSnapshot,
    location_filter: str | None = None,
    *,
    main_tag: str = "mapgl-main",
) -> list[dict[str, Any]]:
    """Produce path records describing how each device/VM reaches a main node."""
    devices = snapshot.devices
    traces = snapshot.traces
    vms = snapshot.vms

    adj: dict[str, set[str]] = defaultdict(set)
    vertex_location: dict[str, str] = {}
    vertex_tags: dict[str, list[Any]] = {}
    vertex_rack: dict[str, Any] = {}
    edge_meta: dict[tuple[str, str], str] = {}

    for device in devices.values():
        name = device.get("_display_name") or device.get("name")
        if name:
            vertex_rack[name] = device.get("rack")

    for iface_id, trace in traces.items():
        endpoints = _trace_endpoints(trace)
        if endpoints is None:
            continue
        first_iface_obj, cable_meta, last_iface_obj = endpoints

        dev_a = devices.get(first_iface_obj.get("device", {}).get("id"))
        dev_b = devices.get(last_iface_obj.get("device", {}).get("id"))
        if not dev_a or not dev_b:
            continue

        name_a = dev_a.get("_display_name") or dev_a.get("name")
        name_b = dev_b.get("_display_name") or dev_b.get("name")
        if not name_a or not name_b:
            continue
        loc_a = get_location_slug(dev_a)
        loc_b = get_location_slug(dev_b)
        if location_filter and (loc_a != location_filter or loc_b != location_filter):
            continue

        adj[name_a].add(name_b)
        adj[name_b].add(name_a)
        vertex_location[name_a] = loc_a
        vertex_location[name_b] = loc_b
        vertex_tags[name_a] = [tag.get("slug") for tag in dev_a.get("tags", [])]
        vertex_tags[name_b] = [tag.get("slug") for tag in dev_b.get("tags", [])]

        edge_id = str(cable_meta.get("id", iface_id))
        edge_meta[(name_a, name_b)] = edge_id
        edge_meta[(name_b, name_a)] = edge_id

    mains = {name for name, tags in vertex_tags.items() if main_tag in tags}
    device_path = _shortest_path_to_main(adj, mains)

    if location_filter:
        cluster_devices = {
            id_: dev
            for id_, dev in devices.items()
            if get_location_slug(dev) == location_filter
        }
    else:
        cluster_devices = devices
    clusters = _build_clusters(cluster_devices)
    _attach_cluster_paths(clusters, device_path)

    vm_path = _build_vm_paths(vms, clusters)

    return _assemble_output(
        mains=mains,
        device_path=device_path,
        vm_path=vm_path,
        clusters=clusters,
        vertex_location=vertex_location,
        vertex_rack=vertex_rack,
        edge_meta=edge_meta,
        location_filter=location_filter,
    )


def _shortest_path_to_main(adj: dict[str, set[str]], mains: set[str]) -> dict[str, list[str]]:
    """BFS from every node to the nearest main node.

    Returns ``{node: [node, ..., main]}`` for nodes that can reach a main.
    Main nodes are included: they search for the nearest *other* main, so a
    main can appear both as a destination and as a path origin.
    """
    result: dict[str, list[str]] = {}
    for start in adj:
        queue: deque[str] = deque([start])
        parent: dict[str, str | None] = {start: None}
        seen: set[str] = {start}
        found: str | None = None
        while queue and found is None:
            current = queue.popleft()
            for neighbor in sorted(adj[current]):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                parent[neighbor] = current
                if neighbor in mains:
                    found = neighbor
                    break
                queue.append(neighbor)
        if found is None:
            continue
        path: list[str] = []
        node: str | None = found
        while node is not None:
            path.append(node)
            node = parent[node]
        path.reverse()
        result[start] = path
    return result


def _build_clusters(devices: dict[int, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group devices by their NetBox cluster."""
    clusters: dict[str, dict[str, Any]] = {}
    for device in devices.values():
        cluster = device.get("cluster")
        if not cluster:
            continue
        cluster_name = cluster.get("name") or cluster.get("display")
        if not cluster_name:
            continue
        node_name = device.get("_display_name") or device.get("name")
        node_loc = get_location_slug(device)
        info = clusters.setdefault(cluster_name, {"nodes": [], "location": node_loc})
        info["nodes"].append(node_name)
    return clusters


def _attach_cluster_paths(
    clusters: dict[str, dict[str, Any]], device_path: dict[str, list[str]]
) -> None:
    """Give each cluster a representative path through one of its nodes.

    The path is prefixed with the cluster name so a VM can be prepended to it.
    """
    for cluster_name, info in clusters.items():
        for node in info["nodes"]:
            if node in device_path:
                info["path"] = [cluster_name] + device_path[node]
                break


def _build_vm_paths(
    vms: dict[int, dict[str, Any]], clusters: dict[str, dict[str, Any]]
) -> dict[str, list[str]]:
    """Map each VM to ``[vm, cluster, ..., main]`` via its cluster's path."""
    vm_path: dict[str, list[str]] = {}
    for vm in vms.values():
        vm_name = vm.get("name") or vm.get("display")
        cluster_name = (vm.get("cluster") or {}).get("name")
        if not vm_name or not cluster_name:
            continue
        info = clusters.get(cluster_name)
        if not info or "path" not in info:
            continue
        vm_path[vm_name] = [vm_name] + info["path"]
    return vm_path


def _assemble_output(
    *,
    mains: set[str],
    device_path: dict[str, list[str]],
    vm_path: dict[str, list[str]],
    clusters: dict[str, dict[str, Any]],
    vertex_location: dict[str, str],
    vertex_rack: dict[str, Any],
    edge_meta: dict[tuple[str, str], str],
    location_filter: str | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for main in sorted(mains):
        loc = vertex_location.get(main)
        if location_filter and loc != location_filter:
            continue
        out.append(
            {
                "instance": main,
                "VertexB": [main],
                "VertexANamespace": rack_namespace(loc, vertex_rack.get(main)),
                "VertexBNamespace": "devices",
                "Location": loc,
                "RemoteLocation": loc,
                "edgeId": "-1",
            }
        )

    for node, path in device_path.items():
        loc = vertex_location.get(node)
        namespace = rack_namespace(loc, vertex_rack.get(node))
        edge_id = edge_meta.get((path[0], path[1]))
        out.append(
            {
                "instance": node,
                "VertexB": path,
                "VertexANamespace": namespace,
                "VertexBNamespace": "devices",
                "Location": loc,
                "RemoteLocation": vertex_location.get(path[-1]),
                "edgeId": edge_id,
            }
        )

    for vm_name, path in vm_path.items():
        cluster_name = path[1] if len(path) > 1 else None
        loc = clusters.get(cluster_name, {}).get("location") if cluster_name else None
        if location_filter and loc != location_filter:
            continue
        out.append(
            {
                "instance": vm_name,
                "VertexB": "",
                "VertexANamespace": cluster_name,
                "VertexBNamespace": cluster_name,
                "Location": loc,
                "RemoteLocation": vertex_location.get(path[-1]),
                "edgeId": f"{vm_name}@{cluster_name}",
            }
        )

    return out
