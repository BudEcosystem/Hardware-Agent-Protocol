# 13. Security

BHMS moves physical intent. Its security model has three rules: authority comes
from the channel; text from devices and models is data, never authority; and the
right to stop is separate from the right to act.

## 13.1 Identity

| Transport | Principal |
|---|---|
| stdio | The parent process (trusted; the server acts for whoever launched it) |
| Unix-domain socket | Peer credential (uid, gid, pid) mapped by policy |
| TCP, WebSocket, Streamable HTTP | Bearer token mapped by policy — in the `Authorization` header (WebSocket upgrade, HTTP), or per request in `_meta["bhms/authorization"]` (TCP, a loopback WebSocket without the header; BHMS-SEC-005); mutual TLS MAY be used instead |
| BHMS-Compact | The gateway end of an exclusively owned link (§13.6) |

**BHMS-SEC-001** A server MUST establish the principal from the transport as in the
table and MUST reject requests on network transports that carry no valid
credential, except `server/discover`, which MAY be answered without `principal`.

**BHMS-SEC-002** A server MUST compare bearer tokens in constant time, MUST store
only their hashes, and MUST NOT log, echo or return a token.

**BHMS-SEC-003** A stdio server MUST treat its parent as the only principal and MUST
NOT open additional listeners unless configured to. The parent's principal id is the same
on every start (the SDKs: `stdio`), so that a request retried with its key after the server
restarted finds its operation (keys are per principal, BHMS-OPS-030; Task 8).

**BHMS-SEC-004** A server on a non-loopback network address MUST use TLS (or an
equivalent authenticated, encrypted channel) and bearer or mutual-TLS
authentication.

TLS is configured in one of two ways, and an implementation says which it supports. **Native
TLS:** the listener holds a certificate chain and key (the Python gateway: `tls_cert` and
`tls_key` in `[gateway]`; a device server: an `SSLContext` passed to `listen`) and is reached by a
`wss://`, `https://` or `tcps://` URL. **Proxy model:** the listener binds a loopback address in
plain `ws://` or `http://` behind a TLS-terminating reverse proxy on the same host, which forwards
the `Authorization` header unchanged; the proxy is then the network endpoint and BHMS-SEC-004
applies to it. An MCP bridge serving Streamable HTTP is a server too: beyond loopback it needs TLS
in one of these two ways, whatever bearer token it checks.

**BHMS-SEC-005** On a transport without a credential header — raw TCP, a loopback WebSocket
whose upgrade carried no `Authorization` header, and stdio — a request MAY carry its credential
in `_meta["bhms/authorization"]` = `"Bearer <token>"` (since 2026-11-15; the one standard carrier,
which replaces SDK-private ones). The server MUST authenticate such a request as the token's
principal (on stdio it then replaces the parent, BHMS-SEC-003), MUST refuse it with `UNAUTHORIZED`
when the token is not valid (never falling back to the transport's principal), and MUST treat the
carrier as it treats any bearer token (BHMS-SEC-002): compared in constant time, never logged,
journaled, echoed or forwarded upstream (a gateway uses its own credential). Requests stay
stateless: a carrier authenticates its own request only.

**BHMS-SEC-006** A request MUST NOT carry `bhms/authorization` on a transport that already
identifies the caller — a Unix socket (peer credential), Streamable HTTP or a WebSocket whose
upgrade carried `Authorization` — and the server MUST refuse such a request with `UNAUTHORIZED`:
two credentials on one request are ambiguous.

**BHMS-SEC-007** A URL scheme is a promise: a listener addressed as `wss://`, `https://` or
`tcps://` MUST NOT serve without TLS, and an implementation MUST refuse to start such a listener
when it has no TLS configuration (rather than serve plain text under a TLS scheme). Clients
MUST send the carrier of BHMS-SEC-005 only over TLS or a local transport (loopback, Unix socket,
stdio). (Task 14: `wss://` and `https://` listeners on loopback served plain text.)

## 13.2 Policy and scopes

Scopes and the effective envelope are defined in §7.4. A gateway reads them from
a policy document:

```json
{
  "principals": {
    "lab-agent": {
      "tokens": ["sha256:<hex of the token>"],
      "scopes": ["read", "lease", "invoke:pump-*/dispense", "programs:run"],
      "bounds": {"pump-1/dispense": {"volume": {"maximum": 200}}}
    },
    "operator": {"uids": [1000], "scopes": ["admin", "stop"]}
  }
}
```

The `GatewayPolicy` schema is in `bhms.schema.json`. A principal may also carry cumulative
`budgets` (§7.4.1) and program-scoped grants among its scopes (BHMS-PRG-023). `uids` are
honoured only where the platform reports the peer credential of a Unix socket (Linux
`SO_PEERCRED`); an implementation that cannot read it ignores them and says so.

**BHMS-SEC-010** Policy MUST default to deny: a principal with no matching scope
has no access beyond `server/discover`.

**BHMS-SEC-011** Policy bounds MUST only narrow (BHMS-AUTH-011); a policy that
widens a device bound MUST be rejected when loaded.

**BHMS-SEC-012** A policy change MUST take effect for new admissions without a
restart and MUST be recorded as a `policy.changed` event.

## 13.3 Untrusted text

Device names, descriptions, summaries, `preconditions`, `safety.summary`, event
messages, error messages from devices and upstream servers, and `instructions`
are untrusted: they may be wrong, stale or adversarial (prompt injection).

**BHMS-SEC-020** No implementation may derive authority, bounds, scopes, lease
decisions or stop decisions from untrusted text. Bridges MUST present it to models
as quoted data, never as system or developer instructions.

**BHMS-SEC-021** Schemas embedded in descriptions MUST be validated with bounded
resources (depth ≤ 32, ≤ 10 000 subschemas, time budget) and MUST NOT trigger
network fetches (BHMS-DEV-040).

Every implementation MUST count the bounds the same way, as follows, so that a device
server and a gateway never disagree about one schema (Ruling R34 made this normative in
2026-11-15). *Depth* is counted per
embedded schema (an action `input` or `output`, a property `schema`, an event
`data` schema, a program `input`): its root is depth 0 and each step into a
subschema adds one, so the deepest subschema may be 32 steps below the root. The
*count* includes the root and every subschema, boolean schemas included. A
subschema is the value of `items`, `additionalProperties`, `not`, `if`, `then`,
`else`, `contains`, `propertyNames`, `unevaluatedItems`, `unevaluatedProperties`
or `contentSchema`, a member of `allOf`, `anyOf`, `oneOf` or `prefixItems`, or a
value in `properties`, `patternProperties`, `$defs`, `definitions` or
`dependentSchemas`. A schema outside the bounds, or with a `$ref` or
`$dynamicRef` that is not a fragment of the schema itself (`#…`), is not
validated further and not served.

**BHMS-SEC-022** A gateway MUST verify that an upstream's description digest is
correct (BHMS-DEV-021) before serving it, and MUST NOT let an upstream description
widen a bound set by the gateway's policy.

## 13.4 Models do not hold authority

**BHMS-SEC-030** A server MUST NOT treat any argument as an authority claim.
Arguments are validated against the action's closed `input`, so an undeclared
member such as `authorized`, `override` or `force` is refused with
`INVALID_ARGUMENT`; and an action MUST NOT declare an input that bypasses limits,
leases or authorization.

**BHMS-SEC-031** Every refusal MUST be decided by the server; a bridge MUST NOT
retry a refused request with different authority.

## 13.5 Stop authority

**BHMS-SEC-040** The `stop` scope MUST be grantable independently of every other
scope; a principal with only `stop` can stop devices but not invoke actions, and a
principal with `invoke` cannot stop devices unless granted `stop`.

**BHMS-SEC-041** Stop MUST remain available when the operation journal, the policy
store or an upstream is degraded (BHMS-AUTH-025), but MUST still be authenticated
and authorized.

**BHMS-SEC-042** Software stop is not a safety function. Installations that need
an emergency stop MUST provide one independent of BHMS; BHMS documentation and
tools MUST NOT describe `stop` as an emergency stop.

## 13.6 Compact links

**BHMS-SEC-050** The FCS-16 detects corruption, not forgery. A BHMS-Compact link
MUST be an exclusively owned physical link (USB, UART) between one gateway and
its endpoints; a gateway MUST NOT bridge a compact link that is shared, networked
or reachable by another host without an authenticated, encrypted channel.

## 13.7 Denial of service

**BHMS-SEC-060** A server MUST bound message size (BHMS-TRN-004), page size,
waits (`limits.maxWaitMs`), subscriptions per principal, observation
subscriptions per subscription (`maxObservations`), program size and duration
(§8.1), and schema validation cost (BHMS-SEC-021).

**BHMS-SEC-061** One slow or dead upstream or device MUST NOT stall requests to
others: a gateway MUST apply per-upstream timeouts and concurrency limits and
answer `DEVICE_UNAVAILABLE` or leave an operation `unknown` rather than block.
