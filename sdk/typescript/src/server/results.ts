/**
 * The one check of an action result before it is recorded (BHMS-OPS-008): an I-JSON value that the action's declared `output`
 * schema accepts.
 *
 * Used by every path that records a result: the executor for a handler's return value and for a device's reconciliation
 * answer ({@link Executor}), and the operator resolution (`resolution.ts`). Each caller turns a {@link ResultDefect} into its
 * own outcome (a failed operation, a refused request, a refused hook answer); the classification lives here once, as in the
 * Python reference (`bhms.runtime.results.check_result`):
 *
 * - `not-ijson`: the value cannot be carried as canonical JSON (NaN, Infinity, an integer beyond +/-2^53, a non-JSON type);
 * - `out-of-range`: the value has the declared shape and its only defects are numbers outside declared ranges, i.e. a
 *   measurement outside its declared range rather than a malformed result (BHMS-OPS-008 reports it as `OUT_OF_RANGE`);
 * - `schema`: anything else the output schema refuses.
 *
 * ```ts
 * const defect = checkResult({ volume: 200.138 }, new SchemaValidator(outputSchema));
 * // { kind: "out-of-range", member: "result.volume", keyword: "maximum", bound: { maximum: 200 }, instance: 200.138, ... }
 * ```
 *
 * Thread-safety: pure functions; a validator may be shared.
 */
import type { SchemaValidator } from "../schema.js";

/** Output-schema keywords whose violation means "a number outside its declared range" (BHMS-OPS-008). */
export const RANGE_KEYWORDS: ReadonlySet<string> = new Set(["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"]);

/**
 * Why a result cannot be recorded as it is. `message` is the reason in words, starting from the result; `cause` is the
 * underlying reason alone. `member` is the path of the first offending member (`result` for the whole value). For
 * `out-of-range` only: `instance` is the offending value, `keyword` the range keyword it breaks and `bound`
 * `{keyword: declared value}`.
 */
export interface ResultDefect {
  kind: "not-ijson" | "out-of-range" | "schema";
  message: string;
  cause: string;
  member: string;
  instance?: number;
  keyword?: string;
  bound?: Record<string, number>;
}

/** The first member of `value` that is not an I-JSON value (RFC 7493) and why, else `undefined`. */
function ijsonViolation(value: unknown, path: string): { member: string; message: string; cause: string } | undefined {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      return { member: path, message: `${path} is ${value}; NaN and Infinity are not JSON numbers: return null or a string`, cause: `${value} is not a JSON number` };
    }
    if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
      return {
        member: path, cause: `${value} is beyond +/-2^53`,
        message: `${path} is the integer ${value}, beyond +/-2^53 (9007199254740991); results are I-JSON, so numbers must be exactly representable as IEEE 754 doubles: return it as a string, or as a float if rounding is acceptable`,
      };
    }
    return undefined;
  }
  if (value === undefined || typeof value === "function" || typeof value === "bigint" || typeof value === "symbol") {
    return { member: path, message: `the result is not JSON-serialisable (${path} is a ${value === undefined ? "undefined value" : typeof value})`, cause: `${typeof value} is not a JSON type` };
  }
  if (Array.isArray(value)) {
    for (const [i, item] of value.entries()) {
      const found = ijsonViolation(item, `${path}[${i}]`);
      if (found) return found;
    }
  } else if (typeof value === "object" && value !== null) {
    for (const [k, item] of Object.entries(value)) {
      const found = ijsonViolation(item, `${path}.${k}`);
      if (found) return found;
    }
  }
  return undefined;
}

/**
 * Check `result` against I-JSON and, when `validator` (of the action's `output` schema) is given, against the declared output.
 * Returns `undefined` when it can be recorded, else the first defect: an I-JSON defect before any schema defect, and
 * `out-of-range` only when every schema error is a range keyword.
 */
export function checkResult(result: unknown, validator: SchemaValidator | undefined): ResultDefect | undefined {
  const bad = ijsonViolation(result, "result");
  if (bad) return { kind: "not-ijson", ...bad };
  if (validator === undefined) return undefined;
  const errors = validator.collect(result).filter((issue) => !issue.context); // what a 2020-12 validator reports at top level
  if (errors.length === 0) return undefined;
  const first = errors[0];
  const member = ["result", ...first.path.map(String)].join(".");
  const message = `the result does not match the declared output schema: ${first.message}`;
  if (errors.every((e) => RANGE_KEYWORDS.has(e.keyword) && e.limit !== undefined)) {
    return { kind: "out-of-range", message, cause: first.message, member, instance: first.instance, keyword: first.keyword, bound: { [first.keyword]: first.limit! } };
  }
  return { kind: "schema", message, cause: first.message, member };
}
