# Workflows, materials and scientific evidence — proposed extension

The core operation interface needs a workflow layer that preserves physical identity and irreversible effects. This requirement applies to scientific samples, factory workpieces, consumables and household resources. It follows from the [LabOP/Bluesky investigation](../research/laboratory/notes/labop-bluesky-review.md); the fields and rules below are proposed HMS semantics, not a claim that these systems implement them.

## Three distinct artifacts

A **protocol intent** states the desired process, constraints, decisions and required capabilities without fixing every device. A **bound procedure** resolves those requirements against commissioned devices, materials, frames, versions and budgets, with an explicit compiler/version and digest. An **execution record** identifies actual operation IDs, observations, material changes, interruptions and outputs. Rendering a human protocol, simulating a graph or generating code MUST NOT produce a record claiming physical execution.

Compilation emits a compatibility report: preserved requirements, unsupported constructs, substituted capabilities, narrowed bounds, manual steps and required runtime barriers. Unknown branches that depend on live evidence remain runtime branches or split the plan at an evidence barrier. A compiler MUST NOT select them using placeholder/simulated measurements and present the result as equivalent. Flattening and loop unrolling must stay within memory, instruction and exposure budgets; an inability to do so is a compile error or explicit deployment choice.

The universal core does not need all of UML, OWL or a full scientific ontology on an MCU. Higher-level importers may use them; the endpoint executes a bounded subset with proven compilation mapping for the advertised constructs. Reuse external stable identifiers for substances, labware or parts where available, while retaining installation-specific physical instances.

## Material and location identity

A `MaterialInstance` identifies a physical sample, aliquot, part, batch or consumable; it is distinct from its material type. A `ContainerInstance` identifies the actual plate/tube/fixture. A `LocationRef` includes container/fixture identity, compartment or spatial frame, geometry revision and location generation. `A1` is only a local well coordinate, not a globally unique specimen ID. A swapped plate with the same dimensions changes the instance binding.

Maintain causal records for split, combine, transfer, transformation, consume and discard. Track expected quantities separately from measured quantities, with units, uncertainty and evidence. A successful dispense command may justify updating a commanded-volume estimate; it does not justify labeling that volume independently measured. Corrections append evidence and revised estimates rather than erasing the original operation history.

Resource admission includes material identity, location generation, remaining quantity/capacity, contamination/compatibility requirements and reservation mode. Two devices touching different actuators can still conflict over one specimen or shared destination. Reserve consumables and shared physical space with the same operation ownership model. After a partial or uncertain transfer, quarantine affected material state until reconciliation; do not let a scheduler assume that an unacknowledged action consumed nothing.

Material movement commits are logical bookkeeping around irreversible physical actions, not transactional rollback. A transport failure after an aspiration or gripper transfer can leave both source and destination uncertain. Record possible locations/effects and seek appropriate evidence; never duplicate a sample identity into two confirmed locations to satisfy both optimistic branches.

## Timing and live decisions

In addition to per-action start/run/completion bounds, a workflow may require time bounds between specified events: acquisition after settling, processing before a sample expires, or a maximum delay between preparation and measurement. Every temporal constraint states clock domains, uncertainty, allowed miss behavior and whether it is scientific quality, physical protection or scheduling preference.

A pause does not stop chemistry, temperature drift, photobleaching, fatigue or a hot workpiece cooling. Resume checks actual current material and device state, elapsed time, exposure and control/binding generations. If the process is no longer valid, terminate or create a separately authorized amended procedure; do not silently resume from an obsolete software checkpoint.

A decision input carries observation IDs, evidence quality, acquisition time and analysis/model revision. A model's assessment of an image is an inferred result, with its own uncertainty and validation context. If the decision changes physical steps beyond the admitted envelope, produce a new bound procedure and admission decision. Preserve the relationship to the original intent and completed work.

## Resume and repetition classes

Every step declares repetition behavior: no physical effect; repeatable only under stated conditions; consumptive/nonrepeatable; or unknown. Action names such as `read`, `trigger` or `measure` are not enough: a measurement can expose a specimen or consume an aliquot. Checkpoint replay MUST preserve stable operation keys for previously issued steps and recover their outcomes before any newly authorized repetition.

A checkpoint records the bound procedure, resource generations, material-state evidence, completed step identities, pending/unknown effects and time constraints. Same-process generator rewind is not crash-durable recovery. The runtime may resume only from supported persisted state or explicitly reconstruct and reconcile it. A process restart with only a Python plan object or a list of messages does not establish safe replay.

Cleanup/compensation are ordinary physical procedures with declared authorization, limits and current-state checks. A cleanup that restores the initial motor position may be invalid after a fixture or human intervention. Stop, hold, release and restore are distinct choices. Choosing a cleanup strategy must not bypass the bounded-stop semantics or silently change a successful partial acquisition into a claim of full task success.

## Records and evidence

Link each acquisition to material/container/location identity, capture time, device/firmware, calibration, coordinate transform, bound procedure digest and operation ID. Raw data references and derived analysis references have separate hashes and retention. Preserve rejected, partial, interrupted and low-quality data with annotations when required for scientific traceability; a UI filter must not delete the underlying evidence.

An external run identifier (Bluesky, SiLA, vendor scheduler, LabOP execution or MES order) is a correlation field, not a substitute for HMS's durable identity. Adapters report native state and errors alongside normalized outcome/effect knowledge. In particular, a native `success` stop label does not prove that the requested scientific objective completed.

## Required interoperability evidence

Before claiming this profile supported, demonstrate: plate/fixture swap between planning and execution; two agents competing for the same sample; partial transfer with lost response; expired material while paused; repeated illumination during checkpoint replay; compiler rejection of unsupported live branching; placeholder measurements denied at physical decision barriers; and a cleanup that must be withheld after changed geometry. Compare exported/imported metadata across one laboratory workflow and one manufacturing workflow. No such integration or physical tests have run yet.
