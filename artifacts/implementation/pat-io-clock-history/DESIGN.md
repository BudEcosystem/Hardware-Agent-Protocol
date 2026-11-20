# Independent clock challenge semantics

Compose the exact 0.3 clock-control grammar with independent PAT correspondence,
whole-domain static timing policy, installed configuration, trusted authorization,
board receipts/effects, authority events/claims, parent state and observation
sampling. The six original GPIO/PWM captures are data-only inputs. Their original
producer, runtime, provider, compiler and old tests stay unchanged.

The delayed-start case preserves the dispatch reservation at 1,000,000 and the
actual board guard at 1,000,099. A one-millisecond duration equals the reserved
100-millisecond run limit, so a derived no-start receipt releases authority claims
without a board activation or fence. It cannot move the dispatch origin forward.

Wall regression and monotonic mapping failure preserve every execution and
configuration table through the failed phases. Mapping-source restoration does
not clear the derived failure latch. Cached observations remain historical.
Reopen advances owner/session/clock epoch while retaining replay identities,
requests, dispatch origin, floors and authority claims. The original owner receipt
is canceled at reopen; reconciliation releases authority claims. Resume is refused,
parent cancellation settles and no later child is admitted.

Private component handoffs are derived only by the composed checker. Each handoff
must be consumed; public old-profile APIs and default component behavior retain
their previous refusals. No captured clock is rewritten. A well-formed control
record alone cannot prove a stop, ownership transition, refresh or outcome.

Passing these three exact challenges is not complete matrix coverage, current
configuration/compiler attestation, physical verification or PAT qualification.
No live project integration, physical I/O, database connection or runtime trial is
part of this stage. Original 180-second, 16 MiB scratch and 8,192-file boundaries
remain. Independent agent review is unavailable because helpers are usage-limited;
primary-agent source/diff review and adversarial tests are recorded explicitly.
