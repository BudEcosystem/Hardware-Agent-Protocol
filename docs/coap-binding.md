# CoAP binding requirements for HMS

Status: proposed HMS adapter requirements, 2026-11-06; no endpoint, transport library or hardware guarantee is implemented by this document. The [execution core](../spec/02-execution.md) defines operation states, replay namespaces, authority and evidence. This document applies those semantics to CoAP without making CoAP the HMS device model. [Reading evidence](../research/protocols/reading-coap-full.json) and [review notes](../research/protocols/notes/coap-full-review.md) identify the exact documents read and remaining scope.

CoAP offers compact resource access suitable for constrained IP endpoints. Its Confirmable messages improve delivery, but acknowledgements, tokens, caching and retransmission timers do not establish durable execution, physical completion, resource ownership or actuator deadlines. An Arduino-class endpoint can implement a small commissioned subset while a gateway owns durable admission; a GPU-class endpoint can expose the same operation semantics with larger payload/data-reference facilities. Neither endpoint needs to implement every optional CoAP extension.

## Scope and current specification baseline

The proposed initial binding uses authenticated unicast requests whose complete application body fits in one bounded CoAP message. The evidence baseline is the complete RFC 7252 text, its current errata records, and complete RFCs 9175, 8974 and 9876. RFC 9175 updates secure token processing and introduces freshness checks; RFC 8974 permits optional extended tokens; RFC 9876 replaces the content-format registration procedures. The current RFC 7252 errata index also lists RFC 7959 and RFC 8613 as updates. Those two specifications have not been fully read in this review: block-wise transfer and OSCORE remain separate profile/review work, as do Observe and reliable-transport bindings. Reading the references to them is not a claim to have read them. [RFC 7252 errata][errata], [RFC 9175][echo], [RFC 8974][tokens], [RFC 9876][formats]

A deployment must select an actual security profile, version and implementation before this becomes a release binding. RFC 7252's 2014 cipher requirements are not a claim that all of its security configuration advice is sufficient for a current deployment. For a DTLS profile, preserve its request/response and epoch matching rules and apply RFC 9175's token requirements. A proxy terminating transport security is inside the trust boundary; it cannot forward a caller's identity or authority merely by copying a string into a request. [RFC 7252 §§9, 9.1, 11.2][coap]

## What received messages establish

| Evidence | CoAP meaning | HMS meaning |
| --- | --- | --- |
| Local send succeeds | Local transport accepted a datagram | Dispatch may have occurred; no remote admission proof |
| Empty ACK for a CON request | The matching message arrived; a separate response may follow | Transport receipt only; no durable admission or physical completion |
| Piggybacked response | Request result is carried in the ACK | Interpret its application body and response code; `2.xx` alone cannot prove the capability's physical effect |
| Separate CON response | A separately acknowledged response, matched by token and endpoint/security context | Correlation evidence, subject to application operation ID, digest and provenance checks |
| NON response | Response without message-level delivery acknowledgement | May be lost; absence says nothing about prior effects |
| RST | Message cannot be processed in the receiver's available context | No proof of a physical reboot, operation cancellation or non-execution |
| 5.04 Gateway Timeout | A proxy did not obtain a usable result in time | Possible downstream effects remain unresolved |
| CoAP ping receives RST | The protocol endpoint responded | No proof of controller task health, fresh measurement, current lease or safe equipment state |

These distinctions follow RFC 7252 §§1.2, 4, 5.2, 5.7 and appendix A. Its separate response can arrive before the request's empty ACK. A client must support piggybacked, separate and NON responses as specified; a Confirmable request does not force a Confirmable response. [RFC 7252][coap]

## Identities and time are separate domains

| Field | Scope and requirement |
| --- | --- |
| CoAP Message ID | A 16-bit message exchange identifier with endpoint-scoped reuse limits. Never the HMS intent key, stream cursor, fence or boot identity. |
| CoAP token | Request/response correlation with the adjacent endpoint; a proxy may replace it. Never an end-to-end operation identity or authorization credential. |
| DTLS session and epoch | Security/matching context. Reconnecting or rekeying does not establish an endpoint execution-history reset. |
| HMS operation ID and caller key | Stable durable intent identity and request digest under the execution core's authenticated replay namespace. Preserved across transport retries and proxy hops. |
| HMS endpoint session | Changes when execution history resets; unknown continuity must remain unknown. |
| HMS control generation | Locally enforced resource authority and invalidation of obsolete queued work. |
| HMS timing policy | Immutable `not_before`, `latest_start`, `max_run_duration` and `latest_completion`, with clock domain, uncertainty and enforcement location. |

RFC 7252's default `ACK_TIMEOUT=2 s`, random factor `1.5`, and `MAX_RETRANSMIT=4` yield a last-retransmission span of 45 s and acknowledgement wait of 93 s. The default exchange lifetime is 247 s; the derived NON duplicate-retention lifetime is 145 s. These are protocol retention/retransmission calculations, not measured delivery bounds or physical execution expiry. For Message ID allocation, use the conservative RFC 7252 §4.4 prohibition on reuse within `EXCHANGE_LIFETIME`, including NON messages; do not use the shorter NON lifetime to weaken that rule. Acknowledged requests with pending separate responses need an independent application timeout. [RFC 7252 §§4.4–4.8, 5.2.2][coap]

Sleep scheduling may delay retransmissions, but the RFC keeps them inside the transmit-span envelope. Decreasing acknowledgement timeouts or increasing NSTART requires congestion-safety mechanisms; those settings are not a shortcut to real-time control. The local controller must enforce hard timing and loss-of-authority behavior. [RFC 7252 §§4.2, 4.8.1][coap]

## Required binding declaration

A commissioned binding must declare the fields below. Unknown or unsupported features remain explicit.

| Area | Declaration |
| --- | --- |
| Route and trust | Enrolled instance, resource URI mapping, proxy chain, authenticated principals, transport/object-security boundary and allowed destinations |
| Protocol subset | CoAP transport/version, implemented options/methods, extension support and supported Content-Formats |
| Sizes and capacity | Datagram/application/token/option limits; decoding depth; maximum pending requests, accepted operations and queued bytes; overload behavior |
| Recovery | Durable caller-key mapping and replay-floor owner; endpoint deduplication guarantees; execution journal; operation-status query and result retention |
| Timing | Configured retransmission parameters and derived lifetimes; application response timeout; admission and local execution bounds; clock uncertainty and reset/wrap handling |
| Authority | Resource lease/fence owner; execution-time checking location; queue invalidation; native cancellation/quiescence limits |
| Observations | Evidence kind, acquisition/receipt time, device-cache age bound, calibration, stream epoch/sequence and representation-cache policy |
| Failure policy | Ambiguous effects, reset recovery, interruption/continuation, independent watchdog and commissioned stop route |

## Proposed HMS binding rules

The CP identifiers are HMS design requirements, not clauses added to the IETF protocol.

| ID | Requirement | Source basis |
| --- | --- | --- |
| CP-01 | Keep the complete HMS intent semantics in an authenticated application envelope or a commissioned equivalent: target, action, arguments/units/frames, pinned revisions, endpoint session, control generation, replay namespace/key, immutable timing and required evidence. Resolve identity from the authenticated channel and commissioned route. Reject missing required semantics before effects. | CoAP defines resource transfer; application authorization semantics are outside its message identifiers (§§1.2, 9). |
| CP-02 | Persist normal admission, replay mapping and dispatch ownership atomically before native dispatch. Return an existing operation for an authorized same-key/same-digest retry; reject a conflicting digest. Maintain the replay namespace floor after individual records expire. Do not rely on CoAP duplicate caches for this persistence. | Message deduplication is bounded and normally SHOULD, with explicit relaxations even for some non-idempotent requests (§4.5). |
| CP-03 | Let the protocol library perform CON retransmission with the original message identity. After a possible physical send, application recovery queries the original operation or reconciles evidence; it never creates a new intent merely because a timeout, RST, lost response or 5.04 occurred. A native non-idempotent request with insufficient deduplication must not be blindly retransmitted by an HMS adapter. | §4 reliability covers messages; §§5.2 and 5.7 do not make effects transactional. |
| CP-04 | Treat a successful operation-creation response as durable admission only when the body confirms the HMS operation ID and digest. Completion and effect verification use the capability's stated evidence. A native `2.04 Changed` proves no more than the commissioned resource semantics support. | §§5.2 and 5.9 distinguish protocol response semantics, not physical evidence. |
| CP-05 | Use GET only for safe retrieval. An acquisition that energizes, moves, irradiates or otherwise performs an effectful procedure uses a mutation operation. Do not expose toggles, relative motion, dispense or cycle restart as PUT. Repeated PUT/DELETE must satisfy their actual idempotent resource semantics, including timers and exposure behavior. | §§5.1 and 5.8 require GET safety and GET/PUT/DELETE idempotence; POST is not inherently idempotent. |
| CP-06 | Enforce immutable latest-start and authority immediately before effects, including after queueing, sleep, retransmission or freshness challenge. Enforce run/completion policy locally once started. Protocol timeouts, Max-Age and Echo never extend the operation's budget. | §§4.8, 5.10.5; RFC 9175 §§2–2.5 establish different notions of time. |
| CP-07 | When request freshness is required, verify it by an authenticated HMS mechanism or integrity-protected Echo under a commissioned server policy. A challenge retry keeps the same HMS intent and original expiry. Reject obsolete intent rather than automatically making it fresh again. Preserve freshness through every proxy; an intermediary may not answer a challenge using an old unsafe request without re-establishing original-client freshness. | RFC 9175 §§2.1–2.5, especially proxy processing in §2.3. |
| CP-08 | Apply RFC 9175 secure token processing. For DTLS/TLS without cryptographic request/response binding, use noncolliding sequence tokens per new/rekeyed secure connection and manage exhaustion. If client state is lost, establish a security context that cannot accept old responses before resetting token allocation. Still check the HMS operation/digest in the response. | RFC 9175 §§4, 5.1. Basic RFC 7252 concurrent-token uniqueness alone is insufficient. |
| CP-09 | Keep application operation/queue/byte limits independent of NSTART. Empty ACKs release the protocol outstanding-interaction limit while work may remain. Reject overload before admission; a 5.03 retry hint does not authorize a new effect. Reserve bounded capacity for the commissioned stop path and maintain a local watchdog. | §§4.7, 5.2.2, 5.9.3.4. |
| CP-10 | Explicitly set `Max-Age=0` on dynamic operation/observation responses and mutation error responses unless a separately declared cache policy is safe. A client must still check acquisition time and uncertainty. Preserve private-cache/access-control boundaries; zero freshness is not a no-storage instruction. | §§5.6, 5.9, 5.10.5, 11.2. Cacheable responses otherwise default to 60 s, including errors. |
| CP-11 | Apply verified erratum 4948: cache lookup includes the request payload when applicable, as well as method and relevant options. Never reuse an authorization/error result across incompatible principal, authority or request-body contexts. Validate each result's HMS key/digest. | Erratum 4948 corrects §5.6; §11.2 imposes access control on cached values. |
| CP-12 | ETag identifies a resource representation, not an enrolled device, fence, global revision or freshness proof. If-Match can protect a resource update; it does not replace local physical interlocks, multi-resource reservations or execution-time checks. Revalidation does not refresh the sensor's acquisition time. | §§5.6.2, 5.10.6, 5.10.8. |
| CP-13 | A proxy must preserve HMS identity, digest, authority and timing semantics through translation. CoAP tokens remain hop-local. Authorize canonical resources using the same decoding rules as dispatch; decode percent escapes exactly once, preserve empty/trailing path segments and keep `coap`/`coaps` namespaces distinct. Limit destinations to commissioned routes. | §§5.7, 6, 11.1; RFC 8974 §2.3. |
| CP-14 | Do not interpret RST, dropping response state, closing DTLS or stopping retransmission as cancellation of physical work. Cancellation targets the existing operation and requires separate progress/termination evidence. Stop uses the execution core's narrow bounded exception and independent fallback; normal NSTART/network delay cannot be presented as a stop-latency bound. | §§1.2, 4.2, 5.3.2 and appendix A describe message-state behavior only. |
| CP-15 | The initial effectful route is unicast. Multicast discovery is candidate evidence with potentially missing, delayed or cached responses; it is not complete inventory, enrollment or a group execution transaction. Do not infer authorization from a link-format resource, `ct` hint or source address. | §§7–9, 11.3–11.5. Base multicast is NON and the RFC's DTLS modes do not secure it. |
| CP-16 | Declare and bound extended-token support rather than assuming every server accepts more than 8 bytes. Discover it statefully per hop, using a safe request, or use reliable commissioned capability evidence. Bound decoded sizes before allocation; test packet limits with security and all options present. Stateless request correlation cannot replace the durable HMS operation ledger. | RFC 8974 §§2–5; RFC 7252 §§3, 4.6. |
| CP-17 | Reject unknown required application semantics even when represented inside an otherwise understood payload. For new CoAP options, explicitly specify criticality, proxy-safety and cache-key behavior using the protocol's option-number rules; do not put mandatory expiry or authority only in an ignorable elective extension. | §§5.4, 12.2. |
| CP-18 | Pin the actual content-format/schema binding, validate types and finite values, and require explicit application semantics. Do not invent an operational Content-Format assignment. A future registration follows RFC 9876; identifiers 64998/64999 are documentation-only and 65000–65535 are experimental with no operational use. | §§5.5, 5.10.3; RFC 9876 §4. |

Except where another RFC or erratum is named, source section numbers in the table refer to [RFC 7252][coap]. These requirements strengthen the application contract; they do not imply that a generic CoAP server already implements HMS.

## Resource mapping sketch

Exact paths, compact field numbers, encodings, error codes and canonicalization fixtures remain wire-design work. A possible resource mapping is:

| Interaction | Resource semantics |
| --- | --- |
| Retrieve a pinned description | GET an immutable description resource; cache by actual digest and access scope |
| Submit an intent | POST a bounded operation envelope to an operation collection; `2.01 Created` identifies a durably admitted operation, not completed actuation |
| Recover a result | GET an authorized operation/status resource; include operation ID, immutable digest, lifecycle, effect certainty and evidence |
| Request cancellation | POST a cancellation request against the existing operation; receipt and observed termination remain separate |
| Retrieve an observation | GET a representation containing acquisition time, clock uncertainty and evidence kind; cache policy does not rewrite those facts |
| Install a bounded procedure | POST a fully validated finite procedure/resource commitment only if it fits the declared size and local runtime budget; larger transfers require a separately specified extension |

Application deduplication makes repeated operation submission refer to one intent even though POST is not generally idempotent. CoAP If-None-Match can help protect resource creation, but a lost creation response followed by a precondition failure does not resolve physical effects by itself. Query the durable mapping under authorization.

A legacy native CoAP actuator can be wrapped by an exclusive gateway for identity, journal, policy and evidence. The gateway cannot add a missing device-side deduplication ledger, queue-expiry check, physical feedback channel or atomic stop. Advertise those limits. If the native library can retransmit a relative-action POST into a server that does not suppress duplicates, that route cannot claim one execution even before a host crash. A weaker route is admissible only for actions whose declared physical semantics and risk assessment support it.

## Failure scenarios to validate

These are acceptance scenarios, not tests already performed.

| Scenario | Required outcome |
| --- | --- |
| A CON dispense request arrives; its ACK is lost | Retransmission cannot create a second HMS admission or second native dispense within the advertised persistence guarantee |
| Device acts and resets before returning a response | Recover durable evidence or report `outcome_unknown`; no new dispense from a new token/MID |
| Same caller key reappears after the CoAP duplicate cache expired | Return the existing operation or reject an expired replay namespace; never admit it as a new intent |
| Caller restarts and reuses a token while an old secure response is delayed | Old response cannot be bound to a new request; operation/digest verification also rejects mismatches |
| Empty ACKs arrive quickly for a slow actuator | Accepted operations and queue bytes stay bounded independently of NSTART |
| A request sleeps in a queue past latest-start | Reject before effect, even if its transport exchange and Echo checks were originally valid |
| Old request receives a new Echo challenge | Preserve the original intent deadline; do not revive expired authority or timing |
| A proxy refreshes Echo itself for an old unsafe request | Reject the freshness claim unless original-client freshness was established as required |
| An authenticated GET returns a cached measurement | Original acquisition time/evidence survives; receipt/revalidation time cannot make the sample fresh |
| A cached 4.00 response exists for a different POST body | Payload-aware cache key prevents poisoning the next valid request; mutation error caching follows the declared policy |
| Stop waits behind a CON exchange or a sleeping radio | Local commissioned watchdog/stop behavior bounds effects; network delivery is not claimed to have a hard bound |
| RST arrives after the client discards response state | Retain and reconcile the physical operation; do not label it canceled |
| URI has percent-encoded separators, empty segments or a trailing slash | Authorization and dispatch resolve the identical resource; no accidental aliasing or double decoding |
| Message exceeds token/body/option or memory budget | Bounded rejection occurs before native effects and without unbounded allocation |
| Multicast discovery loses the last endpoint response | Inventory is explicitly incomplete; silence cannot prove absence or release a resource |

## Release gates

Before implementation claims: resolve precise envelope/schema/canonicalization; pin CoAP/security libraries and options; check the current relevant RFC updates/errata; measure MCU RAM/flash, radio and timer behavior; implement durable admission and endpoint/exclusive-gateway enforcement; and validate the failure scenarios on the actual hardware. Protocol conformance, cache correctness, HMS replay/fencing and measured physical outcomes are distinct checks.

Subsequent lanes have completed the [Observe/Blockwise/reliable-CoAP review](coap-streaming-binding.md) and the [OSCORE review](oscore-binding.md). They close those specific reading gaps from the original base review above. Block-wise actuation still requires exact body-integrity, bounds, assembly identity, no-effect staging and recovery rules in an implemented adapter. Request-Tag remains an ephemeral body identifier, not an HMS operation ID. Sensor-stream retention, selected TLS/DTLS stacks and secure group communication remain separate work. None of these bindings is enabled by reading its specification.

[coap]: https://www.rfc-editor.org/rfc/rfc7252.html
[errata]: https://errata.rfc-editor.org/search/?rfc_number=7252&presentation=records
[echo]: https://www.rfc-editor.org/rfc/rfc9175.html
[tokens]: https://www.rfc-editor.org/rfc/rfc8974.html
[formats]: https://www.rfc-editor.org/rfc/rfc9876.html
