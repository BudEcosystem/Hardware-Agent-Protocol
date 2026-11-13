/**
 * BHMS error model and JSON-RPC code table (spec/bhms/10-errors.md; mirrored by the schema's `x-bhms-errors`,
 * which test/errors.test.ts compares with this table).
 *
 * Wire form: `{code, message, data: {bhmsCode, field?, bound?, operationId?, mayHaveActed, retry, hint}}`.
 * `DEVICE_FAULT` and `UNVERIFIED` exist only inside an operation's `error` (BHMS-ERR-012): `toJsonRpc()` refuses them.
 *
 * Example:
 * ```ts
 * throw new BhmsError("OUT_OF_RANGE", "position 420 mm is above the maximum 300 mm",
 *   { field: "arguments.position", bound: { maximum: 300 }, hint: "send a position between 0 and 300 mm" });
 * ```
 * Thread-safety: immutable after construction.
 */

export type BhmsCode =
  | "INVALID_ARGUMENT" | "OUT_OF_RANGE" | "UNIT_MISMATCH" | "UNKNOWN_DEVICE" | "UNKNOWN_ACTION" | "UNSUPPORTED"
  | "LEASE_REQUIRED" | "LEASE_CONFLICT" | "LEASE_EXPIRED" | "FENCED" | "KEY_CONFLICT" | "STALE"
  | "DEVICE_UNAVAILABLE" | "UNAUTHORIZED" | "BUSY" | "DEADLINE_EXCEEDED" | "INTERNAL" | "UNSUPPORTED_VERSION"
  | "UNVERIFIED" | "DEVICE_FAULT";

export type RetryClass = "never" | "same-key" | "after-reconcile" | "backoff";

export const RETRY_VALUES: readonly RetryClass[] = ["never", "same-key", "after-reconcile", "backoff"];

/** The code table of 10-errors.md §10.2: JSON-RPC number and default retry class. */
export const CODES: Readonly<Record<BhmsCode, { number: number; retry: RetryClass }>> = {
  INVALID_ARGUMENT: { number: -32602, retry: "never" },
  OUT_OF_RANGE: { number: -32602, retry: "never" },
  UNIT_MISMATCH: { number: -32602, retry: "never" },
  UNKNOWN_DEVICE: { number: -32001, retry: "never" },
  UNKNOWN_ACTION: { number: -32002, retry: "never" },
  UNSUPPORTED: { number: -32003, retry: "never" },
  LEASE_REQUIRED: { number: -32004, retry: "never" },
  LEASE_CONFLICT: { number: -32005, retry: "backoff" },
  LEASE_EXPIRED: { number: -32006, retry: "never" },
  FENCED: { number: -32007, retry: "never" },
  KEY_CONFLICT: { number: -32008, retry: "never" },
  STALE: { number: -32009, retry: "after-reconcile" },
  DEVICE_UNAVAILABLE: { number: -32010, retry: "backoff" },
  UNAUTHORIZED: { number: -32011, retry: "never" },
  BUSY: { number: -32012, retry: "backoff" },
  DEADLINE_EXCEEDED: { number: -32013, retry: "after-reconcile" },
  INTERNAL: { number: -32014, retry: "never" },
  UNSUPPORTED_VERSION: { number: -32015, retry: "never" },
  UNVERIFIED: { number: -32016, retry: "after-reconcile" },
  DEVICE_FAULT: { number: -32017, retry: "after-reconcile" },
};

/** Codes that describe admitted work and never appear as a JSON-RPC error (BHMS-ERR-012). */
export const OPERATION_ONLY_CODES: ReadonlySet<BhmsCode> = new Set<BhmsCode>(["DEVICE_FAULT", "UNVERIFIED"]);

export interface ErrorOptions {
  field?: string;
  bound?: unknown;
  operationId?: string;
  mayHaveActed?: boolean;
  retry?: RetryClass;
  hint?: string;
}

export interface ErrorData {
  bhmsCode: BhmsCode;
  field?: string;
  bound?: unknown;
  operationId?: string;
  mayHaveActed: boolean;
  retry: RetryClass;
  hint: string;
}

export interface JsonRpcErrorObject {
  code: number;
  message: string;
  data?: unknown;
}

/** A protocol error. Name the field, the bound and a fix whenever known (BHMS-ERR-003). */
export class BhmsError extends Error {
  readonly bhmsCode: BhmsCode;
  readonly field?: string;
  readonly bound?: unknown;
  readonly operationId?: string;
  readonly mayHaveActed: boolean;
  readonly retry: RetryClass;
  readonly hint: string;

  constructor(code: BhmsCode, message: string, options: ErrorOptions = {}) {
    super(message);
    this.name = "BhmsError";
    if (!(code in CODES)) throw new RangeError(`unknown BHMS error code ${String(code)}`);
    const retry = options.retry ?? CODES[code].retry;
    if (!RETRY_VALUES.includes(retry)) throw new RangeError(`invalid retry class ${String(retry)}`);
    this.bhmsCode = code;
    this.field = options.field;
    this.bound = options.bound;
    this.operationId = options.operationId;
    this.mayHaveActed = options.mayHaveActed ?? false;
    this.retry = retry;
    this.hint = options.hint ?? "";
  }

  /** `ErrorData` in the member order of the spec. */
  data(): ErrorData {
    const d: ErrorData = { bhmsCode: this.bhmsCode } as ErrorData;
    if (this.field !== undefined) d.field = this.field;
    if (this.bound !== undefined && this.bound !== null) d.bound = this.bound;
    if (this.operationId !== undefined) d.operationId = this.operationId;
    d.mayHaveActed = this.mayHaveActed;
    d.retry = this.retry;
    d.hint = this.hint;
    return d;
  }

  /** The JSON-RPC error object. Throws for operation-only codes. */
  toJsonRpc(): JsonRpcErrorObject {
    if (OPERATION_ONLY_CODES.has(this.bhmsCode)) {
      throw new RangeError(`${this.bhmsCode} describes admitted work; use toOperationError()`);
    }
    return { code: CODES[this.bhmsCode].number, message: this.message.slice(0, 2000), data: this.data() };
  }

  /** The `OperationError` wire form: error data plus `message` (any code). */
  toOperationError(): ErrorData & { message: string } {
    return { ...this.data(), message: this.message.slice(0, 2000) };
  }
}

/** Rebuild a BhmsError from a JSON-RPC error object; undefined when it is not a BHMS error (-32700, -32600...). */
export function fromJsonRpc(err: JsonRpcErrorObject): BhmsError | undefined {
  const data = err.data as Partial<ErrorData> | undefined;
  if (typeof data !== "object" || data === null || typeof data.bhmsCode !== "string") return undefined;
  const code = data.bhmsCode;
  if (!(code in CODES)) return undefined;
  if (typeof data.mayHaveActed !== "boolean" || typeof data.hint !== "string" || !RETRY_VALUES.includes(data.retry as RetryClass)) {
    return undefined;
  }
  return new BhmsError(code, String(err.message ?? ""), {
    field: data.field, bound: data.bound, operationId: data.operationId, mayHaveActed: data.mayHaveActed,
    retry: data.retry, hint: data.hint,
  });
}

/** A JSON-RPC error that is not a BHMS error (-32700, -32600, -32601...). */
export class JsonRpcError extends Error {
  constructor(readonly code: number, message: string, readonly data?: unknown) {
    super(`${message} (JSON-RPC ${code})`);
    this.name = "JsonRpcError";
    this.rpcMessage = message;
  }
  readonly rpcMessage: string;
  toError(): JsonRpcErrorObject {
    const e: JsonRpcErrorObject = { code: this.code, message: this.rpcMessage.slice(0, 2000) };
    if (this.data !== undefined) e.data = this.data;
    return e;
  }
}
