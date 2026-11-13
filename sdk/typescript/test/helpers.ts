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
