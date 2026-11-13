# Instrumentation source review

This review supports [the proposed HMS instrumentation bindings](../../../docs/instrumentation-bindings.md). It does not claim implementation or hardware validation. Downloaded material was treated as inert source data; no acquired code was executed and no physical device effects were attempted.

## Acquired and actually read

| Source | Archived text coverage | Visual coverage | Claim |
| --- | --- | --- | --- |
| Modbus Application Protocol Specification V1.1b3, April 26, 2012 | All 3,110 LF-delimited lines | All 50 PDF pages, including flowcharts, tables, examples, and annex | Full reading of the archived artifact |
| Modbus Messaging on TCP/IP Implementation Guide V1.0b, October 24, 2006 | All 2,528 LF-delimited lines | All 46 PDF pages; enlarged class and sequence diagrams on pp.38, 39, 41 | Full reading of the archived artifact |
| SCPI 1999.0 | Selected ranges only; see ledger | PDF pp.50–57 and 517 only | Partial reading; 819-page document is not fully read |
| Modbus over Serial Line V1.02, December 20, 2006 | Lines 229–540 only, principally §§2.1–2.4.3 | PDF pp.7–11 | Partial reading; physical layer, RTU/ASCII framing and remaining annexes are not reviewed |
| IVI SCPI provenance and specification-download pages | All extracted visible text | No separate rendered-page review | Full extracted-text reading; linked works are excluded |
| Modbus current specification landing page | Full web-tool textual rendition | No separate rendered-page review | Provenance only; raw HTML was not acquired |

The [reading ledger](../reading-instrumentation.json) records the exact displayed line intervals and SHA-256 over retained LF-delimited bytes. This matters because PDF extraction includes form feeds: Python `splitlines()` would produce different intervals. [The figure manifest](../figure-manifest.json) links every reviewed image to its page and hash. Text and page-image reading complement each other; an automated coverage check cannot prove comprehension.

## Provenance and version limits

The [current Modbus landing page](https://www.modbus.org/modbus-specifications) identifies application V1.1b3, TCP guide V1.0b, and serial guide V1.02. Its current links resolve through `/file/secure/…`. Direct raw HTTP requests to that route and the landing page received a web-application-firewall `403`; the web reader could view them. The obsolete application `/docs/…` URL returned `404` in the web reader. These results are access-path observations, not evidence that the documents require payment or are generally unavailable.

The archived PDF bytes were acquired successfully from the public Modbus asset directory on Noviams hosting. The precise URLs and hashes are in [manifest.json](../manifest.json). These are named publisher artifacts corroborated against the official specification listing. They are not asserted to be byte-identical to today's `/file/secure/…` rendition. The current application rendition uses Client/Server terminology where the archived PDF uses Master/Slave in its communication-stack figure, despite the same stated version. That visible variation must remain in the provenance record. The full-read claim applies to the archived SHA-256, not all documents labelled V1.1b3.

The TCP extractor reported a PDF default-configuration dictionary warning but produced all text; all 46 pages were also rendered and reviewed. A sparse final page is included in coverage. Some small method names in the published class diagram are clipped at their original diagram boundaries; the analysis does not invent missing signatures.

The [IVI SCPI provenance page](https://www.ivifoundation.org/About-IVI/scpi.html) identifies IVI as steward after the SCPI Consortium merger in late 2003. Its [specifications page](https://www.ivifoundation.org/specifications/default.html) links the [SCPI-99 PDF](https://www.ivifoundation.org/downloads/SCPI/scpi-99.pdf), which returned `200` and was archived completely. Availability was verified, not assumed. SCPI-99's own front notice is retained in the raw file. This acquisition makes no claim that all referenced IEEE documents, transports, or manufacturer programming manuals are free or have been read.

## Modbus application findings

The complete document supplies a useful native data-access foundation. It supplies no generic physical-device lifecycle. Its data model, wire addressing, function behavior, and exceptions need a typed HMS interpretation rather than direct exposure as physical operations.

| Source location | Native issue | HMS inference |
| --- | --- | --- |
| §§4.1–4.4, pp.3–8 | PDU size, byte order, four tables, vendor mapping, zero-based protocol addresses | Fix a typed model-specific map; keep units, scale, cross-register representation, and measurement age explicit |
| §§6.1–6.6, pp.11–19 | Read formats and single-write acknowledgements | Do not confuse write echo with actuator completion or fresh sensor evidence |
| §§6.7–6.8, pp.20–24 | Serial status/diagnostics, restart/listen-only modes, counters | Diagnostics can change device communication state or erase evidence; no arbitrary discovery probes |
| §§6.9–6.10, pp.25–28 | Event counters and bounded newest-first log | These are shared/resettable/wrapping observations, not durable HMS operation identity |
| §§6.11–6.15, pp.29–36 | Multiple writes and file-record access | No application-wide rollback, cross-device atomic commit, or universal controller-scan snapshot is established |
| §6.16, pp.36–37 | Masked register update; later scan may change value | A mask is not ownership or a persistent physical postcondition |
| §6.17, pp.38–39 | Read/write-multiple writes before reading | Do not present it as compare-and-swap or isolated procedure execution |
| §6.18, pp.40–41 | FIFO read does not remove its entries | Side effects must be specified per native operation; do not generalize from SCPI error popping |
| §§6.19–6.21, pp.41–46 | Encapsulated interfaces and identification objects | Identity aids compatibility; it does not authenticate a physical asset or prove uninterrupted boot/session continuity |
| §7, pp.47–49 | Exception categories include execution-time failure and no downstream response | Preserve attempt-specific evidence and ambiguous effects; a transport error is not an automatic replay license |
| Annexes A–B, p.50 | Reserved function/MEI values and references | No unsupported function probing; referenced works are not counted as read |

The binding should enforce the actual function limits, including 125-register reads, 123-register multiple writes, and 121-register writes for read/write-multiple, instead of assuming every operation can use the full ADU. This is parser and device-profile qualification, not a reason to split a physical operation into several writes without modelling the resulting intermediate states.

Apparent internal source discrepancies must not be silently normalized:

- The write-file-record request table (§6.15, p.34) and its processing flowchart (p.36) give different byte-count limits. Keep this function disabled until a precise interpretation is qualified against an authoritative correction and the actual device profile.
- The segmented device-identification example (p.45) repeats an object count of three while displaying two objects and then one. Validate each message's declared counts against its encoded objects and overall size; do not use the example as a parser fixture without documenting its inconsistency.
- The event-log example (p.27) and subsequent listen-only-event description (p.28) give different event bytes. A diagnostic decoder needs an explicit tested profile or clarification.

These are review observations about this archived artifact, not an official errata list. They do not justify choosing a permissive parser or claiming that every device implements the same deviation.

## TCP guide findings

| Source location | Native issue | HMS inference |
| --- | --- | --- |
| §§3.1–3.2, pp.4–6 | MBAP routing/length/transaction fields and TCP stream framing | Bound and validate reassembly; use a connection generation in addition to the native identifier |
| §§4.1–4.3, pp.7–20 | Client/server/gateway components, optional access control, concurrent connections | An IP allowlist is not authenticated ownership; gateway resource arbitration is an additional layer |
| §4.4.1.2, pp.21–23 | Per-connection outstanding transaction correlation; downstream unit routing | No durable deduplication; distinguish direct TCP from bridged unit semantics |
| §4.4.1.3, pp.24–25 | Exception can still be a positive delivery confirmation | Parse the returned native result rather than accepting an API-level success flag |
| §4.4.1.4, pp.25–26 | No prescribed transaction response-time requirement; application retries discussed | HMS must qualify its own deadlines and avoid repeat effects after uncertain dispatch |
| §4.4.2, pp.26–32 | Transaction pools, backend mapping, response processing | Device concurrency and backend coherency remain profile-specific; queue exhaustion is not a global resource lease |
| §§5.1–5.4, pp.32–46 | Illustrative classes, buffer pools, connection and sequence diagrams | These examples are not mandated HMS architecture and software `m_Stop` methods are not physical stopping guarantees |

The guide's historic TCP timing and network-configuration advice is not substituted for current platform documentation. More importantly, TCP connection health and keepalive do not prove an instrument is within its physical operating envelope. Connection closure, reboot, reconnect, and gateway failover require reconciliation of device continuity and unfinished operations.

## Selected SCPI findings and gaps

The front matter, introduction, and all of Volume 1 chapter 4 were read in text. Chapter 9 status reporting was read in text and visually through all its pages, including status fan-out, logical-instrument, and trigger-layer diagrams. Selected Volume 2 passages cover the error queue and `ABORt`; the remainder of those chapters is not covered.

The reviewed material identifies several requirements for a future binding:

- Pending-operation completion applies to the documented participating commands, so the exact model manual is necessary before using `*OPC`, `*OPC?`, or `*WAI` as completion evidence (Vol.1 §4.1.3, PDF pp.15–19).
- Status consumers need a single ownership and evidence policy. Clearing and resetting affect reporting state; completion flags are not direct physical measurements (Vol.1 ch.9, PDF pp.50–57).
- Error reads consume a finite queue, overflow loses information, and filters can suppress entries. HMS must preserve read/clear/filter provenance and acknowledge the gap between destructive reading and external durable logging (selected Vol.2 §21.8, PDF pp.516–520; exact partial limits in ledger).
- `ABORt` concerns trigger sequences and related actions returning to idle. The reviewed semantics do not establish an absolute deadline for energy removal or a universal safe output state (Vol.2 §24.5, PDF p.564; the selected passage continues through p.565).

The diagrams were interpreted together with their text, including operation-versus-questionable status, optional queue summary, channel fan-out, and multiple trigger sequences. Those structures support preserving channel and evidence provenance; they do not supply a manufacturer-independent action map.

Still required before a generic SCPI implementation claim: the remaining SCPI chapters, exact IEEE-488.2 dependency text, selected transport standards, and complete instrument programming manuals. No complete vendor instrument manual was read in this assignment. Native trigger/status/error behavior cannot be inferred from a driver's command names alone.

## Selected serial findings and gaps

The reviewed §§2.1–2.4.3 and their state/timing diagrams establish single-controller request ordering, unicast versus write broadcast, lack of a broadcast response, and response versus turnaround timing. Their illustrative delays are not universal deadlines. A broadcast can reach several devices without producing an acknowledgement set or a physical synchronization guarantee.

The rest of the serial guide remains unread. This review does not claim complete RTU/ASCII framing, CRC, electrical, wiring, or serial conformance coverage. An actual serial binding must close those gaps before implementation or commissioning.

## Audit and next work

The local audit checks acquisition and render hashes, exact LF-interval hashes, full-range continuity for sources labelled complete, partial-range bounds, and page coverage. It does not attest to protocol implementation, device behavior, conformance, safety certification, or the content of unreviewed references. See [audit.json](../audit.json).

The next evidence should be a complete, publicly available programming manual for an intended instrument and a complete register map for an intended controller, followed by transport-specific standards. Select actual devices according to the intended laboratory/manufacturing use, so their output and stop semantics can be qualified rather than guessed from the generic command languages.
