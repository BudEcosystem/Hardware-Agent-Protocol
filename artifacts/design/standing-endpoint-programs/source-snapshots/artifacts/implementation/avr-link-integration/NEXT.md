# Persistent application and platform work still required

The current integrated executor accepts a finite OP with immutable latest-start, completion, run and lease limits. ARM renews only its context; it does not extend an admitted OP. One volatile operation/receipt slot remains. A loop in the hub that repeatedly submits finite OPs is not the standing prompted-application contract described in [prompt-to-PAT](../../../docs/prompt-to-pat.md).

Before a physical board claim, review/promote the isolated candidate through the repository process, then bind a specific board, I/O resources, driver manifest and provisioned identity. Establish oscillator/clock and interrupt-service bounds, queue/service latency, baud/electrical tolerance, finite EEPROM provisioning/exhaustion/power-loss behavior, trusted callback limits, local feedback and independent stop/loss behavior. Clock failure currently closes UART admission; a qualified independent degraded service path is still needed if QUERY/CANCEL must remain available under that failure. Repeat the combined stack/flash/state analysis for the actual installed drivers and stop service. Passing the current synthetic/native and cross-link checks cannot grant any of those qualifications.

The next coherent persistent software profile needs all of these together:

1. A renewable deployment identity and generation, explicit owner, finite resource budget and durable lifecycle, distinct from the immutable finite OP slot.
2. Bounded trigger definitions and local observations with sequence, acquisition time, freshness and quality. A foreground byte-assembly deadline cannot establish input age.
3. A deterministic local state machine with bounded feedback and actuations, sharing the same resource/fence arbitration as direct OPs, with explicit cancellation, draining and quiescence.
4. Explicit hub-disconnection, clock-loss, sensor-loss and ownership-loss behavior. Any permitted local continuation must be authorized by the installed deployment; novel conditions must inhibit or escalate according to that policy.
5. Host/GB10/other-brain lifecycle and resource contracts: adapter identity, driver binding, start/stop/restart ownership, bounded dispatch and observation, durable evidence/decision state, and reconciliation with endpoint claims.
6. Agent learning and PAT promotion tied to the exact observation/driver/deployment versions and recorded outcome evidence. Only the validated deterministic region should execute locally; new or unsupported situations return to the agent under the same limits.

Research and source review must first settle deployment renewal/restart semantics, durable input/effect identities, local trigger/feedback timing, shared arbitration, the supported board and brain APIs, and required outage behavior. Then implement one bounded standing deployment end to end with observable local input and feedback plus hub-loss tests. The present 193 unassigned SRAM bytes and 25 bytes inside the planning stack reserve are arithmetic headroom for this exact build, not permission to assume that a persistent profile fits unchanged.
