# IKA Matrix Orbital

SiLA 2 connector for the **IKA MATRIX Orbital Delta Plus** thermoshaker, built with the
[UniteLabs CDK](https://docs.unitelabs.io/connector-development/) on top of the Hein group's
[`ika`](https://gitlab.com/heingroup/ika) Python driver.

It turns the instrument's NAMUR serial command set into a SiLA server that any SiLA client
(GroundControl, a Python or JavaScript client, an orchestrator) can discover and drive. It runs without
the instrument in simulation mode, which is the default.

> Status: built during the Device Integration Hackathon (October 2026). Tested in simulation; real-mode
> assumptions that still need the instrument are listed in [docs/BUILD_LOG.md](docs/BUILD_LOG.md),
> section 9. The build log also records every step and decision that led to this code.

## What the server exposes

| Feature | Endpoints | Notes |
| --- | --- | --- |
| **ShakerController** | `Speed`, `TargetSpeed` (observable, rpm) · `Start(TargetSpeed)` · `Stop` | 0 to 3000 rpm. `Start` sets the set point and starts the motor in one call. |
| **TemperatureController** | `Temperature`, `TargetTemperature` (observable, °C) · `Start(TargetTemperature)` · `Stop` | 1 to 100 °C. Heats and cools; follow `Temperature` to see when the set point is reached. |
| **WatchdogService** | `State` · `Start(Mode, Timeout)` · `Stop` · `SetSafetyTemperature` · `SetSafetySpeed` | Arms the device's own communication watchdog. `Mode` is `"switch off"` or `"safety values"`, `Timeout` 20 to 1500 s. The connector feeds it while it runs; if the PC dies, the device stops or falls back by itself. |
| **DeviceInformationProvider** | `SoftwareVersion`, `SoftwareIdentifier` | Firmware identification. |
| **SimulationController** | `SimulationMode` · `StartSimulationMode` · `StartRealMode` | Switch between the simulator and the configured serial port at runtime. |
| **LockController**, **SiLAService**, **ConnectionConfigurationService** | standard SiLA core features | Provided by the CDK. |

The generated feature definitions (the XML a SiLA client downloads) are in [`docs/features/`](docs/features/).

## Quick start (simulation)

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --all-extras
uv run config create          # writes config.json next to you; edit sila_server.port if you want a fixed port
uv run connector start
```

The log line `Connected to thermoshaker ... simulation_mode=True` means the server is up and
advertising itself on the local network. Open it in GroundControl, or drive it from Python:

```sh
uv run python scripts/demo_client.py --port <port from config.json>
```

The demo arms the watchdog, starts shaking and heating, follows the speed ramp, shows a rejected
out-of-range set point, and stops everything.

## Running with the instrument

1. Connect the thermoshaker over USB (Windows needs the IKA USB driver; the port appears as `COMx`).
2. In `config.json`, set `"serial_port": "COM8"` (or `/dev/tty.usbserial-...`) and either
   `"simulation_mode": false` or keep simulation on and call `SimulationController.StartRealMode` later.
3. `uv run connector start`. Start-up only sends a version query; nothing moves or heats until a client
   asks for it.

Serial parameters (9600 baud, 7 data bits, even parity, 1 stop bit, CR LF) come from the IKA manual and
are fixed in `constants.py`.

The `simulated_device` section of `config.json` tunes the simulator (ambient temperature, heating and
cooling rates, speed ramp).

## Development

```sh
uv sync --all-extras
uv run pytest                                      # 35 tests, no hardware needed
uv run ruff format src/ && uv run ruff check src/  # the conventions the CDK reviewers enforce
uv run connector dev                               # auto-reload on save
```

Project layout follows the CDK canon: `io/` talks to the device and knows nothing about SiLA
(`protocol.py` wraps the `ika` driver, `simulation.py` is a fake serial port that speaks NAMUR),
`features/` is the thin SiLA layer, `config.py` holds the configuration, `constants.py` the device limits.
`AGENTS.md` and `BEST_PRACTICES.md` are the UniteLabs rule books the template ships; read them before
changing the interface.

Useful scripts:

- `scripts/demo_client.py`: end-to-end client walkthrough against a running server.
- `scripts/export_feature_definitions.py`: dumps the feature definition XML into `docs/features/`.

## Publishing

Intended for the Acceleration Consortium's [sila2-connectors](https://github.com/AccelerationConsortium/sila2-connectors)
index: repository name `sila2-ika-matrix-orbital`, GitHub topic `sila2-connector`, then a pull request
adding the organisation to `orgs.txt`. See the checklist at the end of the build log.

## Licence

GPL-3.0-or-later, see [LICENSE](LICENSE). The same licence as the `ika` driver this connector depends on.

## Acknowledgements

The device communication is the Hein group's `ika` package by Veronica Lai and contributors. The
connector framework, template and conventions are UniteLabs' open-source CDK. Not affiliated with IKA.
