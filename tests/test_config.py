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


class TestDomainDefaults:
    def test_main_tag_default(self) -> None:
        assert Config.from_env(_VALID).main_tag == "mapgl-main"

    def test_main_tag_override(self) -> None:
        env = dict(_VALID, NETBOX_MAIN_TAG="custom-main")
        assert Config.from_env(env).main_tag == "custom-main"

    def test_target_roles_default(self) -> None:
        assert Config.from_env(_VALID).target_roles == frozenset({"router", "switch"})

    def test_target_roles_override(self) -> None:
        env = dict(_VALID, NETBOX_TARGET_ROLES='["router","firewall"]')
        assert Config.from_env(env).target_roles == frozenset({"router", "firewall"})

    def test_target_roles_invalid_json_falls_back(self) -> None:
        env = dict(_VALID, NETBOX_TARGET_ROLES="not-json")
        assert Config.from_env(env).target_roles == frozenset({"router", "switch"})

    def test_target_roles_empty_list_falls_back(self) -> None:
        env = dict(_VALID, NETBOX_TARGET_ROLES="[]")
        assert Config.from_env(env).target_roles == frozenset({"router", "switch"})

    def test_lat_field_default(self) -> None:
        assert Config.from_env(_VALID).lat_field == "lat"

    def test_lat_field_override(self) -> None:
        env = dict(_VALID, NETBOX_LAT_FIELD="latitude")
        assert Config.from_env(env).lat_field == "latitude"

    def test_lon_field_default(self) -> None:
        assert Config.from_env(_VALID).lon_field == "lon"

    def test_lon_field_override(self) -> None:
        env = dict(_VALID, NETBOX_LON_FIELD="longitude")
        assert Config.from_env(env).lon_field == "longitude"
