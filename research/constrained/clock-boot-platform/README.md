# Clock and boot platform evidence

Primary-source acquisition and reading on 2026-11-06 for AVR ATmega328P and
RP2040. Findings and the proposed platform contract are in
[docs/clock-boot-platform.md](../../../docs/clock-boot-platform.md).

`manifest.jsonl` records exact successful response bytes, URLs, redirect
destinations, retrieval times and hashes. `reading.json` records exact LF-byte
coverage and distinguishes full files from selected ranges. PDF extraction
used `pdftotext -layout` (Poppler24.02.0), without normalizing the resulting
bytes. `figure-renders.json` records original PDF page renders and the actual
visual inspection scope. The large AVR and RP2040 manuals are **selected
reads**, not full-datasheet claims. The small AVR101 note, current AVR family
errata, six pinned SDK files and two SDK metadata records were read fully.

```sh
python3 research/constrained/clock-boot-platform/verify.py
```

The verifier is original, stdlib-only, offline code. It verifies evidence
integrity/coverage and performs negative checks against altered metadata in
memory. It does not execute acquired SDK code, infer comprehension from a
hash, validate an electrical fault model or qualify any hardware. No downloaded
source, MCU binary, emulator or physical device was executed in this lane.

`notes/source-status.json` distinguishes current source/release metadata from
manual revision and records acquisition limits. `notes/context-pins.json`
pins local context at review time; these historical hashes are not a demand
that active root-owned implementation files remain unchanged. The original
byte-bank implementation is owned and verified in a separate root lane.
