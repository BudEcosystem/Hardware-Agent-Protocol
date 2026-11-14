/**
 * A JSON Schema 2020-12 validator for the keyword subset BHMS uses, and access to the packaged BHMS schema.
 *
 * The package depends on nothing at runtime, so this validator is its own: it implements exactly the keywords that occur
 * in `spec/bhms/schema/bhms.schema.json` and in embedded device schemas (BHMS-DEV-040/041): `type`, `const`, `enum`,
 * `properties`, `required`, `additionalProperties`, `patternProperties`, `propertyNames`, `items`, `prefixItems`,
 * `min/maxItems`, `uniqueItems`, `min/maxLength`, `pattern`, `minimum`, `maximum`, `exclusiveMinimum/Maximum`,
 * `multipleOf`, `min/maxProperties`, `allOf`, `anyOf`, `oneOf`, `not`, `if/then/else` and local `$ref` (`#/...`). Other
 * keywords (`description`, `default`, `format`, `x-*`) are annotations. `multipleOf` follows BHMS-DEV-071: a float
 * quotient within 1e-9 (relative) of an integer counts as a multiple, so `50.1` is a multiple of `0.1`.
 *
 * `collect()` returns every failing keyword including those inside failed `oneOf`/`anyOf` branches (`context: true`),
 * which the example corpus's `expect` blocks refer to; `validateDef()` raises `INVALID_ARGUMENT` naming the offending
 * member in the spec's path form (`arguments.position`, `resources[2]`).
 *
 * Thread-safety: validators are immutable after construction.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { BhmsError } from "./errors.js";

export type JsonSchema = boolean | { [key: string]: unknown };

export interface Issue {
  /** Instance path segments from the validated root. */
  path: (string | number)[];
  /** The failing keyword (`required`, `type`, `additionalProperties`, `minimum`...). */
  keyword: string;
  message: string;
  /** For `required` and `additionalProperties`: the member concerned (the path is the object that holds it). */
  member?: string;
  /** True for errors found inside a failed `oneOf`/`anyOf` branch (not the combinator itself). */
  context: boolean;
  /** For the range keywords (`minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`): the declared limit. */
  limit?: number;
  /** For the range keywords: the offending value. */
  instance?: number;
}

const TOLERANCE = 1e-9;

function typeOf(v: unknown): string {
  if (v === null) return "null";
  if (Array.isArray(v)) return "array";
  if (typeof v === "number") return Number.isInteger(v) ? "integer" : "number";
  return typeof v;
}

function matchesType(v: unknown, t: string): boolean {
  const actual = typeOf(v);
  if (t === "number") return actual === "number" || actual === "integer";
  return actual === t;
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b || a === null || b === null || typeof a !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => deepEqual(x, b[i]));
  const ka = Object.keys(a as object);
  const kb = Object.keys(b as object);
  return ka.length === kb.length && ka.every((k) => k in (b as object) && deepEqual((a as never)[k], (b as never)[k]));
}

/** Whether `value` is a multiple of `divisor` with the BHMS-DEV-071 tolerance. */
export function isMultipleOf(value: number, divisor: number): boolean {
  if (Number.isInteger(value) && Number.isInteger(divisor)) return value % divisor === 0;
  const q = value / divisor;
  return Math.abs(q - Math.round(q)) <= TOLERANCE * Math.max(1, Math.abs(q));
}

const patternCache = new Map<string, RegExp>();
function regex(p: string): RegExp {
  let r = patternCache.get(p);
  if (!r) {
    r = new RegExp(p, "u");
    patternCache.set(p, r);
  }
  return r;
}

function codePoints(s: string): number {
  let n = 0;
  for (const _ of s) { void _; n++; }
  return n;
}

export class SchemaValidator {
  constructor(private readonly root: JsonSchema) {}

  /** Every failing keyword for `instance` (empty when valid). */
  collect(instance: unknown): Issue[] {
    const issues: Issue[] = [];
    this.check(this.root, instance, [], issues, false);
    return issues;
  }

  isValid(instance: unknown): boolean {
    return this.collect(instance).length === 0;
  }

  private resolve(ref: string): JsonSchema {
    if (!ref.startsWith("#")) throw new Error(`$ref ${ref} points outside the schema (BHMS-DEV-040)`);
    let node: unknown = this.root;
    for (const raw of ref.slice(1).split("/").filter((s) => s !== "")) {
      const key = decodeURIComponent(raw).replace(/~1/g, "/").replace(/~0/g, "~");
      if (typeof node !== "object" || node === null || !(key in node)) throw new Error(`unresolvable $ref ${ref}`);
      node = (node as Record<string, unknown>)[key];
    }
    return node as JsonSchema;
  }

  /** Validate against `schema`; returns whether it is valid and appends failures to `out`. */
  private check(schema: JsonSchema, v: unknown, path: (string | number)[], out: Issue[], context: boolean): boolean {
    if (schema === true) return true;
    if (schema === false) {
      out.push({ path, keyword: "false schema", message: "no value is allowed here", context });
      return false;
    }
    const before = out.length;
    const fail = (keyword: string, message: string, member?: string, range?: { limit: number; instance: number }): void => {
      out.push({ path, keyword, message, context, ...(member !== undefined ? { member } : {}), ...range });
    };
    const s = schema;

    if (typeof s.$ref === "string") this.check(this.resolve(s.$ref), v, path, out, context);

    if (s.type !== undefined) {
      const types = Array.isArray(s.type) ? (s.type as string[]) : [s.type as string];
      if (!types.some((t) => matchesType(v, t))) fail("type", `${JSON.stringify(v)} is not of type ${types.join(", ")}`);
    }
    if ("const" in s && !deepEqual(v, s.const)) fail("const", `${JSON.stringify(s.const)} was expected`);
    if (Array.isArray(s.enum) && !s.enum.some((e) => deepEqual(e, v))) {
      fail("enum", `${JSON.stringify(v)} is not one of ${JSON.stringify(s.enum)}`);
    }

    if (typeof v === "number") {
      if (typeof s.minimum === "number" && v < s.minimum) fail("minimum", `${v} is less than the minimum of ${s.minimum}`, undefined, { limit: s.minimum, instance: v });
      if (typeof s.maximum === "number" && v > s.maximum) fail("maximum", `${v} is greater than the maximum of ${s.maximum}`, undefined, { limit: s.maximum, instance: v });
      if (typeof s.exclusiveMinimum === "number" && v <= s.exclusiveMinimum) {
        fail("exclusiveMinimum", `${v} is less than or equal to the minimum of ${s.exclusiveMinimum}`, undefined, { limit: s.exclusiveMinimum, instance: v });
      }
      if (typeof s.exclusiveMaximum === "number" && v >= s.exclusiveMaximum) {
        fail("exclusiveMaximum", `${v} is greater than or equal to the maximum of ${s.exclusiveMaximum}`, undefined, { limit: s.exclusiveMaximum, instance: v });
      }
      if (typeof s.multipleOf === "number" && !isMultipleOf(v, s.multipleOf)) {
        fail("multipleOf", `${v} is not a multiple of ${s.multipleOf}`);
      }
    }

    if (typeof v === "string") {
      if (typeof s.minLength === "number" && codePoints(v) < s.minLength) fail("minLength", `${JSON.stringify(v)} is too short`);
      if (typeof s.maxLength === "number" && codePoints(v) > s.maxLength) fail("maxLength", `${JSON.stringify(v).slice(0, 60)} is too long`);
      if (typeof s.pattern === "string" && !regex(s.pattern).test(v)) {
        fail("pattern", `${JSON.stringify(v)} does not match ${JSON.stringify(s.pattern)}`);
      }
    }

    if (Array.isArray(v)) {
      if (typeof s.minItems === "number" && v.length < s.minItems) fail("minItems", `${JSON.stringify(v)} is too short`);
      if (typeof s.maxItems === "number" && v.length > s.maxItems) fail("maxItems", `${JSON.stringify(v).slice(0, 60)} is too long`);
      if (s.uniqueItems === true) {
        const seen: unknown[] = [];
        for (const item of v) {
          if (seen.some((x) => deepEqual(x, item))) {
            fail("uniqueItems", `${JSON.stringify(v)} has non-unique elements`);
            break;
          }
          seen.push(item);
        }
      }
      const prefix = Array.isArray(s.prefixItems) ? (s.prefixItems as JsonSchema[]) : [];
      prefix.forEach((sub, i) => { if (i < v.length) this.check(sub, v[i], [...path, i], out, context); });
      if (s.items !== undefined && !Array.isArray(s.items)) {
        for (let i = prefix.length; i < v.length; i++) this.check(s.items as JsonSchema, v[i], [...path, i], out, context);
      }
    }

    if (typeof v === "object" && v !== null && !Array.isArray(v)) {
      const obj = v as Record<string, unknown>;
      const keys = Object.keys(obj);
      if (Array.isArray(s.required)) {
        for (const r of s.required as string[]) if (!(r in obj)) fail("required", `${JSON.stringify(r)} is a required property`, r);
      }
      if (typeof s.minProperties === "number" && keys.length < s.minProperties) fail("minProperties", "too few properties");
      if (typeof s.maxProperties === "number" && keys.length > s.maxProperties) fail("maxProperties", "too many properties");
      const props = (s.properties ?? {}) as Record<string, JsonSchema>;
      const patterns = Object.entries((s.patternProperties ?? {}) as Record<string, JsonSchema>);
      for (const k of keys) {
        let matched = false;
        if (k in props) {
          matched = true;
          this.check(props[k], obj[k], [...path, k], out, context);
        }
        for (const [p, sub] of patterns) {
          if (regex(p).test(k)) {
            matched = true;
            this.check(sub, obj[k], [...path, k], out, context);
          }
        }
        if (!matched && s.additionalProperties !== undefined && s.additionalProperties !== true) {
          if (s.additionalProperties === false) {
            fail("additionalProperties", `additional property ${JSON.stringify(k)} is not allowed`, k);
          } else {
            this.check(s.additionalProperties as JsonSchema, obj[k], [...path, k], out, context);
          }
        }
        if (s.propertyNames !== undefined) {
          const sub: Issue[] = [];
          if (!this.check(s.propertyNames as JsonSchema, k, path, sub, context)) {
            fail("propertyNames", `${JSON.stringify(k)} is not a valid property name`, k);
            out.push(...sub.map((i) => ({ ...i, context: true })));
          }
        }
      }
    }

    if (Array.isArray(s.allOf)) for (const sub of s.allOf as JsonSchema[]) this.check(sub, v, path, out, context);
    if (Array.isArray(s.anyOf)) {
      const branches: Issue[][] = [];
      const ok = (s.anyOf as JsonSchema[]).some((sub) => {
        const b: Issue[] = [];
        branches.push(b);
        return this.check(sub, v, path, b, true);
      });
      if (!ok) {
        fail("anyOf", `${JSON.stringify(v)} is not valid under any of the given schemas`);
        for (const b of branches) out.push(...b);
      }
    }
    if (Array.isArray(s.oneOf)) {
      const branches: Issue[][] = [];
      let valid = 0;
      for (const sub of s.oneOf as JsonSchema[]) {
        const b: Issue[] = [];
        branches.push(b);
        if (this.check(sub, v, path, b, true)) valid++;
      }
      if (valid !== 1) {
        fail("oneOf", valid === 0 ? `${JSON.stringify(v)} is not valid under any of the given schemas` : `${JSON.stringify(v)} is valid under more than one of the given schemas`);
        if (valid === 0) for (const b of branches) out.push(...b);
      }
    }
    if (s.not !== undefined && this.check(s.not as JsonSchema, v, path, [], true)) fail("not", `${JSON.stringify(v)} should not be valid under the given schema`);
    if (s.if !== undefined) {
      if (this.check(s.if as JsonSchema, v, path, [], false)) {
        if (s.then !== undefined) this.check(s.then as JsonSchema, v, path, out, context);
      } else if (s.else !== undefined) {
        this.check(s.else as JsonSchema, v, path, out, context);
      }
    }
    return out.length === before;
  }
}

// ---------------------------------------------------------------------------------------------------- packaged schema

const here = dirname(fileURLToPath(import.meta.url));

/** The packaged `bhms.schema.json` (a symlink to `spec/bhms/schema/bhms.schema.json`). */
export function schemaPath(): string {
  return resolve(here, "../../schema/bhms.schema.json");
}

let loaded: { $defs: Record<string, JsonSchema> } & Record<string, unknown> | undefined;

export function loadSchema(): { $defs: Record<string, JsonSchema> } & Record<string, unknown> {
  loaded ??= JSON.parse(readFileSync(schemaPath(), "utf8"));
  return loaded!;
}

const defValidators = new Map<string, SchemaValidator>();

/** Cached validator for `$defs/<name>`; throws RangeError for an unknown definition. */
export function defValidator(name: string): SchemaValidator {
  let v = defValidators.get(name);
  if (!v) {
    const doc = loadSchema();
    if (!(name in doc.$defs)) throw new RangeError(`unknown definition ${name}`);
    v = new SchemaValidator({ $ref: `#/$defs/${name}`, $defs: doc.$defs });
    defValidators.set(name, v);
  }
  return v;
}

/** Spec path form of an instance path: `arguments.position`, `resources[2]`. */
export function fieldPath(path: readonly (string | number)[]): string {
  let out = "";
  for (const p of path) out += typeof p === "number" ? `[${p}]` : out ? `.${p}` : p;
  return out;
}

const STRUCTURAL = new Set(["oneOf", "anyOf", "allOf", "if", "not"]);

/** Pick the most informative issue (a leaf keyword error beats a combinator error; deeper beats shallower). */
export function bestIssue(issues: readonly Issue[]): Issue {
  const leaves = issues.filter((i) => !STRUCTURAL.has(i.keyword));
  const pool = leaves.length > 0 ? leaves : issues;
  return pool.reduce((best, i) => (i.path.length > best.path.length ? i : best), pool[0]);
}

/** Validate `value` against `$defs/<name>`; throws INVALID_ARGUMENT naming the offending member. */
export function validateDef(name: string, value: unknown): void {
  const issues = defValidator(name).collect(value);
  if (issues.length === 0) return;
  const issue = bestIssue(issues);
  const field = fieldPath(issue.member !== undefined ? [...issue.path, issue.member] : issue.path);
  throw new BhmsError("INVALID_ARGUMENT", `${name}${field ? "." + field : ""}: ${issue.message}`.slice(0, 500), {
    field: field.slice(0, 512),
    hint: `fix ${field || "the value"} (schema keyword ${issue.keyword}); see spec/bhms/schema/bhms.schema.json $defs/${name}`,
  });
}

/** BHMS-SEC-021: the deepest subschema is at most this many subschema steps below the root (the root is depth 0). */
export const MAX_SCHEMA_DEPTH = 32;
/** BHMS-SEC-021: at most this many schemas, the root and boolean schemas included. */
export const MAX_SUBSCHEMAS = 10_000;
const SUBSCHEMA_SINGLE = ["items", "not", "if", "then", "else", "additionalProperties", "contains", "propertyNames", "unevaluatedItems", "unevaluatedProperties", "contentSchema"];
const SUBSCHEMA_LISTS = ["allOf", "anyOf", "oneOf", "prefixItems"];
const SUBSCHEMA_MAPS = ["properties", "patternProperties", "$defs", "definitions", "dependentSchemas"];
const REFERENCES = ["$ref", "$dynamicRef"];

const isPlainObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/** Python's `str.isprintable` for one code point (Unicode "Other" and "Separator" categories except the space are not printable). */
const NOT_PRINTABLE = /^[\p{C}\p{Z}]$/u;

/** Python `repr` of a short string, so the wording matches the reference implementation byte for byte (including `\xNN` / `\uNNNN` escapes). */
function pyRepr(text: string): string {
  const quote = text.includes("'") && !text.includes('"') ? '"' : "'";
  let out = quote;
  for (const ch of text) {
    const cp = ch.codePointAt(0) as number;
    if (ch === quote || ch === "\\") out += "\\" + ch;
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (ch !== " " && NOT_PRINTABLE.test(ch)) {
      out += cp < 0x100 ? "\\x" + cp.toString(16).padStart(2, "0") : cp < 0x10000 ? "\\u" + cp.toString(16).padStart(4, "0") : "\\U" + cp.toString(16).padStart(8, "0");
    } else out += ch;
  }
  return out + quote;
}

/** An embedded schema exceeds the BHMS-SEC-021 bounds or refers outside itself (BHMS-DEV-040); the message names the path. */
export class SchemaBoundsError extends RangeError {
  constructor(message: string) {
    super(message);
    this.name = "SchemaBoundsError";
  }
}

/** A path for a message: property names come from the (possibly hostile) schema, so it is cut like the reference does. */
function shortPath(path: string): string {
  if (path.length <= 160) return path;
  const points = [...path];
  return points.length <= 160 ? path : `${points.slice(0, 120).join("")}...${points.slice(-37).join("")}`;
}

function* childrenOf(node: Record<string, unknown>, path: string): Generator<[string, unknown]> {
  for (const key of SUBSCHEMA_SINGLE) if (key in node) yield [`${path}.${key}`, node[key]];
  for (const key of SUBSCHEMA_LISTS) {
    const members = node[key];
    if (Array.isArray(members)) for (const [index, child] of members.entries()) yield [`${path}.${key}[${index}]`, child];
  }
  for (const key of SUBSCHEMA_MAPS) {
    const members = node[key];
    if (isPlainObject(members)) for (const [name, child] of Object.entries(members)) yield [`${path}.${key}.${name}`, child];
  }
}

/**
 * THE schema walker of this SDK (the same algorithm as `bhms.protocol.schema.iter_subschemas`): yields `[path, subschema]` for
 * the root of an embedded schema and every subschema in document order (pre-order), enforcing BHMS-SEC-021 and BHMS-DEV-040 on
 * the way (spec 13.3). The device server's description checks and {@link schemaBoundsProblem} both use it, so no second copy
 * of the rules can disagree.
 *
 * - depth: the root is depth 0, every step through a subschema keyword adds one; deeper than `maxDepth` (32) throws;
 * - count: the root and every subschema position count (`true`/`false` are schemas); more than `maxNodes` (10 000) throws;
 * - references: a `$ref`/`$dynamicRef` that is not a fragment of the schema itself (`#...`) throws; nothing is ever fetched.
 *
 * Keywords: the 2020-12 applicator, unevaluated and content vocabularies plus `definitions`. A value that is not a schema
 * (a number where a schema belongs) is yielded as it is and has no children. Iterative, and children are counted before they
 * are queued, so time and memory are bounded by the limits whatever the input. Members are visited in `Object.entries` order
 * (integer-like member names first, as `JSON.parse` itself orders them).
 *
 * Thread-safety: pure. Example: `for (const [path, node] of iterSubschemas(action.input, "actions.move.input")) { ... }`
 */
export function* iterSubschemas(schema: unknown, where = "schema", limits: { maxDepth?: number; maxNodes?: number } = {}): Generator<[string, unknown]> {
  const maxDepth = limits.maxDepth ?? MAX_SCHEMA_DEPTH;
  const maxNodes = limits.maxNodes ?? MAX_SUBSCHEMAS;
  let count = 1;
  const stack: Array<[string, unknown, number]> = [[where, schema, 0]];
  for (let top = stack.pop(); top !== undefined; top = stack.pop()) {
    const [path, node, depth] = top;
    if (depth > maxDepth) throw new SchemaBoundsError(`${shortPath(path)}: schema nested deeper than ${maxDepth} (BHMS-SEC-021)`);
    if (isPlainObject(node)) {
      for (const keyword of REFERENCES) {
        const ref = node[keyword];
        if (typeof ref === "string" && !ref.startsWith("#")) {
          throw new SchemaBoundsError(`${shortPath(path)}: ${keyword} ${pyRepr([...ref].slice(0, 80).join(""))} points outside the schema; schemas are never fetched (BHMS-DEV-040)`);
        }
      }
    }
    yield [path, node];
    if (!isPlainObject(node)) continue;
    const children: Array<[string, unknown, number]> = [];
    for (const [childPath, child] of childrenOf(node, path)) {
      if (++count > maxNodes) throw new SchemaBoundsError(`${where}: more than ${maxNodes} subschemas (BHMS-SEC-021)`);
      children.push([childPath, child, depth + 1]);
    }
    for (let k = children.length - 1; k >= 0; k--) stack.push(children[k]);
  }
}

/** Why an embedded schema must not be validated or served (the {@link iterSubschemas} refusal), or `undefined`. Same wording as `schema_bounds_problem`. */
export function schemaBoundsProblem(schema: unknown, where = "schema", limits: { maxDepth?: number; maxNodes?: number } = {}): string | undefined {
  try {
    for (const _ of iterSubschemas(schema, where, limits)) void _;
  } catch (e) {
    if (e instanceof SchemaBoundsError) return e.message;
    throw e;
  }
  return undefined;
}
