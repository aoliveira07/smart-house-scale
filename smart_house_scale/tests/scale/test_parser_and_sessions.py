from datetime import UTC, datetime, timedelta

try:
    from smart_house_scale.custom_components.smart_house_scale.parser import parse_service_info
    from smart_house_scale.custom_components.smart_house_scale.session import SessionAggregator
except ModuleNotFoundError:
    from custom_components.smart_house_scale.parser import parse_service_info
    from custom_components.smart_house_scale.session import SessionAggregator


def test_xiaomi_v1_kg_and_normalized_mac():
    # 61.30 kg * 200 = 12260 = 0x2fe4, little endian e4 2f.
    reading = parse_service_info({"address": "aabbccddeeff", "rssi": -54, "service_data": {"181d": bytes([0x20, 0xE4, 0x2F])}})
    assert reading is not None
    assert reading.weight_kg == 61.3
    assert reading.original_unit == "kg"
    assert reading.stable is True
    assert reading.mac_address == "AA:BB:CC:DD:EE:FF"


def test_xiaomi_v1_native_units_are_normalized_to_kg():
    pounds = parse_service_info({"address": "AA:BB:CC:DD:EE:FF", "service_data": {"181d": bytes([0x03, 0x10, 0x27])}})
    jin = parse_service_info({"address": "AA:BB:CC:DD:EE:FF", "service_data": {"181d": bytes([0x12, 0x10, 0x27])}})
    assert pounds is not None and pounds.original_unit == "lbs" and round(pounds.weight_kg, 3) == 45.359
    assert jin is not None and jin.original_unit == "jin" and jin.weight_kg == 50.0


def test_xiaomi_v2_has_impedance_and_requires_stable_flag():
    # unit=kg, stable+impedance, impedance=500, weight=61.3 kg.
    payload = bytes([0x02, 0x22, 0, 0, 0, 0, 0, 0, 0, 0xF4, 0x01, 0xE4, 0x2F])
    reading = parse_service_info({"address": "AA:BB:CC:DD:EE:FF", "service_data": {"181b": payload}})
    assert reading is not None
    assert reading.weight_kg == 61.3
    assert reading.impedance == 500
    assert reading.stable is True


def test_session_finalizes_once_and_deduplicates_broadcasts():
    now = datetime(2026, 10, 15, tzinfo=UTC)
    clock = lambda: now
    aggregator = SessionAggregator(30, clock)
    # Use a non-stable V2 frame, then a stable frame.
    unstable = parse_service_info({"address": "AA:BB:CC:DD:EE:FF", "service_data": {"181b": bytes([2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xE4, 0x2F])}})
    stable = parse_service_info({"address": "AA:BB:CC:DD:EE:FF", "service_data": {"181b": bytes([2, 0x20, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xE4, 0x2F])}})
    assert aggregator.ingest(unstable) is None
    assert aggregator.ingest(stable) is not None
    assert aggregator.last_finalized is not None
    assert aggregator.last_finalized.advertisement_count == 2
    assert aggregator.ingest(stable) is None
    now += timedelta(seconds=31)
    assert aggregator.ingest(stable) is not None
