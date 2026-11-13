/** Built sdk profile, durable work items and HMS operations under a keyless scripted model. */
import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { existsSync } from 'node:fs'
import { appendFile, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { BudMetaHarness } from '@budmh/sdk-client'
import { writeHostEngineIsolationPatch } from '@budmh/session-snapshot'
import type { JsonValue } from '@budmh/util-values'

const root = fileURLToPath(new URL('../../../../', import.meta.url))
const cli = join(root, 'apps/cli/lib/bin.js')
const hmsRoot = process.env.HMS_ROOT
const clients: BudMetaHarness[] = []
let directory: string | undefined
let daemon: ChildProcess | undefined
let daemonError = ''

/** A complete test-process environment with no credentials, ambient routes or host profile settings. */
function environment(): NodeJS.ProcessEnv {
  return Object.fromEntries(Object.entries(process.env).filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD|PROXY|^BUDMH_|^HMS_/iu.test(key)))
}

afterEach(async () => {
  const closed = await Promise.allSettled(clients.splice(0).map(client => client.close()))
  if (daemon) {
    const child = daemon; daemon = undefined
    if (child.exitCode === null) {
      const exited = once(child, 'exit'); child.kill('SIGTERM')
      expect((await exited)[0], daemonError).toBe(0)
    }
  }
  if (directory) await rm(directory, { recursive: true, force: true }); directory = undefined
  for (const result of closed) if (result.status === 'rejected') throw result.reason
}, 60000)

/** Read the independent checked HMS client; this observer never retries a mutation. */
function request(socket: string, method: string, params: Record<string, JsonValue>): Record<string, JsonValue> {
  const code = 'import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from hms.client import Client;print(json.dumps(Client(Path(sys.argv[2])).request(sys.argv[3],json.loads(sys.argv[4]))))'
  const result = spawnSync('python3', ['-I', '-c', code, hmsRoot!, socket, method, JSON.stringify(params)], { env: environment(), encoding: 'utf8', timeout: 10000 })
  expect(result.status, result.stderr).toBe(0)
  return JSON.parse(result.stdout) as Record<string, JsonValue>
}

/** Independent read-only observation of the synthetic plant's committed effect counter. */
function plant(cwd: string): { value: number; effects: number } {
  const code = 'import json,sqlite3,sys;db=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True);v,n=db.execute("SELECT value,effects FROM devices WHERE id=?",("sim:home-fan",)).fetchone();print(json.dumps({"value":json.loads(v),"effects":n}))'
  const result = spawnSync('python3', ['-I', '-c', code, join(cwd, 'plant/simulated-plant.db')], { env: environment(), encoding: 'utf8', timeout: 10000 })
  expect(result.status, result.stderr).toBe(0)
  return JSON.parse(result.stdout) as { value: number; effects: number }
}

/** Test-only Loader plugin running built LLM exports; every downstream service is the real sdk profile. */
function scriptedPlugin(): string {
  const llm = pathToFileURL(join(root, 'packages/llm/llm/lib/index.js')).href
  const schema = pathToFileURL(join(root, 'vendor/schemastery/lib/index.mjs')).href
  return `import { LlmAdapter, ToolCallId } from ${JSON.stringify(llm)};
import z from ${JSON.stringify(schema)};
import { readFileSync, appendFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
export const name = 'hms-sdk-script';
export const inject = ['llm'];
export const Config = z.object({ requestFile: z.string().required(), capture: z.string().required(), pause: z.boolean().required() });
export function apply(ctx, config) {
  const retained = readFileSync(config.requestFile, 'utf8');
  const prefix = randomUUID();
  class Scripted extends LlmAdapter {
    calls = 0;
    async listModels() { return [{ id: 'script', name: 'script' }]; }
    async resolveModel(provider, id) { return { provider, id, name: id, contextWindow: 1000000 }; }
    async *stream(options) {
      appendFileSync(config.capture, JSON.stringify({ messages: options.messages, tools: options.tools }) + '\\n');
      const turn = this.calls++;
      if (turn > 8) throw new Error('Scripted HMS operation did not settle');
      if (turn > 0 && config.pause) {
        const previous = options.messages.filter(message => message.role === 'tool').at(-1);
        const reply = JSON.parse(previous.content.find(block => block.type === 'text').text);
        if (!reply.ok || reply.result.executionState !== 'accepted') throw new Error('HMS did not confirm the future operation');
        if (!options.signal) throw new Error('The model call has no cancellation signal');
        if (!options.signal.aborted) await new Promise(resolve => options.signal.addEventListener('abort', resolve, { once: true }));
        options.signal.throwIfAborted();
      }
      let name = 'hardware_invoke';
      let args = { request: JSON.parse(retained) };
      if (turn > 1) {
        const previous = options.messages.filter(message => message.role === 'tool').at(-1);
        const reply = JSON.parse(previous.content.find(block => block.type === 'text').text);
        if (!reply.ok) throw new Error('HMS did not confirm its reply');
        if (reply.result.executionState === 'completed') {
          const text = 'HMS simulation completed; physical effect remains unverified.';
          yield { type: 'block-start', index: 0, blockType: 'text' };
          yield { type: 'text-delta', index: 0, text };
          yield { type: 'block-end', index: 0, block: { type: 'text', text } };
          yield { type: 'finish', reason: { kind: 'stop' } }; return;
        }
        name = 'hardware_operation'; args = { operationId: reply.result.operationId };
      }
      const id = ToolCallId(prefix + '-sdk-hms-' + turn); const argumentText = JSON.stringify(args);
      yield { type: 'block-start', index: 0, blockType: 'tool-call' };
      yield { type: 'tool-call-delta', index: 0, id, name, argumentsDelta: argumentText };
      yield { type: 'block-end', index: 0, block: { type: 'tool-call', id, name, arguments: argumentText } };
      yield { type: 'finish', reason: { kind: 'tool-calls' } };
    }
  }
  ctx.effect(() => ctx.llm.registerAdapter(['hms-sdk-keyless'], new Scripted()));
}
`
}

async function setup(pause: boolean) {
  directory = await mkdtemp(join(tmpdir(), 'hms-sdk-profile-'))
  const cwd = directory
  const socket = join(cwd, 'hms.sock')
  daemonError = ''
  daemon = spawn('python3', ['-m', 'hms', 'serve', '--init-simulation', '--state-dir', join(cwd, 'plant'), '--socket', socket], {
    cwd: hmsRoot, env: environment(), stdio: ['ignore', 'pipe', 'pipe'],
  })
  daemon.stderr!.on('data', (chunk) => { daemonError += String(chunk) })
  const ready = await Promise.race([once(daemon.stdout!, 'data'), once(daemon, 'exit').then(() => { throw new Error(daemonError || 'HMS exited before readiness') })])
  expect(JSON.parse(String(ready[0]))).toMatchObject({ ready: true, deployment: 'simulation:local' })
  const now = Date.now()
  const namespace = request(socket, 'namespace', { expiresUnixMs: now + 600000 })
  const prepared = request(socket, 'prepare', {
    instanceId: 'sim:home-fan', actionId: 'set_level', arguments: { level: 55, unit: 'percent' }, operationKey: 'sdk-retained',
    replayNamespace: namespace.token!, requiredEffect: 'capability_completion', timing: {
      notBeforeUnixMs: now + (pause ? 300000 : 0), latestStartUnixMs: now + 420000, maxRunMs: 5000, latestCompletionUnixMs: now + 480000,
    },
  })
  const requestFile = join(cwd, 'immutable-request.json')
  const capture = join(cwd, 'model-calls.jsonl')
  await writeFile(requestFile, JSON.stringify(prepared.request), { flag: 'wx', mode: 0o600 })
  await writeFile(capture, '', { flag: 'wx', mode: 0o600 })
  const plugin = join(cwd, 'scripted-model.mjs')
  await writeFile(plugin, scriptedPlugin(), { flag: 'wx', mode: 0o600 })
  const patch = join(cwd, 'hms-sdk.cordis.yml')
  const rows = [
    { id: 'llm-deepseek', disabled: true }, { id: 'session-title-llm', disabled: true },
    { id: 'session-log-bud', config: { enabled: false } },
    { id: 'session-persistence-jsonl', config: { root: join(cwd, '.budmh/sessions'), compression: 'none' } },
    { insert: [
      { id: 'hms-sdk-script', name: pathToFileURL(plugin).href, config: { requestFile, capture, pause } },
      { id: 'hardware-hms', name: pathToFileURL(join(root, 'packages/experimental/hardware-hms/lib/index.js')).href, config: { hmsRoot, socketPath: socket } },
      { id: 'tool-hardware', name: pathToFileURL(join(root, 'packages/experimental/tool-hardware/lib/index.js')).href },
    ] },
  ]
  await writeFile(patch, JSON.stringify(rows), { flag: 'wx', mode: 0o600 })
  const patches = [writeHostEngineIsolationPatch(cwd), patch]
  const makeClient = () => {
    const harness = new BudMetaHarness({
      budmhBin: cli, budmhHome: join(cwd, '.budmh'), processCwd: cwd, cwd, profile: 'sdk', patches,
      provider: 'hms-sdk-keyless', model: 'script', initializeTimeoutMs: 120000, requestTimeoutMs: 120000,
      env: { ...environment(), BUDMH_AGENTS_HOME: join(cwd, '.agents'), BUDMH_POSTGRES_URL: '', BUDMH_TELEMETRY_DISABLED: '1', BUDMH_PERMISSION_MODE: 'danger-full-access' },
    })
    clients.push(harness); return harness
  }
  return { cwd, socket, requestFile, capture, makeClient }
}

describe.skipIf(!hmsRoot || process.platform !== 'linux' || !existsSync(cli))('built SDK profile with HMS', () => {
  it('retains one HMS effect across native and work-item replay, then reopens the stored work item', async () => {
    const { cwd, socket, requestFile, capture, makeClient } = await setup(false)
    const first = makeClient()
    const result = await first.invoke('Execute the retained simulation request and report its evidence.', { requestId: 'hms-sdk-work', sessionId: 'hms-sdk-session' })
    expect(result.finalResponse).toBe('HMS simulation completed; physical effect remains unverified.')
    expect(result.settled.status).toBe('done')
    const calls = result.events.filter(event => event.type === 'tool/call')
    const invokes = calls.filter(event => event.data.name === 'hardware_invoke')
    expect(invokes).toHaveLength(2)
    expect(invokes[0]!.data.arguments).toEqual(invokes[1]!.data.arguments)
    const retained = JSON.parse(await readFile(requestFile, 'utf8')) as JsonValue
    const receipt = request(socket, 'invoke', { request: retained })
    expect(receipt).toMatchObject({ executionState: 'completed', effectVerification: 'unverified' })
    expect(receipt.result).toMatchObject({ evidenceKind: 'simulation' })
    const events = request(socket, 'events', { operationId: receipt.operationId! })
    expect(plant(cwd)).toEqual({ value: 55, effects: 1 })
    const before = await readFile(capture, 'utf8')
    const again = await first.invoke('Execute the retained simulation request and report its evidence.', { requestId: 'hms-sdk-work', sessionId: 'hms-sdk-session' })
    expect(again).toMatchObject({ workItemId: result.workItemId, submission: 'settled', finalResponse: result.finalResponse })
    await expect(first.invoke('Changed task.', { requestId: 'hms-sdk-work', sessionId: 'hms-sdk-session' })).rejects.toMatchObject({ data: { code: 'sdk/request-mismatch' } })
    expect(await readFile(capture, 'utf8')).toBe(before)
    await first.close()
    const reopened = makeClient()
    const resumed = await reopened.work.resume(result.workItemId)
    expect(resumed).toMatchObject({ workItemId: result.workItemId, submission: 'settled', finalResponse: result.finalResponse })
    expect(await readFile(capture, 'utf8')).toBe(before)
    const session = await reopened.resumeSession(result.sessionId)
    const continued = await session.run('Reconcile the retained simulation request without minting another key.')
    expect(continued.finalResponse).toBe(result.finalResponse)
    const restoredCalls = await readFile(capture, 'utf8')
    expect(restoredCalls.slice(before.length)).toContain(invokes[0]!.data.callId)
    const final = request(socket, 'invoke', { request: retained })
    expect(final.operationId).toBe(receipt.operationId)
    expect(request(socket, 'events', { operationId: receipt.operationId! })).toEqual(events)
    expect(plant(cwd)).toEqual({ value: 55, effects: 1 })
    if (process.env.HMS_SDK_CAPTURE) await appendFile(process.env.HMS_SDK_CAPTURE, JSON.stringify({ scenario: 'work-replay-reopen', result, receipt, events, resumed, continued, plant: plant(cwd), modelCalls: restoredCalls }) + '\n')
  }, 240000)

  it('cancels a Harness item without treating that cancellation as HMS operation cancellation', async () => {
    const { cwd, socket, capture, makeClient } = await setup(true)
    const harness = makeClient()
    await harness.start()
    const admitted = await harness.client.invokeAgent({ requestId: 'hms-sdk-cancel', sessionId: 'hms-sdk-cancel-session', contentBlocks: [{ type: 'text', text: 'Admit the retained future simulation request, then wait.' }] })
    await expect.poll(async () => (await readFile(capture, 'utf8')).trim().split('\n').length, { timeout: 90000, interval: 100 }).toBe(2)
    const second = JSON.parse((await readFile(capture, 'utf8')).trim().split('\n')[1]!) as { messages: { role: string; content: { type: string; text?: string }[] }[] }
    const previous = second.messages.filter(message => message.role === 'tool').at(-1)
    const reported = JSON.parse(previous!.content.find(block => block.type === 'text')!.text!) as { ok: boolean; result: { operationId: string } }
    expect(reported).toMatchObject({ ok: true, result: { executionState: 'accepted', mayHaveActed: false } })
    expect(typeof reported.result.operationId).toBe('string')
    const before = request(socket, 'operation', { operationId: reported.result.operationId })
    expect(before).toMatchObject({ executionState: 'accepted', mayHaveActed: false })
    const canceled = await harness.work.cancel(admitted.workItemId, 'End the Harness activity only')
    expect(canceled).toMatchObject({ kind: 'applied', item: { status: 'cancelled' } })
    const after = request(socket, 'operation', { operationId: before.operationId! })
    expect(after).toMatchObject({ operationId: before.operationId, executionState: 'accepted', cancellationState: 'not_requested', mayHaveActed: false })
    await harness.close()
    const closed = request(socket, 'operation', { operationId: before.operationId! })
    expect(closed.executionState).toBe('accepted')
    expect(plant(cwd)).toEqual({ value: 0, effects: 0 })
    request(socket, 'cancel', { operationId: before.operationId! })
    await expect.poll(() => request(socket, 'operation', { operationId: before.operationId! }).executionState, { timeout: 10000 }).toBe('canceled')
    const stopped = request(socket, 'operation', { operationId: before.operationId! })
    expect(stopped.mayHaveActed).toBe(false)
    expect(plant(cwd)).toEqual({ value: 0, effects: 0 })
    if (process.env.HMS_SDK_CAPTURE) await appendFile(process.env.HMS_SDK_CAPTURE, JSON.stringify({ scenario: 'work-cancel-is-not-hms-cancel', admitted, canceled, reported, before, after, closed, stopped, plant: plant(cwd) }) + '\n')
  }, 240000)
})
