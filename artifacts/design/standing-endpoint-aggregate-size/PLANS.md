This is the complete initial catalogue:28 validation plans/88 rows and five codec plans/38 rows. A row below is a *required* predicate; the walker returns the stated failure token on the first false row. Boolean plans use token1 and their wrapper preserves the original boolean convention. A private reason token is not automatically a wire status: the original C caller still chooses input_fault, loss, unknown or a returned protocol status. No table invokes those actions.

Notation: `p+N` is the existing encoded request field; `t` is finite admission's existing32-byte snapshot (`nb/latest/complete/lease` at0/8/16/24); `C` is the standing32-byte configuration; `A` is the captured acquisition tick; `R` is a report; `O` is its existing observation; `D` is the returned finite description. `span(x,y)` is the complete unsigned64 modulo difference. Signed relations are marked s32. All other relations are unsigned at the field's original width.

| Plan | Rows, in exact order | Failure/use |
| --- | --- | --- |
| common_context (2) | request generation≠0; context handle≠0 | BAD_ARGUMENT; both syntax routines at their original common-field point |
| finite_call_id (1) | p+8≠0 | BAD_ARGUMENT, only original op≥CALL branch |
| standing_identity (2) | p+8≠0;32-byte p+12 digest nonzero | BAD_ARGUMENT, only standing op≥OPEN branch |
| mutation_identity (2) | p+44≠0; p+48≠0 | BAD_ARGUMENT after STATUS/OPEN exits |
| finite_description (7) | D.mask≠0; D.max_run≠0; D.max_run≤INT32_MAX; D.cancel≤1; D.result_length≤32; D.evidence_mask≠0; (D.evidence_mask &0xc1)==0 | BAD_ARGUMENT after successful describe callback |
| admission_shape (6) | captured run≠0; run≤D.max_run; nb<latest; latest≤complete; complete≠ABSENT; lease≠ABSENT | BAD_TIME |
| admission_start (1) | now<latest | START_EXPIRED |
| admission_horizon (3) | if nb>now then span(nb,now)≤INT32_MAX; span(latest,now)≤INT32_MAX; span(complete,now)≤INT32_MAX | BAD_TIME; conditional first row is the closed future-horizon operation |
| admission_lease (3) | complete≤lease; armed_until≥lease; now<lease | LEASE_INVALID |
| admission_after_guard (3) | now<latest; now<lease; armed_until≥lease | START_EXPIRED for first, LEASE_INVALID for next two |
| lease (3) | captured until≠ABSENT; until>now; span(until,now)≤max_lease_ms | Boolean for standing lease_valid; same predicates with LEASE_INVALID translation in finite ARM |
| configuration (24) | C0 s32≥−100000; C4 s32≤200000; C0 s32<C4; C8 s32≥0; C8 s32≤300000; C12 s32>0; C12 s32≤100000; C28==0; C29==1; C30==0; C31==0; C16≤60000; C16≠0; C18≤60000; C18≠0; C20≤60000; C20≠0; C22≤60000; C24≤60000; C26≤60000; C26≠0; C16<C18; C16<C20; C16<C26 | Boolean at original OPEN configuration_valid call; the six original loop iterations remain in their exact order |
| sample_sequence_prefix (2) | captured sequence≠0; sequence≥captured old | ST_GAP via original input_fault; exact-successor conditional stays C after these rows |
| sample_time_prefix (2) | captured A≠ABSENT; now≥A | ST_STALE; no epoch/sequence checks are moved |
| sample_old_time (1) | A≥O.acquired | ST_STALE; C selects only when old≠0 |
| sample_age (1) | span(now,A)<channel_max_age | ST_STALE; executes after old-time predicate |
| demand_range (2) | captured value s32≥−100000; value s32≤200000 | ST_QUALITY; C selects channel0 |
| feedback_range (2) | captured value s32≥0; value s32≤100000 | ST_QUALITY; C selects channel1 |
| quiet_epoch_sequence (2) | R.epoch==current feedback epoch; R.sequence>stored feedback sequence | Boolean after existing quiet header/evidence/mask checks |
| quiet_time (5) | private loss-handoff tick≠ABSENT; R.acquired>handoff; now≥R.acquired; span(now,R.acquired)<feedback_max_age; R.value==0 | Boolean, before any witness write |
| dispatch_zero_fields (3) | R.epoch==0; R.sequence==0; R.value==0 | Boolean after existing dispatch byte-shape checks |
| dispatch_time (3) | before≤R.tick; after≥R.tick; cutoff>R.tick | Boolean; dispatch_report signature and scalar entry captures unchanged |
| fence_admission (2) | captured fence≠0; fence>current floor | STALE_FENCE in finite/standing admission; resource-mask traversal remains C |
| transport (2) | kind==1; channel==0 | UNSUPPORTED only when previous syntax status was zero |
| reserved_lease (1) | p+52 uint64==0 | RESERVED; only standing op other than RENEW/RESUME |
| reserved_ack (1) | p+60 uint32==0 | RESERVED; only standing op other than ACK/RETIRE |
| status_cursor_zero (1) | p+45==0 | RESERVED for already validated page0/1 |
| status_cursor_nonzero (1) | p+45≠0 | RESERVED for already validated page2 |

Total:2+1+2+2+7+6+1+3+3+3+3+24+2+2+1+1+2+2+2+5+3+3+2+2+1+1+1+1=88 rows,704 bytes. Shared plans are stored once. Their per-call source views and failure translation remain caller code and must be charged. The transport plan does not replace discovery-session/boot/sequence logic; those ordered checks stay C. Configuration values retain their admitted ranges; timestamp rules retain the entire64-bit domain.

The two opcode metadata arrays contain exactly these `(opcode, length)` pairs. Finite: `(1,2),(16,72),(17,48),(18,10),(32,0),(33,44),(34,44),(35,44)`. Standing: `(1,3),(16,72),(18,10),(64,134),(65,66),(66,66),(67,49),(68,66),(69,66),(70,66),(71,66),(72,66)`. Finite length0 is trusted metadata selecting the existing CALL syntax branch, not an admitted zero-length frame. That branch still checks minimum88/argument bound, reserved bits, physical flag and primitive before final expected-length equality. No other table stores opcodes.

Codec rows preserve each original store/copy boundary:

| Codec | Ordered rows | Count |
| --- | --- | ---: |
| context | generation32; handle16; raw digest32 | 3 |
| finite_tail | now64 snapshot; armed_until64 snapshot; call_high_water32; held_mask byte | 4 |
| receipt | raw operation identity42; execution; cancellation; evidence; verification; held_mask; may_have_acted; reason16; revision32; queued64 snapshot; started64 snapshot; terminal64 snapshot; result_length byte; raw result with length reloaded immediately before copy | 14 |
| observation | raw report value4; tick8; sequence4; epoch4; quality1; continuity1; pending1; reserved0 | 8 |
| loss_witness | valid-shape1; continuity1; evidence byte; verification byte; raw sequence4; tick8; value4; output0; reserved0 | 9 |

Total38 rows,304 bytes. The receipt wrapper still rereads result_length after the copy to calculate its returned size. The loss-witness codec ends before duration/accounting; a later refusal still leaves precisely those nine writes. Its first valid-shape byte does not mean ST_WITNESS_VALID, which remains published only after successful accounting. No bulk codec replaces OPEN/RESUME/RETIRE/transition state changes or caches pointer-bearing configuration/arena objects across writes.

The observation codec's eight literal/copy rows preserve the current helper ABI. The response codecs preserve existing scalar read-before-write behavior per field and retain raw memcpy's existing defined-overlap scope. No row merges the six receipt byte assignments into a single copy. Constants/source-epoch callbacks, standing response-header memset and request opcode reload, page selection, the190-byte state-page copy and private QUIET_AT masking stay explicit C.
