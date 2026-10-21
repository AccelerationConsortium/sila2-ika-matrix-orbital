"""
An in-memory IKA MATRIX Orbital Delta Plus that answers NAMUR commands like the serial port would.

The simulator stands in for `serial.Serial`: it offers `write`, `read_until`, `close`, `is_open` and `port`,
which is everything the heingroup `ika` driver touches. The real driver code therefore runs unchanged in
simulation mode; only the bytes come from here instead of from the instrument.

Reply formats follow the heingroup driver's observations of the real device (see `ika.thermoshaker`):
value queries answer `<COMMAND> <value>`, watchdog commands echo the number, `IN_VERSION` answers a
version string. The manual does not print reply examples, so these shapes are flagged for verification
against the instrument.
"""

import collections.abc
import time

from ika.thermoshaker import ThermoshakerProtocol as Namur

from ..constants import SPEED_MAX, SPEED_MIN, TEMPERATURE_MAX, TEMPERATURE_MIN

LINE_ENDING = b"\r\n"

SET_WATCHDOG_SAFETY_SPEED = "OUT_SP_42@"
"""Manual-only command (not in the heingroup driver): WD-safety speed with echo of the set value."""

SOFTWARE_VERSION = "1.0.0"
SOFTWARE_ID = "1;1.0.0"

PASSIVE_DRIFT_RATE = 0.5
"""K/min the sample holder drifts towards ambient while temperature control is off (simulator assumption)."""


class SimulatedThermoshaker:
    """
    Minimal physical model of the thermoshaker behind a serial-like byte interface.

    Args:
      ambient_temperature: Room temperature the holder drifts to with temperature control off.
      heating_rate: Heating rate in K/min (6 K/min in the technical data).
      cooling_rate: Cooling rate in K/min (0.8 K/min in the technical data).
      speed_ramp: Speed change in rpm/s when starting or stopping (simulator assumption).
      clock: Monotonic time source in seconds; tests inject a controllable clock.
    """

    port = "simulated"

    def __init__(
        self,
        ambient_temperature: float = 22.0,
        heating_rate: float = 6.0,
        cooling_rate: float = 0.8,
        speed_ramp: float = 500.0,
        clock: collections.abc.Callable[[], float] = time.monotonic,
    ) -> None:
        self.ambient_temperature = ambient_temperature
        self.heating_rate = heating_rate
        self.cooling_rate = cooling_rate
        self.speed_ramp = speed_ramp
        self._clock = clock

        self.temperature = ambient_temperature
        self.target_temperature = ambient_temperature
        self.tempering_on = False

        self.speed = 0.0
        self.target_speed = 0
        self.motor_on = False

        self.watchdog_mode = 0
        self.watchdog_time = 0
        self.safety_temperature = 20.0
        self.safety_speed = 0
        self.error = 0
        """Error code shown on the display; 2 after a watchdog event, 0 otherwise."""

        self.received: list[str] = []
        """Every command line received, oldest first, for assertions in tests."""

        self.is_open = True
        self._last_update = clock()
        self._last_watchdog_feed = clock()
        self._pending = bytearray()
        self._incoming = bytearray()

    # -- serial.Serial look-alike -------------------------------------------------------------------------------

    def write(self, data: bytes) -> int:
        """Accept bytes from the driver; every completed CR LF line is handled as one command."""
        self._incoming.extend(data)
        while LINE_ENDING in self._incoming:
            line, _, rest = bytes(self._incoming).partition(LINE_ENDING)
            self._incoming = bytearray(rest)
            command = line.decode(errors="replace").strip()
            self.received.append(command)
            self._pending.extend(self._reply(command).encode() + LINE_ENDING)
        return len(data)

    def read_until(self, expected: bytes = b"\n", size: int | None = None) -> bytes:
        """Return pending reply bytes up to and including `expected`, like `serial.Serial.read_until`."""
        index = self._pending.find(expected)
        end = len(self._pending) if index < 0 else index + len(expected)
        if size is not None:
            end = min(end, size)
        chunk = bytes(self._pending[:end])
        del self._pending[:end]
        return chunk

    def close(self) -> None:
        """Mark the port closed."""
        self.is_open = False

    # -- physical model -----------------------------------------------------------------------------------------

    def advance(self) -> None:
        """Move temperature and speed towards their targets for the time elapsed since the last call."""
        now = self._clock()
        elapsed = max(0.0, now - self._last_update)
        self._last_update = now

        self._check_watchdog(now)

        if self.tempering_on:
            rate = self.heating_rate if self.target_temperature > self.temperature else self.cooling_rate
            self.temperature = _approach(self.temperature, self.target_temperature, rate / 60 * elapsed)
        else:
            self.temperature = _approach(self.temperature, self.ambient_temperature, PASSIVE_DRIFT_RATE / 60 * elapsed)

        goal = float(self.target_speed) if self.motor_on else 0.0
        self.speed = _approach(self.speed, goal, self.speed_ramp * elapsed)

    def _check_watchdog(self, now: float) -> None:
        if self.watchdog_mode == 0 or now - self._last_watchdog_feed <= self.watchdog_time:
            return
        if self.watchdog_mode == 1:
            self.tempering_on = False
            self.motor_on = False
        else:
            self.target_temperature = self.safety_temperature
            self.target_speed = self.safety_speed
        self.error = 2

    # -- NAMUR command handling ---------------------------------------------------------------------------------

    def _reply(self, command: str) -> str:
        self.advance()
        name, _, argument = command.partition(" ")

        if name == Namur.READ_ACTUAL_TEMPERATURE:
            return f"{name} {self.temperature:.1f}"
        if name == Namur.READ_SET_TEMPERATURE:
            return f"{name} {self.target_temperature:.1f}"
        if name == Namur.READ_ACTUAL_SPEED:
            return f"{name} {self.speed:.0f}"
        if name == Namur.READ_SET_SPEED:
            return f"{name} {self.target_speed}"
        if name == Namur.SET_TEMPERATURE:
            self.target_temperature = min(max(round(float(argument)), TEMPERATURE_MIN), TEMPERATURE_MAX)
            return command
        if name == Namur.SET_SPEED:
            self.target_speed = int(min(max(round(float(argument)), SPEED_MIN), SPEED_MAX))
            return command
        if name == Namur.START_TEMPERING:
            self.tempering_on = True
            return command
        if name == Namur.STOP_TEMPERING:
            self.tempering_on = False
            return command
        if name == Namur.START_MOTOR:
            self.motor_on = True
            return command
        if name == Namur.STOP_MOTOR:
            self.motor_on = False
            return command
        if name == Namur.SWITCH_TO_NORMAL_OPERATING_MODE:
            self.watchdog_mode = 0
            self.error = 0
            return command
        if name == Namur.READ_SOFTWARE_VERSION:
            return SOFTWARE_VERSION
        if name == Namur.READ_SOFTWARE_ID_AND_VERSION:
            return SOFTWARE_ID
        if name.startswith(Namur.SET_WATCHDOG_SAFETY_TEMPERATURE):
            self.safety_temperature = float(name.removeprefix(Namur.SET_WATCHDOG_SAFETY_TEMPERATURE))
            return f"{self.safety_temperature:.1f}"
        if name.startswith(SET_WATCHDOG_SAFETY_SPEED):
            self.safety_speed = int(float(name.removeprefix(SET_WATCHDOG_SAFETY_SPEED)))
            return f"{self.safety_speed}"
        if name.startswith(Namur.WATCHDOG_MODE_1):
            return self._arm_watchdog(1, name.removeprefix(Namur.WATCHDOG_MODE_1))
        if name.startswith(Namur.WATCHDOG_MODE_2):
            return self._arm_watchdog(2, name.removeprefix(Namur.WATCHDOG_MODE_2))
        return ""

    def _arm_watchdog(self, mode: int, seconds: str) -> str:
        self.watchdog_mode = mode
        self.watchdog_time = int(seconds)
        self._last_watchdog_feed = self._clock()
        return f"{self.watchdog_time}"


def _approach(current: float, goal: float, step: float) -> float:
    """Move `current` towards `goal` by at most `step`."""
    if abs(goal - current) <= step:
        return goal
    return current + step if goal > current else current - step
