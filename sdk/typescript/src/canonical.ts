/**
 * RFC 8785 (JCS) canonical JSON and BHMS digests.
 *
 * ECMAScript's `JSON.stringify` already prints strings and numbers exactly as RFC 8785 §3.2.2/§3.2.3 require (that is
 * what the RFC's number algorithm is), so canonicalization here only has to order object members by UTF-16 code
 * units, which is the default JavaScript string comparison. The output is byte-identical to the Python SDK's
 * `bhms.protocol.canonical.canonical` (checked against the example digests by test/canonical.test.ts).
 *
 * JavaScript has one number type, so `1.0` and `1` are the same value and print as `1`, matching Python's output for
 * integral floats.
 *
 * Thread-safety: pure functions.
 */
import { createHash } from "node:crypto";
import { BhmsError } from "./errors.js";

function encode(value: unknown, out: string[]): void {
  if (value === null) {
    out.push("null");
  } else if (typeof value === "boolean") {
    out.push(value ? "true" : "false");
  } else if (typeof value === "string") {
    out.push(JSON.stringify(value));
  } else if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new RangeError("NaN and Infinity are not JSON");
    out.push(JSON.stringify(value));
  } else if (Array.isArray(value)) {
    out.push("[");
    for (let i = 0; i < value.length; i++) {
      if (i > 0) out.push(",");
      encode(value[i] === undefined ? null : value[i], out);
    }
    out.push("]");
  } else if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).filter((k) => obj[k] !== undefined).sort();
    out.push("{");
    keys.forEach((k, i) => {
      if (i > 0) out.push(",");
      out.push(JSON.stringify(k), ":");
      encode(obj[k], out);
    });
    out.push("}");
  } else {
    throw new TypeError(`value of type ${typeof value} is not JSON`);
  }
}

/** The JCS encoding of `value` as a string. Throws BhmsError INVALID_ARGUMENT for non-JSON values. */
export function canonicalString(value: unknown): string {
  const out: string[] = [];
  try {
    encode(value, out);
  } catch (e) {
    throw new BhmsError("INVALID_ARGUMENT", `value is not canonical-JSON serializable: ${(e as Error).message}`, {
      hint: "use finite numbers and JSON types only (null, boolean, number, string, array, object)",
    });
  }
  return out.join("");
}

/** The JCS encoding of `value` as UTF-8 bytes. */
export function canonical(value: unknown): Buffer {
  return Buffer.from(canonicalString(value), "utf8");
}

/** `"sha256:" + hex(sha256(JCS(value)))` (BHMS-DEV-021, BHMS-OPS-030). */
export function digest(value: unknown): string {
  return "sha256:" + createHash("sha256").update(canonical(value)).digest("hex");
}

/** Digest of a description without its own `digest` member (BHMS-DEV-021). */
export function descriptionDigest(description: Record<string, unknown>): string {
  const { digest: _omit, ...rest } = description;
  void _omit;
  return digest(rest);
}
