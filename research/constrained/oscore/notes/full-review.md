# OSCORE full-source review

Reviewed 2026-11-06 for HMS's proposed constrained-device binding. Exact acquisitions and coverage are in [manifest.jsonl](../manifest.jsonl) and [reading-oscore-full.json](../../reading-oscore-full.json). The resulting design is [docs/oscore-binding.md](../../../../docs/oscore-binding.md).

## What was actually read

| Source | Archived coverage | Status |
| --- | --- | --- |
| RFC 8613 | All 5,267 LF-delimited text lines, 94 pages, sections 1–14 and appendices A–E | Complete published RFC text; all 14 ASCII figures, unnumbered tables, five compression examples and eight Appendix C vectors read. |
| RFC 8613 errata | All 98 extracted lines | One verified editorial record and one technical record held for update. |
| RFC 8613 metadata JSON | All 31 lines | Proposed Standard; updates RFC 7252; no listed updates/obsoletion of RFC 8613. |
| RFC 8613 `/info` rendition | Lines 1–150 of 5,795 | Selected metadata/introduction/TOC only; a duplicate full rendition, not another full RFC read. |
| RFC 9668 | All 1,235 text lines | Complete separate published integration RFC, with all five ASCII figures/four tables and references. |
| RFC 9668 metadata JSON / errata | All 40 / 42 lines | Proposed Standard; no listed updates or obsoletion; no matching errata. |
| Key-usage-limits draft -08 | All 840 lines, including three ASCII figures/tables and appendices A–C | Complete **Internet-Draft**, intended Informational, 2026-09-07, expires 2027-03-11. Not a published standard or adopted HMS numeric policy. |
| KUDOS draft -15 | Lines 1–250 of 4,480 | Selected preamble, abstract, TOC, introduction and terminology; 2026-11-02 work in progress. No full algorithm/state-machine review. |
| RFC 9528 | Lines 1–200 of 4,671 | Selected preamble, abstract, TOC and introductory motivation only. EDHOC cryptography, state machine and appendices remain unread here. |

The exact text bytes are preserved, including form feeds, UTF-8 BOMs where present and final unterminated lines. Chunk digests count LF delimiters only and retain them; Python's broader `splitlines()` semantics were not used. All covered RFC chunks were displayed without truncation. The initial combined local-context output was truncated; the three local documents were subsequently read independently and only those complete displays support the context-read claims. No linked bibliography work is claimed read merely because its citation was read.

Official `/info` now renders a full document rather than a compact status card. The full machine metadata is therefore the precise evidence for update/obsoletion status, with live errata records archived independently. This does not imply that historical dependencies or active drafts have no further corrections.

## Source findings and HMS interpretation

**End-to-end boundary.** RFC 8613 protects the request/response application layer while preserving enough visible information for forwarding. Figures 5–6 and §§4–5 distinguish protected Inner method/path/query/payload from mutable routing, token, Message ID and transport type. Appendix D explicitly allows compromised intermediaries in its threat model and analyzes spoofed ACK/RST, error and routing fields. HMS therefore binds target/authority to the verified peer and protected intent; outer delivery signals never establish operation outcomes. This is a proposed HMS rule, not a capability generic CoAP endpoints already have.

**Context identity is not execution identity.** §§3.1–3.3 require unique derivation inputs and distinguish immutable keys/IDs from sender sequence/replay state. A role change does not change Sender/Recipient IDs. A security context may survive a reboot, while a cryptographic rekey may occur without one. Neither event alone supplies the HMS endpoint execution session, physical enrollment, control generation or durable operation namespace. The binding preserves these as separate objects and requires independently authenticated reset detection/reconciliation.

**Replay is not freshness or operation deduplication.** §§7.1–7.5 make protected-message uniqueness and response binding precise. The first delivery of an arbitrarily delayed request may still be accepted; stronger actuator freshness needs another mechanism. Re-encrypting the same intent with a new Partial IV is a new protocol message. HMS therefore retains the same caller key/digest and execution deadline through retransmission, challenge and rekey, with application lookup before new admission. It also preserves sample acquisition age instead of treating a new protected response as a new measurement.

**Verified correction.** Erratum 8229 fixes the reversed/missing-negation wording in §7.3 about a misbehaving server generating a response before receiving a request. The corrected interpretation supplies no dishonest-server aliveness proof. Erratum 8230 proposes rejecting unusable/invalid Recipient Contexts earlier in response verification but is held for update because the RFC has no corresponding invalid-context definition. The HMS binding calls for a reviewed context-validity policy without relabeling that held record as verified text.

**Two independent reset hazards.** Sender-state loss can repeat a key/nonce pair; recipient-state loss can accept a previously processed request. §§7.5 and B.1 handle both. The nonvolatile reservation example requires a proven upper bound on unseen sends/write lag, not merely a large increment. Replay-window recovery uses a protected Echo challenge and the server's own safe Partial IV. It does not reconstruct durable physical history. A reset after actuation but before journaling remains an HMS unknown-outcome case even if cryptographic recovery succeeds.

**Randomized context recovery.** Appendix B.2 requires good random sources at both endpoints and guarantees for all reboot/recommission/error paths. Its five steps, cached nonces/HMAC alternative, concurrent-run race discussion and DoS analysis were read in full. The example permits the second request to be ordinary application work after security recovery, but HMS still needs complete admission and endpoint-session evidence. This binding does not select B.2 as an operational handshake.

**Exhaustion and newer work.** RFC 8613 caps sender sequence numbers below `2^40` and permits algorithm-specific lower limits. The complete key-limits draft separately tracks encryption count, failed decryptions, expiration and message size. Its existence is useful evidence that nonce-space exhaustion alone is an insufficient deployment policy. Its proposed numerical limits, algorithm estimates and counter shortcuts are not adopted as HMS defaults. KUDOS -15's introduction proposes changing response protection/flag bits and deprecating B.2; only that introductory scope was reviewed. It remains work in progress, so there is no claim that a published RFC update has already changed the baseline.

**Draft caution.** In key-limits -08 §2.3 the opening paragraph expresses the maximum in bytes as block-size multiplied by `l`. Later Step 2 computes `T` in bytes while Step 3 says to compare `T` with `l` itself, even though §2.1.1 defines `l` in cipher blocks. This is an apparent unit inconsistency in the draft, not a verified erratum or an independently proven cryptographic flaw. A future implementation should resolve the source interpretation and check the underlying AEAD analysis instead of copying the pseudocode. The draft also retains a security-considerations TODO. No correction was submitted externally.

**EDHOC integration.** Full RFC 9668 §§3–7 establish the combined-message order: retrieve the EDHOC session; verify message_3; derive context; verify the OSCORE request; deliver it to the application; retain ordinary access checks. The text explicitly says successful handshake/context derivation does not decide authorization to the protected resource. This directly supports a boundary between authentication and HMS operation admission. Message_4-required profiles conflict with the combined flow; the EDHOC connection identifiers need collision rules; discovery attributes do not grant authority. Full RFC 9528 review remains a release gate.

**Extensions and multicast.** RFC 8613 fully describes its interaction with Inner/Outer block options, Observe, HTTP mappings and special error handling. The dependency protocols were not re-read in this work. Outer block assembly precedes object verification and therefore needs hard memory/size/time bounds; Inner block verification is not atomic application admission. Authenticated notification ordering does not establish gap-free telemetry or physical acquisition time. Group OSCORE references are hooks for a separate extension, not permission to reuse pairwise contexts among a multicast group. No group execution guarantee is inferred.

## Figure and vector review

RFC 8613 figures 1–4 cover layers, exchange, OSCORE option and mirrored context lookup; figures 5–6 enumerate protection classes; figures 7–10 specify `kid context`, nonce construction, plaintext and compressed option layout; figure 11 illustrates the discovery hint; figures 12–13 cover proxy sensor access/subscription; figure 14 is the B.2 recovery exchange. All were read in their original ASCII layouts. The five §6.3 compression examples include empty IDs/Partial IV and response-without-IV cases. Appendix C.1–C.3 cover derivation with salt, without salt and with ID Context; C.4–C.6 cover requests; C.7–C.8 cover responses without/with Partial IV. These vectors were read, not executed.

RFC 9668 figures 1–2 compare sequential and combined exchanges; figure 3 shows the CoAP option/payload layout; figure 4 is the combined-message byte example; figure 5 shows discovery attributes. Tables 1–4 define the EDHOC option and registry entries. The three key-limits draft figures contain security estimates, maximum message sizes and the CCM_8 parameter table; they were inspected as draft claims, not independently verified numerical analysis.

## Changes and remaining work

Created the dedicated OSCORE binding and this review, archived ten source records, and recorded complete/selected coverage with original-byte and interval hashes. The work changes documentation and research artifacts only. No acquired repository code, cryptographic library implementation, firmware, hardware interface or live endpoint was executed.

Static verification passed for all ten raw/text hashes, every LF interval, contiguous full coverage, manifest/log agreement, local-context hashes and relative artifact links. The workspace is not a Git checkout, so a Git diff check was unavailable; authored documentation was checked directly for trailing whitespace and conflict markers instead.

Remaining release work includes full chosen EDHOC/authorization/rekey specifications and errata; exact supported security parameters and algorithms; implementation provenance; negative parser/replay tests; power-fail persistence evidence; byte-vector interoperability; gateway/physical identity evidence; and actual HMS admission, fencing and physical-outcome tests.
