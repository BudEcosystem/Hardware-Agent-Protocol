# Independent common REVOKE uncertainty

Status: source-only; no candidate execution. The exact273-file freeze03 and
SOURCE-REVIEW are preserved and reverified under `history/source-freeze03`.
`revision-04.patch` records this narrow delta.

A successful standing STATUS or STOP can establish standing sequence knowledge
without establishing the fate of a separately retained common REVOKE. The row
save/read invariant now preserves recovery authority restrictions for every
nonretired common outbox and transport uncertainty while that outbox is possible.
It does not invent standing sequence uncertainty. RETIRE admission and both
retirement settlement paths reject an unresolved prepared/possible common outbox,
so no new RETIRE is handed off and no claims are released on that basis.

An exactly associated accepted/refused REVOKE response resolves only its own
transport possibility; a possible OPEN or standing mutation remains uncertain.
Known accepted REVOKE still permits bounded standing loss collection/ACK/RETIRE,
subject to the existing episode, prefix, sequence and dispute guards.

The twentieth proposed native control starts from accepted OPEN, records a
possible common REVOKE before handoff, reopens the host and observes STATUS.
It requires retained common uncertainty, fresh START refusal, no REVOKE resend,
serviceable STOP/collection without uncertainty erasure, and RETIRE refusal with
all claims retained. The original nineteen cases are unchanged. This is proposed
coverage, not passing evidence. Actual killed-owner checkpoints and the other
completion gates in PLAN.md remain outstanding.
