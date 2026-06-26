"""Tests for the links and paths builders."""

from __future__ import annotations

from typing import Any

from app.builders.links import build_links, build_location_markers
from app.builders.paths import build_paths
from app.cache import CacheSnapshot


def _device(
    dev_id: int,
    name: str,
    *,
    role: str = "switch",
    location_slug: str = "dc1",
    location_id: int = 100,
    tags: list[str] | None = None,
    rack: dict[str, Any] | None = None,
    cluster: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": dev_id,
        "name": name,
        "_display_name": name,
        "role": {"slug": role},
        "location": {"slug": location_slug, "id": location_id},
        "tags": [{"slug": t} for t in (tags or [])],
        "rack": rack,
        "cluster": cluster,
    }


def _location(loc_id: int, slug: str, lat: str, lon: str) -> dict[str, Any]:
    return {
        "id": loc_id,
        "slug": slug,
        "custom_fields": {"lat": lat, "lon": lon},
    }


def _trace(
    iface_a_id: int, dev_a_id: int, iface_b_id: int, dev_b_id: int, cable_id: int
) -> list[Any]:
    return [
        [
            [{"id": iface_a_id, "device": {"id": dev_a_id}}],
            {"id": cable_id},
            [{"id": iface_b_id, "device": {"id": dev_b_id}}],
        ]
    ]


class TestBuildLinks:
    def test_link_between_two_routers_in_different_locations(self) -> None:
        snapshot = CacheSnapshot(
            devices={
                1: _device(1, "rtr-a", role="router", location_slug="dc1", location_id=100),
                2: _device(2, "rtr-b", role="router", location_slug="dc2", location_id=200),
            },
            locations={
                100: _location(100, "dc1", "30.5", "59.9"),
                200: _location(200, "dc2", "31.0", "60.0"),
            },
            cables={},
            vms={},
            traces={5: _trace(10, 1, 20, 2, 99)},
            interfaces={
                10: {"id": 10, "name": "TenGigabitEthernet0/1", "type": {"value": "10gbase-t"}}
            },
        )

        links = build_links(snapshot)
        assert len(links) == 1
        link = links[0]
        assert link["vertexA"] == "dc1"
        assert link["vertexB"] == "dc2"
        assert link["instance"] == "rtr-a"
        assert link["remote_instance"] == "rtr-b"
        assert link["edgeId"] == "5"
        assert link["lon"] == 59.9
        assert link["lat"] == 30.5
        assert link["capacity"] == 10_000_000_000
        assert link["ifDescr"] == "TenGigabitEthernet0/1"

    def test_same_location_is_skipped(self) -> None:
        snapshot = CacheSnapshot(
            devices={
                1: _device(1, "sw-a", location_slug="dc1", location_id=100),
                2: _device(2, "sw-b", location_slug="dc1", location_id=100),
            },
            locations={100: _location(100, "dc1", "30.5", "59.9")},
            cables={},
            vms={},
            traces={5: _trace(10, 1, 20, 2, 99)},
            interfaces={10: {"id": 10, "name": "eth0"}},
        )
        assert build_links(snapshot) == []

    def test_non_target_role_is_skipped(self) -> None:
        snapshot = CacheSnapshot(
            devices={
                1: _device(1, "rtr-a", role="router", location_slug="dc1", location_id=100),
                2: _device(2, "srv-1", role="server", location_slug="dc2", location_id=200),
            },
            locations={
                100: _location(100, "dc1", "30.5", "59.9"),
                200: _location(200, "dc2", "31.0", "60.0"),
            },
            cables={},
            vms={},
            traces={5: _trace(10, 1, 20, 2, 99)},
            interfaces={10: {"id": 10, "name": "eth0"}},
        )
        assert build_links(snapshot) == []

    def test_location_without_geo_is_skipped(self) -> None:
        snapshot = CacheSnapshot(
            devices={
                1: _device(1, "rtr-a", role="router", location_slug="dc1", location_id=100),
                2: _device(2, "rtr-b", role="router", location_slug="dc2", location_id=200),
            },
            locations={
                100: _location(100, "dc1", "0", "0"),
                200: _location(200, "dc2", "31.0", "60.0"),
            },
            cables={},
            vms={},
            traces={5: _trace(10, 1, 20, 2, 99)},
            interfaces={10: {"id": 10, "name": "eth0"}},
        )
        assert build_links(snapshot) == []

    def test_location_markers(self) -> None:
        snapshot = CacheSnapshot(
            devices={},
            locations={
                100: _location(100, "dc1", "30.5", "59.9"),
                200: _location(200, "dc2", "0", "0"),
            },
            cables={},
            vms={},
            traces={},
            interfaces={},
        )
        markers = build_location_markers(snapshot)
        assert len(markers) == 1
        assert markers[0]["vertexA"] == "dc1"
        assert markers[0]["lon"] == 59.9
        assert markers[0]["lat"] == 30.5

    def test_custom_target_roles(self) -> None:
        snapshot = CacheSnapshot(
            devices={
                1: _device(1, "fw-a", role="firewall", location_slug="dc1", location_id=100),
                2: _device(2, "fw-b", role="firewall", location_slug="dc2", location_id=200),
            },
            locations={
                100: _location(100, "dc1", "30.5", "59.9"),
                200: _location(200, "dc2", "31.0", "60.0"),
            },
            cables={},
            vms={},
            traces={5: _trace(10, 1, 20, 2, 99)},
            interfaces={10: {"id": 10, "name": "eth0"}},
        )
        # Default roles skip firewalls
        assert build_links(snapshot) == []
        # Custom roles include firewalls
        links = build_links(snapshot, target_roles=frozenset({"firewall"}))
        assert len(links) == 1


class TestBuildPaths:
    def test_path_from_node_to_main(self) -> None:
        snapshot = CacheSnapshot(
            devices={
                1: _device(1, "leaf1", location_slug="dc1", location_id=100, rack={"name": "R1"}),
                2: _device(2, "spine1", location_slug="dc2", location_id=200, tags=["mapgl-main"]),
            },
            locations={
                100: _location(100, "dc1", "30.5", "59.9"),
                200: _location(200, "dc2", "31.0", "60.0"),
            },
            cables={},
            vms={},
            traces={5: _trace(10, 1, 20, 2, 99)},
            interfaces={},
        )

        objects = build_paths(snapshot)
        instances = {obj["instance"]: obj for obj in objects}

        # main node present with edgeId -1
        assert "spine1" in instances
        assert instances["spine1"]["edgeId"] == "-1"

        # leaf reaches spine
        leaf = instances["leaf1"]
        assert leaf["VertexB"][0] == "leaf1"
        assert leaf["VertexB"][-1] == "spine1"
        assert leaf["Location"] == "dc1"
        # Regression: namespace must use the node's own location, not a leaked
        # variable from a previous loop iteration.
        assert leaf["VertexANamespace"].startswith("dc1")

    def test_vm_path_through_cluster(self) -> None:
        snapshot = CacheSnapshot(
            devices={
                1: _device(
                    1,
                    "node1",
                    location_slug="dc1",
                    location_id=100,
                    cluster={"name": "kube-prod"},
                ),
                2: _device(2, "spine1", location_slug="dc2", location_id=200, tags=["mapgl-main"]),
            },
            locations={
                100: _location(100, "dc1", "30.5", "59.9"),
                200: _location(200, "dc2", "31.0", "60.0"),
            },
            cables={},
            vms={
                7: {"id": 7, "name": "vm-web01", "cluster": {"name": "kube-prod"}},
            },
            traces={5: _trace(10, 1, 20, 2, 99)},
            interfaces={},
        )

        objects = build_paths(snapshot)
        instances = {obj["instance"]: obj for obj in objects}

        vm = instances["vm-web01"]
        assert vm["VertexANamespace"] == "kube-prod"
        assert vm["edgeId"] == "vm-web01@kube-prod"

    def test_empty_cache(self, empty_snapshot: CacheSnapshot) -> None:
        assert build_paths(empty_snapshot) == []
        assert build_links(empty_snapshot) == []

    def test_path_isolated_by_location(self) -> None:
        """With location_filter, paths must stay within that location.

        A core switch in dc1 is physically connected to main nodes in both dc1
        and dc2.  Without filtering the BFS can route through dc2; with
        ``location_filter='dc1'`` only the local main must appear.
        """
        snapshot = CacheSnapshot(
            devices={
                1: _device(
                    1, "core-sw", location_slug="dc1", location_id=100
                ),
                2: _device(
                    2, "main-dc1", location_slug="dc1", location_id=100, tags=["mapgl-main"]
                ),
                3: _device(
                    3, "main-dc2", location_slug="dc2", location_id=200, tags=["mapgl-main"]
                ),
            },
            locations={
                100: _location(100, "dc1", "30.5", "59.9"),
                200: _location(200, "dc2", "31.0", "60.0"),
            },
            cables={},
            vms={},
            traces={
                # core-sw connected to main-dc1
                5: _trace(10, 1, 20, 2, 99),
                # core-sw also connected to main-dc2 (different location)
                6: _trace(11, 1, 21, 3, 100),
            },
            interfaces={},
        )

        # Without filter: both mains reachable, path may go to either
        global_paths = build_paths(snapshot)
        global_core = next(p for p in global_paths if p["instance"] == "core-sw")
        assert global_core["VertexB"][-1] in ("main-dc1", "main-dc2")

        # With filter: must stay in dc1
        filtered = build_paths(snapshot, location_filter="dc1")
        instances = {obj["instance"]: obj for obj in filtered}
        core = instances["core-sw"]
        assert core["VertexB"][-1] == "main-dc1"
        assert core["RemoteLocation"] == "dc1"
        # main-dc2 must not appear anywhere in the filtered output
        assert "main-dc2" not in instances

    def test_bfs_is_deterministic(self) -> None:
        """BFS must produce identical results regardless of hash seed."""
        snapshot = CacheSnapshot(
            devices={
                1: _device(1, "leaf", location_slug="dc1", location_id=100),
                2: _device(
                    2, "main-a", location_slug="dc1", location_id=100, tags=["mapgl-main"]
                ),
                3: _device(
                    3, "main-b", location_slug="dc1", location_id=100, tags=["mapgl-main"]
                ),
            },
            locations={100: _location(100, "dc1", "30.5", "59.9")},
            cables={},
            vms={},
            traces={
                5: _trace(10, 1, 20, 2, 99),
                6: _trace(11, 1, 21, 3, 100),
            },
            interfaces={},
        )
        # Leaf is connected to two equally-close mains; sorted BFS always
        # picks the same one deterministically.
        result = build_paths(snapshot, location_filter="dc1")
        leaf = next(p for p in result if p["instance"] == "leaf")
        assert leaf["VertexB"][-1] == "main-a"

    def test_custom_main_tag(self) -> None:
        snapshot = CacheSnapshot(
            devices={
                1: _device(1, "leaf1", location_slug="dc1", location_id=100),
                2: _device(2, "spine1", location_slug="dc1", location_id=100, tags=["core-node"]),
            },
            locations={100: _location(100, "dc1", "30.5", "59.9")},
            cables={},
            vms={},
            traces={5: _trace(10, 1, 20, 2, 99)},
            interfaces={},
        )
        # Default tag "mapgl-main" does not match -> spine1 is not a main
        default_result = build_paths(snapshot, location_filter="dc1")
        instances = {obj["instance"]: obj for obj in default_result}
        assert "spine1" not in instances or instances["spine1"]["edgeId"] != "-1"

        # Custom tag "core-node" matches -> spine1 is a main
        custom_result = build_paths(snapshot, location_filter="dc1", main_tag="core-node")
        custom_instances = {obj["instance"]: obj for obj in custom_result}
        assert "spine1" in custom_instances
        assert custom_instances["spine1"]["edgeId"] == "-1"
