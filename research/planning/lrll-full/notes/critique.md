# Relevance to experiential learning and deterministic PAT reuse

LRLL offers a useful learning-loop design, but its reuse path still performs model inference. Learning a Python function is a different milestone from admitting a bounded, context-qualified PAT that a deterministic dispatcher can invoke without a model. This distinction is explicit in the [paper's actor/critic inference description](https://arxiv.org/pdf/2406.18746v2), locally preserved in [arXiv text](../text/lrll-v2.txt) and [publisher text](../text/lrll-publisher.txt) LF 276–303.

| Source evidence, paraphrased | Location |
|---|---|
| Wake explores tasks; generated action/success code supplies successful experiences. Sleep clusters policy ASTs, abstracts functions, refactors and replays. | Publisher LF 215–260, Figure 2 |
| Instruction embeddings retrieve examples; actor and critic are parallel LLM calls. | Publisher LF 240–256, 274–303 |
| Evaluation uses four curriculum cycles, 41 templates and three teacher seeds. | Publisher LF 319–327, 348–402 |
| Learned abstraction reduces stored experiences and prompt context. | Publisher LF 419–444, Figure 4 |
| Real demonstrations use dual UR5e arms, Kinect and additional grasp perception; collisions and misclassifications are reported. | Publisher LF 414–456 |

The [official prompt file](https://github.com/gtziafas/LRLL_project/blob/25097958485a91450c3a15e5ba9023936180db4b/prompts.py), fully preserved [locally](../repository/website-prompts-py.py), corroborates policy/success generation templates (LF 1–45), exploration prompts (71–136), and function abstraction prompts (172–213). It contains strings, not the caller, retriever, AST clusterer, persistence manager, admission checker, or controller. No end-to-end implementation behavior is inferred from these strings alone.

## Context selection and zero-inference reuse

For HMS, retrieval should nominate a candidate; it cannot authorize effects. A meaningful deterministic reuse contract must bind normalized intent, argument domains and units, available capabilities, observation age, environment identity, resource ownership, and the procedure's effect envelope. It needs a reproducible match rule and an abstention result for novelty, ambiguity, stale context, or conflicting candidates. Otherwise a familiar instruction can silently select an inapplicable skill. These are design deductions for PAT, not features established in LRLL.

Even deterministic nearest-neighbor ranking over stored vectors does not eliminate the model cost of embedding a new query. LRLL's paper describes both query embeddings and subsequent policy/success generation; the prompt artifact supplies no exact-match cache or model-free routing path. Figure 2's sleep panel omits actor/critic boxes for space, but its caption explicitly says replay still uses them. A scheduler that repeats an already admitted PAT can avoid those calls only if the host supplies an additional deterministic dispatch layer.

The displayed retrieval expression in both PDFs places lambda outside the parenthesized relevance-minus-diversity term and calls cosine a distance. Its exact executable interpretation, initialization with an empty selected set, tie behavior, and parameter values cannot be resolved from the missing retriever source. The equation was visually inspected rather than silently replaced with a familiar MMR implementation. PAT's routing rule should be executable, versioned, and tested directly.

## Promotion, evaluation, and retained experience

AST similarity is useful for proposing abstractions, but identical tree shapes do not prove equal physical effects. Abstracting a constant into a parameter can widen a safe example into an unsafe domain. Candidate promotion therefore needs typed bounds, explicit assumptions, effect and resource declarations, dependency closure, and counterexamples outside the proposed domain. Replaying successful demonstrations alone cannot establish those properties. Both the action and its success predicate may share a generation error, so a separately specified acceptance oracle matters.

The prompt's restriction to imported functions is a textual instruction, not a parser or enforcement boundary. The abstraction exemplar at LF 220–246 is also internally inconsistent: the first demonstration computes names but passes the object collection to `say`; the generalized function passes names. This is direct text inspection, not an executed failure or evidence that the published experiments used this artifact unchanged. It illustrates why “preserve common logic” needs semantic checks rather than relying solely on a prompt.

For PAT, retain the full evidence and dependency versions even when a compact index is enough for routing. Keep candidate, evaluated, admitted, retired and revoked states distinct; record the observation and test scope supporting each transition. A new library version should not mutate an in-flight instance or silently rebind an admitted dependency. These mechanisms are not specified by LRLL's described library union, naming/descriptions and dependency tracing. Memory compression is a storage optimization, not an audit-retention policy.

The tables show finite empirical results, not proof of absence of forgetting, global semantic coverage, or safety. Table I's CLIPort averages span only two applicable task classes, while the LLM averages span four; direct whole-table average comparisons need this qualification. Table II tests a selected prior-task subset. Neither table gives dispersion estimates. Figure 3 projects language embeddings rather than effect coverage. Figure 4's storage reduction is not a measured SRAM budget or combined firmware fit for Arduino. The full evaluation source and unavailable supplementary material would be needed for stronger reproducibility claims.

## Cancellation, recovery, and hardware scope

Simulator replay assumes stored initial simulator state. Physical replay needs separate treatment: a partial grasp, contact, or actuator command cannot generally be undone by resetting software memory. An HMS PAT should identify safe boundaries, bounded execution and retry budgets, cancellation acknowledgment, output-safe terminal states, stale observation handling, and the effect of losing a device lease. Recovery should be an admitted procedure or a return to the host, not an unbounded generated retry. The reviewed papers and prompt strings do not provide these operational contracts; unavailable controller code cannot be presumed to lack or implement them.

Natural-language programming still needs platform capabilities and calibrated primitives. LRLL's real demonstration is evidence for its reported setup, not arbitrary plug-and-play Arduino operation, contact-rich control, real-time guarantees, or combined firmware memory fit. The reported sim-to-real transfer follows provision of platform vision and motion APIs. No hardware trial was repeated here. No acquired code was imported, evaluated, compiled, or executed.

## Acquisition and completeness boundary

The [project HTML](../repository/website-index-html.html) LF 71, 79–117 records the unfinished site and placeholder links. The pinned website tree includes only the selected prompt artifact relevant to LRLL's learning prompts; it does not establish a full implementation release. The author-account inventory is a bounded discovery check, not proof that no other implementation exists anywhere. [Provenance](../provenance.json) preserves 404 supplementary/code failures and the 403 institution download attempt alongside the successful official repository endpoint. Both paper bodies, their references, and all numbered figures/tables are read; separate supplement and full implementation remain gaps. The wider research goal stays open.
