# Source and boundary review

The only operational hierarchy changes from sealed Stage 95 are the explicit
profile, `_encode_inode`, its use by `_save_inode`, and compact-wire validation
at `_valid_inode`. `hierarchical_store.py.patch` is the exact diff. The full
in-memory bitmap validator remains unchanged in `chunk_store_base.py`.

| Consumer | Representation and consequence |
| --- | --- |
| `_pack`, `_unpack`, `_canonical` | Same canonical JSON envelope and SHA-256; compact wire is inside the existing body. |
| `_initialize_inode` | Creates full 512-byte zero map; `_save_inode` serializes a copy with empty map at size zero. |
| Base `_bitmap`, `_present` | Continue to require canonical fixed 512-byte memory maps and scan the same 4,096 bits. |
| `_path`, `_chunk`, inherited `pread` | Same 4 KiB physical payloads, zero holes, EOF masking and shared inode handles. |
| `_zero_tail` | Same rewrite of retained partial payload before logical growth; no bitmap contract change. |
| Hierarchy `pwrite` | Same chunk write loop, full-map update, size change and metadata publication order. |
| Hierarchy `truncate` | Same bit clearing and metadata publication before physical chunk removal; growth retains zero-tail behavior. |
| `_inventory`, `_valid_inode` | Validate entire graph and compact wire before padding and before any recovery mutation. |
| `_recover_inventory`, `_reclaim_native`, `_drop_inode` | Operate on validated full memory maps; orphan/staged cleanup and unlink lifecycle unchanged. |
| `accounting` | Same native used blocks and logical size sums; no inferred reservation or reduced capacity charge. |
| Independent retained reader | Explicit compact/fixed mode; strict wire length/canonical/tail checks before normalization, exact backing hashes before/after. |

The copied base's flat namespace `_load`, `_save`, `_recover`, `open`, `pwrite`
and `truncate` are not the hierarchy operational entry points: the hierarchy
overrides those paths. Its inherited `_bitmap`, `_present`, `_chunk`, `_zero_tail`,
`pread`, synchronization, guard and disposal remain relevant and unchanged.
No changes to native C, ctypes transport, provider, mount helper, fsync selection,
block geometry, directory encoding or full replay loops accompany the format.

The serializer never edits the caller's inode. Invalid size is rejected before
bitmap access. The exact new wire length follows declared size, including sparse
files, rather than the highest set bit. Both missing and extra bytes refuse.
Canonical base64 comparison rejects otherwise-decodable alternate padding bits.
Bits beyond EOF in a retained byte refuse, and encoding also rejects nonzero
bytes that would be omitted. All decoder checks precede full-map padding.

Target codec cases use independent known wires (`''`, `AQ==`, `QQ==`, `gQ==`,
`AQE=`), explicit expected lengths, and invalid maps in newly valid checksum
envelopes. Size vectors cover 0, 1, 4,095, 4,096, 4,097, 7/8/9 chunks and both
last-byte maximum-size boundaries. The real edge scope keeps a full 16 MiB
logical sparse file, tests growth/shrink through the native inline-size threshold,
and cold reads all expected bytes. This checks metadata size crossing, not a
new native inline allocation API; the native binary and prior inline controls
remain exact.

Three deliberately corrupt images isolate wrong length, noncanonical base64 and
nonzero EOF tail. They retain valid envelopes and cleanup sentinels. Refusal must
precede `_recover_inventory`, issue zero native mutation callbacks and preserve
all raw image hashes. The independent corruption helper checks exact malformed
wire bodies and sentinels; the normal reader must refuse those maps.

Four cuts test the existing commit behavior around the new format: after staged
metadata write, after metadata rename, before the second chunk of an existing
cross-chunk overwrite, and before removal following shrink metadata publication.
The owner and its second held handle must refuse afterward. Failed originals
are disposed, hashed and cloned before recovery; only clones may recover. Each
clone's exact committed body and physical cleanup are checked, and original
hashes remain exact. Multi-chunk pwrite is not atomic: the partial-overwrite
case expects a changed first-chunk suffix and old second-chunk data. A cut after
rename may expose new state despite the logical call raising. These are injected
Python boundaries, not simulated media loss or proof of physical crash safety.

`retained_reader.py.patch` records the independent adaptation. It retains the
read-only image descriptor/inode ownership checks and native zero-mutation
callback assertion. It removes the old Stage 95 standalone main, which contained
stage-specific scope assumptions, rather than silently running it for new
fixtures. New audit orchestration must be reviewed against actual receipts.
Semantic comparison can use its normalized metadata, while raw image hashes are
required only within a retained image; profiles intentionally differ on disk.

The runner joins the exact prior seals, public receipt and original dataset,
freezes source copies before children, and retains source/binary/interpreter
hashes. The supervisor uses the sealed AVR WNOWAIT ownership pattern with
wait4 usage collection: group signals occur only while the owned leader remains
unreaped. Monitor exceptions and SIGTERM share anchored cleanup, and group
absence after reaping is only audited; there is no unanchored fallback signal. It reuses the native binary and revalidates original native control
receipts rather than recompiling. The original 96 hierarchy checks and complete
writer/cold-reader source are byte exact. Neither performance claims nor a
successful full replay are asserted before execution and independent audit.
