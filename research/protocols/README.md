# Protocol research corpus

Acquired 2026-11-06 in the workspace timezone (UTC timestamps in the manifest are late 2026-11-05). This first corpus supports [the comparison and proposed design](../../docs/protocol-landscape.md). It is an unfinished research workstream.

## Inventory and evidence

- [manifest.json](manifest.json): 20 acquisition records, including one failed legacy ROS documentation URL and one wrong-document redirect. Each successful record includes source/final URLs, retrieval time, raw/text paths and SHA-256 hashes.
- [reading-wot-full.json](reading-wot-full.json) and [reading-transport-full.json](reading-transport-full.json): later full-reading receipts supersede acquisition-time partial statuses for these four standards.
- [reading-coap-full.json](reading-coap-full.json) and [reading-lwm2m-full.json](reading-lwm2m-full.json): completed constrained-protocol review receipts, with later acquisitions in [the constrained lane](../constrained/README.md).
- [Embedded implementation review](../embedded/README.md): expanded full-file Firmata/scheduler/motion/rclc coverage, superseding earlier partial file statuses.
- [wot-artifacts/manifest.json](wot-artifacts/manifest.json): seventeen archived schemas, context/errata and figure artifacts; reading coverage differs by artifact.
- [repositories.json](repositories.json): three shallow Git checkouts pinned to exact commits, with hashes and reading status for selected files. Complete working trees were downloaded; repository histories were not.
- [raw/](raw/): original downloaded HTML/PDF/text. These are research copies, not source code incorporated into HMS or an assertion of redistribution permission. Upstream copyrights/licenses apply.
- [text/](text/): BeautifulSoup or `pdftotext -layout` extraction. Extraction loses layout, diagrams and potentially non-text content.
- [acquire.py](acquire.py): acquisition helper; the main command refuses to overwrite this existing snapshot and reading ledger. `fetch()` can be imported to append new acquisitions explicitly.

A download is not a reading claim. `read_full_extracted_text` covers all extracted prose of the named page, excluding images and linked documents. `read_full_source_text` covers the complete named textual source. `read_selected_sections` names the inspected passages. Repository reading is file-specific; none of the three entire repositories has been read. No downloaded third-party code has been built or executed.

## Reading notes and critique

### WoT TD 1.1 and Discovery

TD 1.1 interaction affordances already supply a useful typed vocabulary, including asynchronous action query/cancel operations. Properties can be observable, but subscription need not produce an initial value. Its `safe` action flag concerns resource-state changes, not machinery hazards. Discovery separates introductions from authorized metadata exploration and supports external descriptions for constrained/brownfield devices. HMS should preserve these useful distinctions while adding explicit physical evidence, operating envelopes and durable operation semantics. TD and Discovery are now fully read, including all eleven figures; see the [full review](notes/wot-full-review.md), [coverage receipt](reading-wot-full.json) and [reuse decision](../../docs/wot-reuse-decision.md). Architecture and linked materials remain separately pending. [TD](https://www.w3.org/TR/2023/REC-wot-thing-description11-20231205/), [Discovery](https://www.w3.org/TR/2023/REC-wot-discovery-20231205/)

### OPC UA

The general overview and selected Part 3 passages establish rich objects, variables, relationships and callable methods. Ordinary method invocation ends when its result returns; it does not inherently supply a restart-surviving job object. An adapter should preserve native identifiers and models and add explicit operation records only where needed. Avoid converting a complex instrument to a pile of unrelated scalar writes. Security/services/PubSub/companion-model sections still require full review. [Overview](https://reference.opcfoundation.org/specs/OPC-10000-1/4.2), [Part 3](https://reference.opcfoundation.org/specs/OPC-10000-3/full)

### ROS actions and QoS

The action design provides goal UUIDs, feedback, results and explicit cancellation stages. Result retention is configurable and may end on shutdown. QoS documentation distinguishes delivery reliability from durability, history, deadline, lifespan and liveliness; incompatible requested/offered settings prevent communication. Its services discussion specifically warns that persistent old requests can repeat side effects after server restart. HMS adapters should expose QoS incompatibility as a diagnostic, preserve the native goal ID, and specify crash/retry behavior separately. [Actions](https://design.ros2.org/articles/actions.html), [QoS source](https://github.com/ros2/ros2_documentation/blob/rolling/source/ROS-Framework/interfaces/topics/About-Quality-of-Service-Settings.rst)

### micro-ROS and rclc code

The architecture supports a C client and agent bridge with MCU-oriented memory strategies. Exact board/transport support must be checked against a pinned implementation, not inferred from the Arduino brand. In the inspected rclc source, executor setup allocates a fixed handle array; preparation can initialize a wait set; LET processing takes all inputs before executing callbacks. Output publication is not deferred until the period ends. The example trigger program also allocates string memory in a timer callback. Hence the library's configuration can support bounded execution, but copying a demo does not establish an allocation-free realtime application. [Architecture](https://micro.vulcanexus.org/docs/overview/features/), [Executor documentation](https://micro.vulcanexus.org/docs/concepts/client_library/execution_management/), [pinned source](https://github.com/ros2/rclc/tree/c34f5d9121e1190e2cb188a8f19e57eead1448c1)

### MQTT and Sparkplug

MQTT QoS applies per sender/receiver delivery, and acknowledgement can precede onward application delivery. HMS operation identity therefore cannot be replaced by MQTT packet identifiers. The complete MQTT 5 and Sparkplug 3 text has now been read; all fourteen Sparkplug figures were inspected. Sparkplug command publication uses QoS 0, and its wrapping session/sequence values cannot act as HMS fences. Broker acknowledgements, retained BIRTH caches, expiry and death publication have weaker guarantees than durable physical execution. See the [full review](notes/transport-full-review.md), [coverage receipt](reading-transport-full.json) and [binding requirements](../../docs/transport-guarantees.md). Source contradictions remain explicitly recorded; no conformance tests have run. [MQTT](https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html), [Sparkplug 3 PDF](https://sparkplug.eclipse.org/specification/version/3.0/documents/sparkplug-specification-3.0.0.pdf)

### Matter

The ACL guide confirms that read/subscribe, write and invoke are subject to fabric privileges, with cluster-specific requirements. The 1.5 release announcement documents expanded categories including cameras, closures, soil sensors and energy management. These are evidence of breadth in a home-device ecosystem, not proof of arbitrary hardware coverage. The acquisition is of a particular announcement, not a claim that 1.5 is the latest release. Core and cluster specification review remains open. [Access control](https://project-chip.github.io/connectedhomeip-doc/guides/access-control-guide.html), [1.5 announcement](https://csa-iot.org/newsroom/matter-1-5-introduces-cameras-closures-and-enhanced-energy-management-capabilities/)

### Firmata protocol and Arduino parser

Full core protocol and scheduler documents were read, as was `FirmataParser.cpp`. The capability query enumerates pin modes/resolution; analog mapping is explicit, so consecutive analog labels need not imply consecutive physical pins. A pin-state reply is commanded state rather than measured pin value. Scheduler commands demonstrate uploaded delayed/repeated message streams. The parser dispatches bytes to registered callbacks; it does not know what physical machine a pin controls. This is useful evidence for dynamic installed commands on small devices, with installation-specific semantics supplied above the byte protocol. It is not a complete physical safety or durable-execution system. [Pinned protocol](https://github.com/firmata/protocol/tree/7908873e8faae33111143aa6cc236148b12118f2), [pinned Arduino](https://github.com/firmata/arduino/tree/ebd19be71b3673ba16f884c00b0a2e940ef86157)

### Zephyr shell

Selected overview/backend/command sections show a real shell option with configurable command groups and several transports. Commands still depend on firmware configuration and developer handlers; shell availability cannot be assumed on a generic chip. A host-visible typed wrapper can reuse it for development and diagnostics. The remaining shell API and examples require reading before an adapter design. [Shell documentation](https://docs.zephyrproject.org/latest/services/shell/index.html)

## Acquisition failures and corrections

The original micro.ros.org features page returned 404 during browsing; official project migration information led to micro.vulcanexus.org. The ROS documentation HTML page returned an Anubis access-denied page; first-party source RST was acquired instead. A guessed old rolling RST path returned 404; the GitHub repository tree located its new path. A Humble source copy was also acquired and remains unread. The legacy `www.eclipse.org/tahu/spec/sparkplug_spec.pdf` URL returned HTML for the Tahu project, not a PDF; this is retained as `wrong_document`, with the real 141-page Sparkplug 3 PDF acquired separately. HTTP 200 alone is not sufficient acquisition evidence.

## Next reading queue

1. Finish WoT Architecture 1.1 and archived context/Thing Model schema; TD 1.1 and Discovery full readings are complete.
2. Inspect implementations and conformance suites for MQTT 5 and Sparkplug 3; their full standard readings are complete, but no broker or binding tests have run.
3. Finish chosen CoAP extensions and current LwM2M Core/Transport/object/security baseline; base CoAP, selected update RFCs and the retained 1.2 Core full reviews are complete.
4. Complete OPC UA Part 3 and add Parts 4, 6, 12, 14 and appropriate device/robotics/laboratory companion specifications.
5. Read Matter core/cluster/device specifications at an explicitly selected version; acquire SDK portions needed for a real adapter.
6. Extend the completed StandardFirmata, ConfigurableFirmata scheduler/motion and rclc executor review to remaining Arduino/RCL/RMW dependencies and tests. Verify boards and compile-time/runtime bounds on representative tiny and richer MCUs.
7. Add SCPI/VISA, SiLA 2, EPICS, Modbus, CANopen, EtherCAT, IO-Link, BACnet, KNX, BLE GATT, USB and device-management/update sources. These remain outside this first corpus.
