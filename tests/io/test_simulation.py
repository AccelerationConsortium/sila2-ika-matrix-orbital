"""Byte-level behaviour of the simulated device: what the heingroup driver would see on the wire."""

from unitelabs.ika_matrix_orbital.io import SimulatedThermoshaker


def ask(device: SimulatedThermoshaker, command: str) -> str:
    """Send one NAMUR line the way `ika.abc.IKADevice` does and read the reply up to CR."""
    device.write(f"{command}\r\n".encode())
    reply = device.read_until(b"\r").decode()
    device.read_until(b"\n")  # the driver leaves the LF behind; drain it so each test sees a clean line
    return reply.strip()


def test_version_queries_answer_strings(device):
    assert ask(device, "IN_VERSION") == "1.0.0"
    assert ask(device, "IN_SOFTWARE_ID") == "1;1.0.0"


def test_value_queries_answer_command_then_value(device):
    assert ask(device, "IN_PV_2") == "IN_PV_2 22.0"
    assert ask(device, "IN_SP_4") == "IN_SP_4 0"


def test_set_speed_and_start_motor_ramps_speed(device, clock):
    assert ask(device, "OUT_SP_4 1000") == "OUT_SP_4 1000"
    assert ask(device, "START_4") == "START_4"
    clock.advance(1)
    assert ask(device, "IN_PV_4") == "IN_PV_4 500"
    clock.advance(5)
    assert ask(device, "IN_PV_4") == "IN_PV_4 1000"
    assert ask(device, "STOP_4") == "STOP_4"
    clock.advance(10)
    assert ask(device, "IN_PV_4") == "IN_PV_4 0"


def test_tempering_heats_at_six_kelvin_per_minute(device, clock):
    ask(device, "OUT_SP_2 40")
    ask(device, "START_2")
    clock.advance(60)
    assert ask(device, "IN_PV_2") == "IN_PV_2 28.0"
    clock.advance(600)
    assert ask(device, "IN_PV_2") == "IN_PV_2 40.0"
    ask(device, "STOP_2")
    clock.advance(60)
    assert ask(device, "IN_PV_2") == "IN_PV_2 39.5"


def test_set_points_are_clamped_to_device_limits(device):
    ask(device, "OUT_SP_4 5000")
    assert ask(device, "IN_SP_4") == "IN_SP_4 3000"
    ask(device, "OUT_SP_2 150")
    assert ask(device, "IN_SP_2") == "IN_SP_2 100.0"


def test_watchdog_mode_1_switches_off_when_not_fed(device, clock):
    ask(device, "OUT_SP_4 500")
    ask(device, "START_4")
    ask(device, "START_2")
    assert ask(device, "OUT_WD1@30") == "30"
    clock.advance(20)
    ask(device, "OUT_WD1@30")  # fed in time
    clock.advance(31)
    ask(device, "IN_PV_4")  # any command lets the model notice the elapsed time
    assert device.motor_on is False
    assert device.tempering_on is False
    assert device.error == 2
    assert ask(device, "RESET") == "RESET"
    assert device.error == 0
    assert device.watchdog_mode == 0


def test_watchdog_mode_2_falls_back_to_safety_values(device, clock):
    assert ask(device, "OUT_SP_12@25.5") == "25.5"
    assert ask(device, "OUT_SP_42@300") == "300"
    ask(device, "OUT_SP_2 60")
    ask(device, "OUT_SP_4 1500")
    ask(device, "OUT_WD2@20")
    clock.advance(21)
    ask(device, "IN_PV_2")
    assert device.target_temperature == 25.5
    assert device.target_speed == 300
    assert device.error == 2


def test_unknown_command_gets_an_empty_line(device):
    assert ask(device, "HELLO") == ""


def test_partial_writes_are_assembled_into_one_line(device):
    device.write(b"IN_V")
    device.write(b"ERSION\r\n")
    assert device.read_until(b"\r") == b"1.0.0\r"
