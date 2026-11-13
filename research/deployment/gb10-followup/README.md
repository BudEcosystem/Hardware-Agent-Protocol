# GB10 / DGX Spark bounded deployment follow-up

This lane retains six complete bounded NVIDIA HTML pages, their raw bytes and
extracted primary content, all eight table structures and one visually reviewed
rear-panel image. Reading covers 1,013 LF-based lines. “Complete” applies to
these pages, including the advanced tab of one playbook; it does not cover
linked documents, other tabs, complete guides, code repositories or packages.

- [Findings and HMS implications](../../../docs/gb10-deployment-evidence.md)
- [Acquisition manifest](manifest.jsonl)
- [Exact reading coverage](reading.json)
- [Figure provenance](figure-manifest.json)
- [Acquisition and extraction notes](notes/method-and-gaps.md)
- [Offline integrity result](verification.json)

The hardware page is an explicit same-URL, same-byte revisit of an earlier
source. It is one of six acquisition records here, not a sixth new unique work.
Acquisition reading statuses are preserved; the reading overlay supersedes them.

The vLLM response uses server-streamed HTML outside an empty main placeholder.
The initial empty extraction is retained, and the corrected full page was
extracted from the same raw response without executing its JavaScript.

```sh
python3 -I -B research/deployment/gb10-followup/verify.py
```

The checker tests retained hashes, page/line/table/figure coverage metadata and
negative metadata mutations. It does not prove comprehension, publisher truth,
package compatibility or physical behavior. No acquired command or program was
executed; example shell commands in the archive are source material.
