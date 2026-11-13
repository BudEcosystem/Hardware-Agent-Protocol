# EDHOC key establishment binding for HMS

Status: proposed application constraints, 2026-11-06. EDHOC can authenticate peers and establish keys for an HMS security context. It does not establish durable actuator authority, operation deduplication, timely arrival or verified physical completion. This document extends the [OSCORE binding](oscore-binding.md) and [execution core](../spec/02-execution.md); it enables no crypto stack or wire profile.

The [source record](../research/constrained/edhoc-full/reading.json) covers the complete RFC 9528 text, including security considerations, Appendices A–I, references, 13 figures and 15 tables. All figures/tables were corroborated in 25 selected PDF pages. It supersedes the introductory-only RFC 9528 coverage recorded earlier in the OSCORE lane for the same source bytes. It does not turn the earlier selected KUDOS or authorization-extension readings into full reviews. [Detailed review notes](../research/constrained/edhoc-full/notes/full-review.md) retain source status and scope.

## Evidence and current status

RFC Editor metadata retrieved on 2026-11-06 lists RFC 9528 as Proposed Standard with no updating or obsoleting RFC. Two technical errata remain **Reported**: 8258 proposes corrections to Appendix C.2's CDDL; 8272 proposes adding connection identifiers to the initiator's restriction on premature persistent storage. Preserve their status and review them when selecting an implementation. They are not silently applied to the archived RFC. [Metadata](https://www.rfc-editor.org/rfc/rfc9528.json), [errata](https://www.rfc-editor.org/errata/rfc9528)

The current IANA registry is newer than the RFC's initial tables. Exporter labels 24–28 now serve IEEE/EAP purposes; EAD label 1 carries EAP channel binding. The proposed HMS profile allocates none of these labels and enables none of these extensions. A future extension must use the appropriate registered or permitted private-use namespace and a reviewed specification; an unused value in a 2024 table is not a current allocation. [IANA EDHOC registry](https://www.iana.org/assignments/edhoc/edhoc.xml)

## Identity and authority boundary

| EDHOC evidence or field | Proposed HMS interpretation |
| --- | --- |
| Verified proof of possession and trusted credential identity | A commissioned peer identity eligible for separately scoped application authorization. |
| `ID_CRED`, `kid`, certificate reference, network address | Credential lookup or routing input; no independent physical-instance or actor authority. |
| `C_I`, `C_R`, selected suite, transcript hash | Security association metadata; never the HMS endpoint session, control generation or replay namespace. |
| Message 4 or authenticated responder application traffic | Key confirmation for this exchange; no journal admission, cancellation or completion receipt. |
| New output keys or `EDHOC_KeyUpdate` | Security-state transition; does not reset operation records or prove a physical reboot. |
| EAD supplied to an application callback | Untrusted/bounded input until its required independent checks and EDHOC verification complete. |

Validate intended peer identity, credential usage and validity, trust path or pinned key, and the commissioned revocation policy. Receiving a CCS or self-signed credential must not install its own trust anchor. A key shared by a gateway cannot identify a particular downstream legacy device or individual human/agent without another verified binding. Preserve that gateway provenance in HMS identity and evidence. No ordinary actuation is allowed under unauthenticated operation or unresolved TOFU enrollment. [RFC 9528 §§3.5, 9.8 and Appendix D](https://www.rfc-editor.org/rfc/rfc9528.html#appendix-D)

After cryptographic authentication, reconcile the enrolled instance, descriptor/binding/calibration generations, endpoint execution session and authority. The security library may supply peer identity; only commissioned HMS policy supplies action/resource/delegation scope. EAD callbacks must not install trust, expand authority or actuate simply because a parsed field arrived. EAD-based authorization, attestation or enrollment needs a separately selected and fully reviewed application specification. [RFC 9528 §§5, 9.5 and Appendix E](https://www.rfc-editor.org/rfc/rfc9528.html#appendix-E)

## Proposed first-profile constraints

The release declaration must select a concrete method and role, credential format and identifier types, allowed cipher suites and fixed preference policy, transport, maximum encoded sizes, EAD policy and confirmation mechanism. The four base methods all retain ephemeral-ephemeral DH. EDHOC negotiation does not choose the entire application profile. This document does not select an algorithm solely from the RFC's historical table or its small-message examples. [RFC 9528 §§3.2–3.9, 8](https://www.rfc-editor.org/rfc/rfc9528.html#section-3.9)

For the first HMS integration, complete authentication and an explicit protected session-reconciliation exchange before ordinary effects. If no protected responder application traffic supplies confirmation, use message 4 as specified. Stage CIDs and derived key state together and publish the association atomically only after the selected authentication/confirmation gates; the CID policy also addresses the concern in Reported erratum 8272. Handshake completion cannot bypass admission because the initial request is small or combined with message 3.

For OSCORE, follow Appendix A's derivation and ID mapping: exporter labels 0/1 with empty context produce Master Secret/Salt; the initiator's Sender/Recipient IDs are `C_R`/`C_I`, and the responder's are reversed. Enforce collision rules and byte-string/compact-integer conversion. Separate a context lookup handle from application identity. Keep secret key material outside model-visible metadata and logs. [RFC 9528 §§3.3, 4 and Appendix A.1](https://www.rfc-editor.org/rfc/rfc9528.html#appendix-A.1)

The [previous RFC 9668 review](oscore-binding.md#handshake-and-deployment-contract) covers the optimized message-3-plus-OSCORE exchange. Enabling a first mutation through it would require all the same credential, context, request, authority, durable-admission and timing checks before dispatch. A profile requiring message 4 cannot use that combined flow. The current proposal therefore keeps ordinary effects behind session reconciliation.

## Replay, deadlines and exact retransmission

Retain the principal + deployment + server-issued replay namespace + caller operation key and immutable intent digest across new handshakes, new application sequence numbers and key rotation. Re-encrypting the same intent must return the existing authorized operation; a changed digest conflicts. Rekeying does not revive an expired replay namespace. If previous dispatch may have occurred, reconcile it or retain `outcome_unknown`; a handshake error is not proof of non-execution. These are HMS requirements inherited from the execution core.

A fresh exchange can carry an intent that is already too old. Cryptographic aliveness does not place a bound on network delay, queue delay or the age of a sensor sample. Check latest-start, generation/fence, lease, interlocks and required fresh state immediately before the relevant effect. Challenge retries retain the original operation key, digest and expiry. A fresh challenge must not extend an expired command. Key confirmation and authenticated observations preserve their actual evidence kind and acquisition age. [RFC 9528 §9.1](https://www.rfc-editor.org/rfc/rfc9528.html#section-9.1), [OSCORE freshness requirements](oscore-binding.md#message-replay-intent-replay-and-freshness)

Within EDHOC, retransmit the exact previously generated message. Rebuilding it with a different randomized signature can encrypt changed plaintext under the same key/IV. Keep this exchange cache separate from durable operation deduplication. A genuinely new negotiation attempt uses a fresh ephemeral key pair and retains the commissioned preference policy. Forged errors cannot authorize plaintext fallback, arbitrary trust replacement, new actuation or a false outcome. [RFC 9528 §§6–7](https://www.rfc-editor.org/rfc/rfc9528.html#section-7)

## Reset, key state and constrained resources

Fresh ephemeral keys require a qualified random source and safe DRBG state across reset. A boot counter alone supplies no secret entropy. Power failure, rollback, repeated startup, entropy-source failure and state erasure need explicit tests. A security association can change without an execution-history reset, and execution history can reset while keys survive. Track both independently; deny ordinary effects until unknown execution continuity is reconciled. Apply OSCORE sender-counter/replay-window recovery separately. [RFC 9528 §§9.2, 9.8](https://www.rfc-editor.org/rfc/rfc9528.html#section-9.8), [OSCORE reset policy](oscore-binding.md#reset-persistence-and-exhaustion)

`EDHOC_KeyUpdate` is not a replacement for fresh ephemeral DH when recovery from key compromise is required. It needs stored `PRK_out`, an agreed update context and a defined old-key retirement procedure; the RFC explicitly states weaker security properties than rerunning EDHOC. Do not infer post-compromise recovery or reset the HMS ledger from a successful update. Keep it disabled until a complete update/synchronization/recovery profile is selected and qualified. [RFC 9528 Appendix H](https://www.rfc-editor.org/rfc/rfc9528.html#appendix-H)

Bound all attacker-controlled work before deployment: incomplete handshakes, transport fragments, credential paths and candidate keys, EAD item counts, encoded lengths, parser depth, retries, public-key work, cache lifetime and diagnostic output. EDHOC has no intrinsic DoS protection or universal maximum message length. Reachability challenges mitigate only some attacks. A selected profile may decline Appendix G's long-plaintext extension. The 101-byte example handshake is not a RAM, flash or worst-case latency measurement. [RFC 9528 §§1.2, 3.4, 9.7 and Appendix G](https://www.rfc-editor.org/rfc/rfc9528.html#section-9.7)

Handshake flooding or credential retrieval must not starve installed local timing, stop or watchdog behavior. If an endpoint cannot meet measured crypto/state budgets, use a commissioned gateway and state precisely where authentication terminates. Do not advertise end-to-end physical-device authentication merely because the gateway completed EDHOC.

## Future acceptance scenarios

These are required qualification scenarios, **not executed tests**.

| ID | Scenario | Required result |
| --- | --- | --- |
| EDHOC-01 | Valid exchange with an untrusted, wrong-role, revoked or wrong-instance credential | No usable HMS authority or ordinary effect; bounded failure and accurate provenance. |
| EDHOC-02 | Replayed/reordered handshake messages or randomized retransmission | Only expected state transitions; retransmission uses retained exact bytes; no key/nonce reuse. |
| EDHOC-03 | Same operation under new keys; same key with altered digest | Existing authorized operation or conflict; no redispatch or replay-floor reset. |
| EDHOC-04 | Valid command first arrives late or expires while queued | No start after latest-start; authenticated delivery cannot extend its lifetime. |
| EDHOC-05 | Power loss at each key/CID/DRBG publication boundary | No repeated unsafe ephemeral state, partially usable context or guessed continuity. |
| EDHOC-06 | Execution reset with keys intact, or key rotation with ledger intact | Independent security/execution identities and conservative reconciliation. |
| EDHOC-07 | Forged error, unknown critical EAD or credential-fetch amplification | No policy downgrade, premature enrollment/effects or unbounded resource consumption. |
| EDHOC-08 | Maximum commissioned handshake load during local work | Measured memory/work bounds and required local stop/watchdog timing hold. |
| EDHOC-09 | Lost response after a combined first request might have acted | Original intent remains tracked; retry reconciles without a fresh actuation key. |
| EDHOC-10 | Key-update loss, disagreement or stale-key traffic | Explicit recovery/retirement behavior; no authority reset or unsupported healing claim. |

Release still requires the selected profile and current algorithm guidance, implementation review, RFC 9529 trace/vector coverage, negative parser/public-key/credential cases, interoperability, reset/rollback tests, measured target resources and physical timing evidence. This lane completes a specification-reading gap. It ran only original archival checks and document extraction/rendering; no downloaded crypto/controller code, vectors, emulation or hardware was executed.
