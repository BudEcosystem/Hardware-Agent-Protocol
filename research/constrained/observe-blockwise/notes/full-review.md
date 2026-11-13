# Observe, Blockwise and reliable-CoAP source review

Reviewed 2026-11-06. This lane owns no protocol implementation and performed no acquired-code execution, packet exchange or hardware test. The [manifest](../manifest.jsonl) preserves fetched responses and extraction provenance. The [reading receipt](../../reading-observe-blockwise-full.json) supplies exact LF intervals and SHA-256 values; acquisition alone is never counted as a read.

## Complete readings

- RFC 7641: all 1,683 LF-delimited lines, 30 printed pages, sections 1–9, Appendix A.1/A.2, figures 1–8, the Observe option table and the unnumbered IANA table. Read intervals: 1–450, 451–900, 901–1350, 1351–1683.
- RFC 7959: all 2,075 lines, 37 pages, sections 1–8, figures 1–13 and tables 1–4. This RFC has no appendix. Read intervals: 1–450, 451–900, 901–1350, 1351–1800, 1801–2075.
- RFC 8323: all 3,027 lines, 54 pages, sections 1–12, Appendix A, figures 1–18, numbered tables 1–3 and every unnumbered signaling-option table. Read intervals: 1–450, 451–900, 901–1350, 1351–1800, 1801–2250, 2251–2700, 2701–3027.

The RFC bodies were displayed in bounded outputs without truncation, including ASCII figures, example bytes/message traces, references, acknowledgements and addresses. They were read, not executed. Original `.txt` response bytes are retained identically, including page form feeds. LF splitting preserves each LF in interval hashes and includes any final unterminated line; it does not use Python `splitlines()`.

All six archived RFC Editor JSON records and all five archived errata queries were read in full. Metadata currently gives the update chain 7641/7959 → 8323 → 8974, with no further update/obsoletion listed for 8974. The duplicate 8323 entry in the 7959 JSON/errata page is preserved as received and deduplicated only in analysis. No matching errata were returned for 7641, 8323 or 8974. RFC 7959 has verified editorial 7523 and held editorial 6083. RFC 9175 has reported technical 9031; that report is not promoted to a verified correction.

## Selected readings and dependencies

RFC 9175 lines 672–1056 contain all of §§3–4: request-body integrity, Request-Tag format/processing/recycling/concurrency/proxy considerations, response ETag requirements and secure token processing. The entire source was acquired, but only that interval was reread in this lane. The existing [base-CoAP receipt](../../../protocols/reading-coap-full.json) separately records its complete text and RFC 8974's complete text. Their old coverage is cross-referenced, not silently added to this lane's full-read count. Fresh metadata and errata for both were acquired and fully read here.

RFC 9177 lines 1–200 were read: publication context, abstract, complete contents, introduction and terminology. Its metadata confirms a separate Proposed Standard, without a formal update relationship to 7959. Its Q-Block protocol, congestion control, examples and appendices remain unread here. No Q-Block support or conformance conclusion follows. Its errata endpoint was not separately queried; a null metadata field is not substituted for a full errata review.

The bibliography of a fully read RFC is not evidence that the linked works were read. TLS/DTLS security profiles, WebSocket RFC 6455, URI/TCP specifications and later revisions remain separate dependency work. Existing OSCORE and base-CoAP research are identified by their own receipts. Web preview outputs and an initially truncated combined output were used only for navigation and are excluded from full-reading evidence.

## Findings and application implications

1. Observe provides eventual latest-state convergence, with congestion-driven omissions. It is unsuitable as the sole record of every alarm, acquisition or operation transition. An HMS event-log cursor and an authenticated source stream epoch/sequence must remain distinct from the hop's Observe value.
2. UDP serial arithmetic includes wrap and a time fallback; reliable transports discard the ordering value entirely. Transport-specific order cannot become the universal HMS stream order. A gateway receipt sequence establishes only receipt order unless source continuity is independently known.
3. Max-Age, ETag validation and repeated representations concern cache consistency. They cannot rejuvenate an old acquisition or extend a physical-operation deadline. Multi-hop residence and block assembly need age bounds; otherwise freshness is unknown.
4. Observe cancellation is subscription cleanup. Reliable connection closure deletes registrations, but neither it nor UDP RST cancels physical work. Lost continuity requires re-registration plus application snapshot/log recovery, with unresolved operations retained.
5. RFC 7959 deliberately permits per-block application. The proposed effectful HMS route must select full no-effect assembly/staging followed by normal admission; `2.31 Continue` is transfer progress. A generic server's partial-update mode cannot be advertised as atomic actuation.
6. Block size negotiation changes offset arithmetic, while Size1/Size2 are optional estimates. Bound offsets, cumulative bytes, storage and time independently. The final more flag is not a safety/authorization signal, and assembling a syntactically complete body is not enough to authorize it.
7. Dynamic Block2 responses need coherent versions. A stream of first blocks can outpace reconstruction; choose an explicit bounded latest-state policy or pinned immutable acquisitions. A partially reconstructed image/spectrum is not a valid whole-object observation.
8. Request-Tag addresses body identity under its security/recycling rules. A matching tag is not sufficient for one application operation. It must not replace the durable caller key/digest, and an empty ACK cannot generally justify tag reuse for integrity protection. Response bodies require the stronger ETag rules when claiming the corresponding security property.
9. TCP/Pong/Custody supply no physical completion proof. Reliable streams can cause head-of-line blocking, and BERT increases message payload capacity rather than removing body or buffer limits. Alternative-Address routing does not inherit peer trust.
10. Proxies aggregate and recreate hop-local state. Preserve end-to-end application identity, authorization, provenance and object version across cache and transport translation. A new proxy token or Observe value cannot repair missing physical evidence.

These findings are engineering inferences for HMS, not newly asserted IETF requirements. [The binding critique](../../../../docs/coap-streaming-binding.md) labels the proposed behavior and includes release scenarios. The current local runtime remains simulation-only and has no CoAP subscription, block assembler, remote event replay, immutable data service or independent bounded stop implementation.

## Source-quality observations

Verified erratum 7523 is relevant when reading RFC 7959 examples: the slash field is the computed byte size, not SZX itself. RFC 7959 Figure 9 also appears to pair its final requests with inconsistent ACK Message IDs; that is a review observation, not a verified erratum and not a rule adopted for implementation. The normative base-CoAP message-matching rules govern any future test vectors. No new erratum was submitted.

The official current metadata was checked at retrieval rather than inferring update status from an RFC's publication-year bibliography. RFC 8323's historical transport-security references were read as references; this review does not endorse those historical configurations as a current deployment profile.
