# Independent review corrections, source revision02

Status: unexecuted source corrections. The complete prior269-file review freeze,
its original `SOURCE-REVIEW.json` and exact baseline patch are preserved in
`history/source-freeze01`; every copied byte was verified before these edits.
`revision-02.patch` contains the exact change from that freeze. No parent/sealed
packet or public244 input was edited.

The prepared mutation gap is closed by an explicit authenticated
`abandon_prepared` operation. The store accepts only a durably `prepared`, never
`possible`, original and a correlated same-boot STATUS showing the unchanged
accepted endpoint mutation sequence. It commits `never_handed_off`, retaining the
original host key, body, digest and transmit sequence. Old-key replay returns
that terminal record. It does not send, decrement endpoint sequence or manufacture
acceptance. Only a separately requested, freshly guarded new key can create a
new admission. This also handles prepared ACK through a fresh deterministic ACK
key after explicit abandonment. Possible requests cannot be abandoned or retried.

Prepared OPEN has its own never-handed-off path with no prior effect, no standing
mutation and no common REVOKE outbox. Exact NOT_SEEN plus empty same-boot
descriptor and confirmed floors must join the original identity. The host keeps
all allocated numbers/fences; accepted historical OPENs separately derive the
expected observed native high-water/fences. A subsequent new deployment skips
unused allocated numbers without rolling back authority or accepting unexplained
endpoint-ahead state. A possible common REVOKE blocks abandonment and retains
its uncertainty and claims.

The actual coordinator now catches semantic decode failure after the stream has
committed rx and records the bounded original request and raw returned payload,
boot and response sequence against the owning deployment. That short commit
latches disputed/unknown/sequence uncertainty before raising. Later valid STATUS
cannot erase the dispute or release claims. The private original C bridge can
corrupt one real queued response and recompute its valid FCS; two controls exercise
wrong successful identity and malformed state through the real stream, not a
standalone endpoint mock or direct store-only injection.

Finite `InstalledPolicy.admit` registers a pure final `fresh(context)` check,
covering enabled policy and immutable installation, instead of checking only its
image lease. The same check is registered again through dispatch recheck, so
trusted reserve hooks cannot withdraw policy between admission and COMMIT without
rollback. Controls cover both submission and dispatch boundaries. Standing owner
epoch validation now uses Journal's safe-integer domain; a control reopens beyond
32-bit epoch without changing that original authority limit.

Fixture close now checks its actual owned child's joined EOF exit0. Inner and
outer result reducers reject any nonzero/signal fixture exit, even after the last
successful exchange. Reaping alone cannot produce a passing fixture result.

The proposed bounded run increases from10 to18 cases. The original native
qualification source/domain remains12 cases/638 assertions and is still not
executed in this candidate. Actual host-owner death at prepared and possible
outbox/collection/ACK checkpoints remains required. The new live-owner exceptions
and reopen controls are explicitly partial validation, not crash qualification.
