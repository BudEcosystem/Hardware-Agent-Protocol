# Fixed original execution plan

Status: unexecuted source. Root reviews the immutable source freeze before any
invocation. A failed attempt remains intact and stops this matrix; corrections
require a separate source history and distinct exclusive attempt, never a limit
increase disguised as a retry.

All production, native C sources and original fixture bytes are exact copies of
the tested standing-host-deployment freeze07 closure. The only changed reused
source is the original Guardian's `fork` signature and closed rlimit tuple:
native children remain5CPU/256MiB/1MiBFSIZE, ordinary control children remain
30CPU/512MiB/1MiBFSIZE, and a separately named new capacity control profile may
use32MiBFSIZE with the same30CPU/512MiB. Registration, child-relation checks,
pidfds, signal masks, settlement and reaping are unchanged.

The root launcher has eight exact choices, each creating its own exclusive
`boundary-<profile>-attempt01` directory by default. The only optional flag is
`--attempt N`, a canonical integer1..16 selecting an exclusive directory. It
requires and pins every earlier result for that same profile; it never selects
an attempt automatically or overwrites a directory. A subsequent attempt still
requires review of the corrected exact source. Run sequentially, stop at first failure:

```
python3 -I -B run_checks.py negative
python3 -I -B run_checks.py storage
python3 -I -B run_checks.py mutation
python3 -I -B run_checks.py episodes
python3 -I -B run_checks.py activations
python3 -I -B run_checks.py keys
python3 -I -B run_checks.py fixed
python3 -I -B run_checks.py accounting
```

No script imports candidate code during source preparation. The launcher imports
the pinned Guardian only after hashing it and its helper. It freezes every
reviewed input, pins/rechecks both parent inventories and public244, holds and
hashes the actual interpreter descriptor before/after, and execs the fixed
control through that descriptor. It does not compile, relabel an evaluator or
rerun the original qualification.

Each profile gets one owned outer control, observed30-second wall deadline,
30CPU/512MiB, FD64/core0, TERM grace3seconds and the unchanged Guardian settle
bound8seconds. Each actual native fixture is a directly owned5CPU/256MiB child,
execed from its verified held native image FD. Every expected native exit must
be clean EOF exit0; reaping by itself is not success. Sole-thread/kernel-child
ownership is required. Stored/reported PIDs never grant signal authority.

The five capacity profiles have32MiB per-file caps for their new SQLite coverage;
negative/storage/accounting retain1MiB. The native child always lowers FSIZE to
1MiB. The32MiB setting is a finite execution ceiling, not proof that every legal
SQLite layout fits it. The controller uses DELETE journaling; one current DB,
its rollback journal, bounded evidence and logs fit a declared96MiB state-tree
observation ceiling. Sampling is not an atomic disk quota and may miss a transient
peak. The trusted fixed harness cannot select paths or create arbitrary files.
An unexpected fit failure is retained and fails this profile. The launcher also
limits observed state files to256 and retains actual high samples in its receipt.

The exact24 controls are grouped as follows:

| Profile | Controls and evidence |
| --- | --- |
| negative |8: qualification expiry before commit; driver expiry after possible commit/no send; installed context change; boot change after acceptance/sticky dispute; premature retirement; definitive refused original sequence/no false novelty; asynchronous automatic-ACK revision refusal followed by explicitly admitted different body;16 original conflicts retained with sticky dispute after the17th |
| storage |10: exception immediately before/after SQLite COMMIT for prepare, OPEN possibility, collection prefix, and RETIRE receipt; rollback-call exception followed by close/reopen; real SQLITE_FULL from a temporary fixed max-page setting |
| mutation |1:119 original prepared STARTs explicitly abandoned,120th ordinary intent accepted, ordinary overflow refused, six never-possible loss identities retained, loss reserve refuses extension, separate accepted common REVOKE plus ACK127/RETIRE128 settles and releases |
| episodes |1:24 actual SUSPEND episodes at request32; further ordinary RESUME denied before the eight-slot reserve; STOP/RETIRE retain all24 original witnesses |
| activations |1:100 actual synthetic transitions with pending/final versions, exact prefix/ACK, two short interrupted intervals preserving the500ms commanded-ON budget, explicit renewal,101st transition refused, terminal collection/retirement |
| keys |1:16 public prepared deployments explicitly abandoned,17th admission refused, all original keys replayed under withdrawn authority and conflicts refused, then16 finite public submissions canceled and17th finite owner refused in the same authority |
| fixed |1: actual public namespace writes exhaust the fixed partition; repeat overflow rolls back; sixteen-digit clock floor and owner reopen plus loss/retirement still fit reserved metadata/standing partitions |
| accounting |1: no native child; separate invalid-as-Journal in-memory schemas and direct SQL populate exactly16MiB charged values, then each partition/row overflow and unknown writer schema is refused. This is checker evidence only |

All real controls retain their SQLite DB, a raw request/decoded-response trace
across reopen, installed route/native counter snapshot, table counts and actual
logical charges. Original-key identity remains in the DB. The accounting case
retains no authority DB and explicitly reports direct SQL population, no public
writer records and no durable capacity proof. The outer reducer checks exact
ordered names, direct-child identities, exit/reap records, retained evidence/DB
hashes and current `/proc` absence; it never signals an identity from a receipt.

Exception tests are synchronous living-owner fault injection, not process death,
disk failure, rollback durability, power loss or arbitrary SQLite failure proof.
The13-cut sealed owner-death evidence remains separate. Neither scripts nor
source preparation touch physical devices, services, drivers, network or GPU.

Current remaining gates: simultaneous maximum histories across16 standing and16
finite owners; every possible compound failure/clock-floor/COMMIT interruption;
retained-data audit of any future results; physical protected storage and public
mount integration. No current source or future per-edge pass may erase these.
