"""Tests for the NetBox client, focused on ``fetch_all`` pagination."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from app.netbox import NetBoxClient, NetBoxError


class _FakeResponse:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self) -> Any:
        return self._payload


class _FakeSession:
    """Mimics ``requests.Session.get`` using a scripted list of payloads."""

    def __init__(self, pages: list[Any]) -> None:
        self._pages = pages
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(
        self, url: str, params: dict[str, Any] | None = None, timeout: int | None = None
    ) -> _FakeResponse:
        self.calls.append((url, dict(params or {})))
        return _FakeResponse(self._pages.pop(0))


def _client(page_size: int = 1000) -> NetBoxClient:
    return NetBoxClient(
        "https://nb.example.com",
        "tok",
        verify_ssl=False,
        timeout=10,
        page_size=page_size,
    )


def _wire(client: NetBoxClient, pages: list[Any]) -> _FakeSession:
    fake = _FakeSession(pages)
    client._session = fake  # type: ignore[assignment]
    return fake


def test_paginates_across_multiple_pages() -> None:
    client = _client(page_size=2)
    fake = _wire(
        client,
        [
            {"count": 5, "results": [{"id": 1}, {"id": 2}]},
            {"count": 5, "results": [{"id": 3}, {"id": 4}]},
            {"count": 5, "results": [{"id": 5}]},
        ],
    )

    result = client.fetch_all("/api/dcim/interfaces/")

    assert [r["id"] for r in result] == [1, 2, 3, 4, 5]
    # Three sequential offset pages were requested.
    assert [c[1]["offset"] for c in fake.calls] == [0, 2, 4]
    assert all(c[1]["limit"] == 2 for c in fake.calls)


def test_single_page_stops_without_extra_requests() -> None:
    client = _client(page_size=100)
    fake = _wire(client, [{"count": 2, "results": [{"id": 1}, {"id": 2}]}])

    result = client.fetch_all("/api/things/")

    assert result == [{"id": 1}, {"id": 2}]
    assert len(fake.calls) == 1


def test_empty_result_set() -> None:
    client = _client()
    fake = _wire(client, [{"count": 0, "results": []}])

    assert client.fetch_all("/api/things/") == []
    assert len(fake.calls) == 1


def test_bare_list_response_returned_as_is() -> None:
    client = _client()
    fake = _wire(client, [[{"id": 1}, {"id": 2}]])  # one page: a bare list

    result = client.fetch_all("/api/unpaged/")

    assert result == [{"id": 1}, {"id": 2}]
    assert len(fake.calls) == 1


def test_caller_params_are_preserved() -> None:
    client = _client(page_size=10)
    fake = _wire(client, [{"count": 1, "results": [{"id": 1}]}])

    client.fetch_all("/api/dcim/cables/", params={"type__n": "power"})

    params = fake.calls[0][1]
    assert params["type__n"] == "power"
    assert params["limit"] == 10
    assert params["offset"] == 0


def test_http_error_raises_netbox_error() -> None:
    client = _client()

    class _ErrorSession:
        def get(
            self, url: str, params: dict[str, Any] | None = None, timeout: int | None = None
        ) -> _FakeResponse:
            return _FakeResponse({}, status=500)

    client._session = _ErrorSession()  # type: ignore[assignment]

    with pytest.raises(NetBoxError):
        client.fetch_all("/api/things/")
