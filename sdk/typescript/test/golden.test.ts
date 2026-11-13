// Golden vectors: the spec's example corpus (spec/bhms/examples) must validate (valid) or be rejected for the stated
// reason (invalid-*), and the generated types / error table / canonical digests must match the schema.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { canonicalString, descriptionDigest, digest } from "../src/canonical.js";
import { CODES } from "../src/errors.js";
import { defValidator, loadSchema, schemaPath } from "../src/schema.js";
import { EXAMPLES_DIR, PACKAGE_ROOT, SCHEMA_FILE } from "./paths.js";

interface Example {
  $comment: string;
  against: string;
  expect?: { path: string; keyword: string; message?: string };
  message: unknown;
}

const files = readdirSync(EXAMPLES_DIR).filter((f) => f.endsWith(".json")).sort();
const pointer = (path: (string | number)[]): string => path.map((p) => "/" + String(p).replace(/~/g, "~0").replace(/\//g, "~1")).join("");

for (const file of files) {
  const example = JSON.parse(readFileSync(join(EXAMPLES_DIR, file), "utf8")) as Example;
  const def = example.against.replace("#/$defs/", "");
  if (!file.startsWith("invalid-")) {
    test(`valid example ${file} validates and round-trips canonically`, () => {
      const issues = defValidator(def).collect(example.message);
      assert.deepEqual(issues, []);
      const reparsed = JSON.parse(JSON.stringify(example.message));
      assert.equal(canonicalString(reparsed), canonicalString(example.message));
    });
  } else {
    test(`invalid example ${file} is rejected for the stated reason`, () => {
      const issues = defValidator(def).collect(example.message);
      assert.ok(issues.length > 0, `${file} must fail ${def}`);
      const want = example.expect!;
      const hit = issues.some((i) => pointer(i.path) === want.path && i.keyword === want.keyword);
      assert.ok(hit, `${file}: expected ${want.keyword} at "${want.path}"; got ${JSON.stringify(issues.map((i) => [pointer(i.path), i.keyword]))}`);
    });
  }
}

test("description digests in the examples are real (BHMS-DEV-021)", () => {
  const ex = JSON.parse(readFileSync(join(EXAMPLES_DIR, "devices.describe.response.json"), "utf8")) as { message: { result: { description: Record<string, unknown> } } };
  const description = ex.message.result.description;
  assert.equal(description.digest, descriptionDigest(description));
});

test("program digests in the examples are real", () => {
  const ex = JSON.parse(readFileSync(join(EXAMPLES_DIR, "programs.register.request.json"), "utf8")) as { message: { params: { program: unknown } } };
  const response = JSON.parse(readFileSync(join(EXAMPLES_DIR, "programs.register.response.json"), "utf8")) as { message: { result: { info: { digest: string } } } };
  assert.equal(response.message.result.info.digest, digest(ex.message.params.program));
});

test("canonical JSON follows RFC 8785 ordering and number formats", () => {
  assert.equal(canonicalString({ b: 1, a: [true, null, "x\u0007"], "é": 1e21, "😀": 0.000001, z: -0 }),
    '{"a":[true,null,"x\\u0007"],"b":1,"z":0,"é":1e+21,"😀":0.000001}');
  assert.equal(canonicalString({ n: 100, m: 1.5, o: 123456789012345680000 }), '{"m":1.5,"n":100,"o":123456789012345680000}');
  assert.throws(() => canonicalString({ x: NaN }), /canonical-JSON/);
});

test("the error table equals the schema's x-bhms-errors", () => {
  const table = loadSchema()["x-bhms-errors"] as Record<string, { code: number; retry: string }>;
  assert.deepEqual(Object.keys(table).sort(), Object.keys(CODES).sort());
  for (const [name, spec] of Object.entries(table)) {
    assert.equal(CODES[name as keyof typeof CODES].number, spec.code, name);
    assert.equal(CODES[name as keyof typeof CODES].retry, spec.retry, name);
  }
});

test("the packaged schema is the spec schema, byte for byte", () => {
  assert.equal(readFileSync(schemaPath(), "utf8"), readFileSync(SCHEMA_FILE, "utf8"));
});

test("requestDigest follows the §6.4 intent formula and equals the Python reference's digest of the invoke example", async () => {
  const { intentDigest } = await import("../src/server/executor.js");
  const inv = JSON.parse(readFileSync(join(EXAMPLES_DIR, "actions.invoke.request.json"), "utf8")) as { message: { params: Record<string, unknown> } };
  // `bhms.runtime.operations.intent_digest("actions/invoke", params)` over the same params. The `requestDigest` printed in
  // actions.invoke.response.json (sha256:f19b...) predates the last edit of the request example and is stale (see the report).
  assert.equal(intentDigest(inv.message.params), "sha256:648f50c4685066d212a8f56f37dc0c30c75be69491c4a77e1cc039b9805d4093");
});

test("generated types are fresh (scripts/gen-types.mjs --check)", () => {
  execFileSync(process.execPath, [join(PACKAGE_ROOT, "scripts/gen-types.mjs"), "--check"], { stdio: "pipe" });
});
