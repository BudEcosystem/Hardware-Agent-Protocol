# MQTT and Sparkplug transport guarantees for HMS

Status: proposed adapter requirements, 2026-11-06. These are independent HMS design decisions grounded in a complete reading of the archived MQTT 5.0 OASIS Standard and Sparkplug 3.0.0 specification. They are not implemented or validated guarantees. [Reading coverage and hashes](../research/protocols/reading-transport-full.json) distinguish full text reading from structural/figure inspection; [review notes](../research/protocols/notes/transport-full-review.md) record source inconsistencies and remaining work. The [execution core](../spec/02-execution.md) remains authoritative for proposed HMS operation states and identities.

MQTT is useful for distribution; Sparkplug adds industrial metric descriptions and session awareness. Neither supplies durable physical execution, resource ownership, or an actuator deadline. An HMS binding must preserve those distinctions all the way from broker to native driver.

The admission and durable-publication rules below apply to normal commands. A separately commissioned bounded-stop route follows the execution core's narrow exception when the normal journal or lease service is unavailable; it retains local scope/bounds and records evidence when possible. A caller cannot obtain that exception by relabeling an ordinary action. This exception does not make broker delivery a bounded physical stop mechanism.

## What an acknowledgement proves

| Evidence | Established by the protocol | HMS interpretation |
| --- | --- | --- |
| MQTT QoS 0 publish call returns | Local client behavior; MQTT has no delivery acknowledgement | A dispatch attempt; no endpoint receipt or execution proof |
| Publisher receives successful PUBACK | The adjacent MQTT receiver accepted ownership | Transport evidence for that hop; broker acceptance is not device admission |
| Publisher completes QoS 2 exchange | The MQTT exchange completed, with duplicate suppression in that exchange | No claim that a subscriber's physical effect happened exactly once |
| SUBACK grants a requested topic | Subscription accepted at the reported maximum QoS | Readiness of a route, subject to subsequent failure; no application capacity or authority grant |
| Sparkplug NCMD/DCMD followed by a matching DATA value | A metric update was observed | Observation with its declared provenance; correlation to the operation and independent physical verification remain separate |
| Sparkplug NBIRTH/DBIRTH | The node/device advertised its metric model and initial values | Candidate description/session evidence; not enrollment, authorization, calibration or a resource lease |
| Sparkplug STATE online / MQTT PINGRESP | A host advertised state / broker responded | Limited connectivity evidence, not proof that a controller task or physical sensor is functioning |

MQTT acknowledgements may precede completion of onward application delivery. Its Packet Identifier is reused, and its DUP flag concerns a particular PUBLISH packet rather than an application intent. Overlapping subscriptions can also produce multiple copies. Consequently neither identifier is an HMS caller key. [MQTT §§2.2.1, 3.3.1.1, 3.3.4, 4.3][mqtt]

A particularly consequential case is a subscriber's Maximum Packet Size: a broker can discard an onward message that exceeds that limit and account for sending as completed. Publisher-side success therefore cannot even establish delivery to a particular downstream client. Negotiate the complete route's payload budget and require application evidence. [MQTT §3.1.2.11.4][mqtt]

## Required binding declaration

An adapter declaration should record the fields below, referencing a commissioned binding generation. Unsupported or unmeasured properties must remain explicit.

| Area | Required declaration |
| --- | --- |
| Identity and trust | Site/broker authority; authenticated client principal; allowed Client IDs, exact topic routes and response publishers; enrolled instance mapping; gateway-versus-device authentication boundary |
| Protocol | MQTT version and actual negotiated features; Sparkplug role/version when applicable; bridging or topic rewriting; whether HMS metadata survives every hop |
| Session | Clean Start/Session Expiry policy; behavior for Session Present mismatch; broker and client persistence assumptions; connection, endpoint-session and stream epochs kept separate |
| Delivery | Publish/subscription QoS; retained-message policy; permitted replay; application receipt/result mechanisms; endpoint deduplication scope and persistence |
| Admission | Maximum payload, decoded metric count/depth, bounded work queue, byte budget, rate limits, operation/result retention and overload response |
| Timing | Queue/admission bounds; source and local clocks/uncertainty; latest-start enforcement location; maximum-run enforcement; local loss-of-contact behavior |
| Observations | Physical measurement versus controller value/echo; acquisition and receipt times; historical/null/quality mapping; gap detection, snapshot recovery and freshness bounds |
| Ownership | Resource authority and fence check location; whether old queued native work can be invalidated; handover and restart evidence |
| Recovery | Status-query support; durable journal/endpoint state; ambiguous-effect handling; birth/alias resynchronization; operator reconciliation requirements |

A declaration that cannot carry or enforce required operation IDs, generations, expiry and authority is not suitable for that HMS action. It may still expose observations or an explicitly weaker legacy action whose documented evidence and retry policy are acceptable to admission. Do not advertise missing features as supplied by QoS.

## MQTT binding rules

The identifiers below are proposed HMS requirements, not clauses of MQTT.

| ID | Binding rule and rejection behavior | Source reason |
| --- | --- | --- |
| MQ-01 | Preserve the HMS caller key, canonical request digest, enrolled target, descriptor/binding/calibration revisions, endpoint session, control generation, timing policy and scoped authority reference. An authenticated adapter derives actor identity; a publisher-supplied actor string cannot grant privilege. Reject absent required semantics before effects. | Payload meaning and most security choices are outside MQTT; correlation data is opaque (§§3.3.2.3.6, 4.10, 5). |
| MQ-02 | Store admission and dispatch ownership durably before publication. Retries with the same HMS key return the original operation; conflicting digests are rejected. A timeout after a possible send becomes `outcome_unknown` unless independent evidence resolves it. | QoS is a sender/receiver delivery protocol (§4.3), not a transaction with physical equipment. |
| MQ-03 | Publish effectful command messages with RETAIN=0; prohibit retained commands through commissioned broker policy. On MQTT 5 command subscriptions use Retain Handling=2 and Retain As Published=1, and reject received retained command messages. Reject a route that cannot enforce the declared retention prohibition. | Live forwarding may erase the retain flag when RAP=0; subscriber checks alone are insufficient (§§3.3.1.3, 3.8.3.1). |
| MQ-04 | Clear or quarantine pre-existing retained commands during controlled commissioning before enabling an actuator route. A new RETAIN=0 command does not erase old retained data. A retained desired-state object, if supported, is separately authorized input to reconciliation, never an executable request by itself. | Retained messages outlive sessions; deletion uses a retained zero-length publish (§§3.3.1.3, 4.1). |
| MQ-05 | Use Message Expiry as a queue hygiene measure. Independently enforce `latest_start` immediately before effects, including time spent in the endpoint queue; enforce run/completion policy locally once started. Reject expired or unbounded-age requests according to the action's clock requirements. | Expiry prevents starting onward delivery after expiry, not later actuation; QoS 2 sender expiry is not applied after its PUBLISH was sent (§§3.3.2.3.3, 4.3.3). |
| MQ-06 | On reconnect inspect Session Present and apply MQTT state rules. Reconcile physical operations independently even if the MQTT session resumes. A lost MQTT session does not authorize redispatch; a surviving MQTT session does not establish a surviving endpoint execution ledger. | Clean Start, expiry and Session Present (§§3.1.2.4, 3.1.2.11.2, 3.2.2.1); storage failures/admin deletion (§4.1). |
| MQ-07 | Let the MQTT library perform protocol retransmission. Do not invent in-connection timer retransmits of QoS packets. Application retry is a status/deduplication interaction with the same HMS intent. Preserve failure reason codes; never turn a negative PUBACK/PUBREC into an automatic new physical attempt. | MQTT 5 retransmission is confined to reconnect with a retained session; negative acknowledgement terminates that exchange (§4.4). |
| MQ-08 | Reset MQTT Topic Alias mappings on every network connection; resolve the topic before authorization. Do not persist an alias as identity, capability or route. A changed mapping must never change a queued operation's commissioned target. | Topic aliases are directional, reassignable and connection scoped (§3.3.2.3.4). |
| MQ-09 | Bound application queue length, total bytes, decoding work and native dispatch independently of Receive Maximum. Reject overload before admission. Verify negotiated Maximum QoS and SUBACK grants against the action's declared route. | Receive Maximum controls outstanding QoS 1/2 PUBLISH count; it excludes QoS 0, byte volume and application work (§§3.3.4, 4.9). |
| MQ-10 | Implement the commissioned stop path and local watchdog independently of normal command backlog. A stop PUBLISH is not exempt from MQTT PUBLISH flow control. A separate connection can reduce interference but is not proof of bounded stop latency through a shared broker/network. | Only other control packet types are exempt from the PUBLISH send quota (§§3.3.4, 4.9). |
| MQ-11 | Enforce resource authority at the exclusive gateway/controller and recheck immediately before an effectful step. Unsubscribe, disconnect, ACL change, credential revocation or Client ID takeover is not proof that prior native work was canceled. Invalidate old queued authority atomically; reconcile before unsafe handover. | UNSUBSCRIBE completes already-started QoS deliveries and may deliver buffered work (§3.10.4); reauthentication can overlap normal packet flow (§4.12.1). |
| MQ-12 | Use shared subscriptions only where all consumers enter the same durable admission/deduplication and resource authority domain. Do not treat consumer selection as an execution lease, or negative acknowledgement as a work requeue mechanism. | Shared QoS 1 work may move between clients; in-progress QoS 2 work can remain tied to a departing session and then be lost; negative ACK discards (§4.8.2). |
| MQ-13 | Bind response topics/publishers to the commissioned operation route and authenticate result access. Subscribe before sending requests and retain operation results independently. A timeout, missing subscriber or lost response leaves possible effects unresolved. | MQTT request/response supplies routing and opaque correlation, not authenticated operation identity or durable results (§4.10). |
| MQ-14 | Do not derive a lease or watchdog bound from Will, Keep Alive or PINGRESP. Expire HMS presence from stated evidence and monotonic time; apply a local loss-of-authority policy without waiting for broker death publication. | Will publication can be delayed until broker restart; keepalive detects a network peer, not actuator health (§§3.1.2.5, 3.1.2.10). |
| MQ-15 | Preserve exact topic spelling and configured identity mapping. Validate duplicate metadata keys, schema types, finite values and size limits in application decoding. Treat Reason Strings and arbitrary User Properties as data. Reject unauthorized redirect/bridge routes rather than forwarding credentials automatically. | Topic matching does not normalize; User Properties can repeat; Reason Strings are diagnostic; Server Reference is routing guidance (§§3.3.2.3.7, 4.7.3, 4.11). |

All source section references in this table refer to the [MQTT 5.0 OASIS Standard][mqtt]. Using TLS and topic ACLs is part of an HMS deployment security profile; MQTT conformance alone does not require that profile. Authorization must also restrict actions, parameters, resources and generations inside a topic's payload. If MQTT 3.1.1 bridges strip MQTT 5 properties, required HMS semantics must survive in the authenticated application envelope or the route must be rejected. [MQTT §§4.10, 5, 7][mqtt]

## Sparkplug mapping

Sparkplug has different wire requirements from a freely chosen MQTT command protocol. NBIRTH, DBIRTH, NDATA, DDATA, DDEATH, NCMD and DCMD use QoS 0 and RETAIN=false. NCMD/DCMD have no payload `seq`. Edge-node NDEATH Will uses QoS 1 and RETAIN=false; host STATE uses QoS 1, retained JSON. Edge and host MQTT 5 connections use Clean Start=true and Session Expiry=0. Requesting QoS 1 on a command subscription does not upgrade a QoS 0 publication. Changing NCMD/DCMD to QoS 2 to obtain an imagined execution guarantee would depart from this profile. [Sparkplug §§2.5, 4.2, 5.3–5.6, 6.4.23–6.4.27][sparkplug]

| ID | Required HMS mapping | Basis and consequence |
| --- | --- | --- |
| SP-01 | Map `(site/infrastructure, group_id, edge_node_id, device_id)` to an enrolled instance. Keep logical device grouping distinct from physical asset identity. A metric's existence in BIRTH does not grant write permission. | Sparkplug devices can be logical aggregations; uniqueness is scoped (§§1.4.1, 4.1). |
| SP-02 | Track broker connection, Sparkplug session, HMS endpoint session and HMS control generation separately. A new NBIRTH replaces the node's active schema/alias view. Device metrics remain unavailable for current decisions until the corresponding DBIRTH is established. | NBIRTH alone does not revalidate prior attached devices (§4.2.1). |
| SP-03 | Match NDEATH to current `bdSeq`; mark the node and associated devices unavailable/stale. Use host receipt time for NDEATH, device message timestamp for DDEATH with clock quality retained. Host loss of a broker makes affected data stale without waiting for individual deaths. | §§5.3–5.7. A Will timestamp is usually connection time, not failure time. |
| SP-04 | Never use `bdSeq`, `seq`, or STATE timestamp as an HMS fencing or deduplication token. Maintain a separate durable authority/session mechanism. Rebirth within a connection retains `bdSeq`; reconnect cycles and message sequences wrap at 255. | §§5.4, 5.17, 6.4.5, 6.4.25. Repeated values cannot identify lifetime execution history. |
| SP-05 | Scope metric aliases to the validated current BIRTH catalogue, unique across the edge node's metrics and devices. Invalidate queued alias-based commands when that catalogue changes, including rebirth without reconnect. Reject unknown aliases and datatype mismatches; request bounded resynchronization. | §§5.15, 5.17, 6.4.6. Sparkplug aliases identify metrics and are distinct from MQTT Topic Aliases. |
| SP-06 | Preserve the special named `Node Control/Rebirth` command; it has no alias. Rate-limit recovery requests and expose synchronization pending. Rebirth pauses DATA and emits a complete BIRTH sequence; it does not cancel physical work or renew authority. | §5.17. A recovery storm can itself interfere with telemetry. |
| SP-07 | Track sequence across the entire edge-node stream, including device messages. Buffer only within configured reorder limits; expose gaps and invalidate affected decision state when recovery fails. An 8-bit wrap cannot supply an unbounded HMS watch cursor; use a gateway epoch/cursor and explicit gaps. | §§5.9, 6.4.5, 6.4.26. Cross-topic delivery order can differ, especially in clustered deployments. |
| SP-08 | Keep historical values out of current state; preserve metric acquisition time separately from payload publication time. Map GOOD/BAD/STALE plus null independently of HMS evidence kind and freshness. Unknown quality or unbounded acquisition age fails an action requiring current measured state. | §§5.16, 6.4.5–6.4.9. GOOD is not proof of a physical sensor or acceptable age. |
| SP-09 | Treat NCMD/DCMD as writes with limited native acknowledgement semantics. Do not infer operation completion merely from a matching later DATA value: it can be an echo, a pre-existing value, another writer's change or a delayed observation. Require commissioned correlation/evidence, or report the weaker result explicitly. | §§5.17, 6.4.23–6.4.24 describe command-to-value updates, not durable operation IDs or completion transactions. |
| SP-10 | Separate retained STATE and `$sparkplug/certificates/...` cache entries from live device observations. A stored BIRTH is useful for description discovery, not proof of current values, connection or authority. | §10.1.4 explicitly stores the original BIRTH, not subsequent DATA changes. |
| SP-11 | Keep host STATE timestamps per broker; compare death/birth epochs as specified. Edge nodes use one broker at a time and, when configured for a primary host, wait for its valid online state before births. Reconnection and broker failover still require HMS operation reconciliation. | §§5.4, 5.10, 5.13; chapter 8 is non-normative HA guidance. No consensus, lock or native-controller fencing is specified. |
| SP-12 | Reject command metrics outside the commissioned writable set even though Sparkplug only recommends that names occur in prior BIRTH. Apply action-specific envelopes after decoding; a Boolean type alone does not authorize reboot, output activation or server switching. | §§5.11, 5.17, 7. Topic ACLs cannot express all per-metric/parameter restrictions. |

For a native Sparkplug device lacking an HMS envelope, a gateway may add journal, identity, policy and observation provenance. It cannot invent a device-side command ID, deadline check, atomic multi-metric write, cancellable queue or measured physical result. Use a separately agreed extension/command endpoint only where both sides implement it; do not silently reinterpret standard `seq`, `uuid` or timestamps as HMS authority fields. Sparkplug's optional payload `uuid` is not defined as an operation identifier. [Sparkplug §§6.4.5, 6.4.23–6.4.24][sparkplug]

## Discovery and liveness across failures

Discovery should return an enrolled asset, a description revision, a route and current presence evidence as separate facts. A broker catalogue may enumerate previously seen nodes while its source connections are gone. A Sparkplug host can join after BIRTH messages were sent; a quiescent report-by-exception node might produce no subsequent DATA to trigger the usual missing-BIRTH recovery. A passive subscription therefore cannot promise a complete inventory within a bounded time. Use an authorized registry, explicitly cached certificate discovery, or bounded rebirth requests to known nodes, and report incomplete inventory when no such mechanism exists. [Sparkplug §§2.2, 5.15, 5.17, 10.1.4][sparkplug]

A sequence gap becomes visible only when a later message exposes it. Silence alone does not distinguish unchanged data from a stuck task, a missing final update or an incomplete route. HMS freshness and liveness requirements need a declared acquisition/health mechanism; report-by-exception can remain the telemetry policy, but it cannot substitute for a bounded control-state validity argument. Do not mark stale values as fresh merely because the broker connection is still open.

Retained online STATE can be stale during failure detection or broker outage. Sparkplug's timestamp comparison helps reject a delayed death from an older host connection; it is not an expiring lease. Clock rollback, lost local STATE history, multi-broker disagreement and wrapping node sequences require explicit uncertain state in HMS. A remote controller must not acquire a competing resource merely because a directory or broker no longer reports its predecessor. Reconciliation and locally enforced fencing decide handover.

## Failure and restart scenarios to validate

These are acceptance scenarios, not tests already performed.

| Scenario | Required outcome |
| --- | --- |
| Broker accepts `dispense(10 µL)`; adapter loses the response | Operation remains identifiable; status/reconciliation occurs. No new dispense is created from a delivery timeout. |
| Adapter actuates, crashes before storing result; MQTT QoS 2 exchange had completed | Recover the journal and query endpoint/physical evidence. Without enough evidence, report `outcome_unknown` and retain affected resource constraints. |
| Broker restarts with lost session state; endpoint continues a bounded procedure | Reconnect is not interpreted as endpoint reboot or completion. Reconcile endpoint session, progress and authority before any new conflicting action. |
| Same key reaches two overlapping or shared subscriptions | Exactly one durable HMS admission in the authority domain; duplicate workers retrieve the same operation. MQTT consumer selection is not the exclusion mechanism. |
| Two consumers lose shared QoS 1 ownership around actuation | The endpoint/exclusive gateway's deduplication and fencing prevent two effects; otherwise advertise uncertainty and prohibit this dispatch topology. |
| Client session resumes with queued commands after lease or latest-start expiry | Protocol delivery can finish, but application admission/execution rejects obsolete authority or time. Receiving a message does not renew its budget. |
| Subscriber's maximum packet size is smaller than publisher's command | Prevent dispatch through prevalidated size budgets or observe missing application receipt; never convert broker ACK into endpoint success. |
| Old retained command exists when an adapter subscribes | It is suppressed/rejected; commissioning prevents future retained effectful publications. Enabling the route cannot execute it. |
| Revocation/UNSUBSCRIBE completes while a native driver still holds work | The local authority generation invalidates queued starts; running work follows installed policy. Handover waits for quiescence/reconciliation when native cancellation is unavailable. |
| New MQTT connection reuses alias 7 for another topic | Mapping is rebuilt; no old command is routed using an alias from the previous connection. |
| Sparkplug rebirth reassigns metric alias 7 while `bdSeq` stays unchanged | Old catalogue-dependent queued commands are rejected; descriptor/binding state is refreshed before new writes. |
| Delayed NDEATH arrives after a new NBIRTH | Correlate `bdSeq`; do not mark the new session dead from an unrelated prior death. At wrap/continuity ambiguity, do not infer a unique lifetime session. |
| NBIRTH arrives but a device DBIRTH is lost | Node may be online; device remains unavailable for state-critical actions. Bounded resynchronization obtains its model/current data. |
| DATA seq 4 arrives before 3, or 3 never arrives | Bounded reorder buffer and timer; explicit gap/rebirth on expiry; no silent current-state update from an incomplete stream where ordering is required. |
| A historical DATA batch arrives after reconnection | Historical points remain historical even if delivery time is recent. Current observation state and deadline checks do not consume them as fresh. |
| Host connects to a Sparkplug-aware broker and reads cached BIRTH | Import candidate metadata only. Current values/presence require live synchronization; cached data cannot admit motion. |
| Two brokers retain conflicting host STATE; old controller remains partitioned | Per-broker state remains visible, but only current locally enforced HMS authority may act. No last-writer-wins STATE election. |
| Stop PUBLISH waits behind traffic or broker failure | Commissioned local watchdog/stop behavior applies without inference or log-network dependency; report measured behavior and any lost observability. |
| Multiple metrics in a DCMD partly reach a legacy device | Report known partial effects; do not claim atomicity or auto-repeat the whole batch. |

## Release gates

Before shipping an MQTT/Sparkplug binding, pin a client library and broker implementation/version, resolve the source inconsistencies in the [review notes](../research/protocols/notes/transport-full-review.md), implement only the advertised subset, and measure failure/recovery behavior on the chosen hardware. Run protocol compatibility checks separately from HMS admission/journal/fencing tests and physical outcome tests. A successful parser test, MQTT conformance certificate or Sparkplug TCK run alone cannot validate the physical guarantees in this document.

[mqtt]: https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html
[sparkplug]: https://sparkplug.eclipse.org/specification/version/3.0/documents/sparkplug-specification-3.0.0.pdf
