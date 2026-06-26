"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(raw: str) -> bool:
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def _get_int(raw: str, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class Config:
    """Immutable application configuration sourced from the environment."""

    netbox_url: str
    netbox_token: str
    db_path: str
    verify_ssl: bool
    netbox_timeout: int
    listen_host: str
    listen_port: int
    cache_interval_sec: int
    trace_concurrency: int
    netbox_page_size: int
    blank_lines_between_objects: int
    log_level: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        """Build a Config from the process environment.

        Raises SystemExit when mandatory values are missing so the app fails
        fast with a clear message rather than starting in a broken state.
        """
        e = env if env is not None else os.environ

        netbox_url = e.get("NETBOX_URL", "").rstrip("/")
        netbox_token = e.get("NETBOX_TOKEN", "")
        db_path = e.get("DB_PATH", "/data/netbox_cache.db")

        if not netbox_url:
            raise SystemExit("NETBOX_URL is required")
        if not netbox_token:
            raise SystemExit("NETBOX_TOKEN is required")

        return cls(
            netbox_url=netbox_url,
            netbox_token=netbox_token,
            db_path=db_path,
            verify_ssl=_get_bool(e.get("NETBOX_VERIFY_SSL", "true")),
            netbox_timeout=_get_int(e.get("NETBOX_REQUEST_TIMEOUT", "300"), 300),
            listen_host=e.get("LISTEN_HOST", "0.0.0.0"),
            listen_port=_get_int(e.get("LISTEN_PORT", "5000"), 5000),
            cache_interval_sec=_get_int(e.get("CACHE_INTERVAL_SEC", "1200"), 1200),
            trace_concurrency=max(1, _get_int(e.get("TRACE_CONCURRENCY", "1"), 1)),
            netbox_page_size=max(1, _get_int(e.get("NETBOX_PAGE_SIZE", "1000"), 1000)),
            blank_lines_between_objects=max(
                0, _get_int(e.get("BLANK_LINES_BETWEEN_OBJECTS", "3"), 3)
            ),
            log_level=e.get("LOG_LEVEL", "INFO").upper(),
        )
