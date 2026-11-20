# Retained partial native validation

The final original run passed20 host cases and173 checks in26.770118636 seconds.
It also compiled both native images and ran the fixed original12-case/
638-assertion evaluator. The final result is
[host-attempt04/RESULTS.json](host-attempt04/RESULTS.json), SHA256
`fa91f9fa7aece57fe2cbdc9f1326c1946b7a466ffae13768776c8158b3ba9a40`.
Its20 native fixture processes returned cleanEOF exit0; four outer commands were
reaped, with owner empty/closed, no cleanup errors and no pending interrupt.

| Attempt | Retained outcome | Completed host cases/checks | Native/outer reaps |
|---|---|---:|---:|
|01|Invalid service/driver topology profile labels|0/0|0/4|
|02|Lifecycle slot incorrectly included in physical GPIO alias footprint|0/0|0/4|
|03|Capacity test requested forbidden running→running transition|9/81|10/4|
|04|All current controls passed|20/173|20/4|

Every attempt retained its own original reservation, runner/image/source pins,
12/638 result and published qualification manifest. Later attempts use distinct
run/attempt identities; previous failure evidence was not overwritten. The last
correction changed only the finite capacity control: one legal running transition,
five labelled trusted test-only ordinary events, exact eight-event capacity and
failed ninth-write rollback, then public cancel/ACK/terminal/release continuations.
It did not change production transitions or capacity limits.

The passing slice exercises actual native OPEN/START/activation/collection/ACK/
STOP/RETIRE; shared finite/standing and direct binding/lifecycle exclusion;
prepared-only abandonment and later route progress; lost replies with explicit
observation; committed-prefix/ACK ordering; raw wrong-identity/malformed-response
conflict retention; fresh policy withdrawal/replacement; owner epochs beyondu32;
and independent common REVOKE uncertainty. These are retained synthetic controls
for one literal installed PAT domain, not proof of every allowed application or
arbitrary configuration.

Root independently audited each attempt's original provenance, immutable frozen
bytes, process receipts and observed-absent identities. Exact copies of those
audit scripts/results are under audits/; [AUDIT.json](AUDIT.json) pins their
original and copied locations. Packaging reverified all1264 retained attempt
files against those four exact inventories, all244 public baseline files and
all259 source/copy pairs. Audit scripts were not rerun during packaging. The
original audits observed the16 outer and30 native identities absent; that is
historical evidence, not a new process-containment assertion.

The exact tested source manifest SHA256 is
`3711d1f51e70998691b86aa42ba697e78205f36c5d8776bc461245780a0751d2`,
preserved under history/source-freeze07 and host-attempt04/frozen. The tested
runner SHA256 is `ce0b8893a5446c56356322c68257d125bafa7171f99f78a7fc2a3e2cea88cd2c`.
Current SOURCE-REVIEW is a post-run inventory, explicitly distinguishing updated
documentation from those executed inputs. Production, tests, runner and helper
bytes stayed exact during finalization.

This packet is **PARTIAL native validation**, with actualOwnerDeathTested=false,
wholeHostQualified=false, physicalEligible=false, publicMountEligible=false and
protectedCapacity=false. Live-owner exceptions and reply loss do not qualify a
killed host, partial-frame death, host power loss or guardian loss. Logical16MiB
accounting is not reserved physical storage or aggregate compute capacity.
[NEXT.md](NEXT.md) preserves the remaining completion gates, including the
separate13-cut owner-death plan and broader negative/full-capacity controls.
