# Laboratory research corpus

This lane contains six acquisition records: the SiLA downloads page, two SiLA 2 v1.1 specifications, the LabOP paper and two Bluesky 1.15.1 documentation pages. All were downloaded; the downloads landing page has only selected inspection. Acquisition-time reading statuses are retained in [manifest.jsonl](manifest.jsonl), with subsequent coverage recorded separately.

- [LabOP/Bluesky reading receipts](reading-log.json): complete paper/page text, exact source hashes and figure scope.
- [SiLA full-reading receipts](reading-sila-full.json): both documents, 8,248 LF-addressable lines, eighteen hashed ranges and forty-six inspected page renders.
- [Repository pins](repositories.json): Bluesky and LabOP commits, file hashes and exact full/partial inspection ranges. Entire repositories have not been read or executed.
- [LabOP figure derivatives](figure-manifest.json): ten inspected pages containing all twelve numbered figures.
- [LabOP/Bluesky critique](notes/labop-bluesky-review.md) and [SiLA critique](notes/sila-full-review.md), including [mapping details](notes/sila-mapping-review.md).
- Derived design: [laboratory bindings](../../docs/laboratory-bindings.md) and [workflow/material semantics](../../spec/06-workflows-materials.md).

The retained SiLA PDFs came from publicly reachable official URLs; no account or access-control bypass was used. Source copyrights/licenses remain with their owners. Reference checkouts are research material, not installed HMS dependencies. Linked feature schemas, reference servers and additional papers are separate acquisition/reading work. A full document read does not establish implementation conformance or measured instrument behavior.
