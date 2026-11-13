/** Actual Loader/native/PTC tools through HMS and an independently owned original C endpoint. */
import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { appendFile, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createInterface } from 'node:readline'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@budmh/cordis'
import Loader from '@budmh/cordis-plugin-loader'
import Include, { entryListSchema } from '@budmh/cordis-plugin-include'
import yaml from 'js-yaml'
import AgentRegistry from '@budmh/agent'
import AgentLoop from '@budmh/agent-loop'
import LocalFileSystem from '@budmh/fs-local'
import LlmRuntime, { ToolCallId } from '@budmh/llm'
import LocalSandbox from '@budmh/sandbox-local'
import SandboxPolicyService from '@budmh/sandbox-policy'
import SessionStore, { SessionId } from '@budmh/session'
import SessionProjectionRegistry from '@budmh/session-projection'
import LocalSubprocessRuntime from '@budmh/subprocess-local'
import SystemPrompt from '@budmh/system-prompt'
import ToolRuntime from '@budmh/tools'
import WorkingDirectoryService from '@budmh/working-directory'
import NodePtcRuntime from '@budmh/ptc-runtime-node'
import HmsHardware from '@budmh/experimental-hardware-hms'
import type { JsonValue } from '@budmh/util-values'
import * as ToolHardware from '../src/index.ts'

const hmsRoot = process.env.HMS_COMPACT_ROOT
const launcher = fileURLToPath(new URL('./compact-launcher.py', import.meta.url))
const cases: [string, string, Record<string, JsonValue>, number][] = [
  ['sim:home-fan', 'set_level', { level: 25, unit: 'percent' }, 25],
  ['sim:microscope', 'move_absolute', { position: 42, unit: 'um', frame: 'sim:microscope' }, 42],
  ['sim:inspection-cell', 'inspect', { recipe: 1, partId: 'part:α' }, 1],
]
type Reply = {
  ok: boolean
  result: Record<string, JsonValue>
  error?: { code: string }
  attribution: { sessionId: string; callId: string }
}
interface Evidence extends Record<string, JsonValue> {
  operationId: string
  requestDigest: string
  endpointPid: number
  endpointAlive: boolean
  totalOpFrames: number
  operationOpFrames: number
  retainedEqualsForwarded: boolean
  noSQLitePlant: boolean
  retired: boolean
  queriedAfterRestart: boolean
  opWireHex: string
  nativeReceipt: { execution: string; evidenceKind: string; verification: string; heldResources: number; sampleTick: number; value: number }
}
let context: Context | undefined
let directory: string | undefined
let supervisor: ChildProcess | undefined
let control: ((params: Record<string, JsonValue>) => Promise<Record<string, JsonValue>>) | undefined
let stderr = ''

afterEach(async () => {
  const failures: unknown[] = []
  try { await context?.fiber.dispose() } catch (error: unknown) { failures.push(error) }
  context = undefined
  vi.unstubAllEnvs()
  try {
    if (supervisor) {
      const child = supervisor; supervisor = undefined
      const exited = child.exitCode === null ? once(child, 'exit') : Promise.resolve([child.exitCode])
      if (child.exitCode === null) {
        try { expect(await control!({ method: 'close' })).toMatchObject({ daemonClosed: true, endpointExit: 0 }) }
        catch (error: unknown) { failures.push(error) }
        child.stdin!.end()
      }
      expect((await exited)[0], stderr).toBe(0)
    }
  } catch (error: unknown) { failures.push(error) }
  control = undefined
  try {
    if (directory) await rm(directory, { recursive: true, force: true })
  } catch (error: unknown) { failures.push(error) }
  directory = undefined
  if (failures.length > 0) throw new AggregateError(failures, 'Compact integration cleanup failed')
}, 30000)

async function setup(mode: 'native' | 'ptc') {
  directory = await mkdtemp(join(tmpdir(), 'hms-harness-compact-'))
  stderr = ''
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD|PROXY|^BUDMH_/iu.test(key)))
  const child = spawn('python3', ['-B', launcher, hmsRoot!, join(hmsRoot!, 'bin/endpoint-scenarios-pipe'), directory], { env, stdio: ['pipe', 'pipe', 'pipe'] })
  supervisor = child
  child.stderr.on('data', (chunk) => { stderr += String(chunk) })
  const lines = createInterface({ input: child.stdout })[Symbol.asyncIterator]()
  const ended = once(child, 'exit').then(([code]) => { throw new Error('Compact launcher exited ' + String(code) + ': ' + stderr) })
  // The lifetime promise participates in every read; suppress only its detached completion after successful close.
  void ended.catch(() => undefined)
  const read = async () => {
    let timer: NodeJS.Timeout | undefined
    try {
      const line = await Promise.race([lines.next(), ended, new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => { reject(new Error('Compact launcher response deadline: ' + stderr)) }, 15000)
      })])
      if (line.done) throw new Error('Compact launcher output ended: ' + stderr)
      return JSON.parse(line.value) as {
        ready?: { socket: string; deployment: string; endpointPid: number }
        result?: Record<string, JsonValue>
        error?: string
      }
    } finally { clearTimeout(timer) }
  }
  const ready = (await read()).ready!
  expect(ready).toMatchObject({ deployment: 'simulation:compact' })
  control = async (params) => {
    child.stdin.write(JSON.stringify(params) + '\n')
    const reply = await read()
    if (reply.error !== undefined) throw new Error(reply.error + '\n' + stderr)
    expect(reply.result).toBeDefined()
    return reply.result!
  }
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
  const patches = yaml.load(await readFile(new URL('../../hardware-profile/cordis.patch.yml', import.meta.url), 'utf8'), { schema: entryListSchema }) as { insert: { id: string; name: string; config?: Record<string, string> }[] }[]
  for (const row of patches[0]!.insert) row.name = 'cordis:' + row.name
  vi.stubEnv('HMS_ROOT', hmsRoot); vi.stubEnv('HMS_SOCKET', ready.socket)
  const config = join(directory, 'cordis.yml')
  await writeFile(config, JSON.stringify(rows))
  context = new Context(); context.baseUrl = pathToFileURL(directory).href + '/'
  await context.plugin(Loader)
  context.loader.builtins.include = Include
  for (const [name, plugin] of modules) context.loader.builtins[name] = plugin
  await context.loader.create({ name: 'cordis:include', config: { path: pathToFileURL(config).href, patches } })
  await context.loader.await()
  const ctx = context
  const agent = await ctx.agentLoop.create(SessionId('hms-compact-' + mode), {}, { cwd: directory })
  let calls = 0
  const invoke = async (method: string, args: Record<string, JsonValue>) => {
    const result = await ctx.tools.execute({ name: 'hardware_' + method, arguments: args, callId: ToolCallId('compact-' + String(++calls)), agent, signal: new AbortController().signal })
    if (result.isError || !(result.value as Reply).ok) await diagnostics({ method, args, result })
    expect(result.isError, JSON.stringify(result)).not.toBe(true)
    expect(result.content).toEqual([{ type: 'text', text: JSON.stringify(result.value) }])
    const value = result.value as Reply
    expect(value.ok, JSON.stringify(value)).toBe(true)
    return value
  }
  return { ctx, agent, invoke, endpointPid: ready.endpointPid }
}

async function diagnostics(trigger: object) {
  const value = await control!({ method: 'diagnostics' })
  if (process.env.HMS_COMPACT_DIAGNOSTICS) await appendFile(process.env.HMS_COMPACT_DIAGNOSTICS, JSON.stringify({ trigger, value }) + '\n')
}

async function capture(scenario: string, value: object) {
  if (process.env.HMS_COMPACT_CAPTURE) await appendFile(process.env.HMS_COMPACT_CAPTURE, JSON.stringify({ scenario, ...value }) + '\n')
}

function checkEvidence(value: Evidence, receipt: Record<string, JsonValue>, expected: number, count: number, endpointPid: number) {
  expect(value).toMatchObject({ operationId: receipt.operationId, requestDigest: receipt.requestDigest, endpointPid, endpointAlive: true,
    totalOpFrames: count, operationOpFrames: 1, retainedEqualsForwarded: true, noSQLitePlant: true, retired: true })
  expect(value.nativeReceipt).toMatchObject({ execution: 'completed', evidenceKind: 'simulation', verification: 'unverified', heldResources: 0, value: expected })
  expect(receipt).toMatchObject({ executionState: 'completed', effectVerification: 'unverified', resourceClaims: [],
    result: { evidenceKind: 'simulation', output: { value: expected, sampleTick: value.nativeReceipt.sampleTick, effectCommitted: true } } })
}

describe.skipIf(!hmsRoot || process.platform !== 'linux')('Harness tools with original compact C simulator', () => {
  it('runs three scenarios through actual Node PTC and retains one OP frame per immutable request', async () => {
    const { ctx, agent, endpointPid } = await setup('ptc')
    const code = `const ns = await tools.hardware_namespace({ expiresUnixMs: Date.now() + 180000 });
const results = [];
for (const [instanceId, actionId, args, expected] of ${JSON.stringify(cases)}) {
  const now = Date.now();
  const prepared = await tools.hardware_prepare({ instanceId, actionId, arguments: args, operationKey: 'compact-ptc-' + actionId, replayNamespace: ns.result.token, requiredEffect: 'capability_completion', timing: { notBeforeUnixMs: now, latestStartUnixMs: now + 15000, maxRunMs: 5000, latestCompletionUnixMs: now + 25000 } });
  if (!prepared.ok) throw new Error(JSON.stringify(prepared));
  const retained = JSON.stringify(prepared.result.request);
  const admitted = await tools.hardware_invoke({ request: JSON.parse(retained) });
  if (!admitted.ok) throw new Error(JSON.stringify(admitted));
  let status = admitted;
  for (let i = 0; i < 12; ++i) {
    status = await tools.hardware_operation({ operationId: admitted.result.operationId });
    if (!status.ok) throw new Error(JSON.stringify(status));
    if (status.result.executionState === 'completed' && status.result.resourceClaims.length === 0) break;
  }
  if (status.result.executionState !== 'completed' || status.result.result.output.value !== expected) throw new Error('Endpoint did not complete');
  const replayed = await tools.hardware_invoke({ request: JSON.parse(retained) });
  if (!replayed.ok || replayed.result.operationId !== admitted.result.operationId || JSON.stringify(replayed.result.result) !== JSON.stringify(status.result.result)) throw new Error('Replay changed operation');
  results.push({ retained, admitted, status, replayed });
}
return results;`
    const result = await ctx.tools.execute({ name: 'run_code', arguments: { code, description: 'Run three local compact simulations with retained requests' }, callId: ToolCallId('compact-ptc'), agent, signal: new AbortController().signal })
    if (result.isError) await diagnostics({ method: 'run_code', result })
    expect(result.isError, JSON.stringify(result)).not.toBe(true)
    const dispatch = agent.session.snapshotEvents().filter(event => event.type === 'tool/ptc-dispatch')
    const text = JSON.stringify(dispatch)
    expect(text).toContain('simulation')
    const invocations = dispatch.filter(event => event.data.name === 'hardware_invoke')
    expect(invocations).toHaveLength(6)
    for (let i = 0; i < 3; ++i) expect(invocations[2 * i]!.data.arguments).toEqual(invocations[2 * i + 1]!.data.arguments)
    const evidence = []
    // PTC may project the outer return; inspect the actual canonical nested dispatch records.
    const statuses = dispatch.filter(event => event.data.name === 'hardware_operation')
    for (const [instanceId, _action, _args, expected] of cases) {
      const relevant = statuses.map(event => JSON.parse(event.data.content.find(block => block.type === 'text')!.text) as Reply)
        .filter(reply => reply.result.instanceId === instanceId && reply.result.executionState === 'completed')
      expect(relevant.length).toBeGreaterThan(0)
      const status = relevant.at(-1)!.result
      const observed = await control!({ method: 'evidence', operationId: status.operationId! }) as Evidence
      checkEvidence(observed, status, expected, 3, endpointPid)
      evidence.push(observed)
    }
    await capture('ptc-three-native-c', { result, dispatch, evidence })
  }, 150000)

  it('replays native requests after host SIGKILL loses each accepted endpoint OP reply without sending another OP', async () => {
    const { invoke, endpointPid } = await setup('native')
    const namespace = await invoke('namespace', { expiresUnixMs: Date.now() + 180000 })
    let count = 0
    for (const [instanceId, actionId, args, expected] of cases) {
      const now = Date.now()
      const prepared = await invoke('prepare', { instanceId, actionId, arguments: args, operationKey: 'compact-loss-' + actionId,
        replayNamespace: namespace.result.token!, requiredEffect: 'capability_completion', timing: {
          notBeforeUnixMs: now, latestStartUnixMs: now + 15000, maxRunMs: 5000, latestCompletionUnixMs: now + 25000,
        } })
      const retained = JSON.stringify(prepared.result.request)
      await control!({ method: 'arm' })
      const admitted = await invoke('invoke', { request: JSON.parse(retained) as JsonValue })
      expect(['accepted', 'dispatching']).toContain(admitted.result.executionState)
      const crash = await control!({ method: 'crash', operationId: admitted.result.operationId! })
      expect(crash).toMatchObject({ operationId: admitted.result.operationId, requestDigest: admitted.result.requestDigest,
        endpointPid, endpointAlive: true, receiptAbsent: true })
      expect(['queued', 'running']).toContain(crash.nativeExecution)
      const restarted = await control!({ method: 'restart' })
      expect(restarted.endpointPid).toBe(endpointPid)
      const replayed = await invoke('invoke', { request: JSON.parse(retained) as JsonValue })
      expect(replayed.result.operationId).toBe(admitted.result.operationId)
      expect(replayed.result.requestDigest).toBe(admitted.result.requestDigest)
      let status = replayed
      for (let i = 0; i < 12 && (status.result.executionState !== 'completed' || (status.result.resourceClaims as JsonValue[]).length > 0); ++i) {
        status = await invoke('operation', { operationId: admitted.result.operationId! })
      }
      const again = await invoke('invoke', { request: JSON.parse(retained) as JsonValue })
      expect(again.result.operationId).toBe(admitted.result.operationId)
      expect(again.result.result).toEqual(status.result.result)
      const evidence = await control!({ method: 'evidence', operationId: admitted.result.operationId! }) as Evidence
      checkEvidence(evidence, status.result, expected, ++count, endpointPid)
      expect(evidence.queriedAfterRestart).toBe(true)
      expect(evidence.opWireHex).toBe(crash.opWireHex)
      const observation = await invoke('observe', { instanceId, property: 'value', maxAgeMs: 10000, evidenceKind: 'simulation' })
      expect(observation.result).toMatchObject({ value: expected, acquisition: { ticksMs: evidence.nativeReceipt.sampleTick } })
      expect(JSON.stringify(prepared.result.request)).toBe(retained)
      await capture('native-endpoint-reply-loss', { instanceId, retained, admitted, crash, replayed, status, again, evidence, observation })
    }
  }, 180000)
})
