# Independent compact-bitmap evidence audit

This is a separate original audit after candidate attempt01 reaches a terminal
receipt. It does not rerun controls, replay the workload, change the adapter,
repair an image, or retry a failure. The candidate PLAN, REVIEW, source, controls,
runner, reader and their frozen copies remain unchanged. This plan, the audit
orchestrator and its bounded runner are new files requiring source review before
execution. The prior audit runner's unsafe reap-before-group-signal cleanup is
replaced with the reviewed WNOWAIT pattern; `run_audit.py.patch` retains the exact
diff against sealed Stage 96. The old runner is untouched.

`run_audit.py` freezes five audit files into a new audit-process01 directory and
launches one child for 60 seconds wall, 40 seconds CPU, 512 MiB address space,
128 descriptors and 16 MiB per file, with core dumps disabled. It captures stdout
and stderr as files, records launch/terminal receipts, keeps the owned leader
unreaped through any group signal, and uses wait4 for reap and CPU/RSS. Timeout,
monitor exceptions and SIGTERM share anchored cleanup. After reap it only audits
group absence; it never signals an unanchored numeric group. It preserves failed
audit artifacts and does not retry. Source files/hashes are checked around the
run. The main candidate deadline and geometry are not changed by this audit.

The orchestrator revalidates all frozen/original candidate source joins, native
and mount binary identities, interpreter identity, the exact original dataset,
Stage 95's 340-file seal and explicit symlink, Stage 96's 96-file seal, and public
244-file receipt. The unchanged prior native control evidence is hash joined:
12 cases / 1,294 assertions, matching live/durable finite snapshots, not rerun.
The current attempt must have passed all 149 targeted checks (77 codec, 27 edge,
12 malformed-map and 33 interruption), all original 96 hierarchy checks, 52 mount
checks, 24 provider tests, eight profile checks and the paired 426-operation
screen. Check receipts must equal captured stdout, counts must be unique and
expected, scope terminal receipts must pass, and successful scopes must have
empty stderr. Process receipts are joined to exact bounds, reaping, anchored
cleanup and current group absence. Failed full-workload scope receipts remain
explicitly incomplete and cannot be presented as successful checks.

Only the frozen native wrapper and its base definitions are imported through the
already-reviewed independent reader. No hierarchy adapter, controls or tracer is
imported or instantiated; no adapter recovery is invoked. The read-only backing
provider uses held O_RDONLY/O_NOFOLLOW descriptors, ownership/identity checks,
locks, exact full-file hashes before/after and write/erase/sync refusal methods.
All successful native inspections must have zero program, erase and sync
callbacks. Read-only mount is not a physical power-loss model.

The expected retained image inventory is 34 images before a writer image and 35
if one exists: 18 original hierarchy fixtures, two profile fixtures, two paired
screens, one edge fixture, eight cut/original-clone fixtures, three malformed
bitmap fixtures and the optional writer. The cold reader reuses the writer's
image and does not add another. Raw RAM snapshots from the prior native controls
are only hash revalidated in their prior seal. Mount/provider fixtures are
validated by their current scope receipts, not misrepresented as native
hierarchy images.

Original hierarchy fixture assertions retain exact namespace, inode identity,
body, sparse/tail behavior, held-unlinked state, duplicate graph, missing chunk,
owner-loss and callback-failure expectations. Recovery originals and clones join
the saved lineage bytes; no audit recovery is permitted. Profile refusal retains
its wrong-profile superblock and cleanup sentinel. The old-profile comparison
uses explicitly selected fixed512 decoding, while candidate images use explicitly
selected compact decoding. The reader must validate canonical exact map length
and unused bits before padding, then normalize only the semantic comparison
metadata. Raw image bytes may differ across declared profiles and must remain
exact within each individual retained image.

For the new edge image, the auditor independently constructs the complete
transition-file body and the 16 MiB sparse maximum body and checks every byte.
The metadata-size controls remain scope evidence; size crossing is not claimed
as a new allocation API. Four cut originals and their recovery clones receive
independent expected bodies, including the partial two-chunk overwrite, old
state after staged metadata, new state after rename, and shorter state before
chunk cleanup. It also checks the exact staged new compact inode, original
extra physical objects and cleaned clone object sets. Recorded body hashes and
clone lineage must match these independent expectations. Shrink/regrowth on the
clone must conceal the old tail. Original failed images remain exact.

Each deliberately malformed bitmap has an independently specified disk body
(wrong fixed512 length, noncanonical padding bits or nonzero EOF bit) with a valid
canonical envelope/checksum. The normal reader must refuse it, and its raw bytes
must remain unchanged through that refusal. A separate explicit corruption
inspection checks that exact invalid body, the original full payload chunk,
state.tmp and super.tmp sentinels with read-only descriptors. It never pads or
normalizes the invalid map into accepted metadata. The saved refusal's error,
zero mutation callbacks and backing hashes must match.

The paired screens join all 426 logical operation results, full bodies and
normalized inode metadata, namespace, profile-specific superblocks and original
provider fsync relations. They intentionally allow different native callbacks
and physical encodings. CPU/wall values remain observations for those two finite
runs; no extrapolation or general speedup is established.

The writer audit parses only complete newline-terminated progress rows, checks
that they are an exact ordered prefix of the original 4,270 rows, and verifies
all completed bodies in the retained image. At most the next published file may
exist outside that prefix, and its committed body must equal a source prefix.
It reports any unlinked/incomplete physical inodes, pending names and partial
progress tail. A completed writer requires all 4,270 bodies / 35,508,922 bytes,
169 directories, no extra file/tail, and a clean complete inventory. The separate
cold reader's receipt is joined if it ran. A failed writer must not have launched
that dependent reader. Passing the evidence audit does not convert an incomplete
workload gate into a complete one.

EVIDENCE-AUDIT.json records scope counts, exact image hashes, zero-mutation
callback observations, process receipts, comparison measurements, explicit
malformed-image expectations and full/prefix replay outcome. It states that no
adapter recovery, physical power-loss test or service-storage qualification was
performed. No SQLite, POSIX mount, hardware I/O or production adoption claim is
made. The parent must separately join this audit's own terminal receipt and
stdout to EVIDENCE-AUDIT.json before sealing any conclusion.
