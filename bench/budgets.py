"""The performance budgets of the BHMS build plan (Ruling R12 revised) evaluated against measured results.

Every budget yields a record ``{budget, limit, measured, pass, detail}``; a missing measurement is a failure ("not measured"),
never a silent pass. Budgets:

* B1 durable invoke: p50 <= floor + 1 ms, for two floors (the host fdatasync p50 and the measured SQLite FULL commit p50); formerly: p50 <= host fsync p50 + 1 ms and p99 <= 5 x (host fsync p50 + 1 ms) (``dispatch`` durability, unix, one
  client; judged for ``waitMs=0`` (intent durable) and ``waitMs=1000`` (full operation));
* B2 non-durable invoke: p50 <= 1 ms (``process`` durability, i.e. SIGKILL-safe only, and ``memory``, i.e. no store; unix, one
  client; judged for both waits);
* B3 a gateway over 1,000 upstreams lists every device once, in code-point order (the paged catalog is compared with the expected ids);
* B4 ``devices/list`` over 10,000 devices pages in <= 50 ms (per page, p99 and max reported; limit 100 and 500);
* B5 the compact typical invoke frame (request and reply) is <= 64 bytes.
"""

from __future__ import annotations

from typing import Any


def _get(results: dict[str, Any], *path: str) -> Any:
    node: Any = results
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _record(budget: str, limit: str, measured: str, ok: bool | None, detail: str = "") -> dict[str, Any]:
    return {"budget": budget, "limit": limit, "measured": measured, "pass": bool(ok), "detail": detail or ("" if ok is not None else "not measured")}


def evaluate(results: dict[str, Any], fsync_p50_ms: float | None, fsync_p99_ms: float | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    sqlite_p50 = _get(results, "fsync", "result", "sqlite_wal_commit", "FULL", "p50_ms")
    floors = (("fdatasync floor", fsync_p50_ms), ("SQLite FULL commit floor", sqlite_p50))
    for wait in (0, 1000):
        row = _get(results, "invoke", "result", f"unix/dispatch/waitMs={wait}")
        for floor_name, floor in floors:
            name = f"B1 durable invoke (dispatch, unix, waitMs={wait}; {floor_name})"
            if row is None or floor is None:
                out.append(_record(name, "p50 <= floor + 1 ms; p99 <= 5x that", "-", None))
                continue
            p50_limit, p99_limit = floor + 1.0, 5 * (floor + 1.0)
            out.append(_record(f"{name} p50", f"<= {p50_limit:.2f} ms (floor p50 {floor:.2f} + 1)", f"{row['p50_ms']:.2f} ms",
                               row["p50_ms"] <= p50_limit, f"overhead above floor: {row['p50_ms'] - floor:.2f} ms"))
            out.append(_record(f"{name} p99", f"<= {p99_limit:.2f} ms (5 x {p50_limit:.2f})", f"{row['p99_ms']:.2f} ms",
                               row["p99_ms"] <= p99_limit, f"host fsync p99 is {fsync_p99_ms:.2f} ms"))
    for mode in ("process", "memory"):
        for wait in (0, 1000):
            row = _get(results, "invoke", "result", f"unix/{mode}/waitMs={wait}")
            name = f"B2 non-durable invoke ({mode}, unix, waitMs={wait}) p50"
            out.append(_record(name, "<= 1.00 ms", f"{row['p50_ms']:.2f} ms" if row else "-", None if row is None else row["p50_ms"] <= 1.0))
    scale = _get(results, "gateway", "result", "scale")
    gateway = _get(results, "gateway_http", "result")
    listing = _get(results, "gateway", "result", "listing")
    ups = _get(results, "gateway", "result", "upstreams")
    if scale is not None and listing is not None:
        ok = (listing["listed"] == listing["expected"] == ups * 10 and listing["unique"] and listing["ordered"]
              and listing["equals_expected_in_order"])
        out.append(_record(f"B3 gateway lists {ups} upstreams correctly", f"{ups * 10} devices, each once, in code-point order",
                           f"listed {listing['listed']}, unique {listing['unique']}, ordered {listing['ordered']}, equals expected "
                           f"{listing['equals_expected_in_order']}; start {scale['start_s']} s", ok,
                           "asserted directly from the paged catalog (scenarios/gateway.py listing)"))
    else:
        out.append(_record("B3 gateway lists 1000 upstreams correctly", "10000 devices, each once, in order", "-", None))
    for transport in ("unix", "http"):
        for limit in (100, 500):
            row = _get(gateway or {}, transport, f"devices_list_limit_{limit}")
            ok = _get(gateway or {}, transport, f"listed_correctly_limit_{limit}")
            name = f"B4 devices/list 10,000 devices ({transport}, limit {limit}) per page"
            if row is None:
                out.append(_record(name, "<= 50 ms", "-", None))
            else:
                out.append(_record(name, "<= 50 ms (p99), complete and ordered", f"p99 {row['p99_ms']:.1f} ms, max {row['max_ms']:.1f} ms, p50 {row['p50_ms']:.1f} ms",
                                   row["p99_ms"] <= 50 and bool(ok), f"every device listed once in order: {ok}"))
    scale_paging = _get(scale or {}, "paging")
    if scale_paging:
        for limit in (100, 500):
            row = scale_paging[f"limit_{limit}_ms"]
            out.append(_record(f"B4 devices/list 10,000 devices (gateway_scale, unix, limit {limit}) per page", "<= 50 ms (p99)",
                               f"p99 {row['p99']:.1f} ms, max {row['max']:.1f} ms, p50 {row['p50']:.1f} ms", row["p99"] <= 50))
    frame = _get(results, "compact", "result", "native", "typical_invoke_frame_bytes")
    out.append(_record("B5 compact typical invoke frame (native pty)", "<= 64 bytes", f"{frame} bytes (request "
                       f"{_get(results, 'compact', 'result', 'native', 'invoke_request_bytes')}, reply "
                       f"{_get(results, 'compact', 'result', 'native', 'invoke_reply_bytes')})" if frame is not None else "-",
                       None if frame is None else frame <= 64))
    return out
