import dataclasses
from importlib.metadata import version

from unitelabs.cdk import ConnectorBaseConfig, SiLAServerConfig
from unitelabs.cdk.config import Config

__version__ = version("unitelabs-ika-matrix-orbital")


@dataclasses.dataclass
class SimulatedDeviceConfig(Config):
    """How the simulated thermoshaker behaves while the connector runs in simulation mode."""

    ambient_temperature: float = 22.0
    """Room temperature in °C. The simulated sample holder drifts towards it while temperature control is off."""

    heating_rate: float = 6.0
    """Heating rate in K per minute while temperature control is on (6 K/min in the technical data)."""

    cooling_rate: float = 0.8
    """Cooling rate in K per minute while temperature control is on (0.8 K/min in the technical data)."""

    speed_ramp: float = 500.0
    """How fast the simulated platform changes speed, in rpm per second."""


@dataclasses.dataclass
class IkaMatrixOrbitalConfig(ConnectorBaseConfig):
    """Configuration for the IKA Matrix Orbital connector."""

    simulation_mode: bool = True
    """Start with a simulated thermoshaker instead of the real one. Switch at runtime with the SimulationController."""

    serial_port: str | None = None
    """Serial port of the thermoshaker, for example COM8 on Windows or /dev/tty.usbserial-1420 on macOS. Required for real mode."""  # noqa: E501

    simulated_device: SimulatedDeviceConfig = dataclasses.field(default_factory=SimulatedDeviceConfig)

    sila_server: SiLAServerConfig = dataclasses.field(
        default_factory=lambda: SiLAServerConfig(
            name="IKA Matrix Orbital",
            type="Thermoshaker",
            description=(
                """
                SiLA 2 connector for the IKA MATRIX Orbital Delta Plus thermoshaker, built on the
                heingroup ika Python driver. Controls shaking speed, sample temperature and the
                communication watchdog over the instrument's USB serial port.
                """
            ),
            version=str(__version__),
            vendor_url="https://gitlab.com/heingroup",
        )
    )

    def __post_init__(self):
        super().__post_init__()
        if isinstance(self.simulated_device, dict):
            self.simulated_device = SimulatedDeviceConfig(**self.simulated_device)
