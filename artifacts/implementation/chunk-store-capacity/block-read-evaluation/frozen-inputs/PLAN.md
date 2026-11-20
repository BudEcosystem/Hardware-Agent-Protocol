# Bounded block-read follow-up after the original terminal result

The original candidate passes all six semantic scopes / 54 checks and all 22
interruption cases. Full-geometry RAM preparation reaches allocator NOSPC and its
safe finalized 3,888-chunk image verifies in full. The actual host bulk phase then
returns -9 after 40.4 seconds under its hard 40-second CPU limit, without a wall
timeout or any append intent. Its bytes still exactly match the finalized seed.
This is incomplete host-capacity evidence; the original attempt is never restarted.

The RAM enumeration/finalization records over a million read callbacks for about
23 MB. The fixed block provider revalidates ownership and allocation on every I/O.
Evaluate a separate host-oriented native cache profile with read_size=4096 and
cache_size=4096, while prog_size=16, 4,096 blocks, 4 KiB block size, inline policy,
namespace/data layout and every provider verification stay unchanged. This changes
only two native configuration constants; it does not remove validation or increase
the process deadlines. The new cache consumes more bounded host RAM and is not an
Arduino memory-profile claim.

Compile a separate library from exact core sources and this original bridge copy.
Reuse the finalized seed only through a byte-exact copied artifact. Use fresh
bulk/control/recovery images for the same capacity operations. Original adapter,
capacity harness, append bound, expected data and failure interpretation are exact.
Original compiled read-only seed inspection checks all final referenced data across
the cache configurations. Keep 60-second wall / 40-second CPU limits per host
phase, 30/20 for compilation, 512 MiB memory, 128 FDs and 16 MiB per file.

The original stage ceiling remains 1 GiB. Its stopped attempt retains 57 images /
912 MiB backing. This follow-up adds one copied seed and three host images, reaching
at most 61 images / 976 MiB plus bounded metadata. Verify the combined inventory
before and after. No failed evidence is deleted, repaired or overwritten.

This is an evaluation, not adoption. The block-sized cache still needs the complete
semantic/interruption regression matrix before replacing the small-cache candidate.
Do not transfer that candidate's passing counts to this changed native profile.
Record actual allocator, control-isolation and recovery outcomes without claiming
public service qualification, backed continuations or physical power-loss safety.
