import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { PACKAGE_ROOT, PYTHON_SRC } from "./paths.js";
import { join } from "node:path";

/** Whether `python3` can import the Python reference SDK (interop tests skip with a message when it cannot). */
export function pythonAvailable(): boolean {
  if (!existsSync(PYTHON_SRC)) return false;
  const r = spawnSync("python3", ["-c", "import bhms.testing.conformance_device"], { env: pythonEnv(), stdio: "ignore" });
  return r.status === 0;
}

/**
 * What interop tests pass as their `skip` option. Python being unavailable is a FAILURE (the file throws at load), unless
 * the environment explicitly opts out with BHMS_SKIP_PYTHON_INTEROP=1.
 */
export function pythonSkip(): false | string {
  if (pythonAvailable()) return false;
  if (process.env.BHMS_SKIP_PYTHON_INTEROP === "1") return "python interop skipped: BHMS_SKIP_PYTHON_INTEROP=1";
  throw new Error("python3 with the bhms reference SDK (sdk/python/src) is required for the interop tests; set BHMS_SKIP_PYTHON_INTEROP=1 to opt out explicitly");
}

export function pythonEnv(): NodeJS.ProcessEnv {
  return { ...process.env, PYTHONPATH: PYTHON_SRC + (process.env.PYTHONPATH ? `:${process.env.PYTHONPATH}` : "") };
}

/** `stdio:` target launching the Python conformance device. */
export function pythonDeviceTarget(extra = "--memory"): string {
  return `stdio:python3 -m bhms.testing.conformance_device ${extra}`.trim();
}

/** Path of the compiled TypeScript conformance device (run with `node`). */
export function tsDevicePath(): string {
  return join(PACKAGE_ROOT, "dist/src/testing/conformanceDevice.js");
}

export const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));
