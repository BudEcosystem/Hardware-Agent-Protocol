# Home ecosystem primary-source corpus

This corpus supports [the HMS home-binding analysis](../../docs/home-bindings.md). It retains **38 acquisitions**: 34 complete repository-file snapshots at five commits, one published Home Assistant state-object page, and three additional published renditions retained to record URL redirects and current presentation. Acquisition is distinct from reading. No home account or device was contacted; no acquired source program was executed.

[manifest.jsonl](manifest.jsonl) uses repository-root-relative paths and preserves raw/text SHA-256, byte counts, retrieval time and URLs. Repository source is retained byte-for-byte, with the same path/hash serving as raw and text. The four published pages also retain raw HTML and an article/main text extraction. [repos.json](repos.json) pins selected snapshots and records exact repository paths, Git blob IDs, commit/tree metadata paths and hashes. No complete repository checkout is claimed.

[reading-home-full.json](reading-home-full.json) contains **32 full-file/full-extracted-text readings, totaling 11,599 LF-addressed lines**, and **three selected-file readings**, with **58 exact hashed coverage intervals**. The three separately retained live API renditions remain unread; their content must not be conflated with the fully read pinned Markdown sources. Complete source-text reading does not include linked references, browser-generated MDX components, embedded image pixels, generated code or dependencies. The state-object page's screenshot was not separately inspected.

| Repository | Requested ref | Commit | Acquired/read scope |
| --- | --- | --- | --- |
| home-assistant/contributors.home-assistant.io | main | `abdc493f06647a69e8d64da62dd91b784273ac62` | Seven complete developer documents: WebSocket, REST, states, events, updating state, state attributes, fetching data |
| home-assistant/core | 2026.11.0 | `74cf5a49c63ed8d4d87717844bf14f79c28c9cea` | Complete REST and WebSocket connection modules; selected WebSocket command module ranges |
| home-assistant/home-assistant-js-websocket | master | `ad8031f63b996cccb9dc53633325c2039b030aee` | Complete connection, collection, states and legacy entities re-export modules |
| esphome/esphome | 2026.10.2 | `9a78022ded2285861f10de50168a0aa71e2a4322` | Complete api.proto/options, API server, frame helpers, user actions, state-iterator implementation, template switch, time-based cover and four Noise support files; selected API connection .cpp/.h ranges |
| esphome/esphome.io | current | `4dad66388fb0b2b3591ba4bdfb46b3694125b3e5` | Complete Native API, actions/conditions, script, template switch and time-based cover Markdown/MDX source files |

Documentation has independent revisions. Its prose can describe features or defaults that require a particular version or configuration. Firmware compilation flags determine which schema features exist. The full protobuf schema is a source definition, not proof that every deployed firmware exposes every message. The implementation is not a measured build.

The retained developer entry URLs for WebSocket and REST redirect to `contributors.home-assistant.io/core/internals/websocket-api/` and `.../rest-api/`. Redirect histories are preserved on the `published-ha-*` acquisition records. The ESPHome published page is separately retained; the full reading claim is for the pinned source file.

## Findings that change an HMS binding

- Home Assistant state writes, optimistic updates, cached integration data and state timestamps are distinct from physical feedback. The REST state-write endpoint is not an actuator command.
- `subscribe_entities` avoids the initial HA event-loop handoff race by not awaiting between snapshot and subscription. It does not supply a durable reconnect replay cursor or simultaneous physical samples.
- HA command IDs are connection-scoped. Its JavaScript client rejects ordinary in-flight calls on disconnect and resubscribes streams; the state collection replaces its cache from a new snapshot. The current REST implementation shields service calls from HTTP cancellation.
- ESPHome ordinary entity commands lack a generic durable operation lifecycle. Newer user actions have response IDs, but the inspected routing table is volatile, expires calls by default after 30 seconds and drops routing on disconnect. A fresh request creates fresh execution routing rather than deduplicating intent.
- There are domain-specific exceptions: IR/RF transmit completion and serial-proxy exclusive subscription/TX-drain status. These do not prove downstream physical effects. Do not flatten them into either universal success or universal absence of completion support.
- ESPHome state batching may coalesce transitions. Its frame helper can return `OK` after buffering unsent data. A received state has no universal acquisition timestamp in the ordinary state schema.
- Configured Noise authentication is separate from actuator ownership. Keyless/all-zero provisioning is not authenticated physical identity; several legitimate clients and local automations can affect the same installation. Ordinary command messages contain no HMS fencing generation.
- Stopping a script can omit its later cleanup actions. Time-based covers are position estimates. Template-switch restored state can invoke control during setup. Disconnect and reboot policies therefore need installation-specific treatment.

These are source-grounded findings and HMS design inferences, not a declaration of flaws across all Home Assistant integrations or all ESPHome devices. Full cryptographic/library review, hardware tests, aioesphomeapi behavior and specific integration/component guarantees remain outside the scope. Matter specifications are not claimed read.

## Integrity audit

Run `python3 research/home/audit_home.py` from the repository root. The script verifies acquisition hashes, commit/tree metadata identities, every selected file's Git blob identity and membership, exact LF coverage hashes, and full-coverage assertions. It also reconstructs all retained Git tree objects from the recursive metadata; it does not acquire or read the contents of the unselected blobs. [audit.json](audit.json) records its result.

GitHub's HTTPS metadata associates the commits with the trees; independent commit-signature validation was not performed. Hashes verify retained bytes, not comprehension, hardware behavior or conformance. The acquisition/receipt/audit scripts are locally authored research tooling and are separate from the unexecuted acquired source.

The root corpus auditor should include this lane's root-relative JSONL acquisitions and snapshot repository pins. Its existing `research/*/reading-*-full.json` glob already covers the reading receipt. These snapshots are neither Git checkouts nor complete flat subtrees; verification must use their retained metadata/file records rather than `git rev-parse` or the planning lane's flat-subtree assumption.
