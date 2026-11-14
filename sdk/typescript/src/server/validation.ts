/**
 * Argument admission and description checks (spec/bhms/04-devices.md §4.5).
 *
 * {@link admitArguments} admits the `arguments` of one action exactly as BHMS-DEV-043/044 require, before anything is
 * recorded:
 *
 * - a quantity object `{"value": v, "unit": u}` is accepted only when `u` equals the schema's `x-bhms-unit` and is then
 *   treated as `v`; any other unit is `UNIT_MISMATCH` naming the field, with the declared unit as `bound`; nothing is
 *   converted silently;
 * - a wrong type, an unknown member, a missing required member, a `pattern` or a `multipleOf` violation is
 *   `INVALID_ARGUMENT`; `multipleOf` uses the 1e-9 relative tolerance of BHMS-DEV-071;
 * - a violated `minimum`/`maximum`/`exclusive*`/`min/maxLength`/`min/maxItems`/`enum` is `OUT_OF_RANGE` with `field`,
 *   `bound` (the violated keyword and value) and a hint stating the allowed range. Values are never coerced or clamped;
 * - schema `default`s are applied to absent members. The admitted arguments are returned separately from the arguments
 *   as sent (an operation records both, §6.2).
 *
 * {@link checkUnits} scans a schema for BHMS-DEV-041 (every `number`/`integer` schema carries `x-bhms-unit`) and for
 * BHMS-DEV-040 (no `$ref` outside the schema) and the resource bounds of BHMS-SEC-021.
 *
 * Thread-safety: pure functions.
 */
import { BhmsError } from "../errors.js";
import { SchemaValidator, bestIssue, fieldPath, iterSubschemas, type JsonSchema } from "../schema.js";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);


function isNumericType(t: unknown): boolean {
  if (typeof t === "string") return t === "number" || t === "integer";
  return Array.isArray(t) && t.some((x) => x === "number" || x === "integer");
}

/**
 * Throws RangeError naming the path of the first violation of BHMS-DEV-040/041 or BHMS-SEC-021. The walk is the SDK's one schema
 * walker, {@link iterSubschemas}; its `SchemaBoundsError` is a `RangeError` too.
 */
export function checkUnits(schema: unknown, where: string): void {
  for (const [path, node] of iterSubschemas(schema, where)) {
    if (!isObj(node) || !isNumericType(node.type)) continue;
    const unit = node["x-bhms-unit"];
    if (typeof unit !== "string" || unit === "") throw new RangeError(`${path}: a number/integer schema must carry x-bhms-unit (BHMS-DEV-041); use "1" for counts and "%" for percentages`);
  }
}

function fmt(v: unknown): string {
  return typeof v === "string" ? JSON.stringify(v) : String(v);
}

function join(path: string, part: string | number): string {
  return typeof part === "number" ? `${path}[${part}]` : path ? `${path}.${part}` : part;
}

function resolveRef(root: JsonSchema, schema: Obj): Obj {
  let cur: Obj = schema;
  for (let hops = 0; typeof cur.$ref === "string" && hops < 16; hops++) {
    let node: unknown = root;
    for (const raw of (cur.$ref as string).slice(1).split("/").filter(Boolean)) node = isObj(node) ? node[decodeURIComponent(raw).replace(/~1/g, "/").replace(/~0/g, "~")] : undefined;
    if (!isObj(node)) break;
    cur = node;
  }
  return cur;
}

function typesOf(s: Obj): string[] | undefined {
  if (typeof s.type === "string") return [s.type];
  if (Array.isArray(s.type)) return s.type as string[];
  return undefined;
}

function kindOf(v: unknown): string {
  if (v === null) return "null";
  if (Array.isArray(v)) return "array";
  if (typeof v === "number") return Number.isInteger(v) ? "integer" : "number";
  return typeof v;
}

function typeOk(types: string[], v: unknown): boolean {
  const k = kindOf(v);
  return types.some((t) => t === k || (t === "number" && k === "integer"));
}

function outOfRange(field: string, keyword: string, limit: unknown, message: string, hint: string): BhmsError {
  return new BhmsError("OUT_OF_RANGE", message, { field, bound: { [keyword]: limit }, hint });
}

function walk(root: JsonSchema, schema: JsonSchema, value: unknown, path: string): unknown {
  if (schema === true || schema === false || !isObj(schema)) return value;
  const s = resolveRef(root, schema);
  const types = typesOf(s);
  const unit = typeof s["x-bhms-unit"] === "string" ? (s["x-bhms-unit"] as string) : undefined;

  // quantity objects are unwrapped before the type check (BHMS-DEV-043)
  if (types && isNumericType(types) && unit !== undefined && isObj(value) && "value" in value && "unit" in value) {
    const extra = Object.keys(value).filter((k) => k !== "value" && k !== "unit");
    if (extra.length > 0) throw new BhmsError("INVALID_ARGUMENT", `${path}: a quantity object has only value and unit, not ${extra.join(", ")}`, { field: join(path, extra[0]), hint: 'send {"value": <number>, "unit": "<unit>"} or a bare number' });
    if (value.unit !== unit) {
      throw new BhmsError("UNIT_MISMATCH", `${path}: unit ${fmt(value.unit)} is not the declared unit ${fmt(unit)}`, {
        field: path, bound: unit, hint: `send the value in ${unit}; nothing is converted silently`,
      });
    }
    value = value.value;
  }

  if (types && !typeOk(types, value)) {
    throw new BhmsError("INVALID_ARGUMENT", `${path}: expected ${types.join(" or ")}, got ${kindOf(value)}`, {
      field: path, bound: types.length === 1 ? types[0] : types, hint: `send a value of type ${types.join(" or ")}${unit ? ` in ${unit}` : ""}`,
    });
  }

  if (typeof value === "number") {
    const range = (kw: "minimum" | "maximum" | "exclusiveMinimum" | "exclusiveMaximum", bad: boolean, what: string): void => {
      const lim = s[kw];
      if (typeof lim === "number" && bad) {
        throw outOfRange(path, kw, lim, `${path}: ${value}${unit ? " " + unit : ""} is ${what} ${lim}${unit ? " " + unit : ""}`, `send a value ${kw.includes("inimum") ? "of at least" : "of at most"} ${lim}${unit ? " " + unit : ""}`);
      }
    };
    range("minimum", typeof s.minimum === "number" && value < s.minimum, "below the minimum");
    range("maximum", typeof s.maximum === "number" && value > s.maximum, "above the maximum");
    range("exclusiveMinimum", typeof s.exclusiveMinimum === "number" && value <= s.exclusiveMinimum, "not above the exclusive minimum");
    range("exclusiveMaximum", typeof s.exclusiveMaximum === "number" && value >= s.exclusiveMaximum, "not below the exclusive maximum");
  }
  if (typeof value === "string") {
    if (typeof s.minLength === "number" && [...value].length < s.minLength) throw outOfRange(path, "minLength", s.minLength, `${path}: shorter than ${s.minLength} characters`, `send at least ${s.minLength} characters`);
    if (typeof s.maxLength === "number" && [...value].length > s.maxLength) throw outOfRange(path, "maxLength", s.maxLength, `${path}: longer than ${s.maxLength} characters`, `send at most ${s.maxLength} characters`);
  }
  if (Array.isArray(s.enum) && !s.enum.some((e) => JSON.stringify(e) === JSON.stringify(value))) {
    throw outOfRange(path, "enum", s.enum, `${path}: ${fmt(value)} is not one of ${JSON.stringify(s.enum)}`, `send one of ${JSON.stringify(s.enum)}`);
  }

  if (Array.isArray(value)) {
    if (typeof s.minItems === "number" && value.length < s.minItems) throw outOfRange(path, "minItems", s.minItems, `${path}: fewer than ${s.minItems} items`, `send at least ${s.minItems} items`);
    if (typeof s.maxItems === "number" && value.length > s.maxItems) throw outOfRange(path, "maxItems", s.maxItems, `${path}: more than ${s.maxItems} items`, `send at most ${s.maxItems} items`);
    if (s.items !== undefined && !Array.isArray(s.items)) return value.map((item, i) => walk(root, s.items as JsonSchema, item, join(path, i)));
    return value;
  }

  if (isObj(value)) {
    const props = isObj(s.properties) ? (s.properties as Record<string, JsonSchema>) : {};
    const out: Obj = {};
    for (const [k, v] of Object.entries(value)) {
      if (k in props) out[k] = walk(root, props[k], v, join(path, k));
      else if (s.additionalProperties === false) {
        throw new BhmsError("INVALID_ARGUMENT", `${join(path, k)}: unknown member`, { field: join(path, k), bound: Object.keys(props), hint: `the allowed members are ${Object.keys(props).join(", ") || "(none)"}` });
      } else out[k] = isObj(s.additionalProperties) ? walk(root, s.additionalProperties as JsonSchema, v, join(path, k)) : v;
    }
    for (const [k, sub] of Object.entries(props)) {
      if (!(k in out) && isObj(sub) && "default" in sub) out[k] = structuredClone(sub.default);
    }
    for (const r of Array.isArray(s.required) ? (s.required as string[]) : []) {
      if (!(r in out)) throw new BhmsError("INVALID_ARGUMENT", `${join(path, r)}: required member is missing`, { field: join(path, r), hint: `add ${r}` });
    }
    return out;
  }
  return value;
}

/** Equal for two values as admission sees them (used to decide whether `admittedArguments` differs). */
function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export interface Admitted {
  /** What the handler receives. */
  admitted: Obj;
  /** Whether it differs from the arguments as sent (then `admittedArguments` is recorded). */
  differs: boolean;
}

/** Admit `args` against an action `input` schema (see the module docs). */
export function admitArguments(input: JsonSchema, args: Obj, rootPath = "arguments", bounds?: Readonly<Record<string, MemberBound>>): Admitted {
  const admitted = walk(input, input, args, rootPath) as Obj;
  const rest = new SchemaValidator(input).collect(admitted);
  if (rest.length > 0) {
    const issue = bestIssue(rest);
    const field = fieldPath(issue.member !== undefined ? [...issue.path, issue.member] : issue.path);
    const prefixed = field ? `${rootPath}.${field}` : rootPath;
    throw new BhmsError("INVALID_ARGUMENT", `${prefixed}: ${issue.message}`.slice(0, 500), {
      field: prefixed, hint: `fix ${prefixed} (schema keyword ${issue.keyword})`,
    });
  }
  if (bounds) checkEnvelope(input, admitted, bounds, rootPath);
  return { admitted, differs: !sameJson(admitted, args) };
}

/** A policy bound on one member (BHMS-AUTH-010); the same shape as `PolicyBound` of the authority module. */
export interface MemberBound { minimum?: number; maximum?: number; enum?: unknown[] }

/** The effective envelope of a member: the intersection of the device's schema bounds and a policy bound (BHMS-AUTH-010/011). */
export function effectiveBounds(node: Obj, policy: MemberBound): { minimum?: number; maximum?: number; enum?: unknown[]; empty?: true } {
  const out: { minimum?: number; maximum?: number; enum?: unknown[]; empty?: true } = {};
  const nums = (a: unknown, b: unknown): number[] => [a, b].filter((v): v is number => typeof v === "number");
  const lows = nums(node.minimum, policy.minimum);
  const highs = nums(node.maximum, policy.maximum);
  if (lows.length > 0) out.minimum = Math.max(...lows);
  if (highs.length > 0) out.maximum = Math.min(...highs);
  const enums = [node.enum, policy.enum].filter(Array.isArray) as unknown[][];
  if (enums.length > 0) {
    const allowed = enums.length === 1 ? enums[0] : enums[0].filter((v) => enums[1].some((w) => JSON.stringify(v) === JSON.stringify(w)));
    out.enum = allowed;
    if (allowed.length === 0) out.empty = true;
  }
  if (out.minimum !== undefined && out.maximum !== undefined && out.minimum > out.maximum) out.empty = true;
  return out;
}

/** The first member of `bounds` for which the policy leaves no allowed value at all (BHMS-AUTH-011), or `undefined`. */
export function emptyEnvelopeMember(input: JsonSchema, bounds: Readonly<Record<string, MemberBound>>): string | undefined {
  const props = isObj(input) && isObj(input.properties) ? (input.properties as Record<string, unknown>) : {};
  for (const [member, bound] of Object.entries(bounds)) {
    const node = props[member];
    if (effectiveBounds(isObj(node) ? node : {}, bound).empty) return member;
  }
  return undefined;
}

/**
 * Refuse an admitted value outside the effective envelope of the device's bounds and the principal's policy `bounds`:
 * `OUT_OF_RANGE` whose `bound` is the effective bound (BHMS-AUTH-010). Called after schema admission, for top-level members.
 */
export function checkEnvelope(input: JsonSchema, admitted: Obj, bounds: Readonly<Record<string, MemberBound>>, rootPath = "arguments"): void {
  const props = isObj(input) && isObj(input.properties) ? (input.properties as Record<string, unknown>) : {};
  for (const [member, limits] of Object.entries(bounds)) {
    if (!(member in admitted)) continue;
    const value = admitted[member];
    const node = isObj(props[member]) ? (props[member] as Obj) : {};
    const unit = typeof node["x-bhms-unit"] === "string" && node["x-bhms-unit"] !== "1" ? ` ${node["x-bhms-unit"]}` : "";
    const path = `${rootPath}.${member}`;
    const effective = effectiveBounds(node, limits);
    if (typeof value === "number") {
      if (effective.minimum !== undefined && value < effective.minimum) {
        throw outOfRange(path, "minimum", effective.minimum, `${path} ${value}${unit} is below the minimum ${effective.minimum}${unit}`, `send ${member} of at least ${effective.minimum}${unit} (your policy narrows this action)`);
      }
      if (effective.maximum !== undefined && value > effective.maximum) {
        throw outOfRange(path, "maximum", effective.maximum, `${path} ${value}${unit} is above the maximum ${effective.maximum}${unit}`, `send ${member} of at most ${effective.maximum}${unit} (your policy narrows this action)`);
      }
    }
    if (effective.enum !== undefined && !effective.enum.some((e) => JSON.stringify(e) === JSON.stringify(value))) {
      throw outOfRange(path, "enum", effective.enum, `${path} ${fmt(value)} is not allowed for you`, `send one of ${effective.enum.map(fmt).join(", ")}`);
    }
  }
}
