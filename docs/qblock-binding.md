# Q-Block transfer requirements for HMS

Status: proposed extension, reviewed 2026-11-06. HMS has no implemented or qualified Q-Block network adapter. This document extends the [CoAP proposal](coap-binding.md), [large-object and observation requirements](coap-streaming-binding.md), and [OSCORE proposal](oscore-binding.md). It preserves the [execution contract](../spec/02-execution.md) and [bounded procedure requirements](../spec/07-constrained-binding.md#bounded-dynamic-procedures). Requirements below are HMS design decisions unless explicitly attributed to the RFC.

The complete [RFC 9177][qblock] text was read: 2,154 LF-delimited lines, all 20 figures, five tables, references, and Appendices A/B. All figure/table pages were visually corroborated on 21 selected PDF pages out of 41; the remaining PDF pages were not visually reviewed. Current official metadata lists Proposed Standard with no updates or obsoletion; the [errata query][errata] returned no matching errata. The [current IANA registry][iana] confirms Q-Block1 **19**, Q-Block2 **31**, and `application/missing-blocks+cbor-seq` **272**. The [receipt](../research/constrained/qblock-full/reading.json), [review notes](../research/constrained/qblock-full/notes/full-review.md), and [offline verifier](../research/constrained/qblock-full/verify.py) retain exact sources and scope. The previous lane's selected Q-Block reading remains unchanged.

## Select the transport deliberately

Q-Block targets large bodies over NON CoAP exchanges, especially asymmetric loss. It supplements Block1/Block2; it is not a general replacement or a real-time transport. Reliable transports gain little from it, and increasing CON `NSTART` requires congestion tuning outside RFC 9177. Implementations must support both Q-Block options or neither, use CON for reliable UDP capability discovery, and reject unknown critical/unsafe options. Do not discover support by sending an effectful trial operation. Fallback to ordinary Blockwise must retain the same inert object or durable HMS intent; it must not create a second physical action. [RFC 9177 §§3–4.1, 7.1][qblock]

Use Q-Block only on commissioned unicast routes with explicit peer identity, security, message/body capacities, `MAX_PAYLOADS`, congestion parameters, quotas and retention. The RFC requires the peers to share `MAX_PAYLOADS`; its negotiation is outside the specification. Multicast Q-Block2 requests are ignored by servers. Mixed CON/NON delivery for one body is disallowed. These constraints cannot be inferred from a generic CoAP descriptor. [RFC 9177 §§4.8, 7][qblock]

## Assemble one complete, immutable body

Each Q-Block1 payload is a new CoAP request. All payloads of the body require the same Request-Tag, and different bodies require different tags. Response blocks require one ETag for the representation, with a different ETag for different representations. Content-Format describes the whole body. Unlike ordinary Blockwise size estimates, Q-Block requires an **exact, unchanged Size1 or Size2 on every corresponding payload**. A server must reject Q-Block1 lacking Request-Tag or Size1 with `4.00`. [RFC 9177 §§4.1, 4.3–4.6][qblock]

Scope an assembly by authenticated peer/security context, resource/method, matching options, representation format, transfer generation and the appropriate tag. Request-Tag, token and ETag are transfer or representation identifiers; none replaces the durable HMS operation key, immutable intent digest, controller session or binding revision. A proxy may replace Request-Tag on the next hop. Do not interpret its suggested counter encoding as a durable application sequence.

Check declared size against configured limits before reserving storage, then check all offsets, lengths, SZX/M consistency, complete byte coverage and final size. A final block can arrive before missing earlier blocks; it cannot trigger admission. A duplicate must never overwrite previously accepted bytes. RFC 9177 requires ignoring duplicate payloads under the same tag; an implementation that detects conflicting bytes should terminate/quarantine the assembly under its error policy instead of admitting either version. A valid final digest, when pinned by an authorized reference, must match the complete object.

No upload fragment may actuate hardware or advance a procedure. Use bounded whole-envelope assembly followed by normal validation/admission, or an inert object-staging resource followed by a separately authorized operation referencing the validated immutable object. The procedure pins format/schema, digest, exact length, compiler or capability revision, target bindings, instruction/data budgets and access/retention scope. Uploading a procedure is separate from validating, admitting, scheduling and executing it. Partial files or speculative decoded instructions remain unusable.

Persist a validated object only within its promised durability class. Acknowledging stored bytes in volatile RAM must not imply restart persistence. If restart loses the object or transfer state, report that loss and reconcile the original operation before reupload/retry. Never select a substitute object merely because a URI now resolves to new content.

## Recover bytes without replaying effects

`2.31 Continue` acknowledges a received payload set. Final Q-Block1 `2.01`/`2.02`/`2.04`/`2.05` responses carry whole-body receipt and resource-method semantics. They establish only the HMS state explicitly defined by the application response; none alone proves durable operation admission, physical completion or quiescence. A lost final response leaves the client uncertain about the application result. Reconcile the same HMS operation key and immutable intent. [RFC 9177 §4.3][qblock]

`4.08` with format 272 requests missing Q-Block1 blocks. Its payload is a CBOR **sequence of unsigned integers without an array wrapper**. Bound decoding work, entries, packet size and requested block numbers against the active body; suppress duplicate requests and respect ascending ordering. Resend the original Request-Tag, Size1 and block fields. `4.08` without that format has the different RFC 7959 behavior. Transfer feedback cannot authorize a new intent, extend its latest-start deadline or reset a retry budget. [RFC 9177 §§4.3, 5][qblock]

For Q-Block2, M/NUM distinguish the entire body, one block, the remainder of a set and a set-level Continue. Multiple recovery options can overlap; the server must send each block only once. Recover the response representation of the original request without repeating its physical action. Token association is not sufficient evidence that a lost operation never ran. [RFC 9177 §§4.4, 6][qblock]

## Preserve stream gaps and acquisition age

Q-Block2 may carry Observe notifications with a consistent Observe value across the body's original payloads; missing-block requests and their responses omit Observe. Continue retains the original notification relationship. The assembler must associate recovery responses with the correct representation without treating absence of Observe as a new stream. [RFC 9177 §§4.4–4.5, 10.2–10.3][qblock]

A server may stop an old transfer if the representation changes and the old copy is not retained. Missing-block responses then carry the new ETag and Size2. A later notification can supersede an incomplete earlier body. Thus Q-Block recovery does not establish contiguous acquisition or complete event history. Never combine different ETags, publish an incomplete body as a usable sample, or relabel last-block receipt time as sensor acquisition time. Preserve source epoch/sequence, acquisition clock and uncertainty, age including assembly delay, and evidence kind.

A latest-state stream may explicitly discard the obsolete partial sample. An event/acquisition stream must expose the lost range or unknown gap and retrieve a retained immutable object/log page if available. Changing ETags do not count missing acquisitions. A continuous stream needs bounded individual objects or pages with application cursors, not one unbounded Q-Block body. For a decision or procedure precondition, a complete but stale or continuity-unknown object cannot satisfy a stricter freshness/quality requirement.

## Cancellation and bounded resource use

RFC 9177 upload abandonment normally forgets tokens; a later missing-block response with an unknown token causes a Reset, and the server should delete the partial body. This is delayed, best-effort transfer cleanup. Different Request-Tags for one resource can remain concurrently active because a server cannot infer which one the client abandoned. Local timeout, Reset, dropped assembly and Observe deregistration are separate from HMS cancellation, stop and physical quiescence. [RFC 9177 §4.3][qblock]

Record abandonment against the old transfer generation, reject late callbacks into replacement state, and reclaim temporary storage within a finite local bound. Preserve claims for any admitted/dispatched operation until its own reconciliation and stop-evidence rules permit release. A cancel request must prevent new procedure dispatch according to the execution contract; bytes already at a server may still finish assembly. A separate authorized stop path and controller evidence remain necessary.

Cap body bytes, sparse offsets, blocks, active tags/tokens, incomplete assemblies, per-principal and total storage, missing-feedback entries, retry count, repeated starts and absolute transfer age. A trickle of blocks must not refresh the absolute deadline indefinitely. Advertised exact size is still untrusted input. Admission for temporary storage grants no authority to execute. An authenticated peer can also exhaust these budgets.

RFC defaults include ten payloads per set, a 2–3 second inter-set delay without Continue, a four-second initial missing-block wait with backoff, four retransmission requests, and a 247-second partial-body timeout. These are congestion/recovery parameters, not stop or execution guarantees. Preserve all required rate controls, including retransmission pacing and PROBING_RATE, and add a bounded aggregate scheduler so concurrent bodies cannot starve control/watchdog work. End expired transfers instead of compressing congestion delays to meet an action deadline. Qualify any shorter retention policy and disclose its recovery limits. [RFC 9177 §7.2, Table 3][qblock]

## OSCORE and proxies

Q-Block options can be OSCORE Inner class E or Outer class U, independently. Within one layer, Q-Block and ordinary Block options cannot be mixed; different Inner/Outer layers may use different mechanisms. The protected Inner body must be validated in its end-to-end context. Outer offsets and tags cannot establish the authorized inner procedure identity. Apply the selected RFC 9175 body-integrity and secure-token rules and preserve the HMS replay ledger across transfer/security reconnects. [RFC 9177 §4.1][qblock], [OSCORE binding](oscore-binding.md)

OSCORE does not protect Outer Q-Block manipulation. An intermediary can break assembly or repeatedly request large response sets through M-bit changes. RFC 9177 therefore discourages NoSec even when OSCORE protects the inner content. The HMS profile must select and qualify appropriate hop protection and resource controls for its route; authenticated content alone does not provide availability or bounded work. This review does not select or qualify a DTLS/TLS implementation. [RFC 9177 §11][qblock]

The proxy model reassembles complete bodies before forwarding; partial-block caching is outside its specified model. A later completed upload for the same resource may terminate an existing partial outward transfer. That policy is unsuitable as procedure ordering or cancellation evidence. Give immutable staged objects distinct identities and preserve operation sequencing above the proxy. Proxy cache loss may force a full fetch, so cap repeated origin work and preserve provenance, content version and age across the cache. [RFC 9177 §8][qblock]

## Acceptance evidence still required

| Case | Required result |
| --- | --- |
| Missing Request-Tag/Size1, changed exact size, inconsistent offsets/M bits | Reject boundedly before effects |
| Last block arrives first; old blocks or conflicting duplicates follow | No premature or mixed-body admission |
| Final response lost after admission or dispatch | Reconcile original operation; no fresh action key |
| Recovery contains array wrapper, huge integer/count, duplicates or unknown token | Bounded format/body checks; no amplification or unrelated transfer |
| New ETag arrives during recovery | Separate representation, explicit loss/supersession, unchanged acquisition facts |
| Transfer or observation canceled after an operation was dispatched | Preserve unresolved operation/claims; stop requires its own evidence |
| Restart loses assembly, staged bytes or old result tokens | Report loss/uncertainty; no implicit replay or persistence claim |
| Many valid peers send slow partial bodies or repeated recovery requests | Enforce aggregate quotas and absolute deadlines; control path remains bounded |
| Outer Q-Block fields are manipulated beneath valid OSCORE | No authorization expansion; bounded assembly/retransmission work |
| Concurrent proxy uploads replace the old outward body | Application object and operation identities remain distinct |
| Transfer completes after latest-start or source-age budget | Reject/defer according to original timing policy, never extend it silently |

These are proposed release scenarios, not executed protocol tests. A wire schema, selected security/CoAP stack, object-store guarantees, proxy profile, fault tests and measured endpoint behavior remain open. This lane closes the RFC 9177 reading gap only; it establishes no MCU footprint, physical operation, throughput, stop latency or complete-literature claim.

[qblock]: https://www.rfc-editor.org/rfc/rfc9177.html
[errata]: https://errata.rfc-editor.org/search/?rfc_number=9177&presentation=records
[iana]: https://www.iana.org/assignments/core-parameters/
