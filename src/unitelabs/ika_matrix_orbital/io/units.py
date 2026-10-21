"""Unit constants shared by all features (rule `dt-unit-constants-in-io-units`)."""

from unitelabs.cdk import sila

RPM = sila.constraints.Unit(
    label="rpm",
    components=[sila.constraints.UnitComponent(sila.constraints.SIUnit.SECOND, -1)],
    factor=1 / 60,
)

CELSIUS = sila.constraints.Unit(
    label="°C",
    components=[sila.constraints.UnitComponent(sila.constraints.SIUnit.KELVIN)],
    offset=273.15,
)

SECOND = sila.constraints.Unit(
    label="s",
    components=[sila.constraints.UnitComponent(sila.constraints.SIUnit.SECOND)],
)
