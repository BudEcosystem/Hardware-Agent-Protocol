/** Actual Loader, native tools, Node PTC and Session replay against a local synthetic plant. */
import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { appendFile, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@budmh/cordis'
import Loader from '@budmh/cordis-plugin-loader'
import Include, { entryListSchema } from '@budmh/cordis-plugin-include'
import yaml from 'js-yaml'
import AgentRegistry from '@budmh/agent'
import AgentLoop from '@budmh/agent-loop'
import LocalFileSystem from '@budmh/fs-local'
import LlmRuntime, { LlmAdapter, ToolCallId, createUserMessage } from '@budmh/llm'
import type { GenerateOptions, LlmResolvedModelInfo, StreamChunk } from '@budmh/llm'
import LocalSandbox from '@budmh/sandbox-local'
import SandboxPolicyService from '@budmh/sandbox-policy'
import SessionStore, { Session, SessionId } from '@budmh/session'
import SessionProjectionRegistry from '@budmh/session-projection'
import LocalSubprocessRuntime from '@budmh/subprocess-local'
import SystemPrompt from '@budmh/system-prompt'
import ToolRuntime from '@budmh/tools'
import WorkingDirectoryService from '@budmh/working-directory'
import NodePtcRuntime from '@budmh/ptc-runtime-node'
import HmsHardware from '@budmh/experimental-hardware-hms'
import type { JsonValue } from '@budmh/util-values'
import * as ToolHardware from '../src/index.ts'

const hmsRoot = process.env.HMS_ROOT
let context: Context | undefined
let directory: string | undefined
let daemon: ChildProcess | undefined
let daemonError = ''
afterEach(async () => {
  await context?.fiber.dispose(); context = undefined
  vi.unstubAllEnvs()
  if (daemon) { const process = daemon; daemon = undefined; const exited = once(process, 'exit'); process.kill('SIGTERM'); const code: unknown = (await exited)[0]; expect(code, daemonError).toBe(0) }
  if (directory) await rm(directory, { recursive: true, force: true }); directory = undefined
})

async function setup(mode: 'native' | 'ptc') {
  directory = await mkdtemp(join(tmpdir(), 'hms-native-'))
  const socketPath = join(directory, 'control.sock')
  daemonError = ''
  daemon = spawn('python3', ['-m', 'hms', 'serve', '--init-simulation', '--state-dir', join(directory, 'state'), '--socket', socketPath], { cwd: hmsRoot, stdio: ['ignore', 'pipe', 'pipe'] })
  daemon.stderr!.on('data', (chunk) => { daemonError += String(chunk) })
  const ready: unknown = (await once(daemon.stdout!, 'data'))[0]
  expect(JSON.parse(String(ready))).toMatchObject({ ready: true, deployment: 'simulation:local' })
  const modules = new Map<string, unknown>([
    ['@budmh/agent', AgentRegistry], ['@budmh/session', SessionStore], ['@budmh/session-projection', SessionProjectionRegistry],
    ['@budmh/system-prompt', SystemPrompt], ['@budmh/llm', LlmRuntime], ['@budmh/tools', ToolRuntime],
    ['@budmh/fs-local', LocalFileSystem], ['@budmh/subprocess-local', LocalSubprocessRuntime], ['@budmh/sandbox-local', LocalSandbox],
    ['@budmh/sandbox-policy', SandboxPolicyService], ['@budmh/working-directory', WorkingDirectoryService],
    ['@budmh/ptc-runtime-node', NodePtcRuntime], ['@budmh/experimental-hardware-hms', HmsHardware],
    ['@budmh/experimental-tool-hardware', ToolHardware], ['@budmh/agent-loop', AgentLoop],
  ])
  const rows = [...modules.keys()].filter(name => !name.startsWith('@budmh/experimental-')).map(name => ({ name: 'cordis:' + name,
    ...name === '@budmh/tools' ? { config: { mode } } : {},
    ...name === '@budmh/sandbox-policy' ? { config: { mode: 'danger-full-access' } } : {},
    ...name === '@budmh/agent-loop' ? { config: { agents: [] } } : {},
  }))
  const patchPath = new URL('../../hardware-profile/cordis.patch.yml', import.meta.url)
  const patches = yaml.load(await readFile(patchPath, 'utf8'), { schema: entryListSchema }) as { insert: { id: string; name: string; config?: Record<string, string> }[] }[]
  for (const row of patches[0]!.insert) {
    row.name = 'cordis:' + row.name

  }
  vi.stubEnv('HMS_SOCKET', socketPath)
  const configPath = join(directory, 'cordis.yml')
  await writeFile(configPath, JSON.stringify(rows))
  context = new Context(); context.baseUrl = pathToFileURL(directory).href + '/'
  await context.plugin(Loader)
  context.loader.builtins.include = Include
  for (const [name, plugin] of modules) context.loader.builtins[name] = plugin
  await context.loader.create({ name: 'cordis:include', config: { path: pathToFileURL(configPath).href, patches } })
  await context.loader.await()
  const ctx = context
  const agent = await ctx.agentLoop.create(SessionId('hms-integration'), {}, { cwd: directory })
  let calls = 0
  const invoke = async (method: string, args: Record<string, JsonValue>) => {
    const start = performance.now()
    const result = await ctx.tools.execute({ name: 'hardware_' + method, arguments: args, callId: ToolCallId(`hms-${++calls}`), agent, signal: new AbortController().signal })
    if (process.env.HMS_TIMINGS) {
      await appendFile(process.env.HMS_TIMINGS, JSON.stringify({ method, elapsedMs: performance.now() - start }) + '\n')
    }
    expect(result.isError, JSON.stringify(result)).not.toBe(true)
    expect(result.content).toEqual([{ type: 'text', text: JSON.stringify(result.value) }])
    return result.value as {
      ok: boolean
      result: Record<string, JsonValue>
      error?: { code: string }
      attribution: { sessionId: string; callId: string }
    }
  }
  return { ctx, agent, invoke }
}

describe.skipIf(!hmsRoot || process.platform !== 'linux')('native HMS simulation integration', () => {
  it('composes the opt-in profile, executes three scenarios, preserves replay and typed rejection, then unloads tools', async () => {
    const { ctx, invoke } = await setup('native')
    expect(await ctx.hardware.request('discover', {}, { signal: AbortSignal.abort() })).toEqual({ ok: false, error: { code: 'TRANSPORT_INTERRUPTED' }, outcome: 'unconfirmed' })
    const before = await ctx.tools.execute({ name: 'hardware_invoke', arguments: { request: {} }, callId: ToolCallId('before-abort'), signal: AbortSignal.abort() })
    expect(before.isError && before.error.info?.code).toBe('ABORTED_BEFORE_DISPATCH')
    const controller = new AbortController()
    const pending = vi.spyOn(ctx.hardware, 'request').mockImplementationOnce(async () => {
      controller.abort(); return { ok: false, error: { code: 'TRANSPORT_INTERRUPTED' }, outcome: 'unconfirmed' }
    })
    try {
      const interrupted = await ctx.tools.execute({ name: 'hardware_invoke', arguments: { request: {} }, callId: ToolCallId('after-abort'), signal: controller.signal })
      expect(interrupted.isError && interrupted.error.info?.code).toBe('HMS_OUTCOME_UNCONFIRMED')
      expect(JSON.stringify(interrupted.content)).toContain('outcome is unconfirmed')
      expect(pending).toHaveBeenCalledTimes(1)
    } finally { pending.mockRestore() }
    const lateController = new AbortController()
    const lateProvider = vi.spyOn(ctx.hardware, 'request').mockResolvedValueOnce({ ok: false, error: { code: 'TRANSPORT_FAILURE' }, outcome: 'unconfirmed' })
    const disposeLateAbort = ctx.on('tools/post-execute', async (exec, _result, next) => {
      const decision = await next()
      if (exec.callId === 'late-abort') lateController.abort()
      return decision
    })
    try {
      const late = await ctx.tools.execute({ name: 'hardware_invoke', arguments: { request: {} }, callId: ToolCallId('late-abort'), signal: lateController.signal })
      expect(late.isError && late.error.info?.code).toBe('ABORTED')
      expect(JSON.stringify(late.content)).toContain('outcome is unconfirmed')
    } finally { disposeLateAbort(); lateProvider.mockRestore() }
    const discovered = await invoke('discover', { limit: 10 })
    expect(discovered.ok).toBe(true); expect(discovered.result.items).toHaveLength(3)
    await invoke('discover', { limit: 10 }); await invoke('discover', { limit: 10 })
    const namespace = await invoke('namespace', { expiresUnixMs: Date.now() + 180000 })
    const cases: [string, string, Record<string, JsonValue>][] = [
      ['sim:home-fan', 'set_level', { level: 37, unit: 'percent' }],
      ['sim:microscope', 'move_absolute', { position: 12.5, unit: 'um', frame: 'sim:microscope' }],
      ['sim:inspection-cell', 'inspect', { recipe: 2, partId: 'synthetic-part' }],
    ]
    for (const [instanceId, actionId, args] of cases) {
      const now = Date.now()
      const params = { instanceId, actionId, arguments: args, operationKey: 'native-' + actionId, replayNamespace: namespace.result.token!, requiredEffect: 'capability_completion', timing: { notBeforeUnixMs: now, latestStartUnixMs: now + 60000, maxRunMs: 5000, latestCompletionUnixMs: now + 120000 } }
      const prepared = await invoke('prepare', params)
      expect(prepared.ok, JSON.stringify(prepared)).toBe(true)
      const retained = JSON.stringify(prepared.result.request)
      const accepted = await invoke('invoke', { request: JSON.parse(retained) as JsonValue })
      expect(accepted.ok, JSON.stringify(accepted)).toBe(true)
      const replayed = await invoke('invoke', { request: JSON.parse(retained) as JsonValue })
      expect(replayed.result.operationId).toBe(accepted.result.operationId)
      if (actionId === 'set_level') {
        const changed = JSON.parse(retained) as { intent: { arguments: { level: number } } }; changed.intent.arguments.level = 38
        expect((await invoke('invoke', { request: changed })).error?.code).toBe('KEY_CONFLICT')
      }
      let status = accepted
      for (let i = 0; i < 40 && status.result.executionState !== 'completed'; i++) status = await invoke('operation', { operationId: accepted.result.operationId! })
      expect(status.result.executionState).toBe('completed')
      expect(status.result.effectVerification).toBe('unverified')
      expect(status.result.result).toMatchObject({ evidenceKind: 'simulation' })
      const denied = await invoke('prepare', { ...params, operationKey: 'denied-' + actionId, requiredEffect: 'physical_verified' })
      expect(denied.ok).toBe(false); expect(denied.error?.code).toBeDefined()
      expect(JSON.stringify(prepared.result.request)).toBe(retained)
    }
    const now = Date.now()
    const later = await invoke('prepare', { instanceId: 'sim:home-fan', actionId: 'set_level', arguments: { level: 80, unit: 'percent' }, operationKey: 'future-cancel', replayNamespace: namespace.result.token!, requiredEffect: 'capability_completion', timing: { notBeforeUnixMs: now + 60000, latestStartUnixMs: now + 90000, maxRunMs: 5000, latestCompletionUnixMs: now + 100000 } })
    const waiting = await invoke('invoke', { request: later.result.request! })
    const canceled = await invoke('cancel', { operationId: waiting.result.operationId! })
    expect(canceled.ok).toBe(true)
    let stopped = canceled
    for (let i = 0; i < 5 && stopped.result.executionState !== 'canceled'; i++) stopped = await invoke('operation', { operationId: waiting.result.operationId! })
    expect(stopped.result.executionState).toBe('canceled')
    expect(stopped.result.mayHaveActed).toBe(false)
    const entry = [...ctx.loader.entries()].find(row => row.options.name === 'cordis:@budmh/experimental-tool-hardware')!
    await entry.fiber!.dispose()
    expect(ctx.tools.schemas().filter(tool => tool.name.startsWith('hardware_'))).toHaveLength(0)
  }, 120000)

  it('executes actual Node PTC and preserves canonical nested output in restored Session events', async () => {
    const { ctx, agent } = await setup('ptc')
    const result = await ctx.tools.execute({ name: 'run_code', arguments: { code: `const namespace = await tools.hardware_namespace({ expiresUnixMs: Date.now() + 180000 });
const now = Date.now();
const prepared = await tools.hardware_prepare({ instanceId: 'sim:home-fan', actionId: 'set_level', arguments: { level: 42, unit: 'percent' }, operationKey: 'ptc-fan', replayNamespace: namespace.result.token, requiredEffect: 'capability_completion', timing: { notBeforeUnixMs: now, latestStartUnixMs: now + 60000, maxRunMs: 5000, latestCompletionUnixMs: now + 120000 } });
const retained = JSON.stringify(prepared.result.request);
const admitted = await tools.hardware_invoke({ request: JSON.parse(retained) });
const replayed = await tools.hardware_invoke({ request: JSON.parse(retained) });
if (admitted.result.operationId !== replayed.result.operationId) throw new Error('replay identity changed');
const status = await tools.hardware_operation({ operationId: admitted.result.operationId });
if (status.result.executionState !== 'completed' || status.result.effectVerification !== 'unverified' || status.result.result.evidenceKind !== 'simulation') throw new Error('unexpected operation evidence');
return { admitted, replayed, status };`, description: 'Inspect simulated instances' }, callId: ToolCallId('ptc-hms'), agent, signal: new AbortController().signal })
    expect(result.isError, JSON.stringify(result)).not.toBe(true)
    const events = agent.session.snapshotEvents()
    const dispatch = events.filter(event => event.type === 'tool/ptc-dispatch')
    expect(dispatch).toHaveLength(5)
    const restored = Session.create(agent.session.id, events, agent.session.header)
    expect(restored.snapshotEvents().filter(event => event.type !== 'session/end-seed')).toEqual(events)
    expect(JSON.stringify(dispatch)).toContain('simulation')
    expect(JSON.stringify(dispatch)).toContain('ptc-hms:ptc:')
    expect(JSON.stringify(dispatch)).toContain('sim:home-fan')
  }, 120000)

  it('records native AgentLoop tool results and reconstructs model-visible history from a persisted Session', async () => {
    const { ctx } = await setup('native')
    class ScriptedAdapter extends LlmAdapter {
      private turns = 0
      override async resolveModel(provider: string, model: string): Promise<LlmResolvedModelInfo> {
        return { provider, id: model, name: model }
      }
      async *stream(_options: GenerateOptions): AsyncIterable<StreamChunk> {
        if (this.turns++ === 0) {
          const id = ToolCallId('recorded-discover')
          yield { type: 'block-start', index: 0, blockType: 'tool-call' }
          yield { type: 'tool-call-delta', index: 0, id, name: 'hardware_discover', argumentsDelta: '{"limit":10}' }
          yield { type: 'block-end', index: 0, block: { type: 'tool-call', id, name: 'hardware_discover', arguments: '{"limit":10}' } }
          yield { type: 'finish', reason: { kind: 'tool-calls' } }
        } else {
          const text = 'Three simulation instances; no physical effect is verified.'
          yield { type: 'block-start', index: 0, blockType: 'text' }
          yield { type: 'text-delta', index: 0, text }
          yield { type: 'block-end', index: 0, block: { type: 'text', text } }
          yield { type: 'finish', reason: { kind: 'stop' } }
        }
      }
    }
    ctx.llm.registerAdapter(['hms-keyless'], new ScriptedAdapter())
    const agent = await ctx.agentLoop.create(SessionId('hms-recorded'), { provider: 'hms-keyless', model: 'local-script' }, { cwd: directory! })
    const idle = new Promise<void>((resolve) => { const dispose = ctx.on('agent/status', (event) => { if (event.agent === agent && event.status === 'idle') { dispose(); resolve() } }) })
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'List the simulated hardware without acting.' }], source: { kind: 'user' } }))
    await idle
    const captured = { id: agent.session.id, header: agent.session.header, events: agent.session.snapshotEvents() }
    const path = join(directory!, 'session-capture.json')
    await writeFile(path, JSON.stringify(captured))
    const reopened = JSON.parse(await readFile(path, 'utf8')) as typeof captured
    const restored = Session.create(reopened.id, reopened.events, reopened.header)
    expect(restored.deriveMessages()).toEqual(agent.session.deriveMessages())
    const results = reopened.events.filter(event => event.type === 'tool/result')
    expect(results).toHaveLength(1)
    expect(JSON.stringify(results)).toContain('sim:inspection-cell')
    expect(JSON.stringify(results)).toContain('recorded-discover')
    expect(JSON.stringify(results)).toContain('hms-recorded')
    if (process.env.HMS_CAPTURE) await writeFile(process.env.HMS_CAPTURE, JSON.stringify(captured, null, 2) + '\n')
  }, 120000)
})
