# Learned control deployment profile — proposed design

This proposed HMS profile binds a learned policy to a particular device deployment. It extends the [execution semantics](../spec/02-execution.md); it is not an implemented wire schema, robot adapter or certification. Requirements below describe what a conforming implementation would need to deliver. A conventional deterministic controller can use HMS without this profile.

The evidence base is the complete extracted-text and figure/table review of GR00T N1 v2 and OpenVLA v3, documented in [the critical review](../research/physical-ai/notes/vla-full-review.md) and [coverage record](../research/physical-ai/reading-vla-full.json). In particular, OpenVLA's control-mode/quantization experiment and GR00T's lost handover skill after post-training make model-only compatibility insufficient. The protocol requirements here are our design deductions, not features asserted to exist in those projects.

## Authority and identity

A policy service generates proposed actions. It MUST NOT acquire actuator authority merely by returning plausible values, a confidence score or a natural-language claim of success. A commissioned executor checks proposals against the operation's immutable intent, observation requirements, leases, physical limits and current device state. A policy's training distribution is not an authorization boundary.

The deployment binding MUST identify the complete executable configuration:

| Binding component | Required meaning |
|---|---|
| Model artifacts | Architecture/configuration, weights and adapter digests, tokenizer and decoding/sampling configuration |
| Numerical execution | Precision, quantization method/configuration, inference runtime and relevant kernel/backend versions |
| Embodiment | Robot/device description, end-effector/tool identity, kinematic convention, controller mode and semantic revision |
| Action conversion | Field order, dtype, normalization statistics, units, frame transforms, rotation representation and conversion implementation |
| Observation conversion | Camera identities and geometry, calibration, crop/resize/color conventions, input history and required state channels |
| Timing | Validated action cadence, observation age/skew limits, chunk horizon, queue budget, blocking/nonblocking behavior and interruption policy |
| Evidence | Task/environment envelope, evaluation protocol, failure results, timing measurements and commissioning revision |

These artifacts are immutable references. An installed binding generation selects compatible versions; it is distinct from the resource control generation and endpoint session identity. Relevant configuration changes invalidate evidence and queued starts until a new binding is commissioned. Post-training, quantization or a runtime change can affect behavior even when dimensions and API names stay constant. Revalidation must cover retained capabilities as well as newly trained ones; a newer checkpoint does not automatically inherit its predecessor's permissions.

Publishers, transport identities and artifact hashes establish provenance and integrity, not fitness for a physical task. Policy code, serializers and model-loading mechanisms need an installation trust decision. Downloaded executable model code cannot gain device credentials through a model artifact. Online learning produces a candidate revision; it cannot silently replace the commissioned controller.

## Observations and actions

A policy observation bundle MUST reference each contributing observation or immutable data object and preserve its source, evidence kind, acquisition time, clock domain/epoch, uncertainty, maximum age, sequence and calibration. Camera exposure/readout and buffering count toward age. Receipt time alone cannot make an old image current. Bundles specify allowed temporal skew between images and proprioception and which history entries are required. A missing frame or state measurement must not become zero or a silently repeated previous value.

The binding specifies the permitted input subset and dropout response. A single-image policy can be valid for one deployment without pretending to use proprioception; a model trained with synchronized wrist images cannot silently run without them. Simulator observations, inferred object poses, commanded joint positions and measured joint positions retain different evidence kinds. The goal and instruction template are versioned inputs; text seen within images is observation content, not authority to change the goal or physical limits.

An action schema MUST define each channel's physical meaning. For motion this includes unit, frame, handedness, axis ordering, absolute/relative semantics, reference state, rotation convention, target-versus-increment semantics and execution duration. Gripper channels distinguish aperture, force, velocity, binary command and normalized training labels. For a relative rotation, composition order and reference frame are explicit. A seven-element vector is not a device-independent motion command.

The codec converts model values to typed physical proposals before admission. Dataset min/max or quantile ranges serve decoding; independently commissioned workspace, travel, rate, acceleration, effort, exposure and energy bounds govern actuation. Undeclared clipping or unit conversion cannot conceal a changed intent. A bounded policy-level constraint filter may be commissioned explicitly, with its permitted modification envelope included in the admitted procedure; it records original and modified proposals and rejects changes outside that envelope. Persistent filtering is a degraded-controller condition, not silent success.

## Inference jobs, chunks and physical operations

An inference job and an HMS physical operation have separate lifecycles. Completion of an inference request means that a result was produced, not that a controller accepted or applied it. A job identifies its stable request key, observation bundle, model/binding revision, goal revision, endpoint session, resource control generation and result deadline. A physical operation additionally retains HMS's durable admission, replay namespace, resource authority and completion-evidence requirements.

The deployment exposes whether the policy proposes one action or a chunk. A chunk result MUST carry a chunk ID/sequence within a declared producer epoch, its observation references, intended time base, point offsets or durations, reference state, expiry and supersession rule. A predicted horizon is not a promise that every point remains valid for that duration. The executor records the accepted and actually applied prefixes separately. Buffer capacity is bounded.

Chunk acceptance checks current binding and authority generations, observation age, state/reference consistency, limits and remaining operation budgets. Checks that must remain true during motion are enforced locally at the required cadence. For a model that does not condition on proprioception, the executor may still use measured state to reject incompatible proposals; this does not pretend the model consumed it.

Asynchronous inference may overlap execution, but a delayed result based on older state MUST NOT automatically replace a newer chunk. The commissioned scheduling strategy defines ordering, maximum state deviation, latest usable result time and what happens when a result misses its window. Any prefix discard, temporal blending, retiming or overlap correction is part of that validated strategy. A generic server cannot assume that dropping the first few actions repairs staleness, particularly for relative actions whose effects accumulate.

Accepting a replacement atomically invalidates the relevant unexecuted suffix; any already buffered controller commands must be revocable or explicitly reconciled. If hardware cannot revoke them, advertise the actual handover bound and withhold conflicting execution. Transport retry never replays a relative increment as a new effect. After a restart, recover the accepted/executed record and reconcile endpoint state; unknown progress is `outcome_unknown`, not permission to resend a chunk.

## Termination and manual intervention

The bounded procedure defines independent task completion evidence, action/travel/exposure totals, maximum duration, stalled-progress criteria and allowed recovery attempts. A model “done” token or confident caption may request verification; it cannot alone prove a physical objective. Conversely, a policy that continually emits zero motion may be stalled even though inference succeeds. Legitimate holds remain distinguishable from unexplained lack of progress.

The physical operation uses the core accepted/dispatching/running/completed/failed/canceled/outcome_unknown states. Canceling an inference job does not cancel queued motion. Canceling motion requires the controller's documented termination procedure and observed evidence; acknowledgement alone is insufficient. If movement stops but a gripper holds a load or a heater stays energized, the resulting resource and energy obligations remain explicit.

Manual movement, teleoperation, fixture change or takeover advances the affected control generation, invalidates queued proposals and affected inferred state, and invokes the commissioned interruption policy. Pending inference can finish for audit but cannot act under the old generation. Resumption requires fresh observations and reconciliation; it must not silently restart the previous prompt against a moved object. Endpoint restart and camera stream restart also invalidate their respective sessions/epochs without being mistaken for the same event.

Loss of inference, network connectivity, lease authority or fresh sensing invokes a locally installed, bounded response such as hold, controlled stop or completion of an assessed atomic step. There is no universal power-off default. The watchdog, interlocks and operator stop path cannot depend on the inference process remaining responsive or on access to its GPU.

## CPU, edge and hub placement

HMS does not require every endpoint to host a large model. An MCU can execute installed primitives and enforce queue/timer limits while a CPU gateway supplies durable operation state and a GPU service proposes trajectories. A CPU-only controller, classical focus search or small perception model can be preferable when it meets the task requirements. These papers do not supply CPU timing evidence for their full VLAs.

An onboard GPU, edge computer or shared hub—including a proposed GB10 deployment—must be measured with the exact model variant, software stack and controller. Published L40, A5000, A100 or 4090 measurements cannot be converted into a GB10 deadline guarantee by parameter count, memory capacity or advertised peak throughput. Memory fit is necessary for a candidate deployment but does not establish useful control latency. Training, fine-tuning and inference have separate resource budgets.

Measure the complete loop: exposure/readout, preprocessing, queueing, transport, inference, proposal validation, controller enqueue and physical response. Report distributions and observed deadline misses under representative camera, storage, thermal and concurrent-inference load. Separate inference jobs per second, actions per chunk, fresh-observation rate and drive-servo rate. A fast average is not a worst-case bound.

The scheduler admits only work whose measured service budget and queue bound fit the deployment. Batching is allowed only within each device's latency budget. Backpressure cannot block local control or stop handling; preview streams may drop according to an explicit policy while required execution evidence remains retained or produces a gap. Remote inference requires a commissioned partition response and authenticated, integrity-protected channels. Sharing a network with an inference server does not grant that server actuation authority.

## Evidence and evaluation contract

A deployable capability names its task distribution, objects/materials, fixture/layout, initial-state envelope, sensors, calibration and acceptable outcomes. Evaluation records include demonstrations and test-trial counts, scoring rubric, partial-credit rules, seeds, checkpoint selection, operator interventions, timeout policy and failure taxonomy. Report full-task completion separately from intermediate progress. Preserve unfavorable per-task results; aggregate success cannot substitute for coverage of the particular capability being admitted.

Simulation evidence names the simulator, assets, dynamics/randomization, preprocessing and dataset filtering. It does not become physical evidence by using the same operation schema. Real deployment testing must include timing, interruption and recovery behavior that successful-demonstration learning does not establish. Changes in quantization, scheduling or blocking/nonblocking control require evaluation of closed-loop outcomes, not only offline token accuracy.

For each attempt retain the observation references, goal/model/codec/binding versions, raw proposal, rejection or filtering reason, accepted chunk, actually applied prefix, controller measurements, timing, manual interventions and outcome evidence. The distinction between proposed command and achieved motion must survive conversion into future training data. Logs preserve missing/uncertain evidence instead of filling it with intended state. Data access and retention remain attached to image and trajectory references.

## Required behavioral checks before claiming conformance

These are proposed test obligations, not tests already run in this repository.

| Injected condition | Required observable behavior |
|---|---|
| Correct shape, wrong codec/units/frame | Reject before effects; identify incompatible binding |
| Old camera frame with recent receipt timestamp | Fail freshness requirement using acquisition-age bounds |
| Camera/proprioception skew or required input missing | Reject or use only an explicitly commissioned degraded mode |
| Delayed, duplicated or out-of-order inference result | No replay or supersession of newer valid work |
| Manual takeover during inference/queued execution | Advance control generation and invalidate pending work |
| Model, calibration, tool or controller-mode revision changes | Invalidate incompatible binding evidence and queued starts |
| Compute overload or lost server connection | Bound queue and execute the installed local loss response |
| Restart after a partial chunk | Reconcile applied prefix; report uncertainty without reapplying it |
| Cancel acknowledgement without physical stop evidence | Keep execution outcome unresolved until appropriate evidence |
| False model success or indefinitely repeated no-op | Verify independently or terminate under the progress/time budget |
| Disconnect while retaining a load or energy | Apply the installed hold/termination policy and retain obligations |
| Quantized variant has similar offline accuracy but slower loop | Require closed-loop timing and task evaluation for that variant |
| Simulation-only success or fractional benchmark score | Preserve evidence kind and rubric; do not assert verified field reliability |

The same profile supports different practical choices. A home thermostat may need a bounded setpoint controller with no VLA. A microscope may use image analysis to select a region while a measured autofocus routine owns focus motion and exposure limits. A factory cell may use a learned manipulation skill within a commissioned work envelope and recipe. Each installation must demonstrate the particular capability it offers; a broad language interface is not evidence that arbitrary physical instructions are executable.
