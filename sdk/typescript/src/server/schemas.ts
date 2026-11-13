/**
 * Small builders for the JSON Schemas of action inputs/outputs and property values, so a device declaration stays short
 * and always satisfies BHMS-DEV-041 (every number carries `x-bhms-unit`).
 *
 * ```ts
 * input: { position: range(0, 200, "mm", { step: 0.1 }), speed: range(1, 50, "mm/s", { default: 10 }) }
 * output: { position: "mm" }                       // shorthand: a member name and its unit
 * ```
 *
 * Members with a `default` are optional in an input; others are required unless listed in `optional`.
 */
import type { JsonSchema } from "../schema.js";

export type Schema = { [key: string]: unknown };

export interface NumberOptions {
  minimum?: number;
  maximum?: number;
  /** `multipleOf` (BHMS-DEV-071 tolerance applies). */
  step?: number;
  default?: number;
  description?: string;
}

/** A number in `unit` (UCUM; `"1"` for counts, `"%"` for percent). */
export function num(unit: string, o: NumberOptions = {}): Schema {
  return numeric("number", unit, o);
}

/** An integer in `unit`. */
export function int(unit: string, o: NumberOptions = {}): Schema {
  return numeric("integer", unit, o);
}

function numeric(type: "number" | "integer", unit: string, o: NumberOptions): Schema {
  const s: Schema = { type, "x-bhms-unit": unit };
  if (o.minimum !== undefined) s.minimum = o.minimum;
  if (o.maximum !== undefined) s.maximum = o.maximum;
  if (o.step !== undefined) s.multipleOf = o.step;
  if (o.default !== undefined) s.default = o.default;
  if (o.description !== undefined) s.description = o.description;
  return s;
}

/** A bounded number or integer: `range(0, 200, "mm", { step: 0.1 })`, `range(1, 100, "1", { integer: true })`. */
export function range(minimum: number, maximum: number, unit: string, o: NumberOptions & { integer?: boolean } = {}): Schema {
  const { integer, ...rest } = o;
  return numeric(integer ? "integer" : "number", unit, { ...rest, minimum, maximum });
}

export function str(o: { enum?: string[]; pattern?: string; maxLength?: number; default?: string; description?: string } = {}): Schema {
  return { type: "string", ...o };
}

export function bool(o: { default?: boolean; description?: string } = {}): Schema {
  return { type: "boolean", ...o };
}

export function arrayOf(items: Schema, o: { minItems?: number; maxItems?: number } = {}): Schema {
  return { type: "array", items, ...o };
}

/** Closed object schema (BHMS-DEV-040) from a member map; members with a `default` and those in `optional` are not required. */
export function objectOf(members: Record<string, Schema | string>, optional: readonly string[] = []): Schema {
  const properties: Record<string, JsonSchema> = {};
  const required: string[] = [];
  for (const [k, v] of Object.entries(members)) {
    const schema = typeof v === "string" ? num(v) : v;
    properties[k] = schema;
    if (!("default" in schema) && !optional.includes(k)) required.push(k);
  }
  const out: Schema = { type: "object", properties, additionalProperties: false };
  if (required.length > 0) out.required = required;
  return out;
}

/** A full object schema passes through; a member map becomes a closed object schema. */
export function asObjectSchema(spec: Schema | Record<string, Schema | string> | undefined, optional: readonly string[] = []): Schema {
  if (spec === undefined) return { type: "object", properties: {}, additionalProperties: false };
  if (spec.type === "object") return spec as Schema;
  return objectOf(spec as Record<string, Schema | string>, optional);
}
