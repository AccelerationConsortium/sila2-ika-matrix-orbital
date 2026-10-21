from unitelabs.ika_matrix_orbital import create_app
from unitelabs.ika_matrix_orbital.config import IkaMatrixOrbitalConfig


async def test_create_app_registers_all_features_in_simulation():
    config = IkaMatrixOrbitalConfig()
    assert config.simulation_mode is True
    assert config.sila_server.type == "Thermoshaker"

    generator = create_app(config)
    app = await anext(generator)
    try:
        identifiers = {feature.identifier for feature in app.sila_server.features.values()}
        assert {
            "SiLAService",
            "LockController",
            "SimulationController",
            "ShakerController",
            "TemperatureController",
            "WatchdogService",
            "DeviceInformationProvider",
        } <= identifiers
    finally:
        with __import__("contextlib").suppress(StopAsyncIteration):
            await anext(generator)
