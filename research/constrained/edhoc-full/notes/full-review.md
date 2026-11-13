# Complete RFC 9528 review and HMS implications

This review read the complete March 2024 RFC on 2026-11-06. Source scope, exact bytes and manual coverage are recorded in [reading.json](../reading.json). References below are primary publications or this repository's earlier source-backed reviews. Reading a reference entry does not imply reading the referenced publication. Findings marked as HMS decisions are proposed application constraints, not text imposed by the RFC on every deployment.

## Status, errata and bounded current follow-up

Official [RFC Editor metadata](https://www.rfc-editor.org/rfc/rfc9528.json) lists Proposed Standard, March 2024, originating draft `draft-ietf-lake-edhoc-23`, 82 pages, and empty updates/updated-by/obsoletes/obsoleted-by arrays. The [information page](https://www.rfc-editor.org/info/rfc9528) independently displays Proposed Standard in the selected opening text. These are snapshots at the retrieval timestamps, not promises about future status.

The [official errata query](https://www.rfc-editor.org/errata/rfc9528) returned two **Reported technical** records. Neither was Verified or Held for Document Update at retrieval:

| Erratum | Location | Proposed correction and bounded implication |
| --- | --- | --- |
| 8258, 2025-01-23 | Appendix C.2 | Group parentheses for EAD repetitions, an explicit `C_R` type, and a defined `header_map` rather than undefined `map`. A parser must reconcile the grammar appendix with the message definitions; copying the appendix into a generator without review is insufficient. |
| 8272, 2025-01-29 | §5.4.2 | Extend the initiator's premature-persistence restriction to `C_I` and `C_R`, alongside output/application keys. HMS should stage the whole association and publish it atomically only after the selected confirmation and peer-authentication requirements. This stronger local policy does not turn a Reported erratum into an accepted RFC correction. |

The complete [IANA EDHOC XML](https://www.iana.org/assignments/edhoc/edhoc.xml), updated 2026-08-31, was compared with the RFC's initial tables. Later registrations include exporter labels 24/25 for IEEE 802.15.9a key management, 26/27/28 for EAP-EDHOC MSK/EMSK/Method-Id, and EAD label 1 for EAP channel binding. The credential-type registry introduced by RFC 9668 contains CWT, CCS, X.509 and C509; its C509 entry refers to `RFC-ietf-cose-cbor-encoded-cert-20`. EAP entries refer to `RFC-ietf-emu-eap-edhoc-12`. Those exact reference strings are preserved; this review does not infer a published RFC number or claim to have read their specifications. Exporter, suite, method, error, EAD and credential-type registries are distinct namespaces. Current listed method values remain 0–3 plus reserved 23; no new method is implicitly enabled.

RFC 9668's complete prior review in [OSCORE notes](../../oscore/notes/full-review.md) covers combined EDHOC/OSCORE transfer. The present lane fills the missing base EDHOC read. KUDOS, the cited authorization/attestation/enrollment extensions, RFC 9529 traces, cryptographic analyses and underlying COSE/curve/KDF specifications are not newly fully reviewed here. Their presence in a bibliography supplies no release qualification. This bounded follow-up is sufficient to avoid claiming the RFC's initial registry is current; a selected extension still requires its own complete review.

## Sections 1–3: roles, encoding, credentials and profiles

[RFC 9528](https://www.rfc-editor.org/rfc/rfc9528.html) specifies ephemeral-ephemeral DH in all four methods, including methods authenticated with static DH keys. Table 1 gives illustrative total message sizes of 101/128 bytes for static-DH kid/x5t examples and 216/242 bytes for signature examples. These omit a universal maximum, implementation workspace, retransmission storage, credential parsing and transport costs. They do not establish AVR SRAM/flash fit, energy cost, watchdog responsiveness or handshake latency.

The initiator sends message 1; three messages establish output keys, with a fourth available for initiator-side key confirmation when no protected responder application message supplies it. Initiator identity protection covers active and passive attackers; responder identity protection covers passive attackers. Choosing CoAP client/server roles and EDHOC roles is consequential. There is no dedicated protocol-version field: method registration and a commissioned application profile matter.

`C_I` and `C_R` are connection lookup handles, intrinsically byte strings with a compact integer encoding for the one-byte CBOR integer representations. A byte `0x21` becomes wire integer −2, not a one-byte bstr wrapper. Other byte sequences keep bstr form. For OSCORE, the chosen local connection identifier becomes the local Recipient ID, and the IDs must not yield equal Sender and Recipient IDs. CIDs, a 5-tuple and transport tokens are not enrolled physical identities, actor principals or resource fences.

EDHOC does not fix transport, fragmentation or a maximum message size. Its transport expectations include correlation, retransmission, duplicate handling, flow/congestion control and appropriate DoS measures. CoAP reliable mode is recommended, especially with fragmentation. A serial deployment cannot assume these properties from a CRC-framed byte stream.

Credential identity is not the same as credential trust. X.509 uses DER in bstr, C509 its defined credential representation, CWT an untagged CWT, and raw public-key material an untagged CCS wrapper. Exact agreed credential bytes matter to transcript authentication; opportunistic re-encoding can break verification. ID_CRED may contain multiple COSE headers. A `kid` need not be globally unique; context selection and bounded credential lookup are required. A received self-signed credential or CCS must not create its own trust anchor.

EAD is an opaque extension channel. Its sign denotes criticality, while the registry records the absolute label. Unknown or unprocessable critical EAD causes an error and abort; noncritical data can be ignored. Padding label 0 is ignored. This is not a generic slot for actuator authority. The application profile must state transport, method, credential representation/algorithms, identifier types, EAD policy, intended endpoint identity and confirmation behavior. Cipher negotiation does not negotiate all those choices.

## Sections 4–6: derived keys, ordered processing and errors

Transcript hashes and labeled derivations separate key roles. `PRK_out`, `PRK_exporter`, handshake encryption keys and application keys must remain distinct in implementation and logging. Exporter label and context jointly identify purpose. Re-deriving identical bytes does not create a fresh nonce space. Secrets belong in a commissioned protected store, not agent-visible descriptions or diagnostic traces.

Processing is ordered per handshake. Unexpected or duplicate messages cannot be accepted as new transitions. Credential/EAD information may be offered to the application before a message's signature or MAC is verified. HMS callbacks at that point must remain bounded and must not grant authority, install trust, enroll a key or cause physical effects merely because the parser produced values.

The initiator should not persist output/application keys until it has verified message 4 or a derived-key-protected responder message and authenticated the responder at application level. The responder should not persist keys or send application data until application authentication of the initiator. Message 4 must be supported and used if no protected responder application traffic otherwise provides confirmation. Confirmation proves the peer has the derived keys in this exchange; it does not prove journal admission, effect completion, controller quiescence or a durable HMS boot identity.

Cipher-suite negotiation retains the initiator's fixed preferences, including more-preferred alternatives before its selected suite. An unprotected error cannot rewrite security policy. A retry after negotiation begins a new exchange with a fresh ephemeral pair. Unprotected error 3 can induce larger credential traffic; bounded retries and credential-reference policy are needed. Error 0 is reserved for internal success and must not appear as an EDHOC wire error. Diagnostic text is untrusted data. An error sender aborts; a receiver may continue if it suspects a forged error. None of those rules supply an operation outcome after a possible application dispatch.

## Sections 7–8: duplication and conformance

Retransmit the **exact existing message** if it is still relevant. Rebuilding a message from remembered state is unsafe when a randomized signature or another value changes under the same encryption key/IV. Retain retransmission state only as long as the transport/profile requires, with an explicit storage and timeout budget. This small exchange-level cache is different from HMS's durable operation-key ledger.

An RFC-conformant implementation need only support one authentication method, role and credential type, but the RFC's default conformance requirements include kid, the exporter, EAD, errors 1/2, and suites 2/3 unless an application profile overrides the suite requirement. Advertising EDHOC alone therefore says little about actual interoperability. The HMS declaration must enumerate its concrete subset and parameters.

## Section 9: security considerations

The protocol's aliveness, agreement, identity protection and forward secrecy are conditional cryptographic properties. Aliveness supplies no bounded network delay or physical latest-start guarantee. A legitimate sender may encrypt an old intent under newly negotiated keys. HMS replay namespaces, immutable digests, expiry, fencing and fresh-state checks remain separate.

EAD 1 and 2 cannot be relied on as confidential/authenticated application authorization against an active participant. Although EAD 3/4 acquire protection after successful processing, callbacks may occur earlier and external applications still own their security analysis. Transcript protection is not a certificate-policy engine. Verify allowed identity, credential usage and validity, certification path/trust anchor and revocation requirements. Deployments lacking trustworthy time need an explicit credential-validity strategy, not assumed wall-clock validity.

Fresh ephemeral key generation is mandatory at both ends. After reboot, a CSPRNG must not return to an earlier unsafe state. The RFC discusses fresh inputs or retained nonvolatile state when TRNG input is unavailable. A finite monotonic HMS boot counter can help uniqueness but is not secret entropy. Entropy acquisition, reseeding, power-loss behavior, rollback resistance and private-key erasure need implementation evidence. Public-key validation includes all-zero-result checks for X25519/X448 and the stated validation for NIST curves. Compact representation does not waive validation. Reusing one private key for signatures and DH needs its own security analysis.

The RFC's security-level discussion depends on method, MAC sizes and usage conditions; an eight-byte MAC does not justify a generic application-level 128-bit forgery claim. The RFC's 2024 post-quantum discussion is not a selected 2026 post-quantum deployment profile. Side channels, fault injection, deterministic-signature behavior, private-key protection and timely destruction of ephemeral/intermediate secrets remain implementation concerns.

EDHOC has no intrinsic DoS protection. Fresh or replayed message 1 can allocate state, trigger public-key work and amplify traffic. Reachability challenges mitigate some spoofing, not reachable malicious peers or all distributed attacks. Bound concurrent/incomplete exchanges, unauthenticated assembly, credential/EAD sizes, parsing depth, crypto work, retry count, cache lifetime and logging. Preserve local stop/watchdog execution independently of handshake load. Privacy also depends on CIDs, padding, credential exposure, network addresses, packet length and timing; encryption does not conceal all metadata.

## Section 10, references and Appendices A–I

All initial registration tables and both reference lists were read. Current IANA differences are listed above. The original RFC is preserved without applying Reported errata to source bytes.

Appendix A derives OSCORE Master Secret/Salt with exporter labels 0/1 and empty context, selecting the application AEAD/hash from the negotiated suite. Initiator Sender/Recipient IDs are `C_R`/`C_I`; responder IDs are reversed. Forward CoAP flow prepends `true` to message 1 and server-selected `C_R` to message 3; reverse flow swaps EDHOC roles and uses `C_I` for client messages. The transport prefix is outside the actual EDHOC message processing. CoAP success codes are transport results. Reliable transport, Echo reachability and optional block-wise handling do not replace application admission or a bounded reassembly design.

Appendix B specifies compact point representation and possible API conversion; calculating a square root alone is not point validation. Appendix C explains CBOR sequences versus arrays and COSE objects; Table 15's different encodings matter to parser tests. Its CDDL has the currently Reported defects described above. These definitions were read as data, not executed or treated as a checked parser implementation.

Appendix D makes credential content, intended identity, trust-path and revocation verification application responsibilities. Its unauthenticated/TOFU modes are vulnerable to active attacks before an external trust binding exists. HMS should reject ordinary actuation in that state. A proximity assumption needs evidence; being on a local radio or the same LAN does not establish enrollment.

Appendix E gives authorization, attestation and enrollment examples. Each needs its own registered semantics and security analysis; dependencies between concurrent EAD applications need specification. A CSR in message 3 is an example where external processing waits for successful message verification. Appendix F is a rudimentary example with method 1, IDevID/C509, CCS, EAD authorization and protected responder traffic. It is not an HMS-selected profile.

Appendix G extends long plaintext 2 by multiple KDF invocations with negative labels. Ordinary HKDF/SHA-256 output bounds yield 8,160 bytes; that is a KDF boundary, not an acceptable MCU receive-buffer budget. A profile may decline the extension. The proposed first HMS profile should impose substantially smaller measured bounds and reject unsupported long inputs before resource exhaustion, without inventing a numerical fit claim.

Appendix H's optional key update derives a new `PRK_out` using label 11 and an agreed context, then a new exporter using label 10. It requires retaining `PRK_out`, synchronizing the update event, and deleting old keys when no longer needed. It is explicitly weaker than a new ephemeral-DH exchange: compromise can expose future keys, so it is not post-compromise healing. An update cannot erase HMS intent history, turn a first arrival into a timely command, or identify a physical reboot.

Appendix I's example initiator/responder state machines were read in text and visually. `COMPLETED` and `PERSISTED` are EDHOC processing states, not HMS operation states. The appendix expressly omits credential/EAD processing and some verification/error details. Implementing only the diagram would miss required authentication and durability decisions.

## Remaining qualification

The binding document translates these findings into proposed constraints and future scenarios. No selected crypto library, RFC 9529 vector run, independent cryptographic audit, parser fuzzing, target memory measurement, timing/energy test, durable-key-store failure test, controller execution, emulation or hardware qualification occurred in this lane. The complete base-specification read is finished; implementation, profile, trust provisioning, current algorithm guidance and commissioned physical behavior remain open work.
