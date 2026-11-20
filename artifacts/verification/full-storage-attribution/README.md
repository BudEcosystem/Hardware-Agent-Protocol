# Full-workload storage attribution

Stage 96, 2026-11-09. **The instrumentation preserves the paired screen's logical
and physical results; the complete writer still reaches its original deadline.**
This is a diagnostic using the byte-exact Stage 95 inline512 hierarchy, statx
provider and native libraries. It makes no production storage-format change.

The [plan](PLAN.md), [observer](attribution.py) and [bounded runner](run_scopes.py)
retain all original provider checks and full fsync of every backing chunk.
The original replay_write function is called unchanged, with 4,270 files /
35,508,922 bytes, all 169 directories, eight 16 MiB chunks and the original
180-wall/120-CPU limits. The prior 340-file seal and declared alias are verified;
its 192 focused checks are retained evidence and are not rerun.

The forty-file / twenty-directory preflight preserves all **426 logical steps**,
complete bodies, native callback counts and backing bytes. Original/observed CPU
is **3.621923 / 5.986387 seconds**, and wall time **9.230481 / 13.339525 seconds**.
The instrumentation substantially perturbs timing. This one paired difference
includes instrumentation and run variation, and is not a production-performance
estimate or a correction factor for the full workload.

The full writer is killed and reaped at **180.098411 wall seconds**, using
**63.611194 CPU seconds** and 23,092 KiB peak RSS. The dependent cold reader does
not run. No capacity error is reported; complete capacity fit remains unknown.
There is no unchanged retry, altered geometry, reduced workload or repair.

The [independent audit](EVIDENCE-AUDIT.json) passes in **6.816371 wall / 6.704636 CPU
seconds**, with 41,380 KiB peak RSS. It reconstructs both screens and the failed
writer through read-only held descriptors. The writer contains **1,318 complete
source-prefix bodies / 5,930,147 bytes**, all 169 directories, and one next
published file with **zero committed bytes**. That extra file is not counted as
a complete source body. No pending entry, unlinked inode, incomplete physical
inode or partial progress tail is observed. All backing bytes remain unchanged;
no adapter recovery, SQLite or mutation callbacks run.

The three workload children and audit child are reaped and absent. All **244
public inputs** still match the existing **866-test** baseline; that unchanged
suite is not repeated. No candidate is installed publicly.

## What the recorded prefix shows

[METRICS.json](METRICS.json) independently validates 172 complete writer frames /
942,288 bytes, with no partial tail or recorded observer error/drop. The last
frame is at **179.062741 seconds**, immediately before root operation 4,110,
a logical open.
It contains **4,109 completed root calls**, totaling **174.307631 wall /
62.753045 CPU seconds**. Completed call counts and inclusive times are monotone;
native callback counters are monotone within each owner. Inclusive logical totals
exactly equal the sum of nested self times, overall and by phase. Self-time
rounding is retained rather than assumed monotone.

These figures cover the recorded completed boundaries, not the final unobserved
suffix or every file in the intended dataset:

| Recorded component, all phases | Calls | Self CPU seconds | Self wall seconds |
|---|---:|---:|---:|
| Full provider fsync calls | 258,124 | 20.876185 | 116.203276 |
| Provider ownership/inventory verification, excluding its nested timed work | 431,749 | 26.576999 | 35.029731 |
| Current mount checks | 431,749 | 4.003728 | 5.852352 |
| Native-boundary residual, aggregated | — | 3.483054 | 4.925743 |

The fsync calls are the largest recorded wall-time component; verification is
the largest recorded self-CPU label. Native-boundary residual includes ctypes,
native execution and tracing overhead after observed provider callbacks. It does
not identify individual C allocation, compaction or traversal costs. Inclusive
categories overlap and must not be added as independent costs; the self-time
partition is the additive view.

Before the last frame, snapshot serialization/write/fsync accounts for **0.565076
wall / 0.079433 CPU seconds**. This is only the snapshot observer cost, not all
instrumentation overhead. Timer/wrapper bookkeeping is dispersed across traced
spans and gaps. The remaining **4.190034-second prefix wall gap** includes source
reads/hashing, progress receipt work, setup and unwrapped bookkeeping. It is not
native time. No prefix CPU clock was recorded, so no prefix CPU gap is invented.
The terminal envelope minus last frame's elapsed time is **1.035670 seconds**;
that combines the unobserved suffix with clock-origin/startup and parent wait
overhead. A final observer receipt is absent after the hard kill. No throughput
or complete-workload cost is extrapolated from these observations.

## Serialized metadata shape

[dataset-shape.json](dataset-shape.json) is a pure size calculation for the full
intended dataset, reproduced by [analyze_shape.py](analyze_shape.py). It reads the
frozen dataset metadata and uses standard-library JSON/base64/hash functions;
it does not import a storage implementation or open an image.

The current canonical file-inode record always serializes a **512-byte bitmap**.
For the intended final file sizes and sequential inode IDs, complete wrapped
records occupy **814–822 bytes**: none fit the native 512-byte inline limit.
The dataset has 69 empty files, 3,064 files of 1–4,096 bytes, 965 of 4,097–16,384,
136 of 16,385–65,536, and 36 above 65,536 bytes. Their intended payloads occupy
11,523 logical 4 KiB chunks before filesystem overhead.

A hypothetical bitmap length of `ceil(ceil(file_size / 4096) / 8)` would make
**4,269 of 4,270** complete metadata records fit 512 bytes; one remains larger,
with a maximum encoded record of 770 bytes. This is a representation hypothesis,
not implemented compression, a measured speedup, physical capacity proof or
validated sparse-file behavior. Zero bitmap bytes are used only to calculate
base64 length, not to claim valid contents for existing nonempty files. The
current format still requires all 512 bytes and is unchanged.

[Next work](NEXT.md) reviews a separately versioned disk representation while
preserving all current checks, 4 KiB payload chunks and fixed backing geometry.
The larger HMS goal remains active: service storage, prompt learning, persistent
applications, real device/driver/hub providers and physical qualification remain
unfinished.
