#!/usr/bin/env python3
"""Run the BHMS conformance suite (the Python runner, `bhms conformance`) against the TypeScript conformance device.

The runner's built-in `conformance-device` fixtures start the Python device. This wrapper swaps the fixture's command for
`node dist/src/testing/conformanceDevice.js`, so every flavour (stdio, ws, unix, principals) is served by this SDK with the
runner owning state directories, restarts, kills and policy files exactly as it does for the Python device:

    python3 scripts/conformance.py conformance conformance-device            # stdio: core, leases, events, programs, registry
    python3 scripts/conformance.py conformance conformance-device:principals # + authority
    python3 scripts/conformance.py conformance conformance-device:ws

Build first (`npm run build`). The runner is taken from the installed `bhms` or from `PYTHONPATH` (e.g. `sdk/python/src`).
All arguments are passed to the `bhms` command line.
"""
import sys
from pathlib import Path

DEVICE = Path(__file__).resolve().parent.parent / "dist" / "src" / "testing" / "conformanceDevice.js"


def main() -> int:
    from bhms.conformance import targets

    if not DEVICE.is_file():
        print(f"{DEVICE} is missing: run `npm run build` first", file=sys.stderr)
        return 2
    targets._device_command = lambda *extra: ["node", str(DEVICE), *extra]
    from bhms.cli.main import app

    sys.argv[0] = "bhms"
    return app() or 0


if __name__ == "__main__":
    sys.exit(main())
