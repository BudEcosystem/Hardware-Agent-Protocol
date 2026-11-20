# Retention scan cost

All **72 fixed scans** reproduce the original tree's **3,227 entries** and
**11,889,866 logical file bytes**. Before/after metadata matches under all
49 original owner/writer locks. No case database is opened or read, and no worker
is launched. [Results](RESULTS.json) and the [evaluation receipt](attempt01/result.json)
retain the complete comparison.

Median CPU time per scan is **22.498 ms** with the common read-only dispatcher
and **25.689 ms** when the exact original Python audit callback is added, a ratio
of **1.142**. Seven fixed alternating pairs contain five scans per sample, after
one warm scan per mode. One paired sample reverses the ordering. Both modes
include the common dispatcher, so this is not an uninstrumented native baseline.
Every scan performs 97 directory opens and 97 directory iterations.

The [audit](audit.py) verifies exact AST extraction from pinned source, original
borrowed bytes, metadata and timing arithmetic. This is the quiescent original
partial tree; it does not reproduce live growth or prove the earlier timeout's
cause. Production and all worker/storage/effect limits remain unchanged.

The measurements motivate the separate [native prototype](../pat-native-retention-prototype/README.md).
Its results and implementation limits are independent of this scan comparison.
The [design](DESIGN.md) records this evaluation's original scope.
