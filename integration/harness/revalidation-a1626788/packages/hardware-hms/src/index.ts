/** Native Harness provider for an explicitly configured same-UID HMS simulation daemon. */
import { isAbsolute } from 'node:path'
import { Context } from '@budmh/cordis'
import z from '@budmh/schemastery'
import HardwareService from '@budmh/experimental-hardware'
import type { HardwareCall, HardwareMethod, HardwareReply } from '@budmh/experimental-hardware'
import { deadline } from '@budmh/timeout'
import type {} from '@budmh/subprocess'
import type {} from '@budmh/sandbox'
import type {} from '@budmh/sandbox-policy'
import type { JsonValue } from '@budmh/util-values'
import { BRIDGE } from './bridge.ts'
import { decodeBridgeReply, unconfirmed as uncertain } from './reply.ts'

export interface Config {
  hmsRoot: string
  socketPath: string
  pythonExecutable?: string
  timeoutMs?: number
  graceMs?: number
  maxOutputBytes?: number
}
/** The subprocess and sandbox providers must share the configured local Linux execution world. */
export default class HmsHardware extends HardwareService {
  static inject = ['subprocess', 'sandbox', 'sandboxPolicy']
  static Config: z<Config> = z.object({
    hmsRoot: z.string().required(), socketPath: z.string().required(), pythonExecutable: z.string().default('python3'),
    timeoutMs: z.number().default(5000), graceMs: z.number().default(1000), maxOutputBytes: z.number().default(131072),
  })
  private readonly config: Required<Config>
  private readonly lifetime = new AbortController()
  private readonly pending = new Set<Promise<HardwareReply>>()
  constructor(ctx: Context, config: Config) {
    super(ctx)
    this.config = config as Required<Config>
    if (!isAbsolute(config.hmsRoot) || !isAbsolute(config.socketPath)) throw new Error('hardware-hms: hmsRoot and socketPath must be absolute')
    for (const key of ['timeoutMs', 'graceMs', 'maxOutputBytes'] as const) {
      if (!Number.isSafeInteger(this.config[key]) || this.config[key] <= 0 || this.config[key] > 2147483647) throw new Error(`hardware-hms: ${key} must be a positive bounded integer`)
    }
    ctx.effect(() => async () => { this.lifetime.abort(); await Promise.allSettled(this.pending) })
  }
  override async request(method: HardwareMethod, params: Record<string, JsonValue>, call: HardwareCall): Promise<HardwareReply> {
    // Snapshot synchronously before any await; retries must use the caller's original envelope.
    const payload = JSON.stringify({ method, params })
    if (Buffer.byteLength(payload) > 65536) return uncertain('REQUEST_TOO_LARGE')
    const operation = this.send(payload, call)
    this.pending.add(operation)
    try { return await operation } finally { this.pending.delete(operation) }
  }
  private async send(payload: string, call: HardwareCall): Promise<HardwareReply> {
    const signal = AbortSignal.any([this.lifetime.signal, call.signal])
    using timeout = deadline(signal, this.config.timeoutMs, 'HMS_TIMEOUT')
    try {
      timeout.signal.throwIfAborted()
      const policy = this.ctx.sandboxPolicy.resolve(call.agent ? { session: call.agent.session } : {})
      const executable = await this.ctx.subprocess.resolveExecutable(this.config.pythonExecutable, undefined, timeout.signal)
      const argv = [executable, '-I', '-c', BRIDGE, this.config.hmsRoot, this.config.socketPath]
      const confined = policy.mode === 'danger-full-access' ? argv : (await this.ctx.sandbox.confine(argv, { ...policy, mode: policy.mode }, timeout.signal)).argv
      timeout.signal.throwIfAborted()
      const secretNames = Object.keys(process.env).filter(key => /KEY|SECRET|TOKEN|PASSWORD/i.test(key))
      const env: NodeJS.ProcessEnv = Object.fromEntries(secretNames.map(key => [key, undefined]))
      const child = this.ctx.subprocess.spawn({
        argv: confined, cwd: this.config.hmsRoot, env, signal: timeout.signal, graceMs: this.config.graceMs,
        stdio: { stdin: { data: payload }, stdout: { maxBytes: this.config.maxOutputBytes }, stderr: { maxBytes: 4096 } } })
      try {
        const outcome = await child.done
        if (timeout.signal.aborted) return uncertain('TRANSPORT_INTERRUPTED')
        const output = child.collected.stdout?.readFrom(0)
        if (outcome.exitCode !== 0 || output === undefined || output.lossy) return uncertain('TRANSPORT_FAILURE')
        return decodeBridgeReply(output.text)
      } finally { child.terminate(); await child.waitForExit() }
    } catch { return uncertain(timeout.signal.aborted ? 'TRANSPORT_INTERRUPTED' : 'TRANSPORT_FAILURE') }
  }
}
