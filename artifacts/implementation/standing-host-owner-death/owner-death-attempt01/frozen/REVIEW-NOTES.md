# Latest-source and evidence join

The full 223-line sealed thirteen-cut PLAN was read, SHA256
647e0e5af9997f7312b752b4ebd42c8c90ba66d4301b0f7a149a1e5071c7ca9b.
Its revision04 checkpoint contracts were joined to exact tested freeze07 source
review SHA3711d1f51e70998691b86aa42ba697e78205f36c5d8776bc461245780a0751d2,
and sealed host packet index SHA72371ef7752f2e90f6e8b185c125b00b165b8b64ce50d8121680c5a24951249b.
An independent source reviewer fully read the 940-line store, 417-line
coordinator, 160-line fixture and 264-line native pipe and confirmed no production
hook/schema change is needed. All261 copied project/helper files are exact.

Revision06 corrected the topology contract to physical2 proof plus explicitly
validated driver lifecycle slot, giving actual3 claims in both families.
Revision07 corrected a living-owner capacity control only. The latest fixture
and production copies preserve these corrections. New harness files live outside
the13 host-image source names. No production diff is introduced.

The snapshot is keyed to the existing sd_mutations(number,host_key,endpoint_sequence),
sd_activations(number), sd_activation_versions(number,version) and
sd_episodes(episode_key) schemas. Original document bytes and SQL keys are retained.
After reopening, only row ownerEpoch, recoveryRequired and hostRevision may
change before observation, with exact next-epoch/next-revision values checked.
Activation envelope metadata may later change during an explicitly requested
collection; original activation/version bytes are checked before that phase.

Prepared mutations remain sequence-uncertain after STATUS until explicit
abandonment. Prepared/possible OPEN yields NOT_SEEN and the coordinator's
reconciliation refusal; only prepared OPEN may abandon. A possible send is never
reclassified merely from the parent's knowledge that its gate preceded handoff.

Native snapshot vectors below are (lifecycle,standingHigh,activationHigh,ACK,mutation).
The native RETIRE implementation saves standingHigh across its memory reset;
host retirement retains its prior live mutationSequence while the separate
RETIRE item records the accepted next sequence.

| Cut | Native vector |
|---|---|
|OPEN prepared/possible|0,0,0,0,0|
|OPEN reply; START prepared/possible|1,1,0,0,0|
|START reply|2,1,0,0,1|
|Collection; ACK prepared/possible|2,1,1,0,1|
|ACK reply|2,1,1,1,2|
|RETIRE prepared/possible|5,1,1,1,3|
|RETIRE reply|0,1,0,0,0|

OPEN/START have zero dispatch/loss/output. ACK/collection have one dispatch,
zero loss and output1; RETIRE has one dispatch/loss and output0. Read-only recovery
cannot change these or clock, generation, boot and standingHigh. Newly accepted
START does not dispatch without a later cycle; the harness checks that distinction.

The original qualifier is native-standing-original:4 / native-standing-attempt:4
at its absolute original root. Its actual original result is12 cases/638 assertions;
the prerequisite host run passed20 cases/173 checks. Source-pins.json binds the
original manifest/reservation/receipt/binary/output, parent attempts and image.
Copies under originals/ are audit-only and are never fed to the producer as a
new attempt. The native peer image SHA256 is
5ab180cb56526a352691583bbcec4033b85af0c38c6d46057b1f4ae0cd607399.

Initial source review tightened keyed snapshot evidence, accepted new START
checks, native FD identity and cleanup-before-case-publication. Root review added
exact reopen-field checks, all released-lease checks, independent parent audit
body/hash joins and driver/context counter invariants. These are harness evidence
checks, not changes to production behavior. Source review is not executed evidence.
