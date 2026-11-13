#!/usr/bin/env python3
"""Render a results directory as the Markdown tables of ``docs/bhms/performance.md``.

``python bench/tables.py bench/results/<dir> [--runs DIR2 ...]`` prints environment, budget verdicts and one table per scenario.
Every latency row shows samples, p50, p95, p99 and max in milliseconds, and the load average around the measurement.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load(directory: Path, name: str):  # noqa: ANN201
    path = directory / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def lat(label: str, r: dict, load_of: dict | None = None) -> str:
    p = lambda k: f"{r[k]:.2f}" if k in r else "-"  # noqa: E731
    la = (load_of or r).get("load")
    loads = f"{la['before']['load1']:.1f}->{la['after']['load1']:.1f}" if la else "-"
    thr = f"{r['throughput_per_s']:.0f}" if "throughput_per_s" in r else "-"
    return f"| {label} | {r['n']} | {p('p50_ms')} | {p('p95_ms')} | {p('p99_ms')} | {p('max_ms')} | {thr} | {loads} |"


HEAD = "| case | n | p50 ms | p95 ms | p99 ms | max ms | ops/s | load1 |\n|---|---:|---:|---:|---:|---:|---:|---|"


def main() -> None:
    d = Path(sys.argv[1])
    env = load(d, "environment")
    print(f"### {d.name}\n")
    print(f"{env['cpu']}, {env['cpus_online']} CPUs online, pinned to {len(env['affinity'])} ({','.join(map(str, env['affinity']))}); "
          f"{env['mem_gb']} GB; {env['os'].split('=')[1].strip(chr(34))}, kernel {env['kernel']}; Python {env['python']}, Node {env['node']}; "
          f"state dir on `{env['state_dir_fs']}`; {env['mode']} sizes; load1 at start {env['load']['load1']:.1f}.\n")
    print("#### Budgets\n\n| verdict | budget | measured | limit |\n|---|---|---|---|")
    for r in load(d, "budgets"):
        print(f"| {'PASS' if r['pass'] else '**FAIL**'} | {r['budget']} | {r['measured']} | {r['limit']}{' ; ' + r['detail'] if r['detail'] else ''} |")
    f = load(d, "fsync")
    if f and "result" in f:
        r = f["result"]
        print("\n#### Host fsync (state directory filesystem)\n\n" + HEAD)
        for k in ("fdatasync_600B", "fsync_600B", "fdatasync_4096B", "fsync_4096B"):
            print(lat(k.replace("_", " "), r[k], r))
        print(f"\nSQLite WAL commit (600 B row): NORMAL p50 {r['sqlite_wal_commit']['NORMAL']['p50_ms']} ms / p99 {r['sqlite_wal_commit']['NORMAL']['p99_ms']}; "
              f"FULL p50 {r['sqlite_wal_commit']['FULL']['p50_ms']} ms / p99 {r['sqlite_wal_commit']['FULL']['p99_ms']}.")
    t = load(d, "transports")
    if t and "result" in t:
        print("\n#### Transports, ping only\n\n" + HEAD.replace("| ops/s | load1 |\n|---|---:|---:|---:|---:|---:|---:|---|", "| ops/s | load1 |\n|---|---:|---:|---:|---:|---:|---:|---|"))
        for k, v in t["result"].items():
            print(lat(f"{k} sequential", v["sequential"], v))
        print("\nPipelined (256 in flight): " + ", ".join(f"{k} {v['pipelined']['per_s']}/s" for k, v in t["result"].items()))
    i = load(d, "invoke")
    if i and "result" in i:
        print("\n#### `actions/invoke`, one client, sequential\n\n" + HEAD)
        for k, v in i["result"].items():
            if isinstance(v, dict):
                print(lat(k, v))
    c = load(d, "concurrency")
    if c and "result" in c:
        print("\n#### Concurrent clients (`waitMs=1000`, unix)\n\n" + HEAD)
        for k, v in c["result"].items():
            print(lat(k, v))
    ol = load(d, "openloop")
    if ol and "result" in ol:
        print("\n#### Open-loop latency (Poisson arrivals at a fixed offered rate; latency from the scheduled arrival)\n")
        print("| case | offered/s | achieved/s | n (failed) | p50 ms | p95 ms | p99 ms | max ms | load1 |\n|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for mode, v in ol["result"].items():
            for k, r in v.items():
                if isinstance(r, dict):
                    la = r["load"]
                    print(f"| {mode} {k} (capacity {v['measured_capacity_per_s']}/s) | {r['offered_per_s']} | {r['achieved_per_s']} | {r['n']} ({r['failures']}) | {r['p50_ms']:.2f} | "
                          f"{r['p95_ms']:.2f} | {r['p99_ms']:.2f} | {r['max_ms']:.2f} | {la['before']['load1']:.1f}->{la['after']['load1']:.1f} |")
    g = load(d, "gateway")
    if g and "result" in g:
        r = g["result"]
        s, fa, o = r["scale"], r["fanin"], r["overhead"]
        print(f"\n#### Gateway, {r['upstreams']} upstreams x 10 devices (in-process upstreams)\n")
        print(f"start {s['start_s']} s, background validation {s['background_validation_s']} s, RSS +{s['rss_mb_added']} MB; devices {s['devices']}.\n")
        print("| paging | n | p50 ms | p95 ms | p99 ms | max ms |\n|---|---:|---:|---:|---:|---:|")
        for k, v in s["paging"].items():
            print(f"| {k} | {v['n']} | {v['p50']} | {v['p95']} | {v['p99']} | {v['max']} |")
        print(f"\nEvent fan-in: {fa['events']} events from {fa['upstream_streams']} upstream streams in {fa['total_s']} s = {fa['events_per_s']}/s; "
              f"latency under the burst p50 {fa['latency_ms']['p50']} / p99 {fa['latency_ms']['p99']} / max {fa['latency_ms']['max']} ms; +{fa['rss_mb_added']} MB.\n")
        print("| invoke via | n | p50 ms | p95 ms | p99 ms | max ms | overhead p50 ms |\n|---|---:|---:|---:|---:|---:|---:|")
        for k, v in o.items():
            if isinstance(v, dict) and "p50" in v:
                print(f"| {k} | {v['n']} | {v['p50']} | {v['p95']} | {v['p99']} | {v['max']} | {v.get('overhead_p50_ms', '-')} |")
    h = load(d, "gateway_http")
    if h and "result" in h:
        r = h["result"]
        print(f"\n#### Gateway over unix versus Streamable HTTP ({r['devices']} devices)\n\n" + HEAD)
        for tr in ("unix", "http"):
            for k, v in r[tr].items():
                if isinstance(v, dict) and "p50_ms" in v:
                    print(lat(f"{tr} {k}", v, r[tr]))
    s = load(d, "subscription")
    if s and "result" in s:
        print("\n#### Subscription fan-out (1 event stream to N listeners)\n\n" + HEAD)
        for k, v in s["result"].items():
            print(lat(f"{k} delivery", v["delivery"], v))
            print(lat(f"{k} slowest listener", v["slowest_listener_ms"], v))
        print("\nDeliveries lost: " + ", ".join(f"{k}: {v['deliveries_lost']}" for k, v in s["result"].items()))
    rc = load(d, "recovery")
    if rc and "result" in rc:
        print("\n#### Crash recovery (SIGKILL, restart)\n\n| case | journal bytes | to ready s | to first response s | unknown after |\n|---|---:|---:|---:|---:|")
        for k, v in rc["result"].items():
            print(f"| {k} | {v['journal_bytes']} | {v['to_ready_s']} | {v['to_first_response_s']} | {v['unknown_after']} |")
    cp = load(d, "compact")
    if cp and "result" in cp:
        print("\n#### BHMS-Compact\n\n| target | op | n | p50 ms | p95 ms | p99 ms | max ms |\n|---|---|---:|---:|---:|---:|---:|")
        notes = []
        for tgt, v in cp["result"].items():
            for op in ("invoke", "read"):
                r = v[op]
                print(f"| {tgt} | {op} | {r['n']} | {r['p50_ms']} | {r['p95_ms']} | {r['p99_ms']} | {r['max_ms']} |")
            extra = f" wire floor {v['wire_floor_ms']} ms at {v['baud']} baud, p50 over floor {v['invoke_over_floor_ms']} ms;" if "baud" in v else ""
            notes.append(f"{tgt}: invoke request {v['invoke_request_bytes']} bytes, reply {v['invoke_reply_bytes']}, read frames {v['read_frame_bytes']}, hello {v['hello_bytes']};{extra}")
        print("\n" + "\n\n".join(notes))
    m = load(d, "mcp_compare")
    if m and "result" in m:
        r = m["result"]
        print("\n#### MCP bridge versus native client\n\n" + HEAD)
        for k in ("native", "mcp_bridge"):
            print(lat(k, r[k]))
        print(f"\nBridge overhead p50 {r['bridge_overhead_p50_ms']} ms; tool result text {r['mcp_bridge']['result_text_bytes']} bytes; `tools/list` {r['mcp_list_tools_ms']} ms.")
    ts = load(d, "ts_vs_py")
    if ts and "result" in ts:
        r = ts["result"]
        if "skipped" in r:
            print(f"\n#### TypeScript vs Python\n\nskipped: {r['skipped']}")
        else:
            print("\n#### TypeScript SDK server versus Python SDK server (`axis-1.pulse`, `waitMs=1000`, unix)\n\n" + HEAD)
            for k, v in r.items():
                if isinstance(v, dict) and "p50_ms" in v:
                    print(lat(k, v))


if __name__ == "__main__":
    main()
