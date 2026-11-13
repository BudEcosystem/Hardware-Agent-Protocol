#!/usr/bin/env python3
"""Print the N least busy CPUs over a short sample as a taskset list (for pinning on a shared machine).

``python idle_cpus.py [N=8] [seconds=5]`` -> e.g. ``3,9,12,14,15,20,21,30``.
"""

import sys
import time


def snapshot() -> dict[str, tuple[int, int]]:
    out = {}
    for line in open("/proc/stat"):
        if line.startswith("cpu") and line[3].isdigit():
            fields = line.split()
            values = list(map(int, fields[1:]))
            out[fields[0][3:]] = (sum(values), values[3] + values[4])
    return out


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    before = snapshot()
    time.sleep(seconds)
    after = snapshot()
    busy = {c: 1 - (after[c][1] - before[c][1]) / max(1, after[c][0] - before[c][0]) for c in after}
    print(",".join(sorted((c for c in sorted(busy, key=busy.get)[:count]), key=int)))


if __name__ == "__main__":
    main()
