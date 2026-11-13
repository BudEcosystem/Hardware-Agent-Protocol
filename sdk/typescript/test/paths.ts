import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

/** The package root (sdk/typescript) whether tests run from dist/test or test. */
export const PACKAGE_ROOT = resolve(here, here.includes("dist") ? "../.." : "..");
export const REPO_ROOT = resolve(PACKAGE_ROOT, "../..");
export const EXAMPLES_DIR = resolve(REPO_ROOT, "spec/bhms/examples");
export const SCHEMA_FILE = resolve(REPO_ROOT, "spec/bhms/schema/bhms.schema.json");
export const PYTHON_SRC = resolve(REPO_ROOT, "sdk/python/src");
