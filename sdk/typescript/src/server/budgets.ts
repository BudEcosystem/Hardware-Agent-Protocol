/** Grant budgets (AUTH-030..035). The store counts committed reservations, including pruned operations. */
import { BhmsError } from "../errors.js";
import { validateDef, type JsonSchema } from "../schema.js";
import type { Budget, BudgetState } from "../generated/types.js";
import { BUDGET_UNITS } from "../generated/budgetUnits.js";
import type { Principal } from "./authority.js";
import type { BudgetCharge, Store } from "./store.js";

function tokens(pointer: string): string[] {
  if (!pointer.startsWith("/") || pointer === "/" || /~(?![01])/.test(pointer)) throw new RangeError("budget quantity must be a JSON Pointer to a member");
  return pointer.slice(1).split("/").map((s) => s.replaceAll("~1", "/").replaceAll("~0", "~"));
}
function convert(value: number, from: string, to: string): number {
  const a = BUDGET_UNITS[from], b = BUDGET_UNITS[to];
  if (!Object.hasOwn(BUDGET_UNITS, from) || !Object.hasOwn(BUDGET_UNITS, to) || a[0] !== b[0]) throw new RangeError("incompatible budget units");
  const result = from === to ? value : (value * a[1] + a[2] - b[2]) / b[1];
  if (!Number.isFinite(result)) throw new RangeError("budget quantity conversion overflow");
  return result;
}
export function checkedBudgets(values: readonly Budget[]): readonly Budget[] {
  if (!Array.isArray(values)) throw new RangeError("budgets must be an array");
  const ids = new Set<string>();
  for (const budget of values) {
    validateDef("Budget", budget);
    tokens(budget.quantity);
    if (!Number.isFinite(budget.total) || budget.total <= 0) throw new RangeError("budget total must be finite and positive");
    if (budget.action.lastIndexOf("/") < 1 || ids.has(budget.id)) throw new RangeError("invalid or duplicate budget id/action");
    convert(1, budget.unit, budget.unit);
    ids.add(budget.id);
  }
  return structuredClone(values);
}
const glob = (pattern: string, value: string): boolean => new RegExp("^" + pattern.split("*").map((s) => s.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*") + "$", "s").test(value);
export function budgetMatches(budget: Budget, deviceId: string, action: string): boolean {
  const slash = budget.action.lastIndexOf("/");
  return glob(budget.action.slice(0, slash), deviceId) && glob(budget.action.slice(slash + 1), action);
}
export function budgetUnit(budget: Budget, schema: JsonSchema): string | undefined {
  let node: any = schema;
  for (const token of tokens(budget.quantity)) node = node?.properties?.[token];
  if (!node || !["number", "integer"].includes(node.type) || typeof node["x-bhms-unit"] !== "string") return undefined;
  try { convert(1, node["x-bhms-unit"], budget.unit); return node["x-bhms-unit"]; } catch { return undefined; }
}
export class BudgetLedger {
  constructor(private readonly store: Store) {}
  state(principal: string, budget: Budget, now = Date.now()): BudgetState {
    const rows = this.store.budgetReservations().filter((r) => r.principal === principal && r.budgetId === budget.id
      && (budget.windowMs === undefined || r.atMs > now - budget.windowMs));
    // Compensated sum avoids losing small charges alongside large ones.
    let used = 0, correction = 0;
    for (const row of rows) { const y = row.amount - correction; const total = used + y; correction = (total - used) - y; used = total; }
    const state: BudgetState = { ...budget, remaining: Math.max(0, budget.total - used) };
    if (budget.windowMs !== undefined && rows.length) state.resetsAt = new Date(rows.reduce((oldest, r) => Math.min(oldest, r.atMs), Infinity) + budget.windowMs).toISOString();
    return state;
  }
  charges(principal: Principal, deviceId: string, action: string, args: Record<string, unknown>, schema: JsonSchema): BudgetCharge[] {
    const now = Date.now();
    return principal.budgets.filter((b) => budgetMatches(b, deviceId, action)).map((budget) => {
      const declared = budgetUnit(budget, schema);
      let value: any = args;
      const path = tokens(budget.quantity);
      for (const token of path) value = value !== null && typeof value === "object" && Object.hasOwn(value, token) ? value[token] : undefined;
      const field = ["arguments", ...path].join(".");
      if (!declared || typeof value !== "number" || !Number.isFinite(value)) {
        throw new BhmsError("UNAUTHORIZED", `budget ${budget.id} cannot measure ${deviceId}/${action}`, { field,
          hint: "the budget must name a numeric argument in a convertible unit (BHMS-AUTH-031)" });
      }
      let amount: number;
      try { amount = Math.abs(convert(value, declared, budget.unit)); }
      catch { throw new BhmsError("OUT_OF_RANGE", "the budget charge is outside the numeric range", { field, hint: "nothing was done; use a smaller quantity" }); }
      const state = this.state(principal.id, budget, now);
      if (amount > state.remaining + 1e-9 * Math.max(1, budget.total)) {
        throw new BhmsError("OUT_OF_RANGE", `${deviceId}/${action} needs ${amount} ${budget.unit} of budget ${budget.id}, with ${state.remaining} remaining`, {
          field, bound: { maximum: Math.max(0, convert(state.remaining, budget.unit, declared)), budget: state },
          hint: "nothing was done; earlier calls stay counted unless they ended with proof that nothing happened",
        });
      }
      return { budgetId: budget.id, amount, atMs: now };
    });
  }
}
