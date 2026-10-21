import typing_extensions as typing

from unitelabs.cdk.features.core.simulation_controller import (
    SimulationControllerBase,
    StartRealModeFailed,
    StartSimulationModeFailed,
)

from ...io import MatrixOrbitalProtocol


class SimulationController(SimulationControllerBase):
    """Switches the connector between the simulated thermoshaker and the real one on the configured serial port."""

    def __init__(self, protocol: MatrixOrbitalProtocol) -> None:
        super().__init__()
        self.protocol = protocol

    @typing.override
    async def start_simulation_mode(self) -> None:
        try:
            await self.protocol.start_simulation_mode()
        except Exception as error:
            raise StartSimulationModeFailed(str(error)) from error

    @typing.override
    async def start_real_mode(self) -> None:
        try:
            await self.protocol.start_real_mode()
        except Exception as error:
            msg = f"Staying in simulation mode: {error}"
            raise StartRealModeFailed(msg) from error

    @typing.override
    async def simulation_mode(self) -> bool:
        return self.protocol.simulation_mode
