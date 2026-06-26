"""Flask blueprint exposing the MapGL data endpoints."""

from __future__ import annotations

import json
import logging

from flask import Blueprint, Response, current_app, request

from app.builders import format_paths_json
from app.cache import ResponseStore
from app.db import Database

log = logging.getLogger(__name__)

bp = Blueprint("mapgl", __name__)

_NOT_READY = Response(
    "Service Unavailable: initial build in progress",
    status=503,
    content_type="text/plain; charset=utf-8",
)


def _store() -> ResponseStore:
    store: ResponseStore | None = current_app.config["RESPONSE_STORE"]
    if store is None:  # pragma: no cover - set unconditionally in create_app
        raise RuntimeError("RESPONSE_STORE is not configured")
    return store


def _db() -> Database:
    db: Database | None = current_app.config["DATABASE"]
    if db is None:  # pragma: no cover - set unconditionally in create_app
        raise RuntimeError("DATABASE is not configured")
    return db


def _blank_lines() -> int:
    return int(current_app.config["BLANK_LINES_BETWEEN_OBJECTS"])


@bp.route("/links")
def api_links() -> Response:
    """Link records plus per-location coordinate markers."""
    store = _store()
    if not store.is_ready():
        return _NOT_READY

    result = store.result()
    if result is None:  # pragma: no cover - guaranteed by is_ready()
        return _NOT_READY

    location_filter = request.args.get("location")
    if not location_filter:
        return Response(
            result.links_json,
            content_type="application/json; charset=utf-8",
        )

    links = [
        link
        for link in result.links
        if link.get("vertexA") == location_filter or link.get("vertexB") == location_filter
    ]
    markers = [m for m in result.markers if m.get("vertexA") == location_filter]
    body = json.dumps(links + markers, ensure_ascii=False, indent=4)
    return Response(body, content_type="application/json; charset=utf-8")


@bp.route("/paths")
def api_paths() -> Response:
    """Path records, pretty-printed with blank lines between objects."""
    store = _store()
    if not store.is_ready():
        return _NOT_READY

    result = store.result()
    if result is None:  # pragma: no cover - guaranteed by is_ready()
        return _NOT_READY

    location_filter = request.args.get("location")
    if not location_filter:
        return Response(
            result.paths_json,
            content_type="application/json; charset=utf-8",
        )

    blank = _blank_lines()
    filtered = [p for p in result.paths if p.get("Location") == location_filter]
    body = format_paths_json(filtered, blank)
    return Response(body, content_type="application/json; charset=utf-8")


@bp.route("/health")
def api_health() -> Response:
    """Liveness/readiness probe backed by DB counts and build status."""
    ready = _store().is_ready()
    counts = _db().counts()
    body = json.dumps({"status": "ok", "ready": ready, **counts}, ensure_ascii=False)
    return Response(body, content_type="application/json; charset=utf-8")
