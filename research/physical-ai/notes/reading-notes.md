# Reading ledger and critical notes

First-pass record, 2026-11-06 (local date). Retrieval timestamps in manifests are UTC. Reading statements describe actual inspection, not automatic extraction. An archive is not a completed read.

| Source | Reading coverage this pass | Open questions / interpretation |
|---|---|---|
| OpenFlexure WoT, arXiv 2101.00933v3 | All extracted text, 11 PDF pages including references; architecture figure on page 3 visually inspected. Other figures not visually audited. | A persistent local executor is useful independently of AI. The paper's security discussion must not be treated as the current server's complete security model. |
| OpenFlexure autofocus, arXiv 2109.06842v2 | All extracted text, 14 PDF pages including references; flowchart page 9 and result chart page 12 visually inspected. Other image panels not visually audited. | Evaluation concerns particular samples and mechanics, not arbitrary instruments. Smart-stack success measures peak placement, not universal diagnostic validity. |
| NVIDIA DGX Spark hardware page | Complete extracted main page, 107 lines | Benchmark the actual inference/control deployment; hardware capacity alone does not determine response-time tails. |
| NVIDIA GR00T N1.6 report | Complete extracted page after repairing incomplete HTML extraction; embedded videos and graph-image values not reviewed | Relative action semantics and train/deployment normalization require explicit versioning. Report is a historical model version. |
| Isaac Lab ecosystem | Complete extracted main page at corrected URL | Simulation profiles need backend and sensor-fidelity identity. Old URL is only a relocation page. |
| GR00T N1 paper | Text lines 1–220 only: introduction and architecture opening. Remaining text, appendices and figures unread. | Do not extrapolate published control frequencies to GB10. Finish architecture, experiments, limitations, and appendices. |
| OpenVLA paper | Text lines 1–130 only: abstract and introduction. Remaining text, appendices and figures unread. | Finish model action representation, evaluation design, inference efficiency and limitations before comparative ranking. |

## Repository inspections

Full repository snapshots were acquired, with shallow Git history. This does not mean every file was read. GR00T LFS media downloading was interrupted intentionally and checkout completed with `GIT_LFS_SKIP_SMUDGE=1`; most large media/data objects remain pointers. No model weights or full training datasets were downloaded. See `repos.json` for immutable commits, file hashes and exact selected coverage.

OpenFlexure: fully read `things/stage/__init__.py`, `things/stage/sangaboard.py`, and `things/autofocus.py`. Cancellation may be deliberately blocked for an autofocus sweep, so any HMS wrapper must document the actual cancellation granularity and independent stop route. The software's position source needs examination down through the firmware before it can be represented as measured displacement.

GR00T: fully read `getting_started/policy.md` and `gr00t/policy/server_client.py`. The policy service predicts actions and offers reset/ping; it does not establish a physical execution journal or actuator stop. We must avoid copying a network inference timeout into a motion safety timeout. Wire parsing, tensor bounds and deployment authority remain runtime responsibilities even if model-side shape checks are disabled for performance.

Gently: fully read `docs/architecture/hardware-profile-template.md` and `docs/architecture/sample-hardware-domains.md`; read the XY-stage implementation from line 133 through file end. Controller-limit programming with readback is a useful pattern, but its mere presence does not prove every controller path is constrained. Review startup invocation, firmware behavior, partial-write failure and fault injection separately before using it as assurance evidence.

The earlier GR00T/OpenVLA partial rows above are superseded by the [full review](vla-full-review.md) and [coverage record](../reading-vla-full.json). They remain here as reading history.

## Next reading batch

- Complete all remaining figures in the microscopy papers; the two VLA paper reviews are now complete for the pinned versions.
- Read GR00T real-world deployment and real-time chunking guide at the pinned revision; inspect controller adapters and observation/action schema conversion.
- Trace Gently device initialization, job lifecycle, sample-data records, Bluesky abort and laser-off behavior; inspect its simulator and tests.
- Acquire SayCan, Code as Policies, Diffusion Policy, Open X-Embodiment, π0/π0.5, RT-2, TinyML deployment, autonomous laboratory orchestration and domain-specific performance papers.
- Investigate Micro-Manager, Bluesky/Ophyd, SiLA 2, EPICS/Tango, OME metadata and instrument calibration profiles with the protocol-research lane.

## Claims intentionally not made

No universal hardware protocol has been experimentally proven here. No actual motor moved. No physical response time, torque, positional accuracy, clinical reliability or manufacturing safety rating has been established. A complete local corpus and complete reading of every repository remain unfinished requirements.
