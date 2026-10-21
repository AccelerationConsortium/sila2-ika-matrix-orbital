"""
Asynchronous protocol layer around the heingroup `ika` thermoshaker driver.

Method names follow the wording of the IKA manual's command table (rule `proj-protocol-layer-mirrors-vendor-docs`);
the SiLA vocabulary lives one layer up in `features/`.
"""

import asyncio
import collections.abc
import contextlib
import enum
import threading

import serial
from ika.errors import IKAError
from ika.thermoshaker import Thermoshaker

from unitelabs.cdk.logging import BoundLogger, get_logger

from ..constants import BAUDRATE, BYTESIZE, PARITY, READ_TIMEOUT, STOPBITS
from .errors import DeviceUnreachable, NoResponse, NotConnected, UnexpectedResponse

Transport = serial.Serial
"""Anything with `write`, `read_until`, `close` and `is_open`; `serial.Serial` or the simulator."""
TransportFactory = collections.abc.Callable[[], Transport]


class WatchdogMode(enum.Enum):
    """What the device does when the connector stops feeding the watchdog."""

    SWITCH_OFF = enum.auto()
    """Mode 1: temperature control and the motor are switched off, the display shows Error 2."""

    SAFETY_VALUES = enum.auto()
    """Mode 2: set points jump to the configured safety temperature and safety speed, the display shows Error 2."""


_WATCHDOG_COMMANDS = {WatchdogMode.SWITCH_OFF: "OUT_WD1@", WatchdogMode.SAFETY_VALUES: "OUT_WD2@"}
_sleep = asyncio.sleep
"""Seam for tests: the pause between two watchdog feeds."""
_SET_WATCHDOG_SAFETY_SPEED = "OUT_SP_42@"


def open_serial_port(port: str) -> serial.Serial:
    """
    Open `port` with the parameters from the manual's RS 232 section.

    Raises:
      DeviceUnreachable: If the port cannot be opened.
    """
    try:
        return serial.Serial(
            port,
            baudrate=BAUDRATE,
            bytesize=BYTESIZE,
            parity=PARITY,
            stopbits=STOPBITS,
            timeout=READ_TIMEOUT,
            write_timeout=READ_TIMEOUT,
        )
    except (serial.SerialException, OSError, ValueError) as error:
        msg = f"Could not open serial port {port!r}: {error}"
        raise DeviceUnreachable(msg) from error


class _Driver(Thermoshaker):
    """
    The heingroup driver with an injected transport instead of a port it opens itself.

    `ika.abc.IKADevice.__init__` either opens `serial.Serial(port, 9600, 7, 'E', 1)` or, with `dummy=True`,
    opens nothing and short-circuits every request. Neither suits a connector that needs a read timeout and a
    simulation mode, so this subclass constructs in dummy mode and then installs the transport the way the
    base class would have. The attribute names are those of `ika` 2.0.x; a change there surfaces here.
    """

    def __init__(self, transport: Transport) -> None:
        super().__init__(port=getattr(transport, "port", "injected"), dummy=True)
        self._dummy = False
        self._ser = transport
        self._lock = threading.Lock()

    def set_watchdog_safety_speed(self, value: int) -> float:
        """OUT_SP_42@n: set the WD-safety speed. Listed in the manual, missing from `ika` 2.0.3."""
        return self._send_and_receive(f"{_SET_WATCHDOG_SAFETY_SPEED}{value}")


class MatrixOrbitalProtocol:
    """
    Talks to one IKA MATRIX Orbital Delta Plus through either a real serial port or the simulator.

    Args:
      simulated: Factory for the simulated transport, used while `simulation_mode` is true.
      real: Factory for the real serial transport, or None when no serial port is configured.
      simulation_mode: Which transport `open` uses first.
    """

    def __init__(
        self, simulated: TransportFactory, real: TransportFactory | None, simulation_mode: bool = True
    ) -> None:
        self._simulated = simulated
        self._real = real
        self.simulation_mode = simulation_mode

        self._driver: _Driver | None = None
        self._lock = asyncio.Lock()
        self._watchdog_mode: WatchdogMode | None = None
        self._watchdog_task: asyncio.Task | None = None

    @property
    def logger(self) -> BoundLogger:
        """The connector logger."""
        return get_logger(__name__)

    @property
    def is_open(self) -> bool:
        """Whether a transport is open."""
        return self._driver is not None

    @property
    def watchdog_mode(self) -> WatchdogMode | None:
        """The watchdog mode this protocol is currently feeding, or None."""
        return self._watchdog_mode

    # -- lifecycle ----------------------------------------------------------------------------------------------

    async def open(self) -> None:
        """
        Open the transport for the current mode and check that the device answers.

        Opening never moves or heats anything: the only command sent is a software version query.

        Raises:
          DeviceUnreachable: If no serial port is configured for real mode or the port cannot be opened.
          NoResponse: If the device does not answer the version query.
        """
        if self._driver:
            return

        factory = self._simulated if self.simulation_mode else self._real
        if factory is None:
            msg = "No serial port configured. Set `serial_port` in the configuration or keep `simulation_mode` on."
            raise DeviceUnreachable(msg)

        transport = await asyncio.to_thread(factory)
        self._driver = _Driver(transport)
        try:
            version = await self.read_software_version()
        except Exception:
            await self.close()
            raise
        self.logger.info(
            "Connected to thermoshaker", simulation_mode=self.simulation_mode, port=transport.port, software=version
        )

    async def close(self) -> None:
        """Stop feeding the watchdog and close the transport. The device keeps its own watchdog state."""
        await self._stop_watchdog_feed()
        if driver := self._driver:
            self._driver = None
            with contextlib.suppress(Exception):
                await asyncio.to_thread(driver._ser.close)

    async def start_simulation_mode(self) -> None:
        """Switch to the simulated transport; a no-op when already simulating."""
        if self.simulation_mode and self.is_open:
            return
        await self.close()
        self.simulation_mode = True
        await self.open()

    async def start_real_mode(self) -> None:
        """
        Switch to the real serial transport; falls back to simulation if the device cannot be reached.

        Raises:
          DeviceUnreachable: If the port is not configured or cannot be opened. Simulation is running again.
          NoResponse: If the device does not answer. Simulation is running again.
        """
        if not self.simulation_mode and self.is_open:
            return
        await self.close()
        self.simulation_mode = False
        try:
            await self.open()
        except Exception:
            self.simulation_mode = True
            await self.open()
            raise

    # -- temperature (parameter 2 in the NAMUR table) ----------------------------------------------------------

    async def read_actual_temperature(self) -> float:
        """IN_PV_2: the measured temperature in °C."""
        return await self._query_float(lambda d: d.temperature(), "IN_PV_2")

    async def read_set_temperature(self) -> float:
        """IN_SP_2: the temperature set point in °C."""
        return await self._query_float(lambda d: d.target_temperature(), "IN_SP_2")

    async def set_temperature(self, value: float) -> None:
        """OUT_SP_2 xxx: set the temperature set point in °C. The device works in whole kelvin steps."""
        await self._execute(lambda d: d.set_target_temperature(value))

    async def start_tempering(self) -> None:
        """START_2: start the tempering (heating and cooling) function."""
        await self._execute(lambda d: d.start_heating())

    async def stop_tempering(self) -> None:
        """STOP_2: stop the tempering function."""
        await self._execute(lambda d: d.stop_heating())

    # -- motor (parameter 4 in the NAMUR table) ----------------------------------------------------------------

    async def read_actual_speed(self) -> int:
        """IN_PV_4: the measured shaking speed in rpm."""
        return round(await self._query_float(lambda d: d.speed(), "IN_PV_4"))

    async def read_set_speed(self) -> int:
        """IN_SP_4: the speed set point in rpm."""
        return round(await self._query_float(lambda d: d.target_speed(), "IN_SP_4"))

    async def set_speed(self, value: int) -> None:
        """OUT_SP_4 xxx: set the speed set point in rpm."""
        await self._execute(lambda d: d.set_target_speed(value))

    async def start_motor(self) -> None:
        """START_4: start the motor at the current speed set point."""
        await self._execute(lambda d: d.start_shaking())

    async def stop_motor(self) -> None:
        """STOP_4: stop the motor."""
        await self._execute(lambda d: d.stop_shaking())

    # -- software information ----------------------------------------------------------------------------------

    async def read_software_version(self) -> str:
        """IN_VERSION: the software version string."""
        return await self._query_str(lambda d: d.software_version(), "IN_VERSION")

    async def read_software_id(self) -> str:
        """IN_SOFTWARE_ID: the software id and version string."""
        return await self._query_str(lambda d: d.software_id_and_version(), "IN_SOFTWARE_ID")

    # -- watchdog ----------------------------------------------------------------------------------------------

    async def set_watchdog_safety_temperature(self, value: float) -> None:
        """OUT_SP_12@n: the temperature set point the device falls back to in watchdog mode 2."""
        await self._execute(lambda d: d.set_watchdog_safety_temperature(value))

    async def set_watchdog_safety_speed(self, value: int) -> None:
        """OUT_SP_42@n: the speed set point the device falls back to in watchdog mode 2."""
        await self._execute(lambda d: d.set_watchdog_safety_speed(value))

    async def start_watchdog(self, mode: WatchdogMode, seconds: int) -> None:
        """
        OUT_WD1@n or OUT_WD2@n: arm the watchdog and keep re-sending the command every `seconds / 2`.

        The device switches to its watchdog behaviour when the command is not repeated within `seconds`.
        Re-arming with a new mode or time replaces the running feed.
        """
        await self._stop_watchdog_feed()
        await self._feed_watchdog(mode, seconds)
        self._watchdog_mode = mode
        self._watchdog_task = asyncio.create_task(self._keep_feeding(mode, seconds))

    async def reset(self) -> None:
        """RESET: switch to normal operating mode, which disarms the watchdog and clears Error 2."""
        await self._stop_watchdog_feed()
        await self._execute(lambda d: d.switch_to_normal_operation_mode())

    async def _feed_watchdog(self, mode: WatchdogMode, seconds: int) -> None:
        command = _WATCHDOG_COMMANDS[mode]
        if mode is WatchdogMode.SWITCH_OFF:
            await self._execute(lambda d: d.start_watchdog_mode_1(seconds))
        else:
            await self._execute(lambda d: d.start_watchdog_mode_2(seconds))
        self.logger.debug("Fed watchdog", command=f"{command}{seconds}")

    async def _keep_feeding(self, mode: WatchdogMode, seconds: int) -> None:
        while True:
            await _sleep(seconds / 2)
            try:
                await self._feed_watchdog(mode, seconds)
            except Exception as error:  # noqa: BLE001
                self.logger.warning("Watchdog feed failed; the device will fall back on its own", error=str(error))

    async def _stop_watchdog_feed(self) -> None:
        self._watchdog_mode = None
        if task := self._watchdog_task:
            self._watchdog_task = None
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    # -- plumbing ----------------------------------------------------------------------------------------------

    async def _query_float(self, request: collections.abc.Callable[[_Driver], object], command: str) -> float:
        response = await self._execute(request)
        if isinstance(response, float):
            return response
        msg = f"{command} returned {response!r} instead of a number"
        raise UnexpectedResponse(msg)

    async def _query_str(self, request: collections.abc.Callable[[_Driver], object], command: str) -> str:
        response = await self._execute(request)
        if response is None or response == "":
            msg = f"{command} returned an empty reply"
            raise UnexpectedResponse(msg)
        return str(response).strip()

    async def _execute(self, request: collections.abc.Callable[[_Driver], object]) -> object:
        """Run one driver request in a worker thread, one at a time, and map driver failures to io errors."""
        driver = self._driver
        if driver is None:
            raise NotConnected
        async with self._lock:
            try:
                return await asyncio.to_thread(request, driver)
            except IndexError as error:
                # The driver indexes into the reply; an empty reply (read timeout) ends up here.
                msg = "Empty reply from the thermoshaker"
                raise NoResponse(msg) from error
            except (serial.SerialException, OSError) as error:
                raise DeviceUnreachable(str(error)) from error
            except IKAError as error:
                raise UnexpectedResponse(str(error)) from error
