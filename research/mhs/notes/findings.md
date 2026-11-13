# MHS source investigation — 2026-11-06 local time

## Published evidence

[Anthropic announcement](https://www.anthropic.com/news/model-hardware-standard-research-preview): standardized drivers expose read/write operations, device descriptions and discovery; agents use MCP, CLI or APIs. Shared memory supports local data exchange. The expanded cases describe six partner deployments across laboratory, microscopy and laser workflows. These are partner reports, not an independent cross-device benchmark. The GUI-controlled CMU instrument complicates the headline limitation to programmable interfaces. Genentech illustrates how retries can worsen a physical fault. QuEra distinguishes a generated deterministic controller from ongoing agent tuning. Tetsuwan's centrifugal-force prose is dimensionally problematic: treat unit conversion as an independently tested engineering responsibility. The announcement does not publish the wire schema, consistency model or conformance suite. Full extracted article text, including all six expanded cases and captions, was read; embedded videos and external linked studies were not inspected.

[Official site](https://modelhardwarestandard.com/) still describes application-only preview access and future open sourcing. [Later Anthropic science announcement](https://www.anthropic.com/news/ai-for-science-expands-foundations-research-institutions) explicitly retains research-preview status. The GitHub organization API returned an empty repository array; that is evidence about that organization only, not proof that no specification exists elsewhere. No official compatibility claim is justified.

## Acquisition detail

The main HTML extraction omitted expanded case-study content. Reading that extraction alone would not satisfy a full article read. The Next.js payload in the raw HTML contains the missing text. `anthropic-mhs-complete-content.txt` extracts text fields, resolves length-prefixed Flight text references, and removes duplicate fields. Its SHA256 is `75e196b8de5504e2671a22bd201c72714c27dd1c4f287fc8b6d67e3fceaae6f5`. The original HTML and decoded Flight payload remain local. This is textual coverage, not a visual review of figures or playback of videos. Generic extraction must never automatically set a source to fully read.

Waters' primary press release was found through web search but direct download returned HTTP 403. It remains an acquisition gap; a search excerpt is not a downloaded, fully read article.

## Edge/cloud architecture evidence

The [AWS primary article](https://aws.amazon.com/blogs/opensource/building-intelligent-physical-ai-from-edge-to-cloud-with-strands-agents-bedrock-agentcore-claude-4-5-nvidia-gr00t-and-hugging-face-lerobot/) was downloaded and read in full as extracted text. It demonstrates local agents, VLA action chunks, vendor SDK tools, bidirectional edge/cloud delegation, and fleet learning. It is a useful architecture example, not evidence that all VLA inference meets deadlines. Its pedagogical manipulation loop does not specify a maximum duration, stale-observation handling, restart semantics, or independent stop path. HMS needs explicit contracts for these omissions. Cloud reasoning is optional; neither coordination nor fleet learning logically requires a particular cloud vendor.

## Independent Open-MHS implementation

Repository: https://github.com/Abenor-Labs/Open-MHS (exact commit in `repo-manifest.json`). This is an independent project, not Anthropic's implementation. Read `open_mhs/drivers/base.py`, `docs/threat-model.md`, and `docs/standards-map.md` completely. Other repository files are downloaded but unread; README search snippets are not counted as a full read.

The implementation checks writes and optionally polls feedback. Its stop routine reports `stopped: True` after transmitting configured outputs, without confirming stopped motion. That response would be too strong for HMS. The threat model candidly documents process-local discovery, shared authentication, driver trust and event-loop blocking. Reusing one evaluator at two software entry points does not provide independent fault containment. Signed descriptions authenticate publishers; they do not make prose trustworthy or sensor claims true. A hash chain alone cannot detect an attacker rewriting the entire retained log. These observations motivate operation evidence levels, per-device authority, isolated workers and independently anchored records. No upstream test or physical claim was independently reproduced in this pass.

## Original design deductions

1. Universal means a stable semantic interface with explicit capability gaps, not a claim that every device supports every action.
2. State replication and command execution must be different paths. A shared-memory state store cannot substitute for command ownership, ordering or energy isolation.
3. Device facts require a source, time, uncertainty and calibration context. A reported setpoint is not measured position.
4. Post-dispatch ambiguity is unavoidable for legacy hardware. Preserve an unknown outcome and reconcile from observations instead of replaying a physical action.
5. The agent should generate bounded reusable procedures. Timing-critical execution belongs to a local controller with declared failure behavior.
6. Unit conversion, coordinate transforms and action compatibility must be checked by software against declared data, not inferred from prose at execution time.

These are proposed HMS decisions, not statements of the unpublished MHS standard.
