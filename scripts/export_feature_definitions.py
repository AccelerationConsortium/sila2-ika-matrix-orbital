"""
Save the SiLA feature definitions (FDL XML) the running connector generates from the Python code.

Start the connector first, then run `uv run python scripts/export_feature_definitions.py`.
The files land in `docs/features/` and are exactly what any SiLA client downloads when it connects.
"""

import argparse
import asyncio
import pathlib

from sila.client import Client, ClientConfig


async def main(hostname: str, port: int, target: pathlib.Path) -> None:
    config = ClientConfig(hostname=hostname, port=port, tls=False, default_timeout=5000)
    client = Client(config)
    await client.open(sync=False)
    try:
        for identifier in sorted(await client.get_implemented_features()):
            definition = await client.get_feature_definition(identifier)
            path = target / f"{identifier.split('/')[-2]}.sila.xml"
            path.write_text(definition if isinstance(definition, str) else str(definition))
            print(f"{identifier}  ->  {path}")
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=50060)
    parser.add_argument("--target", type=pathlib.Path, default=pathlib.Path("docs/features"))
    args = parser.parse_args()
    args.target.mkdir(parents=True, exist_ok=True)
    asyncio.run(asyncio.wait_for(main(args.hostname, args.port, args.target), timeout=60))
