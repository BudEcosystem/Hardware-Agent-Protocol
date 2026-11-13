# Bounded OPC UA primary-source corpus

Acquired 2026-11-06 from OPC Foundation's public reference. No acquired software, industrial service, device or account was executed/contacted for testing. The acquisition used ordinary HTTPS document requests only.

| Document | Current reference release | Publication date | Reading scope |
|---|---|---|---|
| OPC 10000-4 Services | 1.05.07 | 2026-04-15 | 22 complete selected sections plus introductory context: 1,711/5,827 LF lines; 16 figures |
| OPC 10000-10 Programs | 1.05.00 | 2021-10-15 | Entire available Markdown export: 1,022 LF lines including Annex A and CSV tables; all 15 available figure assets |

Part 10 metadata separately lists namespace model version 1.05.07 and supplementary files UA-1.05.06-2025-11-08. Those are not the document's release version.

Exact version/build export URLs:

- [Part 4 Markdown](https://reference.opcfoundation.org/specs/OPC-10000-4/v1.05.07/t63916693122/download/markdown), [Part 4 STS XML](https://reference.opcfoundation.org/specs/OPC-10000-4/v1.05.07/t63916693122/download/sts-xml).
- [Part 10 Markdown](https://reference.opcfoundation.org/specs/OPC-10000-10/v1.05.00/t63916693079/download/markdown), [Part 10 STS XML](https://reference.opcfoundation.org/specs/OPC-10000-10/v1.05.00/t63916693079/download/sts-xml).

The manifest pins actual response bytes, timestamps and final URLs. The selected section copies are exact inclusive LF-byte slices of the retained official Markdown export, not rewritten excerpts. The text/Markdown copies are byte-identical. Full XML and HTML are acquired provenance/structural evidence; they were **not** separately read in full. Both metadata text files were read completely.

`manifest.jsonl` preserves eight acquisition records. `reading-opcua-full.json` overlays actual reading status for four text sources, with 26 exact chunk hashes. `metadata/selected-sections.json` lists the 22 complete Part 4 section ranges (1,644 lines). The remaining 67 read Part 4 lines are introductory context and a chapter heading. Exact unread gaps are preserved in the receipt; no whole-Part-4 reading claim is made. `figure-manifest.json` pins 31 inspected figures, 16 from Part 4 and all 15 available from Part 10. The tiny labels in Part 10's low-resolution illustrative factory plan are not legible and are not evidence for engineering details.

The current reference URLs and old `/Core/.../v105/...` redirects are not immutable historical pins. Version/build exports plus hashes establish the retained snapshot. Official authoritative document links `https://opcfoundation.org/documents/10000-4` and `https://opcfoundation.org/documents/10000-10` returned HTTP 403; `metadata/official-download-attempts.json` records that limit. No login, license acceptance or bypass was attempted. The reference states that the authoritative publication prevails over its website.

Part 10 Figure 3 (Program states and transitions) and Figure A.11 (Sequence of operations) are referenced but have no available figure asset in the retained HTML/XML. A broken cross-reference to Figure 3 and an XML reference to the absent A.11 are preserved. This means all *available* public text and figure assets were read, not that the authoritative full publication was completely available. Table/figure inconsistencies are summarized in [the binding analysis](../../docs/opcua-binding.md).

The original local `audit_opcua.py` verifies acquisitions, figures, LF ranges, selected-section equality and missing-figure evidence. It executes only locally authored audit code, never acquired OPC code. `audit-result.json` retains its result and exact scope. A successful audit verifies consistency of retained evidence; it does not prove comprehension, device safety or OPC conformance.

Not covered in full: Part 4's remaining sections, Parts 2/3/5/6/7/8/9/11/12/16/18, companion specifications, actual server profiles, certificate configuration, controller code, hardware behavior or failure experiments. No repository snapshot is needed for this specification-only lane.
