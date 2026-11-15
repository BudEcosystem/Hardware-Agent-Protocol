/**
 * The protocol version this SDK implements.
 *
 * The shared schema (and so `PROTOCOL_VERSION` in `generated/types.ts`) is BHMS v0.2, `2026-11-15`. This SDK still
 * implements v0.1 (`2026-11-13`) until the v0.2 port (Task 15b): it is the only version its server serves, its programs
 * name and its client speaks first. A v0.2 server that also serves 2026-11-13 answers it with v0.1 behaviour
 * (BHMS-LIF-026), so the two interoperate.
 */
export const SDK_PROTOCOL_VERSION = "2026-11-13";
