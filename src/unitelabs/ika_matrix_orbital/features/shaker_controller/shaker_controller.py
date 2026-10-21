import typing_extensions as typing

from unitelabs.cdk import Publisher, sila

from ...constants import ORIGINATOR, SPEED_MAX, SPEED_MIN
from ...io import MatrixOrbitalProtocol
from ...io.units import RPM

Speed = typing.Annotated[
    int, RPM, sila.constraints.MinimalInclusive(SPEED_MIN), sila.constraints.MaximalInclusive(SPEED_MAX)
]


class ShakerController(sila.Feature):
    """
    Controls the orbital shaking of the thermoshaker.

    Shaking runs until it is stopped; it has no natural end. Start sets the speed set point and starts the
    motor in one call, so a client never has to remember a previously set value. The device ramps to the set
    point within a few seconds; follow Speed to see when it is reached. Speed and temperature control are
    independent: this feature never changes the temperature.

    The instrument accepts set points in 10 rpm steps and regulates from 300 rpm upwards; a set point below
    that is left to the firmware, which may clamp it. A set point of 0 with the motor running lets the
    platform coast to a standstill.
    """

    def __init__(self, protocol: MatrixOrbitalProtocol) -> None:
        super().__init__(originator=ORIGINATOR, category="shaking")
        self.protocol = protocol
        self._speed = Publisher[int](source=protocol.read_actual_speed, interval=1)
        self._target_speed = Publisher[int](source=protocol.read_set_speed, interval=2)

    @sila.ObservableProperty()
    async def subscribe_speed(self) -> sila.Stream[Speed]:
        """Subscribe to the shaking speed currently measured by the device."""
        return self._speed.subscribe()

    @sila.ObservableProperty()
    async def subscribe_target_speed(self) -> sila.Stream[Speed]:
        """Subscribe to the speed set point the device regulates to while the motor runs."""
        return self._target_speed.subscribe()

    @sila.UnobservableCommand()
    async def start(self, target_speed: Speed) -> None:
        """
        Set the speed set point and start the motor.

        Calling Start while already shaking only changes the set point; the motor keeps running.

        Args:
          TargetSpeed: The speed the platform should shake at.
        """
        await self.protocol.set_speed(target_speed)
        await self.protocol.start_motor()

    @sila.UnobservableCommand()
    async def stop(self) -> None:
        """Stop the motor. The platform coasts to a standstill; the set point is kept. Safe to call when stopped."""
        await self.protocol.stop_motor()
