import enum

import typing_extensions as typing

from unitelabs.cdk import sila

from ...constants import (
    ORIGINATOR,
    SPEED_MAX,
    SPEED_MIN,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    WATCHDOG_TIME_MAX,
    WATCHDOG_TIME_MIN,
)
from ...io import MatrixOrbitalProtocol, WatchdogMode
from ...io.units import CELSIUS, RPM, SECOND

Timeout = typing.Annotated[
    int,
    SECOND,
    sila.constraints.MinimalInclusive(WATCHDOG_TIME_MIN),
    sila.constraints.MaximalInclusive(WATCHDOG_TIME_MAX),
]
SafetyTemperature = typing.Annotated[
    float,
    CELSIUS,
    sila.constraints.MinimalInclusive(TEMPERATURE_MIN),
    sila.constraints.MaximalInclusive(TEMPERATURE_MAX),
]
SafetySpeed = typing.Annotated[
    int, RPM, sila.constraints.MinimalInclusive(SPEED_MIN), sila.constraints.MaximalInclusive(SPEED_MAX)
]


class WatchdogState(enum.Enum):
    """Whether, and how, the device watchdog is armed by this server."""

    INACTIVE = enum.auto()
    SWITCH_OFF = enum.auto()
    SAFETY_VALUES = enum.auto()


class WatchdogService(sila.Feature):
    """
    Arms the instrument's communication watchdog so an unattended run fails safe.

    Once armed, the device expects this server to repeat the watchdog command within the chosen timeout.
    The server does that automatically for as long as it runs. If the server, the computer or the cable fails,
    the device reacts on its own: in "switch off" mode it stops temperature control and the motor, in
    "safety values" mode it jumps to the safety temperature and safety speed. Either way the display shows
    Error 2 until Stop is called, which also returns the device to normal operation.

    Set the safety values before arming "safety values" mode; the device cannot report them back.
    """

    def __init__(self, protocol: MatrixOrbitalProtocol) -> None:
        super().__init__(originator=ORIGINATOR, category="safety")
        self.protocol = protocol

    @sila.UnobservableProperty()
    async def get_state(self) -> WatchdogState:
        """Get the watchdog mode this server is keeping alive. Reflects this server's actions, not a device query."""
        mode = self.protocol.watchdog_mode
        if mode is None:
            return WatchdogState.INACTIVE
        return WatchdogState[mode.name]

    @sila.UnobservableCommand()
    async def start(self, mode: WatchdogMode, timeout: Timeout) -> None:
        """
        Arm the watchdog and start feeding it.

        Calling Start while armed replaces the mode and timeout.

        Args:
          Mode: What the device does when the feed stops: "switch off" stops heating and shaking, "safety
            values" jumps to the safety set points.
          Timeout: How long the device waits for the next feed before reacting.
        """
        await self.protocol.start_watchdog(mode, timeout)

    @sila.UnobservableCommand()
    async def stop(self) -> None:
        """Stop feeding the watchdog and return the device to normal operation, clearing Error 2 if shown."""
        await self.protocol.reset()

    @sila.UnobservableCommand()
    async def set_safety_temperature(self, safety_temperature: SafetyTemperature) -> None:
        """
        Set the temperature the device falls back to in SafetyValues mode.

        Args:
          SafetyTemperature: The fallback temperature set point.
        """
        await self.protocol.set_watchdog_safety_temperature(safety_temperature)

    @sila.UnobservableCommand()
    async def set_safety_speed(self, safety_speed: SafetySpeed) -> None:
        """
        Set the speed the device falls back to in SafetyValues mode.

        Args:
          SafetySpeed: The fallback speed set point.
        """
        await self.protocol.set_watchdog_safety_speed(safety_speed)
