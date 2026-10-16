from datetime import UTC, datetime, timedelta

from smart_house_scale.addon_app.ingestion import SessionAggregator, parse_weight_entity_state


def test_native_xiaomi_entity_state_is_consumed_after_home_assistant_decryption():
    reading = parse_weight_entity_state(
        {
            "entity_id": "sensor.casal_balanca_peso",
            "state": "81.35",
            "last_changed": "2026-10-16T02:24:00Z",
            "attributes": {
                "unit_of_measurement": "kg",
                "device_class": "weight",
                "signal_strength": -61,
                "mac_address": "d0:7b:6f:30:dc:7e",
                "model": "MJTZC02YM",
            },
        },
        entity_id="sensor.casal_balanca_peso",
    )
    assert reading is not None
    assert reading.weight_kg == 81.35
    assert reading.original_unit == "kg"
    assert reading.stable is True
    assert reading.protocol == "home_assistant_entity"
    assert reading.mac_address == "D0:7B:6F:30:DC:7E"
    assert reading.rssi == -61
    assert reading.measured_at == datetime(2026, 10, 16, 2, 24, tzinfo=UTC)


def test_entity_units_are_normalized_to_kg_and_missing_mac_is_stable():
    pounds = parse_weight_entity_state(
        {"state": "180", "attributes": {"unit_of_measurement": "lb", "device_class": "weight"}},
        entity_id="sensor.other_scale_weight",
    )
    grams = parse_weight_entity_state(
        {"state": "81350", "attributes": {"unit_of_measurement": "g", "device_class": "weight"}},
        entity_id="sensor.other_scale_weight",
    )
    assert pounds is not None and round(pounds.weight_kg, 3) == 81.647
    assert grams is not None and grams.weight_kg == 81.35
    assert pounds.mac_address == grams.mac_address
    assert pounds.raw_payload["mac_address_source"] == "entity_id_fallback"


def test_unknown_or_non_weight_values_are_ignored():
    assert parse_weight_entity_state({"state": "unknown", "attributes": {}}, entity_id="sensor.scale") is None
    assert parse_weight_entity_state({"state": "42", "attributes": {"unit_of_measurement": "%"}}, entity_id="sensor.scale") is None


def test_session_finalizes_once_and_deduplicates_entity_changes():
    now = datetime(2026, 10, 15, tzinfo=UTC)
    aggregator = SessionAggregator(30, lambda: now)
    first = parse_weight_entity_state(
        {"state": "61.3", "attributes": {"unit_of_measurement": "kg", "device_class": "weight"}},
        entity_id="sensor.scale_weight",
    )
    second = parse_weight_entity_state(
        {"state": "61.4", "attributes": {"unit_of_measurement": "kg", "device_class": "weight"}},
        entity_id="sensor.scale_weight",
    )
    assert first is not None and second is not None
    assert aggregator.ingest(first) is not None
    assert aggregator.ingest(second) is None
    assert aggregator.last_finalized is not None
    assert aggregator.last_finalized.advertisement_count == 2
    now += timedelta(seconds=31)
    assert aggregator.ingest(second) is not None
