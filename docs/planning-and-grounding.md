# Planning, skill grounding and constrained programs

Status: independent HMS design analysis, 2026-11-06. The complete SayCan v2 and Code as Policies v4 papers have been read, including their appendices and substantive figures/tables. The [research review](../research/planning/notes/full-review.md) records exact source qualifications and discrepancies; the [coverage receipt](../research/planning/reading-planning-full.json) records hashes and line ranges. The proposals below extend the existing [architecture](../spec/01-architecture.md) and [execution semantics](../spec/02-execution.md); they are not implemented by this document.

## What the two approaches contribute

SayCan ranks a fixed skill vocabulary using both language relevance and state-dependent affordance. Code as Policies composes perception/control APIs through generated programs, including arithmetic, conditions and loops. Together they suggest a useful division: learn or implement reliable physical primitives, expose their contracts, and let a planner compose them. Their demonstrations do not establish universal physical semantics, calibrated risk estimates or authority enforcement. [SayCan](https://arxiv.org/abs/2204.01691v2), [Code as Policies](https://arxiv.org/abs/2209.07753v4)

The foundational `hctl` abstraction should therefore describe an observable physical operation with a lifecycle. A shell process’s exit status is too weak for an action that may remain queued, move after disconnection, consume a sample, or finish without a reply. A general tool can compose device-specific operations without claiming that a universal device instruction set already exists.

## Four questions that need distinct answers

| Question | Representation proposed for HMS | Consequence |
|---|---|---|
| Would this advance the goal? | Planner proposal, goal/subgoal IDs, candidate ranking and explanatory evidence | Useful for choosing and inspecting plans; cannot grant execution rights |
| Can this deployment do it now? | Capability revision, embodiment binding, resource availability, fresh observations and feasibility assessment | A learned estimate can rank candidates; required preconditions remain explicit |
| May this principal do it? | Runtime-issued scoped authority, lease/fence, local mode and commissioned envelope | Enforced independently of model output and natural-language descriptions |
| Did the intended effect occur? | Operation record, endpoint evidence, effect verification, partial outputs and unresolved state | Determines continuation and recovery; planner prose cannot substitute for measurement |

This separation is an HMS design choice. In particular, “affordance” should not ambiguously mean both a WoT interaction description and a learned estimate of physical success. The registry can hold the former and reference a versioned estimator for the latter.

A probability field is not self-explanatory. Name its target event, conditioning state, model/policy version, calibration method, domain and validity period. A detector score, a language likelihood, a distance heuristic and an observed success frequency cannot be exchanged as if they have the same semantics. Allow a candidate score to be explicitly uncalibrated. Missing feasibility evidence should be `unknown`, with the deployment policy deciding whether a permissible observation or bounded probe can resolve it.

## Skill contracts and the `hctl` surface

Keep stable capability/action IDs separate from user-facing names. A planner can use rich descriptions and examples while the runtime binds the chosen action to exact semantics. Natural-language edits should not silently change units, frames, effects or permission. Catalog revisions should make aliases and description changes traceable.

An executable skill needs more than an input schema. Its contract should identify resource claims; eligible modes; required observations; physical preconditions; maximum duration and effect budgets; possible partial effects; success evidence; cancellation/stop behavior; and recovery constraints. A composite skill additionally needs its immutable procedure and dependency digests. A learned skill needs the model/controller/observation bindings already proposed in the learned-control profile.

The existing proposed commands remain a useful minimal foundation: `discover`, `describe`, `observe`, `invoke`, `operation`, `watch`, `cancel`, and `procedure check/run`. Add planning assessments as artifacts over this foundation rather than turning an advisory `check` into a reservation or execution guarantee. Its result should state exactly which versions, state revisions and authority scope were checked, and when those facts expire. Execution must recheck conditions that can change.

Object references require the same discipline as device references. A label such as “red vial” is a query, not a durable identity. Bind a selected object to a tracked instance or material ID, observation evidence, frame/calibration revision and confidence/ambiguity status. A duplicated object, occlusion, manual swap or lost track should invalidate assumptions before subsequent effects. A source photograph or detector crop can support a decision without making the detector a trusted authority.

## From dynamic code to a bounded executable plan

Generated code is useful for geometry, image analysis and task composition. The implementation should preserve that expressiveness while assigning computation and physical effects different boundaries. An isolated host computation can produce proposed coordinates, measurements or a procedure artifact. Effectful operations then pass through the same runtime admission used by manual `hctl` calls. Inject resource handles with specific scopes rather than a raw driver, network client or mutable controller object.

Before a generated program can run against hardware, make its executable content concrete. Resolve helper functions and library versions, pin their transitive digests, bind API schemas, and classify each call’s effects. A newly synthesized helper changes the artifact and requires the applicable validation/admission again. A function previously generated for one robot is not automatically qualified for another with different axis conventions or tool geometry.

For a tiny MCU, dynamic behavior should mean bounded composition of installed primitives or a validated compact instruction format. The host can perform richer computation and submit a finite procedure. Reject recursion and unsupported constructs explicitly. A native controller may implement a high-rate feedback primitive; it should advertise the measured timing and stop behavior of that primitive instead of making the network planner responsible for each control cycle.

The verifier should check call targets, typed values, finite arithmetic, units, frames, control-flow bounds, memory/queue limits and aggregate physical budgets. These checks reduce known classes of failure but do not prove a model’s inferred geometry or an arbitrary physical goal correct. Where static proof is unavailable, require a bounded runtime monitor and an explicit failure outcome.

For example, a conditional movement loop needs a maximum iteration count, maximum cumulative travel, local runtime limit and fresh observation condition. If the target is never observed, the loop should exhaust its budget and report an unmet condition. A CPU timeout alone is inadequate because a driver call may already have queued motion. A limit must hold at the component that accepts and executes the physical command.

Separate three budgets: planning/synthesis calls, computational execution, and physical effects. Exhausting one must not silently renew another. Model API retries need their own deadline and attempt count; they must not keep a resource energized or its lease renewed indefinitely. Unbounded recursive synthesis also needs a depth/function/token budget before any resulting artifact is considered executable.

## Failure, recovery and memory

Store attempted and observed outcomes as separate events. Appending a selected skill to a conversation is useful context, but it must not imply that the skill succeeded. A planner should receive structured feedback containing operation state, effect certainty, partial effects, affected resources and observation references. Missing evidence after dispatch becomes an unknown outcome and blocks conflicting follow-on work until reconciliation.

Treat goal completion as an explicit decision with evidence requirements. A model choosing a termination token establishes that it proposes to stop planning. It does not prove every requested subgoal was satisfied. Maintain a goal/subgoal record separately from the action log, including unsatisfied and unverifiable goals. Repeatedly choosing a feasible action without advancing a subgoal should trigger a bounded no-progress policy.

Retries and compensation are physical policies. A failed grasp can leave the object displaced; a timeout after dispensing can leave an unknown delivered volume; a lost inspection reply can concern a part already moved to another station. Reobserve, reconcile and select a permitted recovery based on the actual state. Preserve the original operation key for result lookup; do not create a fresh physical intent merely to escape a timeout. Compensation has its own preconditions, authority and irreversibility.

Conversation history and Python variables are temporary working memory. Persist the operation and evidence records needed for crash recovery in the runtime, including material custody and executed procedure prefixes. After restart, a stored geometric point may be invalid because calibration, frame or object identity changed. Replaying code or loading an old local variable cannot restore the physical world.

## Application across home, laboratory and manufacturing

| Setting | Useful planning behavior | Contract that must constrain it | Recovery evidence |
|---|---|---|---|
| Home comfort automation | Compose occupancy, temperature and actuator capabilities | Fresh sensor state, user scope, bounded setpoints, appliance-specific mode and timing | Actual device state after reconnect; a prior command echo does not prove present state |
| Home manipulation | Find and fetch a selected object | Tracked object identity, reachable workspace, load/tool constraints, bounded navigation and grasp primitives | Gripper/object observations before retry or release; unresolved identity inhibits delivery |
| Microscope or laboratory instrument | Compute candidate scan points and choose acquisition steps | Sample ID, calibration/frame binding, finite travel/exposure budget, reserved axes and camera | Actual position, capture metadata and raw data; partial acquisition stays visible |
| Experimental optimization | Suggest the next setting based on results | Separate analysis provenance, approved search space, material and thermal budgets | Independent measurement quality and sample history before further irreversible work |
| Manufacturing cell | Choose an approved recipe or bounded inspection path | Fixture/tool/material identity, cell mode, shared-zone exclusion, program revision and local interlocks | Part custody, gripper/fixture state and executed prefix before resuming a work order |

These are proposed application designs, not capabilities demonstrated across all domains by either paper. The amount of local autonomy can vary: a home endpoint may accept a bounded desired setpoint, a lab appliance a finite scan procedure, and a cell controller a qualified recipe. The planner’s location may vary too; a GB10 hub can host planning or perception while endpoints keep their own watchdog and authority checks.

## Evaluation to perform before adopting a planner

Evaluate semantic task success and execution reliability separately, then report the complete system outcome. Include refusal accuracy on unavailable or unauthorized actions, calibration under distribution shift, stale observations, repeated-object ambiguity, invalid units/frames, budget exhaustion, interrupted skills and unknown outcomes. Report the exact skills, perception service, controller and test environment; success on code unit tests or a simulator cannot establish real-device behavior.

Use a common fault suite for planners that select skills and planners that generate programs. The key comparisons are whether each respects the same runtime boundaries, recognizes insufficient evidence, and produces recoverable records. Measure time and resource use under contention, including model outages. Preserve failures and incomplete tasks alongside successful demonstrations.

The immediate implementation work is a typed proposal artifact, an admitted bounded procedure format and an operation/evidence runtime. The research supports building those contracts before exposing arbitrary generated programs to physical adapters. Full notebook/dependency audits, planner integration, hardware commissioning and domain-specific evaluations remain open.
