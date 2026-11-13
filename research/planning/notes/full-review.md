# Planning and grounding: full-paper review

Reviewed 2026-11-06. The complete retained text of [SayCan v2](https://arxiv.org/abs/2204.01691v2) and [Code as Policies v4](https://arxiv.org/abs/2209.07753v4) was read, including appendices, references, prompts and acknowledgments. Every substantive figure and table was inspected on retained PDF renders. See [the coverage receipt](../reading-planning-full.json), [acquisitions](../manifest.jsonl), and [selected code receipt](../reading-code-selected.json). This is a historical source review, not a claim about later systems or a replication.

## SayCan evidence and its limits

Sections 3–4 separate a language score from a state-dependent skill affordance, then multiply them for greedy next-skill selection. Appendix D.2 matters: pick values need empirical calibration; navigation uses known object locations; place is assigned 1.0; termination receives 0.1. These scores therefore have different origins. Section 5 distinguishes human-rated plan validity from execution success. Table 2 reports 84%/74% in the mock kitchen and 81%/60% in the real kitchen; the drawer extension has 100% planning but 33% execution. Section 5.2 and Section 8 acknowledge insufficient failure feedback. [Paper, §§3–5, 8, Appendix D.2 and E.3](https://arxiv.org/abs/2204.01691v2)

Publication discrepancies retained rather than silently resolved:

- D.2 page 22 describes place affordance based on gripper state; page 24 sets it to 1.0 and relies on language ordering.
- Page 24 says 54% without examples and without required termination; page 25’s Table 5 says 52%.
- Table 5 labels both the prompt ablation and the task list spanning pages 26–28.
- Figures 15 and 17 repeat the same two rollout panels.

These were checked against rendered pages; none changes the central factorization, but they prevent treating the document as an exact deployment specification. [Paper, pp. 22–28, 32, 34](https://arxiv.org/abs/2204.01691v2)

## Code as Policies evidence and its limits

Sections III–IV generate Python that composes perception/control APIs and recursively defines missing functions. Quantitative robot-system evaluation is confined to simulation; the physical examples are demonstrations. Appendix K specifies scripted perception and an oracle-termination CLIPort comparator. Appendices F, G and I qualify toy controllers, perception errors, prior camera registration, and duplicate-object identity. The paper assumes feasible instructions and offers no advance correctness guarantee. [Paper, §§III–V and Appendices F–K](https://arxiv.org/abs/2209.07753v4)

Publication discrepancies retained:

- Table III gives CLIPort 0.01 for unseen-attribute/unseen-instruction spatial tasks; Table VI gives the corresponding oracle-termination aggregate as 1.3%. No correction is inferred.
- Appendix K calls seen spatial instructions 5–8, while its fifth instruction also belongs to long-horizon tasks. Table VI’s spatial aggregate matches rows 6–8. This review uses the table’s labels without silently fixing the prose.
- Figure numbering jumps from 2 to 4. Inspection of all sixteen pages found figures 1, 2, 4, 5, 6 and 7, with no Figure 3.

HumanEval Table V separates prompting from hierarchy and differs in model version from some cited comparisons. Coding-test pass rates do not establish robot reliability. [Paper, Tables III, V–VI, Appendix K](https://arxiv.org/abs/2209.07753v4)

## Selected implementation evidence

The two linked directories of `google-research/google-research` are archived at commit `d3a4bd8f0eceddda553e47085033b537935b283f`. All eleven subtree files were acquired. Only both READMEs and the explicitly listed source cells were read; outputs, other cells, dependencies and the rest of the monorepo were not audited. Cell indices below are zero-based. The source excerpts are retained for exact reading coverage; notebooks were parsed as JSON, never executed.

| Source | Exact inspection | Finding |
|---|---|---|
| [SayCan notebook](https://github.com/google-research/google-research/blob/d3a4bd8f0eceddda553e47085033b537935b283f/saycan/SayCan-Robot-Pick-Place.ipynb) | Cells 41, 43, 44, 49, 51 | Candidate text scores are summed token log probabilities; detector-derived affordances are binary except termination at 0.2. The runner computes affordances once, plans up to five steps, then executes the stored sequence. It is a tabletop illustration, not the paper’s stepwise robot/value-function system. |
| [CaP interactive notebook](https://github.com/google-research/google-research/blob/d3a4bd8f0eceddda553e47085033b537935b283f/code_as_policies/Interactive_Demo.ipynb) | Cells 5, 12, 21, 23 | Function synthesis parses an AST and recurses; API retry loops have no finite retry count in these cells. `exec_safe` checks two substrings, shadows `exec`/`eval`, then invokes Python execution. The wrapper routes placement directly to the simulator and uses configured object membership for visibility. |

The CaP execution helper is insufficient evidence of a security boundary or physical admission system. That conclusion follows from its inspected structure, without running an escape or claiming a full security audit. The notebook does not establish the behavior of the physical robot controller used in the paper. [Pinned implementation](https://github.com/google-research/google-research/blob/d3a4bd8f0eceddda553e47085033b537935b283f/code_as_policies/Interactive_Demo.ipynb)

## Independent interpretation

The reusable idea is a layered program: language proposes a task decomposition; bounded programs compute and compose; native skills provide physical behavior; observations test outcomes. Each boundary has a different question. A semantically relevant skill may be infeasible. A feasible skill may be unauthorized. An authorized command may fail. A successful command may fail to complete the requested goal. Combining these into one score makes diagnosis and enforcement harder.

The two projects usefully occupy different points in this design space. A finite skill vocabulary makes the executable surface explicit, but extending it requires real capability work. Generated code expands composition without requiring a learned skill for every geometric relationship, but it inherits every missing type, identity, timing and outcome contract in its APIs. Neither mechanism should be the sole source of execution authority.

HMS should carry both planner evidence and executor evidence. It should preserve candidate IDs, score provenance and input observation revisions for diagnosis while independently checking authorization, calibration, current state and budgets. Generated functions can be reviewed and reused as immutable artifacts. They cannot inherit permission merely because the language model wrote or previously used them. The [design analysis](../../../docs/planning-and-grounding.md) develops this into `hctl`, constrained-program and recovery requirements.

## Coverage boundaries and remaining work

- Full papers means the retained versioned PDFs, complete extracted text and all their substantive visual content. It does not mean every linked prompt, video, cited work or repository file was read.
- Project pages were consulted for official links and version context; their HTML/text is acquired, with selected web-page consultation only. Embedded videos and interactive demos were not played.
- No learned weights, training data, installation, inference, robot execution or hardware validation occurred. Toy benchmarks were not reproduced.
- A later review can inspect the remaining notebooks, linked prompt files and execution dependencies, then evaluate a separately implemented HMS planner against deployment-specific fault scenarios. That work remains open.
