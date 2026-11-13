# Visual corroboration

All eight arXiv PDF pages and all nine publisher-copy PDF pages were rendered locally with `pdftoppm -singlefile -scale-to 1800 -png` and viewed. The publisher copy adds a university cover and IEEE page numbers 515–522. This is full-page visual review alongside full LF text reading, not an inference from acquisition alone. Image hashes and source PDF hashes are in `reading.json`.

| Item | arXiv page / publisher PDF page | What was checked |
|---|---|---|
| Figure 1 | 1 / 2 | Wake/sleep cycles, task/demo/exploration legend, skill dependencies across three illustrated stages; arrows show composition, not a runtime safety or deterministic routing contract. |
| Figure 2 | 3 / 4 | Human demos/hints, LLM exploration, actor/critic, embedding retrieval, memory, AST clustering, abstraction, library and replay arrows. Caption explicitly says actor/critic are omitted from the sleep drawing but remain used during replay. |
| Unnumbered retrieval expression | 3 / 4 | Lambda encloses the relevance-minus-diversity term; cosine is described as a distance. No implementation correction was assumed. |
| Table I | 5 / 6 | Column grouping and dashes: CLIPort lacks spatial/visual rows; LRLL averages SA/UA/UI 96.9/97.1/86.6, static 94.5/91.9/76.8. Three runs are stated in text; table has no error bars. |
| Table II | 5 / 6 | FT/BT headers; LRLL averages 88.1/93.5, static 65.1/78.9, no-wake 51.3/50.5, no-sleep 80.6/89.6. These are task success percentages, not routing certainty. |
| Figure 3 | 6 / 7 | Left rearrangement/right visual reasoning, red explored/green train/blue test points. tSNE of instruction embeddings, not physical outcome-space coverage. |
| Figure 4 | 6 / 7 | Left experience counts before/after sleep; right success versus k retrieved examples. Axes are experiences and success percentage; no inference-free runtime or device RAM measurement is plotted. |

The other pages contain method/related-work text or references. They were also viewed, resolving two-column reading order and confirming there is no appendix in either acquired paper. The publisher's cover records version-of-record provenance, DOI and Taverne access context. The separate missing supplementary material is not represented by either paper's final reference page.
