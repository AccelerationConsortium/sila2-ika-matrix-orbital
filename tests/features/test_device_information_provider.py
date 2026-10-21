from unitelabs.ika_matrix_orbital.features import DeviceInformationProvider


async def test_reads_software_information(protocol):
    feature = DeviceInformationProvider(protocol)
    feature.attach()
    assert set(feature.properties) == {"SoftwareVersion", "SoftwareIdentifier"}
    assert await feature.get_software_version() == "1.0.0"
    assert await feature.get_software_identifier() == "1;1.0.0"
