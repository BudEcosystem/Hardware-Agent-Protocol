"""``python -m bhms.gateway <gateway.toml>``: run a gateway from a configuration file."""

from __future__ import annotations

import argparse
import logging
import sys

from bhms.gateway.config import ConfigError, load_config
from bhms.gateway.gateway import Gateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bhms.gateway", description=__doc__)
    parser.add_argument("config", help="path of the gateway TOML file")
    parser.add_argument("-v", "--verbose", action="store_true", help="log at INFO (default WARNING)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = load_config(args.config)
    except (ConfigError, OSError) as exc:
        print(f"bhms.gateway: {exc}", file=sys.stderr)
        return 2
    try:
        Gateway(config).run()
    except ValueError as exc:  # refused at start-up (policy widens a bound, listener without TLS, ...)
        print(f"bhms.gateway: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:  # a listener that cannot be opened (address in use, socket path too long, no permission)
        hint = (" (a Unix socket path is limited to about 107 bytes: listen on a shorter path)"
                if "AF_UNIX path too long" in str(exc) else "")
        print(f"bhms.gateway: cannot serve the configured listeners: {exc}{hint}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
