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
import type { Peer } from "../jsonrpc/session.js";

function globToRegex(glob: string): RegExp {
  return new RegExp("^" + glob.split("*").map((p) => p.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*") + "$", "s");
}

export class Principal {
  readonly scopes: readonly string[];
  readonly id: string;
  constructor(id: string, scopes: readonly string[]) {
    this.id = id;
    this.scopes = [...new Set(scopes)];
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

  wire(): { id: string; scopes: string[] } { return { id: this.id, scopes: [...this.scopes] }; }
}

export type Policy = (peer: Peer) => Principal;

/** The default policy: the transport's scopes, or `read` only. */
export const defaultPolicy: Policy = (peer) => new Principal(peer.principal, peer.scopes ?? ["read"]);
