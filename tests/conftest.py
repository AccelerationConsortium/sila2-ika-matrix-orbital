import pytest

from unitelabs.ika_matrix_orbital.io import MatrixOrbitalProtocol, SimulatedThermoshaker


class FakeClock:
    """A monotonic clock the tests move forward by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def device(clock: FakeClock) -> SimulatedThermoshaker:
    return SimulatedThermoshaker(ambient_temperature=22.0, clock=clock)


@pytest.fixture
async def protocol(device: SimulatedThermoshaker) -> MatrixOrbitalProtocol:
    protocol = MatrixOrbitalProtocol(simulated=lambda: device, real=None, simulation_mode=True)
    await protocol.open()
    yield protocol
    await protocol.close()
