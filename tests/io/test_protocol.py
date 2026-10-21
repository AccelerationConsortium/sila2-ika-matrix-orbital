"""The async protocol over the simulated transport: typed results, error mapping, watchdog feeding, mode switching."""

import asyncio

import pytest

from unitelabs.ika_matrix_orbital.io import (
    DeviceUnreachable,
    MatrixOrbitalProtocol,
    NoResponse,
    NotConnected,
    SimulatedThermoshaker,
    WatchdogMode,
)


async def test_open_checks_the_device_answers(device):
    protocol = MatrixOrbitalProtocol(simulated=lambda: device, real=None)
    await protocol.open()
    assert protocol.is_open
    assert device.received == ["IN_VERSION"]
    await protocol.close()
    assert not protocol.is_open
    assert device.is_open is False


async def test_requests_before_open_raise_not_connected(device):
    protocol = MatrixOrbitalProtocol(simulated=lambda: device, real=None)
    with pytest.raises(NotConnected):
        await protocol.read_actual_speed()


async def test_reads_return_typed_values(protocol, device):
    assert await protocol.read_actual_temperature() == 22.0
    assert isinstance(await protocol.read_actual_temperature(), float)
    assert await protocol.read_actual_speed() == 0
    assert isinstance(await protocol.read_actual_speed(), int)
    assert await protocol.read_software_version() == "1.0.0"
    assert await protocol.read_software_id() == "1;1.0.0"


async def test_shaking_round_trip(protocol, device, clock):
    await protocol.set_speed(800)
    await protocol.start_motor()
    assert device.received[-2:] == ["OUT_SP_4 800", "START_4"]
    clock.advance(10)
    assert await protocol.read_actual_speed() == 800
    assert await protocol.read_set_speed() == 800
    await protocol.stop_motor()
    assert device.motor_on is False


async def test_tempering_round_trip(protocol, device, clock):
    await protocol.set_temperature(37.0)
    await protocol.start_tempering()
    assert device.received[-2:] == ["OUT_SP_2 37.0", "START_2"]
    clock.advance(600)
    assert await protocol.read_actual_temperature() == 37.0
    await protocol.stop_tempering()
    assert device.tempering_on is False


async def test_watchdog_is_fed_until_reset(protocol, device):
    await protocol.start_watchdog(WatchdogMode.SWITCH_OFF, 20)
    assert protocol.watchdog_mode is WatchdogMode.SWITCH_OFF
    assert device.received[-1] == "OUT_WD1@20"
    await protocol.reset()
    assert protocol.watchdog_mode is None
    assert device.received[-1] == "RESET"
    assert device.watchdog_mode == 0


async def test_watchdog_feed_repeats_at_half_the_timeout(device, monkeypatch):
    protocol = MatrixOrbitalProtocol(simulated=lambda: device, real=None)
    await protocol.open()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 2:
            await asyncio.Event().wait()  # park forever; the test cancels us through close()

    monkeypatch.setattr("unitelabs.ika_matrix_orbital.io.protocol._sleep", fake_sleep)
    await protocol.start_watchdog(WatchdogMode.SAFETY_VALUES, 40)
    for _ in range(50):
        if device.received.count("OUT_WD2@40") >= 2:
            break
        await asyncio.sleep(0)
    assert device.received.count("OUT_WD2@40") == 2
    assert sleeps[0] == 20
    await protocol.close()


async def test_safety_values_reach_the_device(protocol, device):
    await protocol.set_watchdog_safety_temperature(30.0)
    await protocol.set_watchdog_safety_speed(400)
    assert device.safety_temperature == 30.0
    assert device.safety_speed == 400
    assert device.received[-2:] == ["OUT_SP_12@30.0", "OUT_SP_42@400"]


async def test_empty_reply_becomes_no_response(device):
    protocol = MatrixOrbitalProtocol(simulated=lambda: device, real=None)
    await protocol.open()
    device.write = len  # device goes silent: nothing is queued, read_until returns b""
    with pytest.raises(NoResponse):
        await protocol.read_actual_speed()


async def test_real_mode_without_port_falls_back_to_simulation(protocol):
    with pytest.raises(DeviceUnreachable):
        await protocol.start_real_mode()
    assert protocol.simulation_mode is True
    assert protocol.is_open


async def test_real_mode_with_unreachable_port_falls_back_to_simulation(device):
    def broken_port() -> SimulatedThermoshaker:
        msg = "could not open port"
        raise DeviceUnreachable(msg)

    protocol = MatrixOrbitalProtocol(simulated=lambda: device, real=broken_port)
    await protocol.open()
    with pytest.raises(DeviceUnreachable):
        await protocol.start_real_mode()
    assert protocol.simulation_mode is True
    assert await protocol.read_software_version() == "1.0.0"
    await protocol.close()


async def test_real_mode_switches_transport(device):
    real_device = SimulatedThermoshaker()
    protocol = MatrixOrbitalProtocol(simulated=lambda: device, real=lambda: real_device)
    await protocol.open()
    await protocol.start_real_mode()
    assert protocol.simulation_mode is False
    await protocol.read_actual_speed()
    assert real_device.received == ["IN_VERSION", "IN_PV_4"]
    await protocol.start_simulation_mode()
    assert protocol.simulation_mode is True
    assert real_device.is_open is False
    await protocol.close()
