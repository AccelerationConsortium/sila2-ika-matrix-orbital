from unitelabs.ika_matrix_orbital.features import TemperatureController


async def test_interface(protocol):
    feature = TemperatureController(protocol)
    feature.attach()
    assert set(feature.commands) == {"Start", "Stop"}
    assert set(feature.properties) == {"Temperature", "TargetTemperature"}
    target = feature.commands["Start"].parameters["target_temperature"].data_type
    constraints = {type(c).__name__: c for c in target.constraints}
    assert constraints["MinimalInclusive"].value.value == 1.0
    assert constraints["MaximalInclusive"].value.value == 100.0
    assert constraints["Unit"].label == "°C"


async def test_start_and_stop(protocol, device, clock):
    feature = TemperatureController(protocol)
    feature.attach()
    await feature.start(target_temperature=50.0)
    assert device.received[-2:] == ["OUT_SP_2 50.0", "START_2"]
    clock.advance(60)
    assert await protocol.read_actual_temperature() == 28.0
    await feature.stop()
    assert device.tempering_on is False
