# Shared-resource challenge

This isolated stage extends the frozen clock-history source. It exercises four
fixed actors on one synthetic board and one authority: GPIO, PWM sharing that
pad, an alias on another route, and an independent pad. Their compiled child
requests are invoked directly; no parent procedure or multi-role PAT is claimed.

The former plan omitted a fresh GPIO request while PWM was active. Replaying the
completed original GPIO request returns historical work and cannot test exclusion.
Matrix version 0.2 declares a fifth, original probe before effects. It expects
RESOURCE_BUSY but reserves its possible admission. Successful executions still
have four operations and four activations. The existing 512-operation global
ceiling is unchanged; the constant and 16-step matrices reserve 43 and 58 child
operations. Failed PWM/alias attempts retry the exact same original request bytes.

Capture uses a new, explicitly selected 0.4 transcript profile. Four registrations,
four compiled plans and the probe are retained before invocation. All 29 execution
tables and 15 configuration tables remain paired. The exact closed schedule uses
the original time origin and offsets 0, 10, 20 and 30 milliseconds. Refusals and
historical reads must leave both stores unchanged. A failed challenge retains its
actual admission/effect state; close is not a settlement claim.

This stage implements capture, independent request/schedule checks and targeted
resource assertions. Complete independent multi-actor board/authority folds,
current-source attestation, aggregate quotas and full qualification remain open.
No runtime/provider business logic, physical devices, live services, MCU execution,
or learning/promotion is added. Existing frozen evidence remains unchanged.
