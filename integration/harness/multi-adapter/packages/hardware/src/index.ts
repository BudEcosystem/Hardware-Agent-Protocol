/** Typed local hardware service. Attribution never supplies HMS authority. */
import { Context, Service } from '@budmh/cordis'
import type { Agent } from '@budmh/agent'
import type { JsonValue } from '@budmh/util-values'

export type HardwareMethod = 'discover' | 'describe' | 'observe' | 'namespace' | 'prepare' | 'invoke' | 'operation' | 'events' | 'cancel'
export type HardwareReply = { ok: true; result: JsonValue } | { ok: false; error: { code: string }; outcome: 'unconfirmed' }
export interface HardwareCall { agent?: Agent; signal: AbortSignal }
declare module '@budmh/cordis' { interface Context { hardware: HardwareService } }
/** Providers authenticate independently. Session identity only selects existing file policy. */
export abstract class HardwareService extends Service {
  constructor(ctx: Context) { super(ctx, 'hardware') }
  /**
   * Send one bounded request without retry. Invoke params contain an already prepared immutable
   * envelope. Cancellation stops waiting; it does not cancel a recorded HMS operation. Query
   * its operationId or replay the exact retained envelope deliberately to resolve uncertainty.
   * Successful replies retain HMS evidence and execution state; they do not prove physical effect.
   */
  abstract request(method: HardwareMethod, params: Record<string, JsonValue>, call: HardwareCall): Promise<HardwareReply>
}
export default HardwareService
