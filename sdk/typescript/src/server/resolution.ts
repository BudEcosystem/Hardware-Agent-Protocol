/**
 * Recording an operator's resolution of an `unknown` operation (`operations/resolve`, spec/bhms/06-operations.md §6.10,
 * BHMS-OPS-102).
 *
 * One function, {@link recordOperatorResolution}, used by the device server ({@link DeviceServer.resolve} through
 * `Executor.resolveByOperator`). The rules live here once, as in the Python reference (`bhms.runtime.resolution`):
 *
 * - An operator's statement is never a measurement. The recorded `effect` is at most `unverified` and the evidence is
 *   `{"kind": "reported"}`; `verified`/`measured` come only from the device itself (the reconciliation every resolve attempts
 *   first). An operation that required a verified effect therefore cannot be resolved as `completed`.
 * - `completed` needs a `result` that the action's `output` schema accepts (`{}` when the action declares none; checked by
 *   {@link checkResult}) and records `unverified` (`none` for an action without effect).
 * - `failed` records `DEVICE_FAULT` with the basis as its message; `mayHaveActed: false` is a claim of proof that nothing
 *   happened and goes with `effect: "none"` (and only then); otherwise the effect is `unknown` or, when the operator says so,
 *   `unverified`.
 * - The history entry is a `reconciliation` carrying `operator: {principal, basis}`; earlier entries are untouched.
 *
 * ```ts
 * recordOperatorResolution(journal, rec, { state: "failed", basis: "axis inspected at rest" }, "operator-7", undefined);
 * ```
 *
 * A resolution that breaks a rule throws {@link BhmsError} naming the member of `resolution` (`mayHaveActed: false`: nothing
 * was recorded). Thread-safety: call on the journal's event loop.
 */
import { BhmsError, type BhmsCode } from "../errors.js";
import type { OperatorResolution } from "../generated/types.js";
import type { SchemaValidator } from "../schema.js";
import type { Journal, OperationRecord } from "./operations.js";
import { checkResult } from "./results.js";

export type { OperatorResolution };

/** The evidence of every operator resolution: a person's report, never a measurement (BHMS-OPS-102). */
export const OPERATOR_EVIDENCE = { kind: "reported" } as const;

/** The hint of a resolution the journal refuses to record (the members an `OperatorResolution` carries). */
export const INVALID_RESOLUTION_HINT = "check state, effect and result against the operation (spec 6.10)";

function refuse(member: string, message: string, hint: string, code: BhmsCode = "INVALID_ARGUMENT", bound?: unknown): BhmsError {
  return new BhmsError(code, `resolution.${member}: ${message}`.slice(0, 2000), { field: `resolution.${member}`, bound, hint });
}

/** The result of a `completed` resolution, checked like a handler's result ({@link checkResult}: I-JSON, the declared output). */
function checkedResult(resolution: OperatorResolution, action: string, validator: SchemaValidator | undefined): unknown {
  let result: unknown;
  if (Object.hasOwn(resolution, "result")) result = resolution.result;
  else if (validator === undefined) result = {};
  else throw refuse("result", `state completed needs the result of ${action}`, `state the result ${action} produced (devices/describe shows its output), or resolve it as failed`);
  const defect = checkResult(result, validator);
  if (defect === undefined) return result;
  if (defect.kind === "not-ijson") throw refuse("result", `cannot be recorded (${defect.cause})`, "results are I-JSON values");
  if (defect.kind === "out-of-range") {
    throw refuse(defect.member, `${JSON.stringify(defect.instance)} is outside the declared output range of ${action}`,
      "state the result the device produced, or resolve the operation as failed", "OUT_OF_RANGE", defect.bound);
  }
  throw refuse("result", `does not match the declared output of ${action}: ${defect.cause}`, `state a result that matches the output of ${action}, or resolve the operation as failed`);
}

/**
 * Record `resolution` (an `OperatorResolution` the schema accepted) on the `unknown` operation `rec`, stated by `principal`.
 * `outputValidator` validates the action's `output` (`undefined` when it declares none or the action is not known here). See
 * the module docs for the rules; throws `BhmsError` and records nothing when one is broken, and the journal's
 * `InvalidTransition` when its own invariants refuse the change.
 */
export function recordOperatorResolution(journal: Journal, rec: OperationRecord, resolution: OperatorResolution, principal: string, outputValidator: SchemaValidator | undefined): void {
  const action = rec.op.action ?? "the action";
  const effectless = rec.data.effectClass === "none";
  const common = {
    kind: "reconciliation" as const, detail: `operator resolution by ${principal}: ${resolution.basis}`,
    operator: { principal, basis: resolution.basis }, evidence: { ...OPERATOR_EVIDENCE },
  };
  if (resolution.state === "completed") {
    if (rec.op.require?.effect === "verified") {
      throw refuse("state", "the operation required a verified effect, which an operator's statement cannot establish", "resolve it as failed and state what was found; only device evidence verifies");
    }
    const expected = effectless ? "none" : "unverified";
    if (resolution.effect !== undefined && resolution.effect !== expected) {
      throw refuse("effect", `a completed ${action} is recorded with effect ${expected}`, `omit effect or state ${expected}; an operator's report is never a measurement`);
    }
    journal.transition(rec, "completed", { ...common, result: checkedResult(resolution, action, outputValidator), hasResult: true, effect: expected });
    return;
  }
  const acted = resolution.mayHaveActed ?? true;
  if ((resolution.effect === "none") === acted) { // "none" is the claim that nothing happened: the two go together
    throw refuse("effect", "effect none and mayHaveActed false are one claim (proof that nothing happened) and must be stated together", "state both, or neither");
  }
  const error = new BhmsError("DEVICE_FAULT", resolution.basis, { mayHaveActed: acted, hint: "read the device state before retrying" }).toOperationError();
  journal.transition(rec, "failed", { ...common, error, effect: resolution.effect ?? "unknown", proof: acted ? undefined : resolution.basis });
}
