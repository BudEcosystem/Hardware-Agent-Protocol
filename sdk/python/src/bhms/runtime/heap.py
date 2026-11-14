"""Start-up heap handling for long-running BHMS processes (device servers and gateways).

A server allocates most of its long-lived objects while it starts: device descriptions, compiled validators, schema
documents, the catalog of a gateway, imported modules. They never die, yet every generation-2 garbage collection walks
them all; in the Task 12a measurements that was a 42 to 81 ms pause of a device server's event loop (about 29,000 objects)
and about 200 ms for a gateway serving ten thousand devices. :func:`freeze_startup_heap` collects once and then moves
everything that survived into the permanent generation (``gc.freeze``), so later collections only look at what the
server allocates while serving.

Example::

    await server.start()
    freeze_startup_heap()

Thread-safety: call it once, from the thread that runs the server, before serving requests.
"""

from __future__ import annotations

import gc


def freeze_startup_heap() -> int:
    """Collect garbage, then exclude every surviving object from future collections; returns how many are frozen."""
    gc.collect()
    gc.freeze()
    return gc.get_freeze_count()


__all__ = ["freeze_startup_heap"]
