"""
Drive the running connector from a plain SiLA client, the way an orchestrator would.

Start the connector first (`uv run connector start -vvv`), then run `uv run python scripts/demo_client.py`.
Uses the `unitelabs-sila` client library (0.11, the version the CDK pins) through its feature mappings:
`feature.properties["Name"].read()` / `.subscribe()` and `feature.commands["Name"].execute({...})`.
"""

import argparse
import asyncio

from sila.client import Client, ClientConfig

ORIGINATOR = "com.gitlab.heingroup"
SHAKER = f"{ORIGINATOR}/shaking/ShakerController/v1"
TEMPERATURE = f"{ORIGINATOR}/temperature/TemperatureController/v1"
WATCHDOG = f"{ORIGINATOR}/safety/WatchdogService/v1"
INFORMATION = f"{ORIGINATOR}/information/DeviceInformationProvider/v1"
SIMULATION = "org.silastandard/core/SimulationController/v1"


async def main(hostname: str, port: int) -> None:
    config = ClientConfig(hostname=hostname, port=port, tls=False, default_timeout=5000)
    client = Client(config)
    await client.open(sync=False)
    try:
        print("Server name:      ", await client.get_server_name())
        print("Features:")
        for identifier in sorted(await client.get_implemented_features()):
            print("   ", identifier)

        shaker = await client.load_feature(SHAKER)
        temperature = await client.load_feature(TEMPERATURE)
        watchdog = await client.load_feature(WATCHDOG)
        information = await client.load_feature(INFORMATION)
        simulation = await client.load_feature(SIMULATION)

        print("Simulation mode:  ", await simulation.properties["SimulationMode"].read())
        print("Firmware version: ", await information.properties["SoftwareVersion"].read())

        print("\n-- arm the watchdog so an unattended run fails safe")
        await watchdog.commands["SetSafetyTemperature"].execute({"SafetyTemperature": 20.0})
        await watchdog.commands["SetSafetySpeed"].execute({"SafetySpeed": 0})
        await watchdog.commands["Start"].execute({"Mode": "safety values", "Timeout": 60})
        print("Watchdog state:   ", await watchdog.properties["State"].read())

        print("\n-- start shaking at 1000 rpm and heating to 37 °C")
        await shaker.commands["Start"].execute({"TargetSpeed": 1000})
        await temperature.commands["Start"].execute({"TargetTemperature": 37.0})
        print("Target speed:     ", await shaker.properties["TargetSpeed"].read())
        print("Target temp:      ", await temperature.properties["TargetTemperature"].read())

        print("\n-- follow the speed ramp; the subscription only delivers changed values")
        stream = await shaker.properties["Speed"].subscribe()
        try:
            while True:
                try:
                    value = await asyncio.wait_for(anext(stream), timeout=4)
                except TimeoutError:
                    print("   (no change for 4 s: speed has settled)")
                    break
                print("   Speed:", value)
                if value >= 1000:
                    break
        finally:
            stream.close()

        print("\n-- the constraint check rejects an out-of-range set point")
        try:
            await shaker.commands["Start"].execute({"TargetSpeed": 5000})
        except Exception as error:  # noqa: BLE001
            print("   rejected:", type(error).__name__, "-", str(error).splitlines()[0][:140])

        print("\n-- stop everything")
        await shaker.commands["Stop"].execute({})
        await temperature.commands["Stop"].execute({})
        await watchdog.commands["Stop"].execute({})
        print("Watchdog state:   ", await watchdog.properties["State"].read())
        print("Temperature now:  ", await temperature.properties["Temperature"].read())
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=50060)
    args = parser.parse_args()
    asyncio.run(asyncio.wait_for(main(args.hostname, args.port), timeout=90))
