# Retained-field review changes

This source-only revision reconciles the initial design worksheet against the promised wire/lifecycle contract. It is a review summary, not a compiler result or a claim that an earlier draft was independently sealed. No public code or sealed AVR artifact changed; no project code, test, compiler, target or device was executed.

| Earlier draft | Reviewed design |
| --- | --- |
| 128-byte sum included duplicate digest/context/initial lease and ten unnamed state bytes | Exact field/offset allocation in MEMORY-RECONCILIATION; immutable identity/configuration/fences/initial lease read from tagged OPEN, with explicit ownership, loss times, flags and 22-byte aggregate witness |
| Current standing number and historical high-water could be conflated | Equality only while STANDING_RECORD; historical high-water survives RETIRE and intervening finite OP use |
| Last mutation prefix described as opcode/reserved | Retain actual version/opcode bytes0..1 plus typed bytes48..65; old expected revision remains separate from today's revision |
| OPEN126 omitted explicit expected source epochs | OPEN134 includes two exact local epochs; validates bindings before owned acquisition |
| STATUS described a snapshot plus a record without an exact size boundary | Read-only explicit pages:62-byte common prefix plus at most128 state bytes, or48 observation/44 event bytes; no export state or atomic multi-page snapshot claim |
| Initial PREPARED expiry released unstarted claims | Both initial and resumed preparation retain ownership until RETIRE because bounded acquisition may already have device/bus effects; histories remain distinguishable |
| Quiescence and ownership not fully separated in the byte worksheet | Separate masks; first standing profile supports one aggregate predicate/witness and no partial release |
| RESUME required fresh observations without defining preservation of suspended evidence | Host first durably collects summary and complete ordinary ledger; ACK equals high-water; RESUME prepares fresh acquisition and a later START allows ordinary output |
| ACK described durable prefix generally | Only contiguous terminal, known, undisputed records are ACK-eligible; ACK cannot release claims or skip a pending/unknown record |
| Ordinary evidence/loss storage boundaries underspecified | First-loss observation/controller snapshots freeze; bounded loss service uses charged driver scratch and dedicated witness even with a full ledger |
| Observation bookkeeping unnamed | One accepted-sample-pending-evaluation byte plus one reserved-zero byte per observation; no hidden last-evaluated sequence |
| Cumulative accounting could imply physical energy | Completed commanded-on milliseconds plus current checked interval against installed fixed limit; no physical energy claim and no reset on renewal/resume |
| Source links could appear to describe subsequently edited root documents | All18 exact inputs retained and hash-mapped under source-snapshots; explicitly point-in-time evidence with unchanged reading-scope limits |

The total proposal remains128 bytes standing state +32 bytes all additional glue/padding, using the existing256-byte primitive allowance and192-byte immutable packet storage only under enforced single-slot reuse. Static/stack/flash fit and service timing remain unproved. The unchanged arithmetic target is2015/2048 SRAM including512 reserved stack; no standing implementation has established it.
