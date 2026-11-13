# Microscope controller source review

This archive supports [the proposed microscope binding](../../docs/microscope-controller-binding.md). It is read-only research, not a physical adapter or hardware validation. No acquired code/test was run and no device or live microscope service was contacted. The local verifier checks retained bytes and source pins only.

| Record | Purpose |
|---|---|
| [pins.json](pins.json) | Existing versus newly acquired repositories; verified current heads; distinct latest release commits |
| [selected-files.json](selected-files.json) | Exact SHA-256 values and complete/partial reading ranges for 32 selected source/test files |
| [coverage.json](coverage.json) | 31 complete files, 765 selected function lines, full autofocus paper and all eight figures, partial Picamera2 manual, four rendered ASI command pages |
| [source-notes.md](source-notes.md) | Original critique, concrete failure paths and limits of the evidence |
| [acquisition.json](acquisition.json) | Official URL, acquisition time, HTTP status and response hash, including failed requests |
| [manifest.json](manifest.json) | Inventory of retained source, document, metadata and figure bytes |
| [audit.json](audit.json) | Local consistency verification result |

OpenFlexure and Gently remain at their earlier physical-AI corpus commits. Selected files were copied into `snapshot/` so this review has a stable bounded set without changing old manifests. `repos/` contains newly acquired Sangaboard firmware and Python serial sources; the presence of their other files does not imply they were read. Release metadata is not release-artifact validation.

The existing autofocus PDF and extracted text remain under `research/physical-ai/`; their hashes and new full-reading/figure coverage are recorded here. Figures were rendered locally from that PDF without altering it. The Picamera2 PDF is complete, but only the selected sections in `coverage.json` were read. ASI HTTP 403 response bodies are retained as failed retrievals. `asi-selected-web-render.json` contains the separately obtained primary-page web-tool text and is not represented as original HTML. Unavailable commands are explicitly excluded from the claims.

Run the locally authored, non-network verifier from the HMS root with `python3 research/microscopy-controller/verify_retained.py`. It does not import or execute acquired programs. The review has not been added to the root corpus auditor; that integration belongs to the coordinating agent.
