# Independent retained-field reconciliation

Status: source-only design review. The original worksheet's total was arithmetically correct, but its unnamed state bytes did not establish that every promised lifecycle field was retained. This review replaces that assumption with the exact allocation below. No implementation, layout test or target fit is claimed.

The review found three substantive gaps: the retained mutation prefix must be actual version/opcode bytes rather than an invented reserved wire byte; reservation ownership must remain distinct from known quiescence; and initial input epochs plus loss/settlement evidence need explicit retained storage. The revised draft also makes suspended evidence collection and renewed preparation explicit. It does not add another memory buffer or remove an existing reservation.

## Exact 128-byte standing-state worksheet

Offsets are an accounting worksheet for a proposed fixed-storage representation, not a mandated C ABI or wire layout. Implementation must verify its actual complete static delta and stack usage.

| Offset | Field | Bytes | Required invariant |
| ---: | --- | ---: | --- |
| 0 | `standing_high_water` | 4 | Never cleared on standing RETIRE, finite OP use, BIND, transport reset or suspend; reset only with qualified new boot |
| 4 | `slot_kind` | 1 | EMPTY / FINITE_OP / STANDING_RECORD; distinguishes current record from high-water-only history |
| 5 | `lifecycle_revision` | 4 | Current non-wrapping control/lifecycle revision; not a sample or transport sequence |
| 9 | `last_mutation_sequence` | 4 | Last accepted control mutation in this standing namespace |
| 13 | `last_mutation_comparison` | 20 | Exact request bytes0..1 and48..65; version+opcode and18 typed body bytes |
| 33 | `lease_until` | 8 | Current prepared/active interval; changes only through accepted profile mutations |
| 41 | `activation_high_water` | 4 | Last allocated activation, never reset by ACK/renew/resume |
| 45 | `acknowledged_activation` | 4 | Highest contiguous durable ordinary-activation prefix acknowledged by host |
| 49 | `next_service_tick` | 8 | Bounded scheduler deadline, independent of observed acquisition times |
| 57 | `first_loss_tick` | 8 | First cause time for the current loss episode, or absent sentinel |
| 65 | `cleanup_deadline` | 8 | Exclusive installed loss-service deadline, or absent when no qualified timing exists |
| 73 | `quiescence_at` | 8 | Qualified acceptance time of aggregate quiescence evidence, or absent sentinel |
| 81 | `pinned_input_epoch[2]` | 8 | Exact expected local source epochs from OPEN; never overwritten by an unexpected observation |
| 89 | `completed_command_on_ms` | 4 | Completed commanded-on intervals; not measured energy or physical run time |
| 93 | `lifecycle_state` | 1 | PREPARED / ACTIVE / DRAINING / SUSPENDED_QUIESCENT / STOPPED_QUIESCENT / FAULT_UNKNOWN, as specified |
| 94 | `drain_target` | 1 | Suspend, terminal stop or fault; draining cannot forget why it began |
| 95 | `service_phase` | 1 | One bounded acquisition/control/feedback/loss phase; not an unbounded callback queue |
| 96 | `owned_mask` | 1 | Complete retained reservation; ordinary ACK and quiescence alone do not clear it |
| 97 | `quiescent_mask` | 1 | This first profile accepts aggregate evidence: zero or the whole owned mask |
| 98 | `first_loss_reason` | 2 | First cause retained; later clock/driver faults also remain visible in live flags |
| 100 | `standing_flags` | 2 | Explicit bit allocation below; no hidden extra boolean array |
| 102 | `ledger_head` | 1 | Index0..1, never unbounded |
| 103 | `ledger_count` | 1 | 0..2; all allocated unacknowledged ordinary activations occupy a slot |
| 104 | `pending_feedback_slot` | 1 | Slot0/1 or absent; no second in-flight output activation |
| 105 | `loss_command_state` | 1 | None/requested/possibly handed off/driver-finished/unknown; driver finish is not quiescence |
| 106 | `quiescence_witness` | 22 | Dedicated retained witness, independent of a full ordinary ledger |
| 128 | End | — | Total128 |

The 22-byte witness is source index1, quality1, evidence kind1, verification1, source sequence4, acquisition tick8, value4, settled controller-output code1 and reserved0 byte1. The witness's producer epoch is the corresponding pinned epoch and its interpretation is fixed by the installed aggregate quiescence contract. It is not a generic proof of every device's rest. A provider needing multiple independent retained quiescence witnesses or partial release is unsupported by this first standing profile. The existing finite OP profile keeps its own partial-quiescence behavior.

The two-byte flags budget reserves explicit bits: ever-possibly-acted, unresolved effect, disputed evidence, initial start occurred, prepared-after-resume, demand-ready, feedback-ready, witness-valid, first-loss-latched, loss-command-possible, counter-exhausted, demand-source-fault and feedback-source-fault; three bits remain reserved zero. Global boot/clock/platform/USART qualification remains in the existing common runtime, not another standing copy. Any later implementation requiring more state must change the worksheet and re-evaluate fit rather than hide it in padding or driver globals.

## Exact immutable-data reuse

The complete OPEN packet remains in the original192-byte immutable buffer under STANDING_RECORD. It now has an explicitly counted maximum134-byte shape, including two expected source epochs. Fields read there rather than duplicated in the128-byte state are: deployment digest32, recorded control generation/handle6, kernel ID2, configuration length/data33, declared resource mask1, original fence vector up to32, original initial lease8, outage/evidence modes2 and activation cap4. The current standing number is the retained high-water value **only while slot_kind is STANDING_RECORD**. When EMPTY/FINITE_OP, that same value is historical high-water only and cannot be returned as a current deployment identity.

OPEN exact replay compares its complete immutable packet, not the current lease, current revision, current fence floors, or current observation values. Thus renewal, resume, quiescence and a new control revision cannot make a changed OPEN look identical. No new OPEN may overwrite this buffer until RETIRE; finite admission must enforce the discriminator in the common core. FINITE_OP may use the buffer only after the standing record is retired, while the standing high-water field itself remains intact. A failed OPEN does not consume a new number or any fence.

The last accepted mutation comparison contains actual version/opcode bytes0..1 plus expected revision/lease/ACK/reason bytes48..65. Identity bytes2..43 are compared to retained OPEN; sequence bytes44..47 are compared to `last_mutation_sequence`. The expected revision from the last request is therefore retained separately inside the20-byte body even if the current lifecycle revision later advances. No inference such as `expected = current - 1` is valid after asynchronous loss.

All unused mutation fields are canonical zero. An exact duplicate of the last accepted mutation is recognized before checking today's expected revision and never reapplies effects; it returns current status with the retained accepted mutation identity. Rejected mutations do not consume the sequence and are not claimed to have a durable local refusal history. Older bodies are not retained and yield OLD_OR_FORGOTTEN without mutation; host history remains authoritative. No original response byte array, mutation digest or hidden mutation queue is promised. Lifecycle revision changes on accepted control/state transitions, not on each sample or pending feedback update; activation record state, sample identity and correlated response sequence describe those updates separately.

## Ledger, ACK and resumed evidence

The existing256-byte primitive allowance remains exactly allocated as driver state64 + configuration32 + controller working state24 + two observations48 + two ordinary records88. Each ordinary record retains its own activation ID and pending/terminal evidence state. Allocations are contiguous, with `activation_high_water - acknowledged_activation == ledger_count` while the record is live; overflow is checked before allocation. The host cannot ACK a pending/unknown/disputed record or skip a prefix. ACK frees only terminal records whose complete evidence is durably retained, and cannot release the owned mask or authorize a new effect.

Four tail bytes in each44-byte record must have an explicit final codec: previous output, requested output, bounded execution/possible-effect/verification flags, and evidence-kind/quality flags. They are not four unconstrained miscellaneous values. The remaining reason field is counted separately. The final layout must refuse combinations that would manufacture physical evidence from simulation or echo. If those exact fields do not express the selected qualified kernel's outcome, that kernel/profile is unsupported until the budget is revised.

Observation records preserve the last accepted identity/value/acquisition time. Invalid candidates set fault/quality state without lowering a retained accepted sequence or replacing the pinned epoch. At first loss, ordinary input snapshots and controller state freeze for diagnosis. Loss/quiescence acquisition uses its bounded driver scratch and the dedicated22-byte witness; it does not overwrite a full ordinary ledger or erase the trigger context. Dynamic records beyond those locations are not retained or claimed.

Each observation's two previously budgeted bookkeeping bytes are accepted-sample-pending-evaluation1 and reserved-zero1. A newly accepted sample sets the pending flag; bounded evaluation clears it. Duplicate publication cannot manufacture another trigger, and no additional last-evaluated sequence is silently retained. Foreground service owns the observation records; any ISR acquisition state is part of the64-byte driver allowance. The exact codec must retain quality/continuity separately from whether the sample is new to evaluation.

SUSPENDED_QUIESCENT retains both owned resources and its immutable loss/quiescence summary. Before RESUME, the trusted host must durably collect that summary and the complete ordinary ledger, with ACK watermark equal to activation high-water. RESUME is allowed only for a resumable, undisputed cause and unchanged ownership/epochs. It prepares a new absolute lease under the same deployment, moves to PREPARED, clears only the now-exported episode/witness and freshness-ready flags, and starts fresh bounded acquisition. It does not reset activation/high-water/ACK/cumulative counters or the original OPEN bytes. A subsequent START mutation, after fresh STATUS/host checks and local guards, permits output. This explicit preparation avoids silently overwriting evidence to obtain fresh inputs while paused.

STOPPED_QUIESCENT and FAULT_UNKNOWN cannot resume. The first profile retains its local reservation until explicit RETIRE after eligible terminal quiescence and durable collection; `owned_mask` and `quiescent_mask` are never conflated. On clock failure the time fields are absent as appropriate; a separately qualified protection mechanism must establish any claimed loss/quiescence behavior. No clock-failure evidence is manufactured from an ordinary timer deadline.

Initial PREPARED has no ordinary output history, while prepared-after-resume retains prior activation/ACK/accounting history. Both acquire under owned resources and may therefore have declared acquisition bus effects. Expiry excludes ordinary output and enters installed settlement without automatic release in either case. The initial-start/prepared-after-resume flags distinguish those histories; eligible RETIRE remains the release point.

Read-only STATUS is paged, not an additional retained transaction. Its proposed62-byte common response prefix plus a state payload capped at128 bytes fits190 bytes; observation/event pages carry48/44 bytes instead. Explicit canonical serialization uses the existing response buffer, and the request supplies its cursor. No per-host export cursor, response-history array or atomic multi-page freeze is included in this128-byte state. The host must detect changed state or preserve time-separated page evidence rather than combining it into a fabricated historical snapshot.

## Accounting equality and unsupported cases

The controller24-byte working allocation supplies last committed output-transition tick8, feedback deadline8, baseline demand4 and four declared phase/output/index bytes. The32-bit accounting field stores completed **commanded-on** intervals; while currently on, checked `u64` arithmetic uses the retained transition tick to compare completed time plus current duration against the installed fixed limit. It is not an unqualified physical energy integral. Renewal/resume never reset it, and overflow or an unknown dispatch time inhibits ordinary output. If another kernel requires simultaneous accumulators or dynamic budget state, it is outside this budget.

The revised allocation retains the128-byte protocol ceiling and32-byte total glue/padding allowance, so the proposed static delta remains160. No extra full digest, context tuple, original lease, original fence vector, mutation response, per-sample journal or ordinary trace slot is silently charged elsewhere. The source snapshot copies pin the consulted inputs at review time; root documentation changed later, and this packet does not claim its pins describe those later edits. Compiler layout, actual installed callback state, full static/stack/flash bounds and service timing remain unproved implementation gates.
