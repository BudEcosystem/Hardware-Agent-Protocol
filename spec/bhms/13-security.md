# 13. Security

BHMS moves physical intent. Its security model has three rules: authority comes
from the channel; text from devices and models is data, never authority; and the
right to stop is separate from the right to act.

## 13.1 Identity

| Transport | Principal |
|---|---|
| stdio | The parent process (trusted; the server acts for whoever launched it) |
| Unix-domain socket | Peer credential (uid, gid, pid) mapped by policy |
| TCP, WebSocket, Streamable HTTP | Bearer token mapped by policy; mutual TLS MAY be used instead |
| BHMS-Compact | The gateway end of an exclusively owned link (§13.6) |

**BHMS-SEC-001** A server MUST establish the principal from the transport as in the
table and MUST reject requests on network transports that carry no valid
credential, except `server/discover`, which MAY be answered without `principal`.

**BHMS-SEC-002** A server MUST compare bearer tokens in constant time, MUST store
only their hashes, and MUST NOT log, echo or return a token.

**BHMS-SEC-003** A stdio server MUST treat its parent as the only principal and MUST
NOT open additional listeners unless configured to.

**BHMS-SEC-004** A server on a non-loopback network address MUST use TLS (or an
equivalent authenticated, encrypted channel) and bearer or mutual-TLS
authentication.

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

The `GatewayPolicy` schema is in `bhms.schema.json`.

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
