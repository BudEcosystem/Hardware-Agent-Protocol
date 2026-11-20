/**
 * Principals, scopes and policy (spec/bhms/07-leases-and-authority.md §7.4).
 *
 * A principal is established only by the transport (BHMS-AUTH-001): {@link Policy.principalFor} maps the connection's
 * {@link Peer} to a {@link Principal}. The default policy trusts the scopes the transport attached to the peer (the
 * stdio parent and same-user Unix peers are `admin`; a WebSocket client that presented the right bearer token is
 * `admin`) and gives a peer without scopes `read` only. Pass your own `policy` function to narrow or widen that, e.g.
 * to grant a token `["read", "invoke:*\/*", "lease"]`.
 *
 * Scope patterns: `<deviceGlob>/<actionGlob>` split at the LAST `/`, or `cap:<capabilityGlob>`; `*` matches any
 * sequence. An action with `effect: "hazardous"` is never granted by a pattern whose action part contains `*` or by a
 * `cap:` pattern (BHMS-AUTH-003); only `admin` or a literal action name grants it.
 *
 * Thread-safety: principals are immutable snapshots.
 */
import { createHash, timingSafeEqual } from "node:crypto";
import type { Budget } from "../generated/types.js";
import { checkedBudgets } from "./budgets.js";
import { BhmsError } from "../errors.js";
import type { Peer } from "../jsonrpc/session.js";
import type { JsonSchema } from "../schema.js";

function globToRegex(glob: string): RegExp {
  return new RegExp("^" + glob.split("*").map((p) => p.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*") + "$", "s");
}

/** A policy bound on one top-level member of an action input (BHMS-AUTH-010): it can only narrow the device's own bounds. */
export interface PolicyBound { minimum?: number; maximum?: number; enum?: unknown[] }
/** `{"<deviceId>/<action>": {"<member>": bound}}` */
export type PolicyBounds = Readonly<Record<string, Readonly<Record<string, PolicyBound>>>>;

export class Principal {
  readonly scopes: readonly string[];
  readonly id: string;
  readonly bounds: PolicyBounds;
  /** A gateway may use the `g-` idempotency-key prefix, which is reserved for gateways (BHMS-OPS-037). */
  readonly gateway: boolean;
  readonly budgets: readonly Budget[];
  constructor(id: string, scopes: readonly string[], bounds: PolicyBounds = {}, gateway = false, budgets: readonly Budget[] = []) {
    this.gateway = gateway;
    this.budgets = checkedBudgets(budgets);
    this.id = id;
    this.scopes = [...new Set(scopes)];
    this.bounds = bounds;
  }

  /** The policy bounds of this principal for `<deviceId>/<action>`, if any. */
  boundsFor(deviceId: string, action: string): Readonly<Record<string, PolicyBound>> | undefined {
    return this.bounds[`${deviceId}/${action}`];
  }

  /** A digest-scoped grant authorizes only a run of that exact program. */
  canRunProgram(digest: string): boolean { return this.has("programs:run") || this.programGrant(digest); }
  programGrant(digest: string): boolean { return this.scopes.includes(`programs:run:${digest}`); }
  withScopes(scopes: readonly string[]): Principal {
    return new Principal(this.id, [...this.scopes, ...scopes], this.bounds, this.gateway, this.budgets);
  }

  get admin(): boolean { return this.scopes.includes("admin"); }
  has(scope: string): boolean { return this.admin || this.scopes.includes(scope); }
  get canRead(): boolean { return this.has("read"); }
  /** May see other principals' operations (`operations:read`, BHMS-OPS-062). */
  get operationsAll(): boolean { return this.has("operations:read"); }

  /** Whether `invoke:` scopes grant `action` on `deviceId` (`effect` decides the hazardous rule, BHMS-AUTH-003). */
  canInvoke(deviceId: string, action: string, capabilities: readonly string[], effect = "reversible"): boolean {
    if (this.admin) return true;
    for (const scope of this.scopes) {
      if (!scope.startsWith("invoke:")) continue;
      const pattern = scope.slice("invoke:".length);
      if (pattern.startsWith("cap:")) {
        if (effect === "hazardous") continue;
        const re = globToRegex(pattern.slice(4));
        if (capabilities.some((c) => re.test(c))) return true;
        continue;
      }
      const slash = pattern.lastIndexOf("/");
      if (slash < 0) continue;
      const deviceGlob = pattern.slice(0, slash);
      const actionGlob = pattern.slice(slash + 1);
      if (effect === "hazardous" && actionGlob.includes("*")) continue;
      if (globToRegex(deviceGlob).test(deviceId) && globToRegex(actionGlob).test(action)) return true;
    }
    return false;
  }

  /** Whether `stop` (all devices) or `stop:<glob>` covers `deviceId`. */
  canStop(deviceId: string): boolean {
    if (this.has("stop")) return true;
    return this.scopes.some((s) => s.startsWith("stop:") && globToRegex(s.slice(5)).test(deviceId));
  }

  /** Whether the principal holds any stop scope at all. */
  get hasAnyStop(): boolean { return this.has("stop") || this.scopes.some((s) => s.startsWith("stop:")); }

  wire(version?: string): { id: string; scopes: string[] } {
    return { id: this.id, scopes: this.scopes.filter((scope) => version !== "2026-11-13" || !scope.startsWith("programs:run:")) };
  }
}

export type Policy = (peer: Peer) => Principal;

/** The default policy: the transport's scopes, or `read` only. */
export const defaultPolicy: Policy = (peer) => new Principal(peer.principal, peer.scopes ?? ["read"]);

/** The policy of a server that is an upstream of a gateway (`--gateway`): every peer is a gateway principal (may use `g-` keys). */
export const gatewayPolicy: Policy = (peer) => new Principal(peer.principal, peer.scopes ?? ["read"], {}, true);

/** The stored form of a bearer token (BHMS-SEC-002): `"sha256:" + hex(sha256(token))`. */
export function tokenDigest(token: string): string {
  return "sha256:" + createHash("sha256").update(token).digest("hex");
}

/** One principal of a policy document (the `GatewayPolicy` of the schema). */
export interface PolicyPrincipalDocument { budgets?: Budget[]; tokens?: string[]; uids?: number[]; scopes: string[]; bounds?: Record<string, Record<string, PolicyBound>> }
/** A policy document: `{"principals": {name: {tokens?, uids?, scopes, bounds?}}}` (`GatewayPolicy` of the schema). */
export interface PolicyDocument { principals: Record<string, PolicyPrincipalDocument> }

const DIGEST = /^sha256:[0-9a-f]{64}$/;

function invalidPolicy(message: string): RangeError {
  return new RangeError(`invalid policy document: ${message}`);
}

/**
 * Named principals keyed by bearer-token digests, from a {@link PolicyDocument}. Immutable after construction.
 *
 * - WebSocket peers: the principal holding the presented token (constant-time comparison of digests, BHMS-SEC-002).
 * - Every other peer keeps the transport's own scopes (stdio parent and Unix peers are `admin`). `uids` are accepted in the
 *   document for compatibility but cannot match: Node exposes no `SO_PEERCRED`, so a Unix peer's uid is unknown.
 *
 * {@link authorityCapability} is `capabilities.authority`: `{}` when the policy defines several principals or any principal
 * that is not an administrator, `undefined` for a single-principal server. It carries no member, so a caller learns
 * nothing about how many principals exist.
 */
export class PolicyTable {
  private readonly entries: Array<{ principal: Principal; digests: Buffer[] }>;

  constructor(doc: PolicyDocument) {
    if (typeof doc !== "object" || doc === null || typeof doc.principals !== "object" || doc.principals === null || Array.isArray(doc.principals)) {
      throw invalidPolicy('"principals" must be an object');
    }
    this.entries = Object.keys(doc.principals).sort().map((name) => {
      const spec = doc.principals[name];
      if (typeof spec !== "object" || spec === null || !Array.isArray(spec.scopes) || !spec.scopes.every((x) => typeof x === "string")) {
        throw invalidPolicy(`principal ${JSON.stringify(name)} needs a "scopes" array of strings`);
      }
      const tokens = spec.tokens ?? [];
      if (!Array.isArray(tokens) || !tokens.every((t) => typeof t === "string" && DIGEST.test(t))) {
        throw invalidPolicy(`principal ${JSON.stringify(name)}: tokens are "sha256:<64 hex>" digests, never the token itself (BHMS-SEC-002)`);
      }
      const uids = spec.uids ?? [];
      if (!Array.isArray(uids) || !uids.every((u) => Number.isInteger(u) && u >= 0)) throw invalidPolicy(`principal ${JSON.stringify(name)}: uids are non-negative integers`);
      for (const [key, members] of Object.entries(spec.bounds ?? {})) {
        if (typeof members !== "object" || members === null || key.lastIndexOf("/") < 1) throw invalidPolicy(`principal ${JSON.stringify(name)}: bounds key ${JSON.stringify(key)} is "<deviceId>/<action>"`);
      }
      return { principal: new Principal(name, spec.scopes, structuredClone(spec.bounds ?? {}), false, spec.budgets ?? []), digests: tokens.map((t) => Buffer.from(t)) };
    });
  }

  get principals(): readonly Principal[] { return this.entries.map((e) => e.principal); }

  authorityCapability(): Record<string, never> | undefined {
    const ps = this.principals;
    return ps.length > 1 || ps.some((p) => !p.scopes.includes("admin")) ? {} : undefined;
  }

  /** The principal holding `token`, or `undefined`. Compares digests of every stored token (no early exit). */
  byToken(token: string | undefined): Principal | undefined {
    if (!token) return undefined;
    const presented = Buffer.from(tokenDigest(token));
    let found: Principal | undefined;
    for (const e of this.entries) for (const stored of e.digests) if (stored.length === presented.length && timingSafeEqual(stored, presented)) found = e.principal;
    return found;
  }

  /** The principal of `peer` under this table (see the class docs). */
  principalFor(peer: Peer): Principal {
    if (peer.kind === "ws") {
      const held = this.byToken(peer.token);
      if (held) return held;
      return new Principal(peer.principal, peer.scopes ?? ["read"]);
    }
    return defaultPolicy(peer);
  }

  /**
   * Reject bounds that would widen a device bound (BHMS-SEC-011) or name an unknown action or argument; `describe(deviceId)`
   * returns the device's description or `undefined`. Throws {@link RangeError}.
   */
  checkBounds(describe: (deviceId: string) => { actions: Record<string, { input: JsonSchema }> } | undefined): void {
    for (const principal of this.principals) {
      for (const [key, members] of Object.entries(principal.bounds)) {
        const slash = key.lastIndexOf("/");
        const action = describe(key.slice(0, slash))?.actions[key.slice(slash + 1)];
        if (!action) throw new RangeError(`policy bounds for ${JSON.stringify(principal.id)} name unknown action ${JSON.stringify(key)}`);
        const properties = ((action.input as { properties?: Record<string, Record<string, unknown>> }).properties) ?? {};
        for (const [member, bound] of Object.entries(members)) {
          const node = properties[member];
          if (!node) throw new RangeError(`policy bounds for ${JSON.stringify(principal.id)}: ${key} has no argument ${JSON.stringify(member)}`);
          if (typeof bound.minimum === "number" && typeof node.minimum === "number" && bound.minimum < node.minimum) {
            throw new RangeError(`policy bound ${key}.${member}.minimum=${bound.minimum} widens the device bound ${node.minimum} (BHMS-SEC-011)`);
          }
          if (typeof bound.maximum === "number" && typeof node.maximum === "number" && bound.maximum > node.maximum) {
            throw new RangeError(`policy bound ${key}.${member}.maximum=${bound.maximum} widens the device bound ${node.maximum} (BHMS-SEC-011)`);
          }
          if (Array.isArray(bound.enum) && Array.isArray(node.enum)) {
            const allowed = new Set((node.enum as unknown[]).map((v) => JSON.stringify(v)));
            if (!bound.enum.every((v) => allowed.has(JSON.stringify(v)))) throw new RangeError(`policy bound ${key}.${member}.enum widens the device enum (BHMS-SEC-011)`);
          }
        }
      }
    }
  }
}

/** An `UNAUTHORIZED` for a policy that leaves no allowed value for an argument (BHMS-AUTH-011). */
export function emptyEnvelope(deviceId: string, action: string, member: string, field: string): BhmsError {
  return new BhmsError("UNAUTHORIZED", `your policy leaves no allowed value for ${member}`, { field, hint: `${deviceId}/${action} is unavailable to you (BHMS-AUTH-011)` });
}
