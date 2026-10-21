import pytest

from unitelabs.cdk.features.core.simulation_controller import StartRealModeFailed

from unitelabs.ika_matrix_orbital.features import SimulationController


async def test_reports_simulation_mode(protocol):
    feature = SimulationController(protocol)
    feature.attach()
    assert await feature.simulation_mode() is True
    assert set(feature.commands) == {"StartSimulationMode", "StartRealMode"}
    assert set(feature.properties) == {"SimulationMode"}


async def test_real_mode_without_device_is_refused_and_stays_simulated(protocol):
    feature = SimulationController(protocol)
    feature.attach()
    with pytest.raises(StartRealModeFailed):
        await feature.start_real_mode()
    assert await feature.simulation_mode() is True
    assert protocol.is_open
