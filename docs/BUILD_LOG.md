# Build log: a SiLA 2 connector for the IKA MATRIX Orbital Delta Plus

*Written while building, on 21 October 2026 (day two of the Device Integration Hackathon). First person,
in the order things actually happened. Nothing here was generated after the fact.*

How to read the tags:

| Tag | Meaning |
| --- | --- |
| **[TEMPLATE]** | Produced by the UniteLabs Connector Factory. I did not write it. |
| **[DRIVER]** | Learned from reading `heingroup/ika` (the existing Python driver). |
| **[MANUAL]** | Taken from the IKA operating instructions for the MATRIX Orbital Delta Plus. |
| **[MY CALL]** | My own understanding or design decision. Challenge these first. |
| **[VERIFY ON HARDWARE]** | Something I could not check without the instrument. Listed again in section 9. |

---

## 0. Starting point

Goal: wrap the Hein group's `ika` thermoshaker driver as a SiLA 2 connector with the UniteLabs CDK, in
a way that could be published to the Acceleration Consortium's `sila2-connectors` index.

Constraints I set myself from the hackathon material:

- Follow the CDK conventions the reviewers enforce (`AGENTS.md` and `BEST_PRACTICES.md` from the
  template, and the review checklist at docs.unitelabs.io). I read both in full before writing code.
- Simulation mode must work without the instrument, and the SiLA layer must run the same code path in
  simulation and real mode.
- Do not commit anything (requested). The repository has a `.git` with no commits.

The instrument itself was not connected to this Mac during the build (`ls /dev/tty.*` showed only the
debug console), so every run below is in simulation mode. Section 8 is the recipe for the real thing.

---

## 1. Understanding the existing driver [DRIVER]

```bash
git clone https://gitlab.com/heingroup/ika
find ika -type f | sort
cat ika/README.md ika/setup.py ika/ika/abc.py ika/ika/errors.py
cat -n ika/ika/thermoshaker.py
git log --format='%h %ad %an %s' --date=short -- ika/thermoshaker.py ika/abc.py
curl -s https://pypi.org/pypi/ika/json | python3 -c "..."   # is it on PyPI? yes: ika 2.0.3
```

What I took from it, file by file:

**`ika/abc.py`, class `IKADevice`.** The base class for every IKA product in the package.

- Opens `serial.Serial(port, 9600, 7, 'E', 1)`: 9600 baud, 7 data bits, even parity, 1 stop bit. No
  read timeout is passed, so a silent device blocks a read forever. I noted this as something a
  long-running server cannot live with.
- `_send` appends CR LF, writes, then sleeps 100 ms. `_send_and_receive` writes and then reads until
  `\r`. Because the device answers with CR LF, the `\n` is left in the buffer and is swallowed by the
  next read. Harmless for the driver (it strips whitespace), but my simulator has to reproduce it
  exactly or the parsing changes.
- `dummy=True` skips the serial port entirely and makes every request return `None`. That is a unit-test
  stub, not a simulation; I could not build simulation mode on it.
- There is a `threading.Lock` around requests, so the driver is thread safe but blocking. For asyncio I
  decided to run every driver call in a worker thread and serialise them with an `asyncio.Lock`.

**`ika/thermoshaker.py`.** Two classes.

- `ThermoshakerProtocol` is a plain namespace of NAMUR command strings with a docstring copied from the
  manual: `IN_PV_2` / `IN_PV_4` (actual temperature / speed), `IN_SP_2` / `IN_SP_4` (set points),
  `OUT_SP_2 xxx` / `OUT_SP_4 xxx`, `OUT_SP_12@n` (watchdog safety temperature), `OUT_WD1@n` /
  `OUT_WD2@n`, `RESET`, `START_2` / `STOP_2` (tempering), `START_4` / `STOP_4` (motor), `IN_VERSION`,
  `IN_SOFTWARE_ID`. I reuse this class as the single source of command strings in my simulator, so the
  connector and the driver can never disagree about spelling.
- `Thermoshaker` exposes one method per command: `temperature()`, `target_temperature()`,
  `set_target_temperature()`, `speed()`, `target_speed()`, `set_target_speed()`, `start_heating()`,
  `stop_heating()`, `start_shaking()`, `stop_shaking()`, `software_version()`,
  `software_id_and_version()`, `set_watchdog_safety_temperature()`, `start_watchdog_mode_1/2(t)` (with a
  20 to 1500 s range check) and `switch_to_normal_operation_mode()`.
- Its `_send_and_receive` parses replies with a three-step fallback: try `float(reply.split()[1])`, then
  `float(reply.split()[0])`, else return the string. The comment says the thermoshaker answers
  value queries as `<command> <value>`. The other drivers in the same package (magnetic stirrer,
  overhead stirrer, chiller) use `split()[0]`, which tells me the author observed the thermoshaker
  answering differently from the other IKA devices. I trust this because the README lists the MATRIX
  Orbital Delta Plus as tested, and because a wrong index would have returned nonsense in their lab.
  My simulator therefore answers `IN_PV_4 500`, not `500 4`. **[VERIFY ON HARDWARE]**
- Side effect of that parser: an empty reply raises `IndexError` out of the driver (the `except` only
  catches `ValueError`). I map that to a `NoResponse` error in the protocol layer.
- The watchdog docstring says mode 2 changes the temperature set point to the safety value. The manual
  says mode 2 changes *both* temperature and speed set points, and there is a second command
  `OUT_SP_42@n` for the safety speed that the driver does not have. I added it (section 5).

**`README.md`.** "Package not compatible with Mac OS." pyserial itself runs fine on macOS, so I read this
as the IKA USB driver and `COMx` port naming being Windows-only in their setup. **[MY CALL]** It does not
affect the connector code, but it means real mode will most likely be exercised on the lab's Windows PC.

Version check: the repository is at v2.0.3 and PyPI has the same version, so I depend on `ika~=2.0`
instead of a git URL.

---

## 2. Finding the ground truth: the manual [MANUAL]

`AGENTS.md` is explicit: the vendor's protocol documentation is ground truth, third-party drivers are a
cross-check. The IKA product page returned 403 to a plain fetch, so I searched for mirrors and found the
English operating instructions hosted by a distributor (Imlab). I pulled the text out with a small
Swift/PDFKit script because `pdftotext` is not installed here.

What the manual adds to what the driver already told me:

- RS 232 section: 9600 bit/s, 1 start bit, 7 data bits, even parity, 1 stop bit, no flow control.
  Commands in capitals, separated by spaces, terminated with CR LF, max 80 characters, decimal point is
  `.`. The device only ever speaks when asked ("even fault indications cannot be sent spontaneously").
  That last sentence shaped the design: there is no event channel, so every observable property is a
  poll.
- The command table matches the driver's constants exactly, plus `OUT_SP_42@n` (WD-safety speed).
- Watchdog semantics: mode 1 switches tempering and mixing off and shows Error 2; mode 2 switches the
  set points to the safety values and shows Error 2. `RESET` returns to normal operation. The watchdog
  command itself has to be re-sent within the watchdog time.
- Technical data: speed range 0 to 3000 rpm, adjustable minimum 300 rpm, 10 rpm steps, deviation
  ±30 rpm; temperature setting 1 to 100 °C with 1 K setting resolution and 0.1 K display resolution;
  heating 6 K/min, cooling 0.8 K/min, working temperature down to room temperature minus 15 K.

The manual does not print example replies, so the reply format stays a driver observation.

---

## 3. Toolchain and scaffold

Checks first:

```bash
which uv uvx cruft pipx; uv python list --only-installed
```

uv 0.11 was already installed with Pythons 3.10 to 3.14; `cruft` and `pipx` were not. The CDK needs
Python 3.10+, the system Python is 3.9, so I pinned uv to 3.12 for the scaffold step.

The Connector Factory prompts interactively, which does not work in my setting, so I read its
`cookiecutter.json` to learn the variable names and answered them non-interactively:

```bash
UV_PYTHON=3.12 uvx cruft create --no-input --extra-context '{
  "connector_name": "IKA Matrix Orbital",
  "project_description": "SiLA 2 connector for the IKA MATRIX Orbital Delta Plus thermoshaker, wrapping the heingroup ika Python driver.",
  "author_full_name": "Ivory Zhang",
  "author_email": "ubc.hein.lab@gmail.com",
  "project_repo": "https://gitlab.com/heingroup/sila2-ika-matrix-orbital",
  "communication_type": "none",
  "env": "uv"
}' https://gitlab.com/unitelabs/cdk/connector-factory.git
```

Two answers deserve a word:

- **`communication_type: none`** **[MY CALL]**. The alternative, `serial`, would add UniteLabs' Omnibus
  (`unitelabs-bus`) and generate an `io/protocol.py` that speaks bytes over Omnibus. We already have a
  working driver on pyserial, and the whole point was to reuse it. "none" gives the clean skeleton
  (config, `create_app`, tests, CI, Dockerfile) and I write `io/` myself around the `ika` package.
  Omnibus also comes from UniteLabs' GitLab package index rather than PyPI, which is one more thing to
  go wrong on a lab PC.
- **`connector_name: IKA Matrix Orbital`**. The rules want `<Brand> <Model>`, hyphen-case project name,
  snake_case package name. The template derived `ika-matrix-orbital` and `unitelabs.ika_matrix_orbital`
  from it. The AC index wants the GitHub repository named `sila2-ika-matrix-orbital`; the folder name
  here does not have to match that.

The scaffold took seven seconds. The post-generation hook created `.venv`, ran `uv lock`, `uv sync
--all-extras`, formatted with ruff and initialised an empty git repository. Everything in the tree at
that moment is **[TEMPLATE]**: `pyproject.toml`, `README.md`, `AGENTS.md`, `BEST_PRACTICES.md`,
`Dockerfile`, `docker-compose.yml`, CI and pre-commit configs, `.vscode/`, `src/.../__init__.py`
(a `create_app` registering only `LockController`), `src/.../__main__.py`, `src/.../config.py` (with
`type="Example"`), `tests/test_version.py`, an empty `tests/conftest.py`.

Then the driver:

```bash
uv add "ika~=2.0"          # pulls ika 2.0.3 and pyserial 3.5
```

Two template-level surprises, neither mine to fix:

- `uv run config show` crashes in CDK 0.16.0 with the template's own `config.py`
  (`InvalidSchemaFieldError: version is not a valid field`). `config create` and `connector start`
  work. Worth a message in `#sila_python_unitelabs`.
- `connector start -vvv`, which the generated README recommends, prints a deprecation warning: log
  levels now live in the `logging` key of `config.json`.

I also added `config.json`, `config.yaml` and `logs/` to `.gitignore`; the template did not, and the
rules say never to commit `config.json`.

---

## 4. Designing the interface before writing code [MY CALL]

I wrote the interface on paper first, as the server slide deck recommends, by asking what an
orchestrator (ivoryOS, Prefect, GroundControl) would want from a thermoshaker rather than what the
NAMUR table offers.

**Features and why they are split this way** (rule: one feature per concern, role suffix):

| Feature | Role | Category | Endpoints |
| --- | --- | --- | --- |
| `ShakerController` | controls the motor | `shaking` | `Speed` (observable), `TargetSpeed` (observable), `Start(TargetSpeed)`, `Stop` |
| `TemperatureController` | controls tempering | `temperature` | `Temperature` (observable), `TargetTemperature` (observable), `Start(TargetTemperature)`, `Stop` |
| `WatchdogService` | device setting, not normal operation | `safety` | `State`, `Start(Mode, Timeout)`, `Stop`, `SetSafetyTemperature`, `SetSafetySpeed` |
| `DeviceInformationProvider` | read-only | `information` | `SoftwareVersion`, `SoftwareIdentifier` |
| `SimulationController` | SiLA core | `core` (org.silastandard) | `SimulationMode`, `StartSimulationMode`, `StartRealMode` |
| `LockController` | SiLA core, from the template | `core` | as standard |

Decisions worth defending:

1. **`Start(TargetSpeed)` instead of `SetTargetSpeed` + `Start`.** The best-practice rule
   `op-expose-stateless-api` uses almost this exact example ("offer a single `start_incubation` that
   takes the target"). It also removes a whole class of bugs where a client starts the motor at
   whatever set point the last user left on the front panel. Calling `Start` again while running just
   changes the set point; the device accepts `OUT_SP_4` at any time.
2. **Start and Stop are unobservable commands.** `op-indefinite-duration-start-stop-pair` says an action
   with no natural end is a start/stop pair of unobservable commands, and its example is literally a
   shaker. The alternative, an observable `Start` that completes when the speed settles, would be
   nicer for the door-style demo but worse for a heater that takes twenty minutes to reach 60 °C.
3. **All four measured and set values are observable properties.** They change (the set points can be
   changed from the front panel too), and the rule is "observable if the value changes". Each one is a
   `Publisher` that polls the driver at 1 s (actual values) or 2 s (set points). With a 100 ms sleep per
   command inside the driver this is comfortably within what the line can do.
4. **Typed values.** `Speed`/`TargetSpeed` are integers in rpm (the device works in 10 rpm steps and
   reports whole rpm); temperatures are floats in °C. Constraints come from the technical data:
   speed 0 to 3000, temperature 1 to 100. Units are declared once in `io/units.py` and show up in the
   feature definition, so GroundControl shows "rpm" and "°C" without anyone configuring it.
5. **Speed minimum is 0, not 300.** The manual's "adjustable minimum 300 rpm" describes the front
   panel. The Hein group README example sets speed 0 while running, so the firmware accepts it. What the
   firmware does with 150 I do not know; the docstring says so. **[VERIFY ON HARDWARE]**
6. **The watchdog is a feature, not an internal detail.** A heater left running unattended is the one
   real safety story this device has, and the NAMUR watchdog is exactly the mechanism for it. The
   connector feeds the watchdog at half the timeout for as long as it runs; if the PC dies, the device
   falls back on its own. On purpose, closing the connector does *not* send `RESET`: an intentional
   shutdown should not disarm the protection that is about to become useful. The device cannot be asked
   whether the watchdog is armed, so `State` reflects what this server did, and its docstring says so.
7. **Names.** Vendor words were normalised: "tempering" became temperature control, "motor" became the
   shaker, `IN_SOFTWARE_ID` became `SoftwareIdentifier` (no abbreviations). Inside `io/` the method names
   follow the manual (`start_tempering`, `start_motor`, `read_actual_speed`) so a reader can trace the
   code back to the command table.
8. **Originator `com.gitlab.heingroup`.** Reverse domain of gitlab.com/heingroup. Change it in
   `constants.py` if the group prefers a real domain (one constant, one place).
9. **Server type `Thermoshaker`, vendor URL gitlab.com/heingroup.** The template rules say the vendor
   is UniteLabs; for a connector written and published by the Hein group I think the honest value is
   the group. Easy to flip.

What I deliberately left out: an `IsShaking` property (no NAMUR query exists and I will not pretend
the last command proves the state), the timer/program modes (not in the serial command set), and a
`Connect` command (the connector opens the port itself at start-up, as the rules require).

---

## 5. Implementation, file by file

Layout (the canonical one from `AGENTS.md`, plus `constants.py` at the package root):

```text
src/unitelabs/ika_matrix_orbital/
  __init__.py            create_app: builds the protocol, registers six features
  __main__.py            [TEMPLATE] untouched
  config.py              IkaMatrixOrbitalConfig + SimulatedDeviceConfig
  constants.py           limits from the manual, serial parameters, originator
  features/<name>/       one thin SiLA feature per folder
  io/errors.py           four exceptions a caller can react to
  io/units.py            rpm, °C, s
  io/simulation.py       SimulatedThermoshaker: a fake serial port speaking NAMUR
  io/protocol.py         MatrixOrbitalProtocol: async layer over the ika driver
```

**`io/simulation.py`.** The key choice: simulate at the *byte* level, not at the method level. The
class looks like `serial.Serial` (`write`, `read_until`, `close`, `is_open`, `port`) and answers NAMUR
lines, so the real driver's parsing runs in simulation too. If the reply format assumption in section 1
is wrong, the fix is one place and the tests will tell me. The model inside is deliberately small:
temperature moves towards the set point at the manual's 6 K/min up and 0.8 K/min down while tempering
is on, and drifts to ambient at 0.5 K/min when off (my number); speed ramps at 500 rpm/s (my number)
towards the set point when the motor runs and towards zero when it does not. Set points are clamped to
the device limits. The watchdog is modelled too: only `OUT_WDx@n` resets its timer (the manual says
"this command" must be repeated), and on expiry mode 1 switches everything off while mode 2 jumps to the
safety values, both setting Error 2 until `RESET`. Time comes from an injectable clock so tests can
advance it by hand instead of sleeping.

**`io/protocol.py`.** Three parts.

- `_Driver(ika.thermoshaker.Thermoshaker)`: the one place I reach into the driver's internals. The
  base class either opens its own `Serial` without a timeout or (dummy) opens nothing, so I construct
  it in dummy mode and install my own transport the way the base class would have (`_ser`, `_lock`,
  `_dummy = False`). It is three private attributes of a package the group owns; I would rather send
  a small merge request upstream (accept a ready `Serial` or a factory in `IKADevice.__init__`) than
  keep this forever, and said so in the docstring. The subclass also adds `set_watchdog_safety_speed`
  for the manual-only `OUT_SP_42@n`.
- `open_serial_port(port)`: the real transport, built with the manual's parameters plus a 2 s read and
  write timeout so a dead device produces an error instead of a hang.
- `MatrixOrbitalProtocol`: holds two transport factories (simulated and real), opens one of them,
  verifies the device answers `IN_VERSION` (a read, so opening never moves or heats anything, as rule
  `io-no-movement-on-transport-open` demands), and exposes one `async` method per command. Every call
  goes through `_execute`: take the asyncio lock, run the blocking driver call in a thread, map
  failures (`IndexError` on empty replies to `NoResponse`, serial errors to `DeviceUnreachable`,
  `IKAError` to `UnexpectedResponse`). Replies are typed here (`float`, `int`, `str`), never passed
  through raw. Mode switching lives here as well: `start_real_mode` closes the simulator, opens the port,
  and on any failure reopens the simulator before re-raising, so the server is never left without a
  transport. The watchdog feed is an asyncio task that re-sends the arm command every `timeout / 2`.

**`features/`.** Each feature is a dozen lines of decorators, type hints and docstrings calling the
protocol. The docstrings matter more than the code: the CDK turns them into the feature description a
client reads, so I wrote them for an automation user, not for a Python developer. One thing I only
learned by running it: the CDK serialises enum members as lower-case words, so the `Mode` parameter of
`WatchdogService.Start` is sent as `"switch off"` or `"safety values"`, not `SWITCH_OFF`. I adjusted the
docstrings and tests to the on-wire strings.

**`config.py`.** `simulation_mode` (default true, as the rules require), `serial_port` (None by default,
with Windows and macOS examples in the field docstring, because that docstring becomes the schema
description), and a nested `simulated_device` section for the simulator's four numbers. The
`__post_init__` converts the nested dict that comes back from `config.json` into the dataclass, calling
the base class first as `AGENTS.md` says.

**`__init__.py`.** `create_app` builds the protocol from the config (two `functools.partial` factories),
registers `LockController`, `SimulationController`, the four device features, opens the protocol before
`yield app` and closes it in `finally`. If `simulation_mode` is false and the port is missing or silent,
start-up fails loudly with the `DeviceUnreachable`/`NoResponse` message rather than quietly falling back;
an operator who asked for real mode should hear that it did not happen. **[MY CALL]**

Linting throughout:

```bash
uv run ruff format src/ && uv run ruff check src/ --fix
```

The only rule I kept tripping was D401 (property docstrings must start with an imperative verb), so
property docstrings read "Subscribe to ..." / "Get ...", which is also how the CDK's own examples read.

---

## 6. Tests

```bash
uv run pytest -q          # 35 passed in 7.4 s
```

`tests/` mirrors the package. What each file proves:

- `tests/io/test_simulation.py`: the bytes. Sending `IN_PV_4\r\n` the way the driver does yields
  `IN_PV_4 500\r\n`; set points clamp; speed ramps and decays; tempering heats 6 K in the first minute;
  watchdog mode 1 switches off after the timeout only if not fed, `RESET` clears it; mode 2 falls back
  to the safety values; partial writes are reassembled into one line.
- `tests/io/test_protocol.py`: typed results, `NotConnected` before `open`, round trips for shaking and
  tempering with the exact command sequence asserted (`OUT_SP_4 800` then `START_4`), watchdog feed at
  half the timeout, safety values reaching the device, an empty reply becoming `NoResponse`, and all
  three mode-switch paths (no port configured, port unreachable, port works).
- `tests/features/*`: each feature attaches, exposes exactly the intended identifiers, carries the
  intended constraints and units, and drives the protocol. One test streams `Speed` through the real
  `Publisher` and reads a value.
- `tests/test_create_app.py`: `create_app` in default config registers all features.

One bug of my own on the way: a test monkeypatched `asyncio.sleep` on the module object the protocol
imports, which is the global `asyncio` module, so the test's own `await asyncio.sleep(0)` never
returned and the whole run hung. I replaced that with a tiny module-level `_sleep` seam in
`protocol.py` and patched that instead. Also, the CDK keys command parameters by the Python argument
name (`parameters["target_speed"]`), not the SiLA identifier; and constraint values come back wrapped
(`MinimalInclusive(value=Integer(value=0))`).

---

## 7. Running it

Start, in simulation (the default):

```bash
uv run config create                 # writes config.json (gitignored); I set port 50060 and hostname 127.0.0.1
uv run connector start -vvv
```

Server log (trimmed):

```text
Starting application
Connected to thermoshaker      port=simulated simulation_mode=True software=1.0.0
Starting Server...
Server bound to '127.0.0.1:50060'.
Registering service 'IKA Matrix Orbital' (64478b2c-...)      <- mDNS discovery, visible to GroundControl
```

Then a plain SiLA client in a second terminal, the way an orchestrator would talk to it. The CDK pins
`unitelabs-sila` 0.11, whose API is the "unopinionated" one from the hackathon's client guide
(`client.load_feature(...)`, `feature.properties["Speed"].read()`, `feature.commands["Start"].execute({...})`);
the dotted namespace API from the slides needs 0.12, so the demo uses the mappings.

```bash
uv run python scripts/demo_client.py
```

Output of the full run:

```text
Server name:       IKA Matrix Orbital
Features:
    com.gitlab.heingroup/information/DeviceInformationProvider/v1
    com.gitlab.heingroup/safety/WatchdogService/v1
    com.gitlab.heingroup/shaking/ShakerController/v1
    com.gitlab.heingroup/temperature/TemperatureController/v1
    org.silastandard/core/ConnectionConfigurationService/v1
    org.silastandard/core/LockController/v2
    org.silastandard/core/SiLAService/v1
    org.silastandard/core/SimulationController/v1
Simulation mode:   True
Firmware version:  1.0.0

-- arm the watchdog so an unattended run fails safe
Watchdog state:    safety values

-- start shaking at 1000 rpm and heating to 37 °C
Target speed:      1000
Target temp:       37.0

-- follow the speed ramp; the subscription only delivers changed values
   Speed: 270          (first run; the second run started with the motor already at 1000)
   Speed: 770
   Speed: 1000

-- the constraint check rejects an out-of-range set point
   rejected: ValidationError - Value '5000' must be less than or equal to the maximal inclusive limit of '3000'.

-- stop everything
Watchdog state:    inactive
Temperature now:   26.9
```

Two things I learned from this run rather than from the docs: a SiLA subscription only delivers
*changed* values, so once the speed settled at 1000 the stream went quiet (my first version of the demo
waited for a fourth value and timed out), and when the client cancels a subscription the server logs an
ugly `RuntimeError: async generator raised StopAsyncIteration` from inside the `sila` framework
(`sila/server/observable_property.py`, `subscribe_rpc_handler`). The
client had its value by then; it is log noise in the framework, not in this connector, but worth knowing
before someone panics at the log.

Finally I pulled the feature definitions the server generates from the Python code, because that XML is
the artefact every non-Python SiLA client works from:

```bash
uv run python scripts/export_feature_definitions.py     # -> docs/features/*.sila.xml
```

`docs/features/ShakerController.sila.xml` shows `Originator="com.gitlab.heingroup" Category="shaking"`,
the `Start` command with its `TargetSpeed` parameter constrained to 0..3000 with the `rpm` unit, and the
docstrings as descriptions. I never wrote a line of XML.

---

## 8. Running against the real instrument (not done here)

On the lab PC that has the IKA USB driver and the device on, say, `COM8`:

```bash
uv sync --all-extras
uv run config create
```

Edit `config.json`: `"serial_port": "COM8"`, and either `"simulation_mode": false` or leave simulation
on and switch at runtime with `SimulationController.StartRealMode` (GroundControl can do that with a
click). Then `uv run connector start`. The first thing the connector does is `IN_VERSION`; the log line
`Connected to thermoshaker ... software=<version>` is the proof the line works. Then, in this order:

1. Read `DeviceInformationProvider.SoftwareVersion` and `SoftwareIdentifier`: confirms the two string
   replies parse.
2. Read `ShakerController.Speed` and `TemperatureController.Temperature` with the device idle: confirms
   the `<command> <value>` reply format assumption. If these come back as `4.0` and `2.0`, the device
   answers `<value> <parameter>` and the parser index in the driver is the culprit.
3. `TemperatureController.Start(TargetTemperature=30)` and watch `Temperature`; then `Stop`.
4. `ShakerController.Start(TargetSpeed=500)` with an empty platform, watch `Speed`, then `Stop`.
5. `WatchdogService.Start(Mode="switch off", Timeout=30)`, then kill the connector process and watch
   the device show Error 2 after about 30 s and stop. `uv run connector start` again and
   `WatchdogService.Stop` clears it.

---

## 9. Open questions for the instrument [VERIFY ON HARDWARE]

1. Reply format of value queries (`IN_PV_4 500` vs `500 4` vs `500`). The simulator and driver assume
   the first.
2. Does the firmware accept, clamp or reject speed set points between 1 and 299 rpm? The constraint
   currently allows 0..3000.
3. Does `START_4` while already running, or `STOP_4` while stopped, return an error? I assumed both are
   harmless no-ops (idempotent), as NAMUR devices usually are.
4. Does the device accept commands while showing Error 2, and does `RESET` alone clear it?
5. Is the temperature over the serial line always in °C even when the front panel is set to °F?
6. What exactly do `IN_VERSION` and `IN_SOFTWARE_ID` return on this unit? The simulator answers
   `1.0.0` and `1;1.0.0` following the driver's comment on the formats.
7. The "not compatible with macOS" remark in the driver README: whether the USB serial port enumerates
   on macOS at all (`/dev/tty.usbserial-*`), which would make this Mac usable for real-mode testing.

---

## 10. Publishing checklist (for after your review)

- Pick a licence, and do it knowingly: the `ika` driver is **GPL-3.0** (I checked its `LICENSE` file after
  first assuming MIT; this line is the corrected version). A connector that imports a GPL-3 library and
  is distributed to others is, in the usual reading, a derivative work, so the straightforward options
  are to publish this connector under GPL-3.0 as well, or to relicense `ika` (the group owns it) under
  something permissive such as MIT or Apache-2.0 before publishing. The template left a licence badge but
  no `LICENSE` file, so nothing is decided yet. **[MY CALL]** on the legal reading; check with whoever
  handles licensing for the group.
  *Update after review:* the group chose GPL-3.0-or-later. `LICENSE` holds the licence text and
  `pyproject.toml` carries `license = "GPL-3.0-or-later"`. Done.
- Create the GitHub repository `sila2-ika-matrix-orbital` (AC naming: `sila2-<manufacturer>-<model>`),
  add the topic `sila2-connector`, and open a pull request adding the organisation to `orgs.txt` in
  `AccelerationConsortium/sila2-connectors`.
- The AC layout also expects `workflows/` (a Prefect flow calling the connector) and a `deploy.sh`.
  Neither exists yet; `scripts/demo_client.py` is the seed for the former.
- Update `project_repo` in `.cruft.json`/`pyproject.toml` if the repository ends up on GitHub rather
  than the GitLab URL I guessed, and decide on the originator (section 4, item 8).
  *Update after review:* published to `github.com/ivoryzh/sila2-ika-matrix-orbital`; URLs updated, a GitHub
  Actions workflow runs ruff and pytest on every push.
- Optional but cheap: a GroundControl screenshot of the feature list for the README and the Day 3 update.

---

## 11. Who wrote what

| Path | Origin |
| --- | --- |
| `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `.gitlab-ci.yml`, `.pre-commit-config.yaml`, `.editorconfig`, `.vscode/`, `.gitlab/`, `AGENTS.md`, `BEST_PRACTICES.md`, `CHANGELOG.md`, `src/.../__main__.py`, `tests/test_version.py` | **[TEMPLATE]**, untouched (`pyproject.toml` gained the `ika` dependency through `uv add`) |
| `.gitignore` | **[TEMPLATE]** plus three lines I appended (`config.*`, `logs/`) |
| `README.md` | **[TEMPLATE]** skeleton, rewritten by me for this connector |
| `src/.../__init__.py`, `src/.../config.py` | **[TEMPLATE]** skeleton, rewritten by me |
| `src/.../constants.py`, `src/.../io/*`, `src/.../features/*`, `tests/*` (except `test_version.py`), `scripts/*`, `docs/*` | written by me |
| `docs/features/*.sila.xml` | generated by the running connector from my Python code |

Nothing in this repository was produced by the SiLA Feature Generator or any other code generator
beyond the Connector Factory scaffold and the CDK's own feature-definition rendering.
