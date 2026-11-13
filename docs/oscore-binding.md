# OSCORE security binding for HMS

Status: proposed application requirements, 2026-11-06. This document defines no implemented crypto stack, wire profile, hardware result or certification. It specializes the [CoAP binding](coap-binding.md) and [execution core](../spec/02-execution.md) for end-to-end object security. The [reading record](../research/constrained/reading-oscore-full.json) pins the source bytes and actual coverage; [review notes](../research/constrained/oscore/notes/full-review.md) separate published specifications, work in progress and HMS decisions.

OSCORE can protect an HMS intent across a forwarding proxy without giving that proxy the application keys. It does not supply durable physical-operation deduplication, actuator authority, completion evidence, timely delivery or a safe reset procedure. The proposed first profile remains authenticated unicast, with one bounded complete application request. Block-wise transfer, Observe, group communication and HTTP translation require explicit commissioned extensions.

## Evidence and specification status

The review covers all of RFC 8613, including its 14 ASCII figures, deployment appendices and eight test vectors, and all of RFC 9668, including five figures and four tables. Official RFC Editor metadata retrieved for this review lists neither an updating nor an obsoleting RFC for either document. RFC 9668 is a separate EDHOC integration specification, not a formal update of RFC 8613. [RFC 8613 metadata][metadata], [RFC 9668 metadata][metadata9668]

RFC 8613 verified editorial erratum 8229 corrects §7.3: response binding does not prevent a dishonest server from preparing a response before receiving a request. Technical erratum 8230, proposing an additional unusable/invalid Recipient Context check in §8.4, is **Held for Document Update**, not verified. The RFC 9668 errata query returned no matching records. [RFC 8613 errata][errata], [RFC 9668 errata][errata9668]

The complete key-usage-limits draft `draft-ietf-core-oscore-key-limits-08` was read as work in progress. Only the first 250 lines of KUDOS `draft-ietf-core-oscore-key-update-15` and first 200 lines of EDHOC RFC 9528 were read. The KUDOS draft proposes replacing RFC 8613 Appendix B.2; it has not made that appendix obsolete in the published standard. These sources identify release work, not an enabled handshake or rekey profile. A full RFC 9668 read does not substitute for reviewing RFC 9528. [Key-limits draft][limits], [KUDOS draft][kudos], [RFC 9528][edhoc]

## Trust, fields and identities

The verified OSCORE context identifies a commissioned peer. Map that peer to the enrolled physical instance or declared gateway and then evaluate HMS actor/delegation scope. An authenticated gateway is not automatically the authenticated physical device. A shared credential cannot establish which human or agent originated a request unless a separate validated delegation binding provides that evidence.

| OSCORE/CoAP element | Security meaning | HMS treatment |
| --- | --- | --- |
| Inner Code, Uri-Path, Uri-Query, options and payload | Encrypted and integrity protected under the context | Carry and validate the complete operation semantics here, including target, stable caller key, intent digest, generations, timing and required evidence. |
| Sender ID, Recipient ID, ID Context, Partial IV | Context lookup, key/nonce derivation and message replay state | Never substitute them for an HMS instance ID, endpoint session, control generation, replay namespace or operation key. |
| Outer Uri-Host, Uri-Port, Proxy-Uri/Proxy-Scheme and network address | Routing fields that intermediaries can change | Do not authorize a physical target from these fields. Bind the protected target to the verified context and commissioned route. |
| Token, Message ID, Type, ACK/RST | Correlation and messaging fields outside OSCORE's end-to-end protection | No durable-admission, reboot, cancellation, lease or completion evidence. |
| Outer response Code | Usually a transport-facing `2.04 Changed`, or `2.05 Content` for Observe | Read the authenticated Inner response and application evidence; an outer success code has no operation-state meaning. |
| `osc` discovery attribute | Hint that a resource uses OSCORE | Does not enroll a device, authenticate a description or provide context material. |

Different servers must have different security contexts so that altered routing cannot make an unintended server verify the request. Do not clone a context across independent controllers or unsynchronized replicas: shared replay windows and nonce allocation would require a separately reviewed coordinated design. The default proposed binding gives each endpoint relationship its own context. [RFC 8613 §§3–5, 9, 12.4, Appendix D][oscore]

Secrets remain in the commissioned credential store: Master Secret, Sender/Recipient Keys and Common IV are not model-visible metadata. Sender IDs and ID Contexts may be public yet reveal linkable identity information. Logs should record an access-controlled context reference, verification outcome and source provenance rather than keys or plaintext credentials. OSCORE does not conceal all traffic timing, length, addressing or correlation metadata. [RFC 8613 §§12.3, 12.6, 12.8][oscore]

## Message replay, intent replay and freshness

OSCORE protects accepted requests from being accepted again under the same context's replay policy. A legitimate client can still encrypt the same physical intent as a new message with a new Partial IV, and can do so again after rekeying. HMS must retain its principal/deployment/replay-namespace/caller-key mapping and immutable digest across those events. A fresh cryptographic context never clears the operation ledger or authorizes redispatch.

An old request arriving for the first time can pass OSCORE replay verification. RFC 8613 only establishes that it is no older than the security context. Effects require the independent latest-start, control-generation, authority and state checks in the execution core. Use an authenticated request-freshness mechanism where required, such as the commissioned Echo policy in the [CoAP binding](coap-binding.md), and recheck before each relevant effect after queueing. Echo/challenge retries preserve the original HMS key, digest and expiry; a refreshed challenge cannot revive an expired intent. [RFC 8613 §§7.1–7.5, 12.5][oscore]

Response binding ties a protected response to the request's `kid` and Partial IV. It does not prove that a reported sensor sample was acquired after that request, nor that an actuator completed its task. Preserve acquisition time, clock domain/uncertainty, device-cache age and evidence kind. A truthful server may return an old stored sample in a newly protected response. Apply verified erratum 8229 when describing dishonest-server behavior. [RFC 8613 §7.3][oscore], [erratum 8229][errata]

The protocol implementation must allocate Sender Sequence Numbers atomically and atomically validate/update replay state, updating the replay window only after successful cryptographic verification. Preserve request-to-context/Partial-IV associations while responses remain eligible; do not reuse a stale association for a later operation. CoAP retransmission, replay rejection and HMS retry recovery are separate state machines. A lost response after possible actuation produces reconciliation or `outcome_unknown`, not a fresh operation. [RFC 8613 §§7.2, 7.4, 8][oscore]

## Reset, persistence and exhaustion

Commission one explicit recovery method before allowing effects. The implementation must never restart a sequence counter at zero under a previously used key or clear a replay window and immediately accept old traffic. Preserve the distinction between security-state recovery and the endpoint execution history.

| Event | Required recovery behavior |
| --- | --- |
| Sender counter is lost but keys survive | Restore a provably unused range or establish new keys/context before transmitting protected data. No guessed increment or random unproved counter reset. |
| Recipient replay window is lost | Preserve/recover trustworthy replay state, perform the specified fresh challenge recovery, or establish a fresh context. Reject ordinary effects while recovery is unresolved. |
| Execution history resets while security state survives | Establish a new authenticated HMS endpoint session and reconcile physical work. Successful OSCORE decryption alone cannot detect this history reset. |
| Security keys rotate while execution history survives | Preserve HMS operation records, replay floor and endpoint-session continuity where independently established. Rotation alone is not evidence of a physical reboot. |
| Both execution and security continuity are unknown | Disarm/deny new ordinary mutations, retain possibly executed operations, establish the commissioned session and reconcile before new authority. |
| Sequence/key budget or credential validity is exhausted | Stop using the affected context according to the reviewed policy; re-establish security without erasing unresolved operation state. The local loss-of-contact/authority policy still applies. |

RFC 8613 Appendix B.1.1 gives a flash-write reservation example using `SSN2 = SSN1 + K + F`. It is usable only when write-delay/failure and send-rate bounds prove the post-reboot value exceeds every previously used sequence number. A storage API returning success without the required durability evidence is insufficient. Flash endurance, write interruption, rollback and repeated power-loss behavior need measured implementation evidence. This document selects no numerical `K` or `F`. [RFC 8613 §§3.3, 7.5, Appendix B.1.1][oscore]

Appendix B.1.2's replay-window recovery uses a protected Echo challenge before normal request processing. The server first restores safe sender allocation and uses its **own new Partial IV** for that challenge response; reusing the request nonce after losing replay knowledge would defeat the uniqueness argument. Only a request verified as fresh establishes the new replay-window lower bound. This security recovery does not reconstruct an operation journal or prove that pre-reset effects did not occur. A client that loses notification state must also re-establish observations as described in Appendix B.1.3. [RFC 8613 Appendix B.1][oscore]

Appendix B.2 derives contexts repeatedly from existing shared material, requires good randomness at both endpoints and does not provide forward secrecy. Its state/cache, race and replay handling are part of the procedure, not optional details. For HMS, do not silently enable it on an unknown-context error or treat it as an actuation handshake. A selected implementation must review the current rekey work and choose a complete supported method. [RFC 8613 Appendix B.2][oscore], [KUDOS work in progress][kudos]

The Sender Sequence Number must be less than `2^40`; lower algorithm-specific limits also apply. This is a hard nonce-space bound, not a general safe lifetime of a key. A release profile must separately justify encryption count, failed-verification budget, message size, credential lifetime and recovery of any retained counters. The key-limits draft reinforces this distinction but remains work in progress; its numerical recommendations are not adopted here. Rekey capacity and failure behavior must be commissioned before exhaustion, including a bounded local stop/watchdog path if network security becomes unavailable. [RFC 8613 §§7.2.1, 12.6][oscore], [key-limits draft][limits]

## Proxies, errors and optional extensions

A forwarding proxy without OSCORE keys can delay, drop, reorder or redirect traffic and change unprotected fields. Integrity protects accepted application content; it does not guarantee availability or stop latency. An attacker can spoof an ACK to suppress retransmission, or an RST that disrupts an observation. Preserve independent local timing/authority enforcement and physical-stop behavior. [RFC 8613 Appendix D.5][oscore]

OSCORE-processing errors can be unprotected, including unknown-context, replay and decryption errors. Treat them as untrusted diagnostics. They cannot authorize insecure fallback, context replacement, a new operation key, success, cancellation or a claim that no effect occurred. Authenticated application errors produced after successful OSCORE processing are different evidence. Never downgrade a commissioned protected resource to plaintext because an error or discovery hint suggests doing so. [RFC 8613 §§8, D.5.3][oscore]

Unknown CoAP options default to encrypted Inner treatment under RFC 8613. An implementation must still reject unknown required application semantics; encryption does not make an unknown expiry or authority extension enforceable. Outer copies of Class E fields are discarded by the verifier rather than replacing authenticated Inner values. [RFC 8613 §§4.1, 8.2, 8.4][oscore]

If extensions are commissioned, apply these additional boundaries:

| Extension | Required distinction |
| --- | --- |
| Block-wise | Inner blocks can be authenticated individually; Outer fragments are assembled before OSCORE verification. Bound unauthenticated assembly by `MAX_UNFRAGMENTED_SIZE`, time, concurrent transfers and memory. No partial application may escape complete HMS intent validation. |
| Observe | Use authenticated Partial IV ordering, not the mutable Outer Observe value. Protect per-registration replay state, recognize lost continuity and preserve HMS stream epochs/gaps/acquisition age. A freshest notification is not proof that every change was delivered. |
| HTTP translation | Restrict the commissioned bijective CoAP mapping; outer HTTP status/headers do not supply authenticated application semantics. Use the specified OSCORE header/body mapping and a reviewed TLS policy for HTTP hops. |
| Group/multicast | Base RFC 8613's references to Group OSCORE are extension hooks, not a group security profile. Do not share pairwise contexts across a group or infer atomic group execution. Membership, sender authentication, rekey/revocation and HMS resource coordination require separate review. |

These boundaries follow RFC 8613 §§4.1.3.4–4.1.3.5, 7.4.1, 10–12 and its explicit references to a separate group-communication extension. The initial profile enables none of them implicitly. No-Response is likewise inappropriate as an assumed completion protocol for an effectful HMS operation.

## Handshake and deployment contract

The binding declaration must name how the Master Secret, Sender/Recipient IDs, algorithms and context lookup are established; credential validation/trust anchors; required forward secrecy; reset/rekey protocol; replay-window policy; allowed endpoints/routes; key-use limits; storage guarantees; and bounded failure behavior. Credential provisioning, replacement and revocation remain maintenance-authorized transitions. LwM2M's OSCORE object or an established secure channel is configuration evidence, not proof that these requirements were implemented correctly; preserve the secret-handling and enrollment limits in the [LwM2M binding](lwm2m-binding.md).

RFC 9668 permits an optimized EDHOC message_3 plus first OSCORE request. Its processing completes EDHOC verification, derives the context, verifies OSCORE and only then delivers the application request. Its §7 explicitly retains the normal access-control checks. HMS admission, durable intent recording, generation checks and local interlocks remain mandatory even on that first exchange. Handshake success does not grant actuation rights. [RFC 9668 §§3.3, 7][combined]

The combined flow applies to the default client-Initiator/server-Responder direction. A profile requiring EDHOC message_4 cannot use it; the successful OSCORE response provides the combined flow's confirmation. Connection identifiers must avoid collisions with current EDHOC sessions and relevant OSCORE Recipient IDs. Discovery attributes describe offered capabilities but cannot override the commissioned method or credential policy. The first HMS integration should use an explicit authenticated session/identity reconciliation step before ordinary effects; enabling a combined first mutation requires demonstrating all the same admission conditions. [RFC 9668 §§3–6][combined]

## Acceptance scenarios and release gates

These are required future checks, not executed tests.

| Scenario | Required result |
| --- | --- |
| Same intent is re-encrypted with a new Partial IV or new context | Existing authorized operation is returned; changed digest conflicts; expired replay namespace is rejected. |
| A valid old request first arrives after latest-start | No effect, even though OSCORE replay verification passes. |
| Power fails at every sender-reservation write boundary | No key/nonce reuse, including repeated reboot and storage rollback cases. |
| Server loses replay state after dispensing | Security recovery cannot replay the dispense or erase the unresolved operation. |
| A proxy changes host, port, token, Outer Code or an Outer Class E option | No wrong-target authorization or forged authenticated result; possible availability loss is reported honestly. |
| A spoofed unknown-context error follows an ambiguous send | No plaintext fallback or automatic new-key actuation; original operation is reconciled. |
| A response is authenticated but contains an old measurement | Freshness policy uses acquisition evidence and rejects stale state. |
| Crypto budget expires while an operation runs | No forbidden key reuse; local continuation/stop policy applies and the operation remains tracked. |
| Combined EDHOC succeeds for a principal lacking action scope | Deny application access before dispatch. |
| A handshake or rekey succeeds after execution-history loss | New HMS session/reconciliation is required; old queues/fences cannot silently revive. |
| Outer fragmentation never completes or exceeds its bound | Bounded discard before application effects, without unbounded allocation. |

Before enabling this binding: finish RFC 9528 and the selected authorization/key-establishment/rekey profile; check their current errata and algorithm guidance; pin reviewed implementations; exercise all eight RFC 8613 vectors and negative parsing/replay cases; validate power-loss persistence and HMS operation recovery separately; measure actual constrained-device resource use and local timing. Passing published cryptographic vectors alone proves neither durable operation semantics nor physical safety. This review downloaded and read specifications; it executed no acquired implementation code and operated no hardware.

[oscore]: https://www.rfc-editor.org/rfc/rfc8613.html
[metadata]: https://www.rfc-editor.org/rfc/rfc8613.json
[errata]: https://errata.rfc-editor.org/search/?rfc_number=8613&presentation=records
[combined]: https://www.rfc-editor.org/rfc/rfc9668.html
[metadata9668]: https://www.rfc-editor.org/rfc/rfc9668.json
[errata9668]: https://errata.rfc-editor.org/search/?rfc_number=9668&presentation=records
[edhoc]: https://www.rfc-editor.org/rfc/rfc9528.html
[limits]: https://www.ietf.org/archive/id/draft-ietf-core-oscore-key-limits-08.txt
[kudos]: https://www.ietf.org/archive/id/draft-ietf-core-oscore-key-update-15.txt
