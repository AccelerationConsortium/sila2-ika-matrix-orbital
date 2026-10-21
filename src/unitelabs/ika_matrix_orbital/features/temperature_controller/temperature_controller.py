import typing_extensions as typing

from unitelabs.cdk import Publisher, sila

from ...constants import ORIGINATOR, TEMPERATURE_MAX, TEMPERATURE_MIN
from ...io import MatrixOrbitalProtocol
from ...io.units import CELSIUS

Temperature = typing.Annotated[float, CELSIUS]
TargetTemperature = typing.Annotated[
    float,
    CELSIUS,
    sila.constraints.MinimalInclusive(TEMPERATURE_MIN),
    sila.constraints.MaximalInclusive(TEMPERATURE_MAX),
]


class TemperatureController(sila.Feature):
    """
    Controls the temperature of the sample holder.

    The thermoshaker both heats (up to 100 °C) and cools (down to about 15 K below ambient), so one Start
    command covers both directions. Temperature control runs until stopped; reaching the set point can take
    minutes, so follow Temperature rather than waiting on the command. The device rounds set points to whole
    degrees. Temperature control and shaking are independent: this feature never changes the motor.
    """

    def __init__(self, protocol: MatrixOrbitalProtocol) -> None:
        super().__init__(originator=ORIGINATOR, category="temperature")
        self.protocol = protocol
        self._temperature = Publisher[float](source=protocol.read_actual_temperature, interval=1)
        self._target_temperature = Publisher[float](source=protocol.read_set_temperature, interval=2)

    @sila.ObservableProperty()
    async def subscribe_temperature(self) -> sila.Stream[Temperature]:
        """Subscribe to the temperature currently measured at the sample holder."""
        return self._temperature.subscribe()

    @sila.ObservableProperty()
    async def subscribe_target_temperature(self) -> sila.Stream[TargetTemperature]:
        """Subscribe to the temperature set point the device regulates to while temperature control is on."""
        return self._target_temperature.subscribe()

    @sila.UnobservableCommand()
    async def start(self, target_temperature: TargetTemperature) -> None:
        """
        Set the temperature set point and switch temperature control on.

        Calling Start while control is already on only changes the set point.

        Args:
          TargetTemperature: The temperature the sample holder should be regulated to.
        """
        await self.protocol.set_temperature(target_temperature)
        await self.protocol.start_tempering()

    @sila.UnobservableCommand()
    async def stop(self) -> None:
        """Switch temperature control off. The holder drifts back to ambient. Safe to call when already off."""
        await self.protocol.stop_tempering()
