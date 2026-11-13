/**
 * @bhms/sdk: the TypeScript SDK for BHMS (spec/bhms), interoperable byte for byte with the Python reference SDK.
 *
 * - Client side: {@link Client} (`Client.connect("stdio:...")`), a typed method for every protocol method.
 * - Server side: {@link DeviceServer} with {@link Device} builders, a durable operation journal, leases, stop,
 *   subscriptions.
 * - Plumbing: {@link Session} (JSON-RPC), transports (stdio, Unix and TCP sockets, WebSocket, in-memory), the generated
 *   protocol types, RFC 8785 canonicalization and digests, and the JSON Schema validator.
 */
export * from "./client.js";
export * from "./canonical.js";
export { BhmsError, JsonRpcError, fromJsonRpc, CODES, RETRY_VALUES, OPERATION_ONLY_CODES, type BhmsCode, type ErrorOptions, type JsonRpcErrorObject } from "./errors.js";
export * from "./generated/types.js";
export { Session, ClientStream, Complete, TransportClosed, SUBSCRIPTION_KEY, type Handler, type Notification, type Peer, type RequestContext, type Transport, type TransportSink } from "./jsonrpc/session.js";
export { SchemaValidator, defValidator, loadSchema, schemaPath, validateDef, fieldPath, bestIssue, isMultipleOf, type Issue } from "./schema.js";
export { DeviceServer, summaryMatches, type DeviceServerOptions, type ExtensionHandler } from "./server/server.js";
export { Device, DescriptionError, type ActionOptions, type DeviceOptions, type PropertyOptions } from "./server/device.js";
export { Canceled, DeviceFault, Reading, type ActionContext, type Reconciled } from "./server/context.js";
export { arrayOf, bool, int, num, objectOf, range, str, type Schema } from "./server/schemas.js";
export { Principal, defaultPolicy, type Policy } from "./server/authority.js";
export { JournalStore, MemoryStore, StoreError, type Store } from "./server/store.js";
export { admitArguments, checkUnits } from "./server/validation.js";
export { LineTransport } from "./transport/stream.js";
export { memoryPair } from "./transport/memory.js";
export { spawnServer, stdioServerTransport } from "./transport/stdio.js";
export { connectSocket, listenTcp, listenUnix } from "./transport/socket.js";
export { connectWebSocket, listenWebSocket } from "./transport/websocket.js";
