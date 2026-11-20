# Full-geometry allocation and inventory gate

Stage 86, 2026-11-09. Stage 85 made verified progress with all 22 selected
interruption cases. Reverify its exact seal and the 244 public runtime inputs.
Keep all earlier artifacts unchanged. This stage edits only a new private adapter
candidate and original research harnesses, not the public runtime.

The old inventory performs a native lookup for every already-listed name. Add a
typed native directory enumeration that returns each name/type/size together.
Keep the same ownership, range, identity, presence and length checks. Rerun all
six stage 84 scopes / 54 checks and all 22 stage 85 interruption cases because
the native bridge and inventory path change. Original control sources and case
oracles are exact; only the interruption harness's library path/hash become
explicit inputs for the new build. Keep all original process/time/file bounds.

Construct full 4,096-block / 16 MiB boundary fixtures with the reviewed core in
bounded RAM. No reduced geometry is used. An original C preparer writes 4 KiB
chunks until the actual allocator returns NOSPC, retaining that raw RAM image.
It also retains the last completed snapshot with at least 32 free reachable-block
slots. The safe snapshot contains an explicit namespace placeholder; it is not
an admitted adapter image. Finalize its canonical namespace on an independent
RAM copy and retain the resulting valid image. Verify all declared chunk bytes
with a separate bounded native read pass before copying it to host backing.

RAM preparation is only fixture construction: sync is a counter there and it
proves no durability. Host trials copy exact finalized bytes into a fresh fully
allocated fixed-block image with external object anchors. Reopen the actual
candidate, append at most 64 original 4 KiB writes to observe allocator exhaustion,
retain the first failed attempt and verify poisoned-owner refusal. Record the
specific failing native operation to distinguish data allocation from metadata
publication. No whole-file-size cap or injected exception substitutes for NOSPC.

Use a separate control image before and after bulk failure, then with an actually
missing bulk path. Verify its cold data separately. Preserve the failed bulk image
unchanged and recover only an exact derived copy. Record whether recovery and a
new metadata allocation can complete; NOSPC/unavailable results remain limitations,
not successful recovery. Inspect the actual committed namespace and all referenced
data. A lost reply/error can leave old or new size/presence; retain that distinction
without retrying the original operation.

Each original semantic/interruption scope retains its 60-second wall, 40-second
CPU, 512 MiB address-space, 128-FD and 16 MiB per-file bounds. Compiler wall/CPU
limits are 30/20 seconds. New preparation, full-read and host phases each use
60/40 seconds, except nested interruption owners retain 15/10 seconds. Stop on an
unexpected failure or timeout and preserve all evidence; no automatic retries or
widened limits. Maximum new retained inventory is 1 GiB: 52 regression images,
three raw seed images and three host capacity images, at most 58 × 16 MiB = 928 MiB
backing plus bounded source/log files. Earlier retained stages are untouched.

A full recovery outcome is measured rather than assumed. This gate does not yet
qualify SQLite DELETE/EXTRA, every-writer confinement, protected control capacity,
physical power loss, arbitrary file hierarchies or real device/driver/hub providers.
Separate control storage still owes actually backed remaining continuations;
successful example writes do not reserve them.
