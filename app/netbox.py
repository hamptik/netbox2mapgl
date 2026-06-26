"""NetBox REST API client.

A single :class:`NetBoxClient` reuses a ``requests.Session`` (HTTP keep-alive)
and centralizes timeout / SSL / auth handling. Paged endpoints are read in full
by walking ``offset`` pages of ``page_size`` rows, so a server-side
``MAX_PAGE_SIZE`` cap can never silently truncate the result set.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

log = logging.getLogger(__name__)


class NetBoxError(RuntimeError):
    """Raised when NetBox returns an unrecoverable error."""


class NetBoxClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        verify_ssl: bool,
        timeout: int,
        page_size: int = 1000,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._page_size = max(1, page_size)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Token {token}",
                "Accept": "application/json",
            }
        )
        self._session.verify = verify_ssl

    def fetch_all(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch the full result list of a paged NetBox endpoint.

        Pagination is driven by ``offset`` against ``page_size`` rather than the
        ``limit=0`` shortcut: when a NetBox deployment sets ``MAX_PAGE_SIZE`` the
        server silently caps any request (including ``limit=0``), so a single
        shot would drop everything beyond that cap. Walking the pages by offset
        guarantees the complete result set is retrieved regardless of the
        server-side limit.
        """
        base_params: dict[str, Any] = dict(params or {})
        base_params["limit"] = self._page_size
        url = f"{self._base_url}{endpoint}"

        results: list[dict[str, Any]] = []
        offset = 0
        while True:
            request_params = dict(base_params)
            request_params["offset"] = offset
            try:
                resp = self._session.get(url, params=request_params, timeout=self._timeout)
                resp.raise_for_status()
            except requests.RequestException as exc:
                raise NetBoxError(f"Failed to fetch {endpoint}: {exc}") from exc

            payload = resp.json()
            # Non-paged endpoints return a bare list; return it as-is.
            if isinstance(payload, list):
                return payload

            page = list(payload.get("results", []))
            results.extend(page)

            # Stop on the last page: an empty page, a short page, or when the
            # accumulated offset reaches the reported total count.
            if not page or len(page) < self._page_size:
                break
            total = payload.get("count")
            if isinstance(total, int) and offset + len(page) >= total:
                break
            offset += len(page)

        return results

    def fetch_interface_trace(self, interface_id: int) -> list[Any] | None:
        """Fetch the cable trace for one interface.

        Returns ``None`` for any non-200 response or network error so callers
        can simply skip the interface without bubbling exceptions out of the
        thread pool.
        """
        url = f"{self._base_url}/api/dcim/interfaces/{interface_id}/trace/"
        try:
            resp = self._session.get(url, timeout=self._timeout)
        except requests.RequestException as exc:
            log.debug("Trace request failed for interface %d: %s", interface_id, exc)
            return None
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if not isinstance(payload, list):
            return None
        return payload

    def close(self) -> None:
        self._session.close()
