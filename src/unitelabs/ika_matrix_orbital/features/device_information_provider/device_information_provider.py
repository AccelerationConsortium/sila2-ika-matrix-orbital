from unitelabs.cdk import sila

from ...constants import ORIGINATOR
from ...io import MatrixOrbitalProtocol


class DeviceInformationProvider(sila.Feature):
    """Reports the software identification of the connected thermoshaker."""

    def __init__(self, protocol: MatrixOrbitalProtocol) -> None:
        super().__init__(originator=ORIGINATOR, category="information")
        self.protocol = protocol

    @sila.UnobservableProperty()
    async def get_software_version(self) -> str:
        """Get the firmware version reported by the device."""
        return await self.protocol.read_software_version()

    @sila.UnobservableProperty()
    async def get_software_identifier(self) -> str:
        """Get the software identification string reported by the device, which includes its version."""
        return await self.protocol.read_software_id()
