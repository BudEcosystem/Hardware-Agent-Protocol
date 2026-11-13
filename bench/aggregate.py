#!/usr/bin/env python3
"""Aggregate B1 and B2 across several run directories of the same machine and print the verdict as Markdown.

``python bench/aggregate.py bench/results/<run1> bench/results/<run2> ...``

A run passes B1 under a floor when every cell (waitMs 0 and 1000, p50 and p99) passes against that floor (the host ``fdatasync`` p50,
or the measured SQLite WAL FULL-commit p50, both taken in the same run). The aggregate verdict is PASS only if every run passes; otherwise
it is FAIL with the number of passing runs and the load of each. Recomputed from the raw scenario JSON with ``budgets.evaluate``, so runs
made before the second floor existed are judged by the same code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import budgets  # noqa: E402


def results_of(directory: Path) -> dict:
    out = {}
    for path in directory.glob("*.json"):
        if path.stem not in ("environment", "budgets", "summary"):
            out[path.stem] = json.loads(path.read_text())
    return out


def main() -> None:
    dirs = [Path(a) for a in sys.argv[1:]]
    rows = []
    for d in dirs:
        r = results_of(d)
        f = r["fsync"]["result"]
        records = budgets.evaluate(r, f["reference"]["fsync_p50_ms"], f["reference"]["fsync_p99_ms"])
        inv = r["invoke"]["result"]
        load = r["invoke"]["load_around"]
        verdict = {}
        for floor in ("fdatasync floor", "SQLite FULL commit floor"):
            cells = [x for x in records if x["budget"].startswith("B1") and floor in x["budget"]]
            verdict[floor] = (all(c["pass"] for c in cells),
                              [("w0" if "waitMs=0;" in c["budget"] else "w1000") + (" p50" if c["budget"].endswith("p50") else " p99")
                               for c in cells if not c["pass"]])
        b2 = [x for x in records if x["budget"].startswith("B2 non-durable invoke (process")]
        rows.append((d.name, load["before"][0], load["after"][0], f["fdatasync_600B"]["p50_ms"], f["sqlite_wal_commit"]["FULL"]["p50_ms"],
                     inv["unix/dispatch/waitMs=0"], inv["unix/dispatch/waitMs=1000"], verdict, all(x["pass"] for x in b2)))
    print("| run | load1 (invoke scenario) | fdatasync p50 | SQLite FULL p50 | dispatch w0 p50 / p99 | dispatch w1000 p50 / p99 | B1 vs fdatasync | B1 vs SQLite FULL | B2 (process) |")
    print("|---|---|---:|---:|---|---|---|---|---|")
    for name, b, a, fs, sq, w0, w1, v, b2 in rows:
        cell = lambda t: "PASS" if t[0] else "FAIL (" + ", ".join(t[1]) + ")"  # noqa: E731
        print(f"| {name} | {b:.0f} to {a:.0f} | {fs:.2f} | {sq:.2f} | {w0['p50_ms']:.2f} / {w0['p99_ms']:.2f} | {w1['p50_ms']:.2f} / {w1['p99_ms']:.2f} | "
              f"{cell(v['fdatasync floor'])} | {cell(v['SQLite FULL commit floor'])} | {'PASS' if b2 else 'FAIL'} |")
    print()
    for floor in ("fdatasync floor", "SQLite FULL commit floor"):
        passed = [r[0] for r in rows if r[7][floor][0]]
        n = len(rows)
        print(f"* B1 under the {floor}: **{'PASS' if len(passed) == n else 'FAIL'}**, {len(passed)} of {n} runs pass"
              + (f" ({', '.join(passed)}; load1 {', '.join(f'{r[1]:.0f}-{r[2]:.0f}' for r in rows if r[0] in passed)})" if passed else "") + ".")
    n2 = sum(r[8] for r in rows)
    print(f"* B2 (process mode, p50 <= 1 ms): {n2} of {len(rows)} runs pass.")


if __name__ == "__main__":
    main()
