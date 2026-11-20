# Laboratory workflow evidence — reading pass 2

## Sources and coverage

- [LabOP paper, author-hosted accepted article](https://jakebeal.github.io/Publications/JETC23-LabOP.pdf), DOI 10.1145/3604568: complete extracted text, all 878 LF-addressable lines including references and the final formatting-only formfeed, read. All twelve numbered figures inspected, using pages 5, 6, 9, 10, 11, 13, 14, 15, 17 and 18; recorded separately in `reading-log.json`.
- [Bluesky 1.15.1 message protocol](https://blueskyproject.io/bluesky/v1.15.1/msg.html) and [interruptions](https://blueskyproject.io/bluesky/v1.15.1/state-machine.html): complete extracted page text read. The command reference itself labels its command section incomplete; full reading of that page does not mean full API coverage.
- Public pinned Bluesky and LabOP repositories: exact commits and file/line coverage in `repositories.json`. Reference source was inspected, not executed. Other files are unread.
- SiLA 2 core and mapping 1.1 PDFs were acquired from publicly reachable official URLs. The downloads landing page advertises registration for its links; the direct PDF URLs returned full PDF documents. No account was created. The later [full SiLA review](sila-full-review.md) and [coverage receipt](../reading-sila-full.json) now record both completed document reads separately from this LabOP/Bluesky investigation.

## Reported results and limits

LabOP separates reusable operation definitions, protocols and execution histories, using UML token flow plus linked data. Its example translates a calibration protocol to human instructions and automation formats. Translation to a less expressive target can require linearization and intervention at branches; it is not generally reversible. The paper's evidence is primarily a representation/prototype demonstration around one simple protocol, not a measured multi-laboratory reliability trial. Sample-content reasoning is future work in the paper. A structurally valid graph therefore does not establish physically feasible execution. [Paper](https://jakebeal.github.io/Publications/JETC23-LabOP.pdf)

Bluesky routes plan messages through a RunEngine, supports status objects and checkpoint-based resume. Its stop/abort distinction includes how runs are labeled; it does not encode HMS's stronger outcome semantics. The source `_stop_movable_objects` logs stop exceptions and continues. Thus the documentation's broad statement about stopped motors is not independent physical verification. The native interface permits missing stopping support; an HMS adapter must make that limitation visible. The complete `protocols.py` supports status-returning `stage` as well as lists, while the message documentation describes only lists: pin implementation evidence rather than freeze an outdated documentation example into the adapter.

## Implementation observations

Bluesky `Status` exposes done, success, exception and completion callbacks. Those are supplied by the device implementation; a conforming Python interface does not determine the physical evidence behind success. `Reading` contains value and Unix timestamp, but does not mandate clock uncertainty, maximum cache age or calibration. `Locatable` explicitly separates setpoint and readback. `Checkable` is optional and simulator guidance can assume validity if it is absent; HMS admission cannot promote that default into a hardware authorization.

`_rewind` replays cached messages and rewinds associated run bundlers. `_clear_checkpoint` makes the message cache absent. HMS must distinguish this same-process replay mechanism from persistent physical operation deduplication. A replayed trigger can create another exposure; a replayed dispense cannot be treated like another software calculation. `_wait` may return while statuses remain incomplete when configured not to error on timeout; translate this as pending, never completed.

In the inspected LabOP `LabInterface`, default measurements create placeholder data and inventory selection returns the first matching container. These are extension hooks, not proof of installed instrument measurement or compatibility. An HMS specialization must label placeholders as simulation/unknown and replace inventory selection with commissioned constraints. Sample masks and maps preserve useful collection/location semantics, but a well coordinate is not a globally unique physical specimen identity. Repository data structures can be reused without inheriting unproved physical guarantees.

## Original implications for HMS

1. Separate protocol intent, bound executable procedure and actual execution history. A protocol graph is not an operation receipt; simulated translation is not a completed experiment.
2. Require explicit capability-loss reporting during compilation. If a branch needs live measurements, do not choose it using a placeholder and send the resulting flattened program to hardware.
3. Add sample/workpiece/consumable identity and location versions. Resource locking solely by actuator cannot prevent two otherwise independent devices from consuming the same sample or using the same well.
4. Separate arithmetic/material bookkeeping from measurement. Commanded transfer volume is an estimate until suitable evidence exists; derived concentration remains uncertain when inputs are uncertain.
5. Treat retries and resume as a physical-effect decision per step. Some measurements consume material or alter exposure; observation-named methods are not necessarily side-effect-free.
6. Treat cleanup as another admitted procedure. Returning a motor to its initial position may collide after a fixture change; automatic cleanup is not inherently safer than holding.
7. Link raw captures, analysis/model versions, sample identity, calibration and actual procedure revision. Keep invalid/interrupted acquisitions with quality annotations instead of silently dropping them from the durable scientific record.
8. Time constraints belong between operations as well as inside them. A valid bounded action may become scientifically useless if a sample waits too long between steps.

These are proposed HMS requirements inferred from research and code inspection, not claims about implemented HMS or limitations of every possible Bluesky/LabOP deployment.

Visual cross-check: Figure 2 pairs AdhesiveSeal with thermal mode and ThermalSeal with adhesive mode. This appears reversed by the names; retain it as an unresolved source-table anomaly and do not use those rows as an executable conversion rule without checking the actual operation specifications.
