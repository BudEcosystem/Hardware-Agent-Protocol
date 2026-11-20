# Full-geometry storage capacity observations

Stage 86, 2026-11-09. Two native cache profiles have different evidence and must
not share qualification claims. Public runtime inputs remain unchanged.

| Profile | Completed evidence | Limitation |
| --- | --- | --- |
| Typed inventory, 16-byte reads / 256-byte cache | Six original scopes / 54 checks and all 22 interruption cases / 24 selected owner terminations pass | Host capacity phase terminates with -9 after 40.4 seconds under its 40-second CPU limit, before any append intent |
| Separate 4,096-byte read / cache evaluation | Actual host allocator exhaustion, preserved committed data, derived-copy recovery and independent control writes | Full semantic/interruption regressions have not run for this profile; it is not adopted |

The [candidate](chunk_store.py) obtains directory names, types and sizes together
through a bounded native enumeration. Existing data mutation, namespace, ownership
and recovery policy remains exact. [Change review](candidate-diff.json) records
37 unchanged existing Python methods and unchanged original C functions.
The first [attempt](attempt01/RESULTS.json) retains its completed regressions and
terminal host failure. Its bulk image exactly matches the finalized seed, with
zero append intents. Timing does not independently establish the termination cause.

Fixture preparation uses the full 4,096-block / 16 MiB geometry. A bounded RAM
preparer reaches real allocator `NOSPC`, then separately finalizes a safe copied
snapshot containing 3,888 chunks. An independent read verifies all 15,925,248
payload bytes. RAM sync is only a counter; preparation proves no host durability.
The exhausted and pre-finalization RAM artifacts retain placeholder namespaces
and are not valid admitted adapter images.

The [block-read evaluation](block-read-evaluation/RESULTS.json) changes only native
read and cache sizes to 4,096 bytes. Program size remains 16 bytes, geometry stays
16 MiB, and every provider ownership/allocation check remains active. It uses a
byte-exact copied seed, fresh host images and the same CPU/wall/file bounds. More
host cache memory is not an Arduino memory-profile claim.

On the actual host-backed image, 38 appends complete. The next original append
returns `NOSPC` (-28) while writing `state.tmp`; no callback failure is injected.
The poisoned owner refuses further reads and writes. Read-only inspection finds
all 4,096 blocks occupied, an unpublished chunk and empty staged namespace.
The authoritative namespace still contains 3,926 chunks / **16,080,896 bytes**.
Independent native reads verify the complete original A-prefix and 38 B-chunks.
The failed in-memory size is not used as committed state.

Recovery runs only on a verified copy. It removes the staged namespace and extra
chunk and leaves 4,095 occupied blocks. A subsequent new metadata allocation still
returns `NOSPC`; no new named file is published. Complete committed payload bytes
verify again. The original failed bulk image remains unchanged.

The separate control image accepts writes with bulk both full and actually
missing, then cold-reads all 47 expected bytes. This demonstrates the example's
storage-domain independence. It does **not** reserve future continuation capacity
or qualify complete service recovery. Payload caps alone do not account for the
transient metadata allocations observed here.

[Read-only evidence audit](EVIDENCE-AUDIT.json) checks the 52 regression images,
both capacity images and the control image, joins original intents and selected
terminations, and verifies preserved originals and the 244 runtime inputs.
An initial audit comparison incorrectly compared Python tuples with JSON lists;
[the failed audit](audit-process01/result.json) and its source remain retained.
The correction compares the complete canonical serialized values. No experiment
or storage image is repaired or repeated for that correction.

The stage retains 61 images / 976 MiB backing, within its unchanged 1 GiB fixture
ceiling. This is test inventory, not an enforced service quota. The
[seal](AUDIT.json) and [exact index](index.json) cover both successful observations
and failures. Review is by the primary agent only. SQLite DELETE/EXTRA, complete
writer confinement, backed continuations, physical power loss and physical
device/driver/hub providers remain unqualified. [Next work](NEXT.md).
