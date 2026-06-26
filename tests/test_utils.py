"""Tests for the speed parser and geo helpers."""

from __future__ import annotations

from app.builders.utils import extract_geo, parse_speed_bps, rack_namespace


class TestParseSpeedBps:
    def test_gigabit(self) -> None:
        assert parse_speed_bps("TenGigabitEthernet1/0/1", "10gbase-t") == 10_000_000_000

    def test_gigabit_short(self) -> None:
        assert parse_speed_bps("1gbase-sx") == 1_000_000_000

    def test_megabit(self) -> None:
        assert parse_speed_bps("1000base-t") == 1_000_000_000

    def test_bare_number_defaults_to_megabit(self) -> None:
        assert parse_speed_bps("100base-tx") == 100_000_000

    def test_no_match_returns_zero(self) -> None:
        assert parse_speed_bps("eth0", "cat5e") == 0

    def test_none_name_still_uses_cable_type(self) -> None:
        # Regression: the original code dropped if_name entirely when the cable
        # type was not a string; if_name must still be considered.
        assert parse_speed_bps("10gbase-t", None) == 10_000_000_000

    def test_non_string_cable_type_does_not_crash(self) -> None:
        assert parse_speed_bps("1gbase-sx", {"value": "10gbase-t"}) == 1_000_000_000

    def test_decimal_speed(self) -> None:
        assert parse_speed_bps("2.5gbase-t") == 2_500_000_000


class TestExtractGeo:
    def test_returns_lon_lat(self) -> None:
        loc = {"custom_fields": {"lat": "59.9", "lon": "30.5"}}
        assert extract_geo(loc) == (30.5, 59.9)

    def test_missing_custom_fields(self) -> None:
        assert extract_geo({}) == (0.0, 0.0)

    def test_invalid_values(self) -> None:
        loc = {"custom_fields": {"lat": "abc", "lon": "59.9"}}
        assert extract_geo(loc) == (0.0, 0.0)

    def test_custom_field_names(self) -> None:
        loc = {"custom_fields": {"latitude": "59.9", "longitude": "30.5"}}
        assert extract_geo(loc, lat_field="latitude", lon_field="longitude") == (30.5, 59.9)


class TestRackNamespace:
    def test_no_rack(self) -> None:
        assert rack_namespace("dc1", None) == "dc1"
        assert rack_namespace("dc1", {}) == "dc1"

    def test_rack_with_name(self) -> None:
        assert rack_namespace("dc1", {"name": "Rack 2.3"}) == "dc1.2-3"

    def test_rack_name_without_digits(self) -> None:
        assert rack_namespace("dc1", {"name": "ABC"}) == "dc1"

    def test_none_location(self) -> None:
        assert rack_namespace(None, {"name": "Rack 1"}) == ".1"
