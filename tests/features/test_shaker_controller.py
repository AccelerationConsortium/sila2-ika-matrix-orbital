import asyncio

from sila.server import UnobservableCommand

from unitelabs.ika_matrix_orbital.features import ShakerController


async def attached(protocol) -> ShakerController:
    feature = ShakerController(protocol)
    feature.attach()
    return feature


async def test_interface_identifiers_and_constraints(protocol):
    feature = await attached(protocol)
    assert feature.identifier == "ShakerController"
    assert set(feature.commands) == {"Start", "Stop"}
    assert set(feature.properties) == {"Speed", "TargetSpeed"}
    speed = feature.commands["Start"].parameters["target_speed"].data_type
    constraints = {type(c).__name__: c for c in speed.constraints}
    assert constraints["MinimalInclusive"].value.value == 0
    assert constraints["MaximalInclusive"].value.value == 3000
    assert constraints["Unit"].label == "rpm"


async def test_start_sets_speed_then_starts_motor(protocol, device):
    feature = await attached(protocol)
    await feature.start(target_speed=1200)
    assert device.received[-2:] == ["OUT_SP_4 1200", "START_4"]
    assert device.motor_on
    await feature.stop()
    assert device.motor_on is False


async def test_speed_subscription_streams_device_readings(protocol, device, clock):
    feature = await attached(protocol)
    await feature.start(target_speed=500)
    clock.advance(10)
    subscription = await feature.subscribe_speed()
    try:
        value = await asyncio.wait_for(anext(subscription), timeout=5)
    finally:
        subscription.terminate()
    assert value == 500


async def test_commands_are_unobservable(protocol):
    feature = await attached(protocol)
    assert isinstance(feature.commands["Start"], UnobservableCommand)
    assert isinstance(feature.commands["Stop"], UnobservableCommand)
