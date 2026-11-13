# Visual corroboration scope

Rendered the pinned 42-page arXiv v2 PDF with `pdftoppm -singlefile -scale-to 1600 -png` and inspected the saved images. Text reading covers the entire PDF extraction; visual inspection covers only pages listed below. Image labels, arrows, table columns, code indentation, and graph axes were checked. No data were digitized or experiments reproduced.

| PDF page | Inspected content |
|---|---|
| 1 | Figure 1: distinct-item graph and prompting-iteration axis; skill-library ablation and four methods' curves. |
| 2 | Figure 2: curriculum → iterative generation; retrieval into generation; environment and critic feedback; success adds a skill. |
| 3 | Figure 3: contextual states feed GPT-4 task proposals. |
| 4 | Figure 4: description model → embedding key; code value; task suggestion plus environment feedback → embedding query → top-five retrieval. |
| 5 | Figure 5: environment/error messages precede model code revisions. |
| 6 | Figure 6: inventory-based model success/critique examples. |
| 7 | Table 1's success fractions and iteration means; Figure 7 enclosing map circles. |
| 8 | Table 2; Figure 8 subgoal progress over code-generation iterations. |
| 9 | Figure 9 ablations; Figure 10 building progression with human feedback. |
| 19 | Pseudocode 1: model generation and critic remain inside each task attempt; success stores code. |
| 21 | Table A.1: observation/context warm-up thresholds. |
| 30 | Prompt 4: the loop/recursion prohibition is a textual instruction. |
| 32 | Skill example 1: immutable pre-mining log choice is not refreshed; skill example 2 and start of example 3 also present. |
| 34 | Skill example 5: unbounded search and decrement-to-retry branch are visible. |
| 38 | Table A.2: system-level comparisons, including differing observations/actions. |
| 39 | Table A.3 and Figure A.1 icon/name legend. |
| 41 | Figure A.2 trajectories recorded at GPT-4 interactions; relationship to enclosing circles. |
| 42 | Figure A.3; Table A.4 top-k retrieval accuracy; Figure A.4 historical model variation curves. |

All 14 numbered figures and six numbered tables have corresponding images. Pseudocode/code checks are additional selected visual observations. Referenced studies and the project's videos, interactive demonstrations, and linked media articles were not watched or read through this lane.
