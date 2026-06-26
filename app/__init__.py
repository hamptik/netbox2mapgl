"""Application factory for netbox2mapgl.

Importing this package has no side effects: the database, response store and
refresher thread are only brought up through :func:`create_app`, which is what
gunicorn calls via ``app.wsgi:application``.
"""

from __future__ import annotations

import logging

from flask import Flask

from app.builders import build_all
from app.cache import ResponseStore
from app.config import Config
from app.db import Database
from app.netbox import NetBoxClient
from app.refresh import CacheRefresher
from app.routes import bp

log = logging.getLogger(__name__)


def create_app(config: Config | None = None) -> Flask:
    """Build and configure the Flask application."""
    config = config or Config.from_env()

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log.setLevel(config.log_level)

    app = Flask(__name__)
    app.config["BLANK_LINES_BETWEEN_OBJECTS"] = config.blank_lines_between_objects
    app.config["NETBOX_CONFIG"] = config

    _wire_persistence(app, config)

    app.register_blueprint(bp)
    return app


def _wire_persistence(app: Flask, config: Config) -> None:
    """Connect SQLite + NetBox, seed the response store and start the refresher."""
    database = Database(config.db_path)
    database.init_schema()

    store = ResponseStore()

    netbox = NetBoxClient(
        base_url=config.netbox_url,
        token=config.netbox_token,
        verify_ssl=config.verify_ssl,
        timeout=config.netbox_timeout,
        page_size=config.netbox_page_size,
    )
    refresher = CacheRefresher(
        config,
        netbox,
        database,
        store,
        blank_lines=config.blank_lines_between_objects,
    )
    app.config["DATABASE"] = database
    app.config["RESPONSE_STORE"] = store
    app.config["REFRESHER"] = refresher

    _startup_build(database, store, config.blank_lines_between_objects)

    refresher.start()
    log.info("Cache refresher started (interval=%ss)", config.cache_interval_sec)


def _startup_build(database: Database, store: ResponseStore, blank_lines: int) -> None:
    """Build API responses from existing DB data so they are ready on restart.

    On a fresh start (empty database) the build is skipped and the API returns
    503 until the first refresh + build cycle completes.
    """
    try:
        snapshot = database.load_snapshot()
        if not snapshot.devices and not snapshot.locations:
            log.info("Database empty, skipping startup build")
            return
        result = build_all(snapshot, blank_lines)
        store.update(result)
        log.info("Startup build from DB complete")
    except Exception:
        log.exception("Startup build failed")
