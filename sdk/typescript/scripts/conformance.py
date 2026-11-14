#!/usr/bin/env python3
"""Run the BHMS conformance suite (the Python runner) against the TypeScript conformance device through the public option.

    python3 scripts/conformance.py conformance-device            # stdio: core, leases, events, programs, registry
    python3 scripts/conformance.py conformance-device:principals # + authority

is the same as `bhms conformance <target> --device-command "node dist/src/testing/conformanceDevice.js"`. Build first
(`npm run build`). The runner is taken from the installed `bhms` or from `PYTHONPATH` (e.g. `sdk/python/src`); further
arguments are passed to `bhms conformance`.
"""
import shlex
import sys
from pathlib import Path

DEVICE = Path(__file__).resolve().parent.parent / "dist" / "src" / "testing" / "conformanceDevice.js"


def main() -> int:
    if not DEVICE.is_file():
        print(f"{DEVICE} is missing: run `npm run build` first", file=sys.stderr)
        return 2
    from bhms.cli.main import app

    sys.argv = ["bhms", "conformance", *sys.argv[1:], "--device-command", f"node {shlex.quote(str(DEVICE))}"]
    return app() or 0


if __name__ == "__main__":
    sys.exit(main())
