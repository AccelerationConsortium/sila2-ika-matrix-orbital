import collections.abc
import functools
from importlib.metadata import version

from unitelabs.cdk import Connector
from unitelabs.cdk.features.core.lock_controller import LockController

from .config import IkaMatrixOrbitalConfig
from .features import (
    DeviceInformationProvider,
    ShakerController,
    SimulationController,
    TemperatureController,
    WatchdogService,
)
from .io import MatrixOrbitalProtocol, SimulatedThermoshaker, open_serial_port

__version__ = version("unitelabs-ika-matrix-orbital")


async def create_app(config: IkaMatrixOrbitalConfig) -> collections.abc.AsyncGenerator[Connector, None]:
    """Create the connector application."""

    app = Connector(config)

    simulated = config.simulated_device
    protocol = MatrixOrbitalProtocol(
        simulated=functools.partial(
            SimulatedThermoshaker,
            ambient_temperature=simulated.ambient_temperature,
            heating_rate=simulated.heating_rate,
            cooling_rate=simulated.cooling_rate,
            speed_ramp=simulated.speed_ramp,
        ),
        real=functools.partial(open_serial_port, config.serial_port) if config.serial_port else None,
        simulation_mode=config.simulation_mode,
    )

    app.register(LockController())
    app.register(SimulationController(protocol))
    app.register(ShakerController(protocol))
    app.register(TemperatureController(protocol))
    app.register(WatchdogService(protocol))
    app.register(DeviceInformationProvider(protocol))

    try:
        await protocol.open()
        yield app
    finally:
        await protocol.close()
