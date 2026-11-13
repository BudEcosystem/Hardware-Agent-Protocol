# 2. Transports

A transport is a *binding*: it frames and delivers JSON-RPC messages, carries
identity, and signals request cancellation. It never changes what a message
means. Protocol semantics are identical on every transport.

**BHMS-TRN-001** A binding MUST deliver client requests and notifications to the
server, and server responses and notifications to the client. Servers MUST NOT
send JSON-RPC requests; clients MUST NOT send JSON-RPC responses.

**BHMS-TRN-002** Senders MUST NOT send JSON-RPC batch arrays. A server receiving
a batch MUST answer with a single error `-32600` (Invalid Request) and `id: null`.

**BHMS-TRN-003** A binding MUST allow several requests in flight at once on one
connection; responses MAY arrive in any order and are correlated by `id`.

**BHMS-TRN-004** A server MUST reject a message larger than its advertised
`limits.maxMessageBytes` (at least 1 048 576 bytes) with `-32600` and MUST NOT
buffer an unbounded partial message.

**BHMS-TRN-005** Closing a connection MUST NOT cancel, roll back or forget any
operation, lease or durable record. It only abandons the requests in flight on
that connection (as if each had received `notifications/cancelled`).

## 2.1 stdio

The client launches the server as a subprocess. Each message is one line of
UTF-8 JSON on stdin (client → server) or stdout (server → client).

**BHMS-TRN-010** Messages on stdio MUST be delimited by `\n` and MUST NOT contain
embedded newlines. The server MUST NOT write anything to stdout that is not a
BHMS message; it MAY log to stderr.

**BHMS-TRN-011** The server SHOULD exit when stdin reaches end-of-file. The
parent process is the principal for stdio (BHMS-SEC-003).

**BHMS-TRN-012** On stdio a client MUST cancel an in-flight request with
`notifications/cancelled`; there is no per-request stream to close.

## 2.2 Unix-domain and TCP sockets

The stdio framing (newline-delimited JSON) is reused unchanged over a reliable
byte stream.

**BHMS-TRN-020** Socket bindings MUST use the stdio framing (BHMS-TRN-010).

**BHMS-TRN-021** A TCP listener MUST bind only to a loopback address unless the
connection is protected by TLS and every request is authenticated with a bearer
token (BHMS-SEC-004).

**BHMS-TRN-022** A Unix-domain socket server SHOULD derive the principal from the
peer credential (`SO_PEERCRED` or equivalent) and MUST create the socket with
permissions no wider than its policy grants.

## 2.3 WebSocket

**BHMS-TRN-030** A WebSocket binding MUST carry exactly one JSON-RPC message per
text frame and MUST negotiate the subprotocol `bhms`.

**BHMS-TRN-031** A WebSocket server reachable from anything but loopback MUST
require `Authorization: Bearer <token>` on the upgrade request and MUST reject
the upgrade with HTTP 401 when it is missing or invalid.

**BHMS-TRN-032** On WebSocket a client MUST cancel an in-flight request with
`notifications/cancelled`.

## 2.4 Streamable HTTP (optional in v0.1)

A server MAY expose one HTTP endpoint (conventionally `/bhms`).

**BHMS-TRN-040** Each client message MUST be an HTTP POST with
`Content-Type: application/json` and headers `BHMS-Protocol-Version` and
`BHMS-Method` mirroring `params._meta["bhms/protocolVersion"]` and `method`.
A server MUST reject a mismatch between header and body with HTTP 400 and error
`INVALID_ARGUMENT` naming the header.

**BHMS-TRN-041** The response to an ordinary request MUST be either
`application/json` (one response) or `text/event-stream` whose events each carry
one JSON-RPC message, ending with the response. `subscriptions/listen` MUST use
`text/event-stream`.

**BHMS-TRN-042** On Streamable HTTP, closing the response stream is the
cancellation signal for that request; the server MUST treat a disconnect exactly
as `notifications/cancelled` (and therefore MUST NOT cancel the underlying
operation, BHMS-TRN-005).

**BHMS-TRN-043** Notifications sent by the client (only `notifications/cancelled`)
MUST be POSTed and answered with HTTP 202 and no body.

There is no stream resumption: a broken response stream loses that request, and
the client re-issues it with a new JSON-RPC id. Because operations are durable
and keyed, re-issuing `actions/invoke` with the same `operationKey` is safe
(BHMS-OPS-030).

## 2.5 BHMS-Compact

BHMS-Compact is not JSON-RPC. It is a fixed-layout binary binding for
microcontrollers, carried in the HDLC-style `HM` frames of
`protocol/serial/frame.{c,h,py}`, and terminated by a gateway that translates it
into JSON-RPC. See [11-compact-binding.md](11-compact-binding.md).

## 2.6 Custom transports

**BHMS-TRN-050** A custom transport MUST preserve the JSON-RPC message format,
the per-request `_meta` model and the cancellation semantics of this chapter,
and SHOULD reuse the stdio framing when it runs over a byte stream.
