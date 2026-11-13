# EDHOC full-source review

Reviewed 2026-11-06. This lane completes the RFC 9528 reading obligation previously left at introductory coverage in the [OSCORE reading record](../reading-oscore-full.json). It supplies research evidence and proposed [HMS binding constraints](../../../docs/edhoc-binding.md), not a crypto implementation or a qualified embedded target.

The RFC Editor plain-text RFC was read completely: 4,671 LF-delimited lines, all sections, security considerations, normative/informative reference lists, Appendices A–I, acknowledgments and author addresses. All 13 figures and 15 tables were read in text and corroborated visually in 25 selected pages of the 82-page official PDF. The whole PDF is retained, but a second complete page-by-page PDF reading is not claimed. Reference entries were read; the contents of every referenced work were not followed.

Six primary-source retrievals are frozen in [manifest.jsonl](manifest.jsonl): official TXT, PDF, RFC Editor JSON metadata, errata page, RFC information page, and IANA EDHOC XML registry. The metadata, extracted errata and registry were read completely. Only information-page text lines 1–180 were read; that page now embeds a full alternate RFC rendition. Its unreviewed remainder is explicitly excluded from reading credit. PDF layout text is a caption/page index, not another full-read source.

The new RFC TXT is byte-identical to the earlier OSCORE lane's selected RFC 9528 copy (SHA-256 `16b0959ee791bba5b06a4368470f8eb296ac11b84101c82b9013073ec6defe9e`). This new reading overlay supersedes the earlier limited coverage for these bytes; it does not rewrite historical reading assertions or count a new protocol publication. RFC 9668's full review remains in the OSCORE lane and was not reacquired or reread here.

Use [reading.json](reading.json) for exact source hashes, LF coverage hashes, reading status, visual scope and integrity files. [Review notes](notes/full-review.md) separate RFC requirements, current errata/registrations, and HMS inferences. [Figure inventory](notes/figure-inventory.json) records exact rendered bytes and inspected pages. The read-session note records the actual untruncated reading boundaries, including a truncated attempt that was reread before receiving coverage credit.

From the repository root, run:

```sh
python3 research/constrained/edhoc-full/verify.py
```

The verifier is original, offline and standard-library-only. It checks archival integrity and the consistency of declared coverage, including negative self-checks. Hashes cannot prove that a human or model understood a document. It does not implement, test or execute EDHOC, cryptographic vectors, a controller or acquired code. Its bounded result is [verification.json](verification.json).

`acquire.py` documents retrieval/extraction and may refresh raw files if explicitly run; changing those files invalidates the frozen reading evidence until reviewed again. `render.py` reproduces selected-page PNGs using installed Poppler tools and does not mark new renders as reviewed. Raw HTML, XML, TXT and PDF are data. The original downloads were not executed.
