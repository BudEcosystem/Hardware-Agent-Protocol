# Instrumentation research corpus

Complete reading covers Modbus Application V1.1b3 (50 pages, 3,110 LF lines) and the TCP messaging implementation guide V1.0b (46 pages, 2,528 LF lines), including every rendered page. A separate [serial V1.02 full-reading receipt](../../artifacts/verification/modbus-serial-full-read/README.md) now covers all 2,459 LF-split text lines and all 44 pages, superseding the earlier 312-line partial coverage without rewriting it. SCPI-99 remains partial: the [header follow-up](scpi-headers-followup/README.md) adds 600 lines and twelve visually reviewed PDF pages, bringing combined coverage to 2,296 of 42,293 lines. Its separate receipt preserves the earlier 1,696-line record and is not yet included in the consolidated corpus counts.

The [serial critique](../../artifacts/verification/modbus-serial-full-read/CRITIQUE.md) distinguishes one shared bus owner, broadcast uncertainty, response correlation, framing and operation deadlines, and register acknowledgment from physical completion. It records a baud-rate class discrepancy and misleading numeric remnants in the extracted p.36 flowchart. The new lane has its own hash index; the earlier consolidated corpus counts do not include this reading overlay.

- [Acquisition manifest and access limits](manifest.json)
- [Full and selected reading receipts](reading-instrumentation.json)
- [Page/figure coverage](figure-manifest.json)
- [Source review and discrepancies](notes/instrumentation-review.md)
- [HMS binding proposal](../../docs/instrumentation-bindings.md)
- [Independent lane integrity audit](audit.json)

Current secure Modbus endpoints blocked direct downloads. The archived publisher CDN PDFs are corroborated by the official listing but are not claimed byte-identical to the current secure renditions; terminology differs under the same version label. Raw sources retain publication notices. No physical device or acquired program was executed. The consolidated corpus audit also verifies these source bytes, LF ranges and retained figure images.
