"""Background thread that periodically refreshes the cache from NetBox.

After each refresh cycle the pre-built API responses are regenerated from the
fresh database state and published to the :class:`ResponseStore`, so request
handlers always serve the latest data without doing any computation themselves.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.builders import build_all
from app.cache import ResponseStore
from app.config import Config
from app.db import Database
from app.netbox import NetBoxClient

log = logging.getLogger(__name__)


def _with_display_name(devices: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Normalize a device list into ``{id: device}`` with a ``_display_name``.

    Prefer the virtual chassis name when present, falling back to the device's
    own name so multi-member chassis show a single label on the map.
    """
    result: dict[int, dict[str, Any]] = {}
    for device in devices:
        vc = device.get("virtual_chassis")
        name = vc.get("name") if isinstance(vc, dict) and vc.get("name") else device.get("name")
        device["_display_name"] = name
        result[device["id"]] = device
    return result


class CacheRefresher(threading.Thread):
    """Daemon thread driving the NetBox -> DB -> build sync loop."""

    def __init__(
        self,
        config: Config,
        netbox: NetBoxClient,
        database: Database,
        store: ResponseStore,
        blank_lines: int,
    ) -> None:
        super().__init__(daemon=True, name="cache-refresher")
        self._config = config
        self._netbox = netbox
        self._db = database
        self._store = store
        self._blank_lines = blank_lines
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        interval = self._config.cache_interval_sec
        while not self._stop_event.is_set():
            try:
                self._refresh_once()
                self._build()
            except Exception:
                log.exception("Error during refresh cycle")
            # Event.wait lets stop() interrupt the sleep promptly.
            self._stop_event.wait(timeout=interval)

    def _refresh_once(self) -> None:
        log.info("Starting cache refresh cycle")

        locations = self._netbox.fetch_all("/api/dcim/locations/")
        self._db.write_bulk("locations", [(loc["id"], loc) for loc in locations])

        raw_devices = self._netbox.fetch_all("/api/dcim/devices/")
        devices = _with_display_name(raw_devices)
        self._db.write_bulk("devices", list(devices.items()))

        vms = self._netbox.fetch_all("/api/virtualization/virtual-machines/")
        self._db.write_bulk("vms", [(vm["id"], vm) for vm in vms])

        cables = self._netbox.fetch_all("/api/dcim/cables/", params={"type__n": "power"})
        self._db.write_bulk("cables", [(cable["id"], cable) for cable in cables])

        interfaces = self._netbox.fetch_all("/api/dcim/interfaces/")
        self._db.write_bulk("interfaces", [(iface["id"], iface) for iface in interfaces])

        traces = self._fetch_traces(interfaces)
        self._db.write_bulk("traces", list(traces.items()))

        log.info("Cache refresh complete")

    def _build(self) -> None:
        snapshot = self._db.load_snapshot()
        result = build_all(snapshot, self._blank_lines)
        self._store.update(result)
        log.info(
            "Build complete: %d links, %d paths",
            len(result.links),
            len(result.paths),
        )

    def _fetch_traces(self, interfaces: list[dict[str, Any]]) -> dict[int, list[Any]]:
        iface_ids = [
            iface["id"]
            for iface in interfaces
            if iface.get("id") and iface.get("cable") is not None
        ]
        traces: dict[int, list[Any]] = {}
        if not iface_ids:
            return traces

        with ThreadPoolExecutor(max_workers=self._config.trace_concurrency) as executor:
            futures = {
                executor.submit(self._netbox.fetch_interface_trace, iface_id): iface_id
                for iface_id in iface_ids
            }
            for future in as_completed(futures):
                iface_id = futures[future]
                try:
                    result = future.result()
                except Exception:
                    log.exception("Error fetching trace for interface %d", iface_id)
                    continue
                if result:
                    traces[iface_id] = result
        return traces
