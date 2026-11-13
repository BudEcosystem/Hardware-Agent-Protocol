# End-to-end scenarios and acceptance evidence

These scenarios exercise the intended breadth. They are designs, not demonstrations already run.

## Home IoT: ventilation with local agent control

A home hub discovers a temperature sensor, air-quality sensor, fan and window actuator through Matter, MQTT or vendor adapters. The registry binds measurements and actions to rooms and physical instances. The user delegates ventilation within configured noise, opening and occupancy constraints. A local or hub agent chooses a bounded rule/procedure; the local controller executes it without a cloud round-trip.

Sequence: discover authorized room capabilities; verify fresh sensor quality and window state; reserve the window; compute an admissible opening target; invoke with a stable operation key; verify position from feedback; observe ventilation effect over a bounded period; close or hold according to the installed policy. Manual intervention preempts automation, changes control epoch and invalidates the prior target. Sensor loss triggers the configured policy instead of repeating the last optimistic value.

Failure cases: replayed broker message; retained stale telemetry; wrong room binding; revoked delegation; manual close during motion; power loss after send; offline cloud; spoofed device advertisement; smoke/security systems requiring priority. Home automation does not get to override separately controlled life-safety systems.

Evidence required: a real integration trace with a local disconnected-cloud run, timestamps and feedback evidence; zero double execution on retry; old epoch rejected; stale telemetry refused; manual override demonstrated. A simulated fan validates software only, not actuator force or pinch behavior.

## Scientific experiment: microscope knob retrofit and adaptive imaging

A bolt-on focus drive, optional stage axes and camera form a commissioned imaging assembly. The drive advertises its axis, position evidence, travel/torque/speed limits, calibration and manual disengagement state. The microscope objective and sample geometry constrain the usable envelope. The sample itself can have exposure/time limits independent of motor limits.

Sequence: verify mounting and calibration; discover the correct camera/axis binding; acquire an image with capture timestamp and objective metadata; run a bounded coarse/fine focus procedure; make each move within commissioned limits; wait for settling and verify motion according to available feedback; score new frames; select a focus position with confidence and failure conditions; optionally scan an approved region. The model chooses the scientific strategy; the local procedure drives timing. Save raw images, transform/calibration versions, command history and analysis outputs so another investigator can inspect the run.

Do not equate maximal image sharpness with correct scientific focus. Saturation, debris, motion, bleaching and the wrong specimen plane can produce misleading scores. A failed focus search returns evidence and leaves the system in its declared termination state; it does not expand its travel budget autonomously. Manual knob movement invalidates inferred position unless independently sensed. See the [retrofit design](../docs/microscope-retrofit.md).

Failure cases: jammed coupler, direction reversal/backlash, unplugged encoder, stale camera frame, objective swap, lost limit switch, hub restart after relative move, worker hang, and user disengagement. Evidence includes measured repeatability/backlash under actual loading, stopping/holding behavior, reconnection behavior and image-to-axis synchronization. Simulator results cannot complete this physical gate.

A second laboratory profile should test coordination across liquid handler, plate transport and reader. Reserve shared zones and sample ownership, verify plate identity/orientation, and record irreversible dispenses. Recovery may require a fresh consumable, not repetition. The protocol must preserve sample identity, units and uncertainty through the full design–execute–measure–analyze cycle.

The [workflow/material extension](06-workflows-materials.md) makes these requirements explicit: separate protocol intent from bound procedure and execution; detect swapped containers; account for specimen aging during a pause; and reconcile uncertain effects before checkpoint replay. LabOP conversion and Bluesky resume semantics supply useful interfaces, while the HMS adapter must retain the stronger physical-evidence and recovery requirements.

## Manufacturing: inspection and rework cell

An industrial cell contains a PLC, feeder/conveyor, robot, camera and inspection station. Existing controllers implement machine modes, guards and protective functions. HMS exposes commissioned recipes and verified status through adapters; it does not replace the PLC scan loop. An agent selects a recipe and analyzes defects, while cell control owns motion coordination.

Sequence: query cell readiness and active recipe revision; reserve workpiece and shared workspace; validate tool/fixture identity and calibration; invoke a bounded handling recipe with a durable job identity; wait for native completion plus part-presence evidence; capture inspection data; classify against a versioned quality criterion; route to accept/reject/rework according to delegated limits. MES/work-order correlation remains attached to every physical operation and observation.

Failure cases: guard opening, PLC mode change, network partition after dispatch, duplicate order, stale fixture data, delayed camera frame, clock drift, wrong gripper, occupied shared zone, unreachable robot while conveyor continues, and restart between irreversible assembly steps. Conflicting work remains inhibited until the actual part and machine states are reconciled.

Evidence required: fault-injected cell simulation followed by limited commissioned physical runs; native stop evidence; no re-execution on ambiguous ACK; bounded scheduling under load; correlation of input part to final inspection; qualified review of installation protections. The HMS interoperability suite makes no SIL/PL or regulatory conformity claim.

## Further coverage to research

| Family | Additional semantic pressure |
|---|---|
| Test/measurement and electronics benches | SCPI queues, triggers, instrument error registers, destructive measurements |
| Agriculture/environmental monitoring | Intermittent power, slow links, sparse feedback, weather-dependent behavior |
| Buildings/energy/storage | Long-duration control, tariff vs stability goals, shared power budgets |
| Mobile robots/logistics | Localization uncertainty, fleet traffic, spatial ownership and human presence |
| Medical/assistive devices | Product-specific regulated workflows and qualified oversight; no generic enablement claim |
| Space/underwater/remote systems | Delayed communication, autonomous recovery, strictly bounded local missions |
| Soft robots/wearables | Body interaction, deformation, nonrigid state and sensor drift |
| FPGA/DAQ/quantum instruments | Hardware-synchronous timing, waveforms, bounded buffered programs |

These families expand the research search matrix. They are not implied supported integrations.
