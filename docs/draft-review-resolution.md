# Draft review disposition

The [first independent review](draft-review.md) inspected earlier hashes retained in `research/protocols/draft-review-inputs.json`. The following changes were applied to the working specification. They are design resolutions, not implementation verification or conformance evidence.

| Findings | Applied resolution | Remaining evidence |
|---|---|---|
| R1 stop blocked by lease/log | Separate bounded-stop admission, no conflicting lease wait, commissioned degraded-audit path | Disk-full plus unresolved-motion test |
| R2 stale queued authority | Execution-time fencing, queue invalidation, persistent floor/session reset, legacy quiescence gate | Delayed packet/reboot/partition tests |
| R3 forgotten keys | Server-issued replay namespaces, durable epoch floor, immutable intent separate from credentials/renewals, authorized lookup first | Canonical wire fixtures and crash/expiry/access tests |
| R4 conflated epochs | Distinct endpoint session, control generation, stream producer epoch; unknown legacy continuity and tiny handshake requirements | Manual intervention/adapter-only restart/endpoint reset tests |
| R5 cancellation races | Transition table, orthogonal cancellation state, evidence-based reconciliation preserving history | Exhaustive state-machine tests |
| R6 ambiguous timing | Separate uncertainty fields, cache-inclusive sample age, four deadline kinds, timer/epoch semantics | Clock skew/cache replay/wrap tests |
| R7 local procedure overhead | One durable procedure admission, local per-step checks and external barriers, partial progress rules | Bounded MCU execution and restart tests |
| R8 binding drift | Commissioned binding generation checked at execution; invalidation inhibits queued work | Firmware/objective/fixture change tests |
| R9 snapshot-watch gap | Replay cursor or subscribe-first handshake; explicitly weaker gapped fallback | Transition-at-subscribe and retention tests |
| R10 universal overclaim | Scope now defines an extensibility requirement supported per binding | Broad device matrix and useful adapters |
| R11 revision vocabulary | Glossary separates reusable types from commissioned bindings and authority | Machine-readable schemas and compatibility fixtures |

All eleven findings have corresponding prose changes. A follow-up reviewer confirmed the main conflicts were addressed and found a missing dispatching-to-canceled transition plus inconsistent epoch field lists; both were corrected, and the replay-key tuple now explicitly includes its namespace epoch. A second implementation-oriented review is needed when full wire schemas and the first runtime exist. In particular, the current description schema implements only a small exploratory subset; it does not encode these operation invariants yet.
