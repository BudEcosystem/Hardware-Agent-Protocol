# CoAP observation and large-object binding requirements

Status: proposed HMS extension, reviewed 2026-11-06. The local runtime implements neither CoAP Observe nor Blockwise transfer. These requirements extend the [bounded unicast CoAP proposal](coap-binding.md) and preserve the [execution core](../spec/02-execution.md). They do not install a transport, confer physical authority or establish a latency guarantee. Exact source bytes, full/selected reading scope and hashes are in the [reading receipt](../research/constrained/reading-observe-blockwise-full.json) and [review notes](../research/constrained/observe-blockwise/notes/full-review.md).

## Standards baseline and limits of this review

The complete published texts of [RFC 7641][observe], [RFC 7959][block] and their formal update [RFC 8323][reliable] were read, including every figure/table, references and both available appendices. The review covers 121 printed pages and 6,785 LF-delimited text lines. No protocol implementation or acquired example code was executed.

| Source | Current official metadata and errata at retrieval |
| --- | --- |
| RFC 7641 Observe | Proposed Standard; updated by RFC 8323; no matching errata |
| RFC 7959 Blockwise | Proposed Standard; updates RFC 7252; updated by RFC 8323; verified editorial erratum 7523 and held editorial erratum 6083 |
| RFC 8323 reliable transports | Proposed Standard; updates RFCs 7641/7959; updated by RFC 8974; no matching errata |
| RFC 8974 extended tokens | Proposed Standard; updates RFCs 7252/8323; no further listed update/obsoletion or matching errata; full text is covered by the separate base-CoAP review |
| RFC 9175 Request-Tag/token processing | Proposed Standard; formally updates RFC 7252; no further listed update/obsoletion; technical erratum 9031 remains **Reported**, not verified |
| RFC 9177 Q-Block | Separate Proposed Standard, with no listed updates/obsoletion; only introductory material was read here; excluded from this binding |

The archived RFC 7959 metadata repeats RFC 8323 twice; this is one distinct update, not two specifications. Erratum 7523 corrects the examples' terminology: the slash notation contains the resulting block size, not the exponent. Erratum 6083 proposes table-notation cleanup and remains held. RFC 9175 erratum 9031 concerns the word used for a preemptive Echo-bearing response; it is not an approved normative change. [RFC 7959 errata][block-errata], [RFC 9175 errata][tag-errata]

RFC 9175 §§3–4 were independently reread for body integrity and secure token use; its remaining text is outside this lane's selected read, although the [base-CoAP receipt](../research/protocols/reading-coap-full.json) records a separate full review. RFC 8974 is also cross-referenced to that existing full review rather than counted again here. Q-Block, TLS/DTLS specifications and their current deployment profiles, WebSocket internals, and other linked works are not fully reviewed by this document. The 2018 TLS references in RFC 8323 do not select a current security configuration. OSCORE has a [separate review and proposed binding](oscore-binding.md).

## Notifications represent state, not complete event history

Observe registers interest in a resource and sends representations as additional responses. Its consistency model permits skipped intermediate states. A successful registration requires a successful response carrying Observe; a normal response without it is only a GET result. A discovery `obs` attribute is a hint. The server can drop the registration, and proxies may aggregate observers and generate their own notification ordering values. [RFC 7641 §§1–5][observe]

The adapter must therefore declare whether the resource supplies a **latest-state snapshot** or an application-defined retained event stream. Ordinary Observe supports the first. It cannot, by itself, certify that every alarm, sample, material transfer or operation transition was received. A jump in the CoAP Observe value is not a count of missing HMS events: the origin may derive that value from a clock, skip states, or pass through a proxy with a different sequence.

An HMS observation needs its own authenticated origin identity, property, stream epoch, source sequence policy, endpoint session, binding/calibration revisions, acquisition time/clock domain, uncertainty, quality and evidence kind. A gateway-assigned sequence can order gateway receipts but must not be presented as proof of contiguous origin acquisition. Only a declared origin sequence contract can support that claim.

For an application that needs all events, Observe can announce a durable log head. The consumer then retrieves authorized pages by the application cursor and checks continuity. An unavailable retained range produces an explicit gap and an application-specific recovery decision. Fetching the latest state may recover a display, but cannot reconstruct omitted transitions or prove that an actuator did nothing. The current HMS Journal has local event pages; it has no implemented CoAP log projection, remote gap-recovery protocol or retained sensor stream.

## Freshness, ordering and reconnection

UDP Observe uses a 24-bit serial value and a client-local time fallback for reordering. Reliable Observe ignores the numeric value. Neither orders HMS operations across reconnects. Max-Age governs representation-cache usability; repeated notification, cache validation or receipt does not establish a new sensor acquisition. [RFC 7641 §§3.3–4.4][observe], [RFC 8323 §7][reliable]

The HMS adapter must implement protocol ordering in the selected CoAP library and separately enforce application epoch/sequence and acquisition-age policy. In particular, the UDP rule accepting a notification after a silence longer than 128 seconds is not permission to make its payload physically fresh. A validly ordered or cryptographically authentic delayed sample can still be stale. A `2.03 Valid` notification selects an existing cached representation; it preserves that representation's acquisition facts.

The [local-runtime observation model](../spec/09-local-runtime.md) already separates receipt and acquisition clocks and rejects unknown age for fresh preconditions. A CoAP ingress must add bounds for device caching, transmission, proxy residence and large-body assembly, or report the age as unknown. Timestamping the last block's arrival as a new acquisition would hide both assembly delay and source staleness. Receipt-clock restart, mapping failure or unqualified discontinuity must not reduce a previously known age.

The base proposal's default `Max-Age=0` prevents reusable freshness unless a safe cache policy is declared. Observe deployments should explicitly select that policy: a positive bounded Max-Age may be useful for snapshot availability, while HMS acquisition-age limits can remain stricter. Neither a positive cache lifetime nor a repeated unchanged value extends an action deadline. Expired or unknown observation quality cannot satisfy an admission precondition merely because the subscription appears alive.

For DTLS, the original Observe rule confines notifications to the connection epoch that created the registration. For reliable transports, closing or timing out the connection removes associated registrations. A new transport/security connection requires a new confirmed observation relationship and qualified application continuity. Transport reconnection is not evidence that the device's execution session reset; equally, continuing to use a URI/token is not proof that its history survived. [RFC 7641 §7][observe], [RFC 8323 §§3.4, 7.4][reliable]

On interruption, mark the subscription unavailable, preserve the last sample with its age/quality, and obtain an authenticated snapshot or retained-log continuation. If source continuity cannot be established, start an explicit new HMS stream epoch and report the gap. Preserve outstanding physical operation IDs and unresolved claims through this process. Apply RFC 9175 secure response-token rules on new/rekeyed connections; a reused token must not attach an old notification to a new logical request. [RFC 9175 §4][tag]

## Three different cancellation operations

| Action | What it establishes |
| --- | --- |
| Deregister Observe | Stop an observation relationship; late notifications can still be in flight |
| Abandon a Blockwise assembly | Stop collecting this representation; it says nothing about earlier server effects |
| Cancel or stop an HMS operation | Invoke the separately authorized operation/protection path and obtain its required evidence |

UDP observation cancellation may use explicit deregistration or rejection of later notifications. Reliable transports require explicit deregistration; connection loss also removes observations. These rules manage subscriptions, not machinery. A canceled observation of a motor does not stop the motor. A canceled upload does not undo blocks already applied by a generic server. A closed connection or Abort message cannot resolve an already-dispatched operation's outcome. [RFC 7641 §§3.6, 4.5][observe], [RFC 8323 §§5.5–5.6, 7.4][reliable]

The adapter should use explicit deregistration and bounded cleanup for local resource accounting. Pending callbacks must remain associated with their original subscription generation so they cannot reactivate a replaced stream. Normal unsubscribe/cancel messages may contend with bulk traffic; they do not implement the independent bounded-stop path required for a physical deployment.

## Whole representations and large objects

Block1 describes request bodies and Block2 response bodies across separate exchanges. Block boundaries need not align with JSON, CBOR or other application units. The base block sizes are 16–1024 bytes; size indications are estimates, and the more flag identifies completion. ETags correlate response versions but are not a general-purpose cryptographic digest. [RFC 7959 §§2, 4][block]

For an HMS complete-object read, bind assembly to the authenticated peer/security scope, canonical resource, selected representation format, current transfer identity and pinned object version. Require consistent ETag/version evidence for every assembled response block, validate offsets and lengths without overflow, reject conflicting bytes at the same position, and validate the complete content before exposing it as a usable object. Never concatenate blocks from different tags, formats, principals, bindings or source epochs. If an immutable expected digest is available, check the final bytes against it; an ETag alone does not authenticate them.

The binding must cap total bytes, highest offset, block count, simultaneous assemblies, per-principal memory/storage, transfer duration and retry/restart budget before allocation. Optional Size1/Size2 values can guide early rejection but cannot authorize allocation or prove that all bytes arrived. A false small estimate must not bypass the cumulative cap, and a sparse high block number must not allocate a huge object. Drop incomplete objects with an explicit reason when deadlines or quotas expire.

When observing a large resource, the notification supplies the first block and the client retrieves the rest. The observation applies to the whole resource; subsequent block exchanges have their own correlation tokens. A changing resource may never yield one coherent set of blocks unless the server provides an adequate snapshot facility. [RFC 7959 §§2.4, 2.6, 3.4][block]

Do not publish the first block as a valid HMS sample. Retain a bounded assembly tied to its ETag and application metadata. A newer snapshot may supersede it under an explicit latest-state policy; report the discarded acquisition/continuity consequence instead of silently completing old bytes as the new sample. If every acquisition matters, use pinned immutable objects and a durable index rather than assuming Observe plus Block2 retains all images or spectra.

For large image, spectrum, model or procedure data, a suitable HMS design is an authorized immutable data reference carrying digest, media/schema version, byte length, origin/acquisition provenance and access/retention scope. The control operation pins that reference and still passes normal admission. This is a proposed design, not an implemented data store. A URI from a device or redirect must remain inside commissioned routing/access rules; retrieving metadata must not become arbitrary privileged network access.

## Body integrity and effectful uploads

Authenticated individual blocks can still be mixed between request bodies when replay windows permit it. Request-Tag distinguishes temporary request assemblies; it is neither an HMS operation key nor a durable replay namespace. The same Request-Tag is necessary but insufficient to prove one operation, and recycling depends on the purpose and security-layer invalidation of earlier messages. [RFC 9175 §§3.1–3.5][tag]

The selected upload profile must apply RFC 9175 body-integrity rules end to end. Keep the tag consistent through the Block1 phase and any following Block2 response retrieval, protect all contributing exchanges, and do not recycle a tag merely because the local client timed out or received an empty ACK. Scope assembly using the authenticated requester and complete matching options. Intermediaries must preserve the integrity boundary; an Outer OSCORE tag does not replace protected Inner body identity. For response integrity, require the specified ETag behavior and reject reused tags for different representations. Ordered secured delivery can change which tag mechanism is needed, but does not supply application replay protection. [RFC 9175 §§3.2–3.8][tag]

Generic Block1 allows atomic assembly, per-block application, or mixtures. `2.31 Continue` reports transfer progress, not durable HMS admission. A server that applies blocks in place may expose a partial resource or effect before the final block; a later error does not reverse it. The initial HMS effectful upload profile must therefore refuse per-block actuation. [RFC 7959 §§2.3, 2.5, 2.9, 7][block]

Use either bounded complete-envelope assembly with no effects until full validation/admission, or an inert upload/staging resource followed by a separate operation referencing the validated digest. The final operation preserves its original replay key, immutable intent and timing. Recheck authority, limits, binding revisions and freshness before dispatch; time spent uploading cannot extend latest-start. Quota admission for temporary bytes is separate from resource authority to actuate. A failed or abandoned upload cannot release claims belonging to an already admitted operation.

A timeout or `4.08`/`4.13` response may justify transfer recovery only under the chosen no-effect staging contract. It is not generic permission to restart a native non-idempotent POST with a new application key. Reconcile the durable HMS operation whenever a prior effect is possible. Block2 retrieval of a POST result must retrieve that result without repeating the physical action.

## Reliable transport changes and proxies

RFC 8323 removes the UDP message-level Type/MID mechanism, uses CSM capability negotiation and introduces BERT for larger block payloads. Its Observe value is ignored on reception. Ping/Pong checks a connection hop; Custody has no defined physical processing meaning. Closing a connection loses its observation/signaling state while requests may already have taken effect. [RFC 8323 §§3–7][reliable]

A reliable-transport adapter must check the peer's message-size and Blockwise/BERT capabilities, bound its own buffers and asynchronous pending requests, and account for headers/options as well as payload. BERT uses SZX 7 with 1024-byte units; it does not mean a fixed 2048-byte block. Do not enable it on the base UDP profile. A transport's maximum message size is distinct from the maximum reassembled body size. Apply the separately reviewed RFC 8974 extension if extended tokens are supported; do not parse future-sized tokens using the original header limit. [RFC 8323 §§5.3, 6][reliable], [RFC 8974][tokens]

TCP delivery and application processing do not establish physical completion. Neither Pong/Custody nor connection release is adequate evidence to release a physical claim. Bulk objects can cause head-of-line blocking; keep bounded stop/protection independent. A suggested Alternative-Address needs renewed routing and peer authorization, not inherited trust. Reliable transport schemes identify distinct resource namespaces and must not be aliased by string similarity alone. [RFC 8323 §§5, 8, 10.1][reliable]

Proxies may poll upstream, fan out observations, alter tokens, create their own Observe ordering, and cache individual blocks. Authorize every downstream consumer and preserve acquisition provenance, object version and remaining age. Cache revalidation may refresh representation usability but cannot manufacture a new measurement. Block options require aware processing; they are not an excuse to blindly forward partial authenticated bodies across unrelated contexts. Keep OSCORE end-to-end protected semantics separate from hop-local transfer state. [RFC 7641 §5][observe], [RFC 7959 §§2.10, 5, 7][block], [RFC 9175 §3][tag]

## Required acceptance cases

These are release scenarios, not tests performed by this research lane.

| Scenario | Required HMS behavior |
| --- | --- |
| Observe registration falls back to ordinary GET | Expose polling/unsubscribed status; do not promise updates |
| Notifications are lost, coalesced or reordered | Preserve protocol ordering and declared HMS continuity; never infer a complete event log |
| Serial wrap or the UDP 128-second fallback accepts a message | Independently reject stale acquisition or wrong application epoch |
| Cached payload receives `2.03 Valid` or a proxy refresh | Preserve original acquisition time and uncertainty |
| Reliable connection reconnects with an empty Observe value | Reestablish registration and application continuity; retain unresolved operations |
| A late callback arrives after unsubscribe/replacement | It cannot populate the new stream generation |
| New ETag arrives during a large notification assembly | No mixed object or partial fresh sample; bound restart work |
| Size estimate lies, offset is huge, or overlap conflicts | Reject without oversized allocation or effects |
| Protected blocks from an earlier body arrive within replay tolerance | Body identity/integrity rules prevent cross-assembly contamination |
| Block1 server applies non-final blocks | Refuse the HMS atomic-upload route or classify existing effects as unresolved |
| Last upload response is lost after commit | Recover the same operation/digest; do not create a new action key |
| Connection/Pong succeeds while origin sensor or actuator is unavailable | No physical freshness, completion or quiescence claim |
| Bulk traffic stalls ordinary cancellation | Commissioned independent stop/protection remains effective |

Release still requires an exact wire/Content-Format profile, selected security and CoAP implementations, resource quotas, object storage/retention rules, proxy policy, adapter tests and measured endpoint behavior. Full standards reading closes a research gap; it does not establish those implementation or physical guarantees.

[observe]: https://www.rfc-editor.org/rfc/rfc7641.html
[block]: https://www.rfc-editor.org/rfc/rfc7959.html
[reliable]: https://www.rfc-editor.org/rfc/rfc8323.html
[tokens]: https://www.rfc-editor.org/rfc/rfc8974.html
[tag]: https://www.rfc-editor.org/rfc/rfc9175.html
[block-errata]: https://errata.rfc-editor.org/search/?rfc_number=7959&presentation=records
[tag-errata]: https://errata.rfc-editor.org/search/?rfc_number=9175&presentation=records
