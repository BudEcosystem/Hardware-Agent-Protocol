#!/usr/bin/env python3
"""Pin the original shared-board simulation example to this source tree."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hms.contracts import MAX_BYTES, canonical, parse_json
from hms.resource_topology import topology_digest
from hms.synthetic_io_installation import implementation_digest, normalize_installation, require


def build():
    with (ROOT / 'examples/io/shared-board.blueprint.json').open('rb') as source:
        value = parse_json(source.read(MAX_BYTES + 1))
    # Only an unpinned blueprint is accepted. An existing installation must
    # retain its provenance instead of silently receiving new source pins.
    require('driverDigest' not in value and 'topologyDigest' not in value['initialGenerations'],
            'IO_EXAMPLE_ALREADY_PINNED')
    digest = implementation_digest()
    for node in value['topology']['nodes'].values():
        if node['kind'] == 'driver':
            require('implementationDigest' not in node['properties'], 'IO_EXAMPLE_ALREADY_PINNED')
            node['properties']['implementationDigest'] = digest
    value['driverDigest'] = digest
    value['initialGenerations']['topologyDigest'] = topology_digest(value['topology'])
    return normalize_installation(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Create a new installation file; refuse to overwrite')
    args = parser.parse_args()
    data = canonical(build()) + b'\n'
    if args.output is None:
        sys.stdout.buffer.write(data)
    else:
        with args.output.open('xb') as target:
            target.write(data)


if __name__ == '__main__':
    main()
