# Planning and grounding corpus

The complete retained SayCan v2 and Code as Policies v4 papers were read on 2026-11-06: 3,053 LF-delimited logical lines, including appendices/references, with all substantive figures/tables checked on 40 retained page renders. Code as Policies has sixteen pages; all sixteen were also visually inspected. SayCan has thirty-four pages; twenty-four containing figures/tables or discrepancy prose were visually inspected.

The [PAT learning lane](pat-learning/README.md) adds full Voyager arXiv v2 reading on 2026-11-07: 2,553 LF lines including both appendices/references; all 14 figures and six tables checked on 18 selected PDF pages. The official project text and thirteen complete selected repository files are also read. Its [critique](pat-learning/notes/critique.md) distinguishes reusable code inside an LLM loop from deterministic contextual selection and zero-inference PAT execution. Voyager publisher-final access remains unresolved. Its historical [LRLL, AutoSkill and Skill++ queue](pat-learning/queue.json) preserves metadata-only coverage at that point in time; AutoSkill and Skill++ remain unread papers.

The subsequent [LRLL lane](lrll-full/README.md) fully reads arXiv 2406.18746v2 (529 LF, eight pages) and the official institutional publisher copy (622 LF, nine pages including its cover). Every page and all four figures/two tables were visually checked in both versions. Three complete selected website files include a 248-LF prompt artifact; there is no full orchestration-source review. The unfinished project's supplementary and Code links fail. The [critique](lrll-full/notes/critique.md) distinguishes abstraction/replay and model-based reuse from deterministic applicability and PAT admission; [version comparison](lrll-full/notes/paper-comparison.json) retains metadata/email differences without asserting equivalence. All earlier acquisition and reading pins remain unchanged; the broader research queue stays open.

| Artifact | Purpose and scope |
|---|---|
| [manifest.jsonl](manifest.jsonl) | Four immutable acquisition records: two versioned PDFs and two official project pages. `unread` is the acquisition-time status, superseded only by an explicit reading record. |
| [reading-planning-full.json](reading-planning-full.json) | Full-paper receipts with source hashes, contiguous exact-byte LF ranges, visual-page coverage and publication inconsistencies. |
| [repos.json](repos.json) | Complete snapshots of the two official Google Research subdirectories at one pinned monorepo commit, eleven files total. No clone of the rest of the monorepo. SHA-256, Git blob hashes and reconstructed subtree hashes were checked. |
| [reading-code-selected.json](reading-code-selected.json) | Full reading of two READMEs and nine selected notebook source cells; all other notebook cells/outputs remain unreviewed. |
| [artifacts.json](artifacts.json) | Digests and sizes for sixty-eight acquired or derived artifacts, including all snapshots and page renders. |
| [review](notes/full-review.md) | Source evidence, exact discrepancies, implementation qualifications and independent critique. |
| [HMS analysis](../../docs/planning-and-grounding.md) | Proposed grounding, authority, program bounds and recovery contracts for `hctl`, home, laboratory and manufacturing applications. |

Notebook files were parsed as JSON to extract source text. No downloaded code, weights, datasets, inference, simulation, installation or physical-device interaction was executed. Reading the complete papers does not imply reading their external linked prompts or videos.

The corpus auditor already discovers `reading-planning-full.json` through its full-reading glob. Integration should additionally verify the four acquisition records, the `artifacts.json` list, and each selected notebook cell’s equality to its parent notebook source. `repos.json` is a pinned snapshot manifest, not a Git checkout manifest: verify recorded Git blob/tree hashes and do not call `git rev-parse` in these snapshot directories. Count the two subtrees as one distinct monorepo commit pin and retain their narrower acquisition scope.
