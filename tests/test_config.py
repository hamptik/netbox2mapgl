"""Tests for configuration loading and validation."""

from __future__ import annotations

import pytest

from app.config import Config

_VALID = {
    "NETBOX_URL": "https://netbox.example.com/",
    "NETBOX_TOKEN": "secret",
}


def test_strips_trailing_slash_from_url() -> None:
    cfg = Config.from_env(_VALID)
    assert cfg.netbox_url == "https://netbox.example.com"


def test_defaults() -> None:
    cfg = Config.from_env(_VALID)
    assert cfg.verify_ssl is True
    assert cfg.listen_host == "0.0.0.0"
    assert cfg.listen_port == 5000
    assert cfg.cache_interval_sec == 1200
    assert cfg.trace_concurrency == 1
    assert cfg.netbox_page_size == 1000
    assert cfg.log_level == "INFO"


def test_missing_url_raises() -> None:
    env = dict(_VALID)
    env.pop("NETBOX_URL")
    with pytest.raises(SystemExit):
        Config.from_env(env)


def test_missing_token_raises() -> None:
    env = dict(_VALID)
    env.pop("NETBOX_TOKEN")
    with pytest.raises(SystemExit):
        Config.from_env(env)


def test_db_path_default() -> None:
    cfg = Config.from_env(_VALID)
    assert cfg.db_path == "/data/netbox_cache.db"


def test_db_path_override() -> None:
    env = dict(_VALID, DB_PATH="/tmp/test.db")
    assert Config.from_env(env).db_path == "/tmp/test.db"


def test_bool_parsing() -> None:
    env = dict(_VALID, NETBOX_VERIFY_SSL="false")
    assert Config.from_env(env).verify_ssl is False
    env = dict(_VALID, NETBOX_VERIFY_SSL="0")
    assert Config.from_env(env).verify_ssl is False
    env = dict(_VALID, NETBOX_VERIFY_SSL="true")
    assert Config.from_env(env).verify_ssl is True


def test_bad_int_falls_back() -> None:
    env = dict(_VALID, LISTEN_PORT="not-a-number")
    assert Config.from_env(env).listen_port == 5000


def test_page_size_override() -> None:
    env = dict(_VALID, NETBOX_PAGE_SIZE="2500")
    assert Config.from_env(env).netbox_page_size == 2500


def test_page_size_clamped_to_minimum() -> None:
    env = dict(_VALID, NETBOX_PAGE_SIZE="0")
    assert Config.from_env(env).netbox_page_size == 1
    env = dict(_VALID, NETBOX_PAGE_SIZE="-5")
    assert Config.from_env(env).netbox_page_size == 1
