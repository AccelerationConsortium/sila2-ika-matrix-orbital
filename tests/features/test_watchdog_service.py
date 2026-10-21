from unitelabs.ika_matrix_orbital.features import WatchdogService
from unitelabs.ika_matrix_orbital.features.watchdog_service.watchdog_service import WatchdogState
from unitelabs.ika_matrix_orbital.io import WatchdogMode


async def test_state_follows_start_and_stop(protocol, device):
    feature = WatchdogService(protocol)
    feature.attach()
    assert await feature.get_state() is WatchdogState.INACTIVE
    await feature.start(mode=WatchdogMode.SAFETY_VALUES, timeout=60)
    assert await feature.get_state() is WatchdogState.SAFETY_VALUES
    assert device.watchdog_mode == 2
    await feature.stop()
    assert await feature.get_state() is WatchdogState.INACTIVE
    assert device.watchdog_mode == 0


async def test_safety_values(protocol, device):
    feature = WatchdogService(protocol)
    feature.attach()
    await feature.set_safety_temperature(safety_temperature=20.0)
    await feature.set_safety_speed(safety_speed=0)
    assert device.safety_temperature == 20.0
    assert device.safety_speed == 0


async def test_mode_parameter_is_a_constrained_string(protocol):
    feature = WatchdogService(protocol)
    feature.attach()
    mode = feature.commands["Start"].parameters["mode"].data_type
    allowed = next(c for c in mode.constraints if type(c).__name__ == "Set")
    # the CDK turns enum member names into lower-case words on the wire
    assert {str(getattr(v, "value", v)) for v in allowed.values} == {"switch off", "safety values"}
    timeout = feature.commands["Start"].parameters["timeout"].data_type
    bounds = {type(c).__name__: c.value.value for c in timeout.constraints if hasattr(c, "value")}
    assert bounds["MinimalInclusive"] == 20
    assert bounds["MaximalInclusive"] == 1500
