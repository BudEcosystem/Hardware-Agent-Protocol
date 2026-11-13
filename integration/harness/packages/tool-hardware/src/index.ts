/** Native and PTC tools retain canonical operation facts and typed uncertainty. */
import type { Context } from '@budmh/cordis'
import z from '@budmh/schemastery'
import { HarnessError } from '@budmh/llm'
import type { HardwareMethod } from '@budmh/experimental-hardware'
import { parameterSchemaSpecToJsonSchema, valueSchemaSpecToJsonSchema, validateArgs } from '@budmh/tools'
import type { ParameterSchemaSpec } from '@budmh/tools'
import type { JsonValue } from '@budmh/util-values'
import { hardwareOutputSchema } from './output-schema.ts'
export const name = 'tool-hardware'
export const inject = ['tools', 'hardware']
export interface Config {}
export const Config: z<Config> = z.object({})
const interrupted = 'Hardware call interrupted; its outcome is unconfirmed. Inspect the operation or deliberately replay the unchanged retained request. Do not create a replacement operation key.'
const text = { type: 'string', required: true } as const
const integer = { type: 'integer', required: true } as const
const object = { type: 'object', additionalProperties: true, required: true } as const
const methods: Record<HardwareMethod, { description: string; parameters: ParameterSchemaSpec }> = {
  discover: { description: 'List local simulation instances and pinned descriptions.', parameters: { capability: { type: 'string' }, limit: { type: 'integer' }, cursor: { type: 'string' } } },
  describe: { description: 'Read a simulation instance description and semantic generations.', parameters: { instanceId: text, digest: { type: 'string' } } },
  observe: { description: 'Read bounded-age simulation evidence, including quality and uncertainty.', parameters: { instanceId: text, property: text, maxAgeMs: integer, evidenceKind: text } },
  namespace: { description: 'Allocate an expiring replay namespace before preparing an immutable request.', parameters: { expiresUnixMs: integer } },
  prepare: { description: 'Prepare an immutable request with pinned generations. This does not admit or execute it. Retain the complete request unchanged for invoke and any deliberate replay.', parameters: { instanceId: text, actionId: text, arguments: object, operationKey: text, replayNamespace: text, timing: object, requiredEffect: text } },
  invoke: { description: 'Submit a retained complete request once. Never reconstruct or change it after uncertain delivery. Acceptance is not completion or physical verification; query its operationId. Automatic retries are disabled.', parameters: { request: object } },
  operation: { description: 'Read durable execution, cancellation, resource and effect-verification states. Completed simulation is not a verified physical effect.', parameters: { operationId: text } },
  events: { description: 'Read bounded durable operation events after a sequence cursor.', parameters: { operationId: text, after: { type: 'integer' }, limit: { type: 'integer' } } },
  cancel: { description: 'Request cancellation of an operation. Cancellation acceptance does not prove stopped hardware or rollback; inspect operation state and resources.', parameters: { operationId: text } },
}
/** Register effect-scoped tools. Session and call IDs are output attribution, never authority. */
export function apply(ctx: Context): void {
  for (const method of Object.keys(methods) as HardwareMethod[]) {
    ctx.tools.register({
      name: `hardware_${method}`, description: methods[method].description, parameters: { ...parameterSchemaSpecToJsonSchema(methods[method].parameters) },
      output: { schema: valueSchemaSpecToJsonSchema(hardwareOutputSchema(method)), render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] },
      finalizeContent(_exec, result) {
        if (result.isError && result.error.info?.code === 'ABORTED') return [{ type: 'text', text: interrupted }]
        return undefined
      },
      async execute(args, exec) {
        const violations = validateArgs(methods[method].parameters, args)
        if (violations.length > 0) throw new Error(`hardware_${method}: invalid arguments`)
        // The registry snapshots lossless JSON; the parameter schema above proves an object.
        const params = args as Record<string, JsonValue>
        const reply = await ctx.hardware.request(method, params, { ...(exec.agent ? { agent: exec.agent } : {}), signal: exec.signal })
        if (exec.signal.aborted) throw new HarnessError(interrupted, 'HMS_OUTCOME_UNCONFIRMED')
        return { ...reply, attribution: { sessionId: exec.agent?.session.id ?? null, callId: exec.callId } }
      },
    })
  }
}
