/**
 * Takeover of an SDK request after SIGKILL, on the embedded store of a home
 * with no other process: the built `budmh --profile sdk` runtime is killed
 * while the item of its `agent/invoke` runs a tool call; a new runtime on the
 * same home takes the item over with `work/resume`, recovers the interrupted
 * turn with the recovery note first, and sends `work/settled` with the
 * item's result. `agent/invoke` with the same request id then answers from
 * the stored result and calls no model, and the id reused for another task is
 * refused. The model is a scripted local endpoint, so the case needs no key.
 */

import { existsSync } from 'node:fs'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { ChildProcess } from 'node:child_process'
import { afterEach, describe, expect, it } from 'vitest'
import { startMockLlmServer, type MockLlmServer } from '@budmh/llm-mock-server'
import { BudMetaHarness } from '../src/index.ts'
import { itemSessions } from '../../../transport/transport-cli/tests/session-logs.ts'

const cli = fileURLToPath(new URL('../../../../apps/cli/lib/bin.js', import.meta.url))

const REQUEST = 'sdk-takeover-e2e-3'
const SESSION = 'sdk-takeover-session'
const TASK = 'Run `sleep 120` with the bash tool, then reply with the single word DONE.'
const RESULT = 'DONE'

let cwd: string | undefined
let server: MockLlmServer | undefined
const harnesses: BudMetaHarness[] = []
afterEach(async () => {
  for (const harness of harnesses.splice(0)) await harness.close()
  await server?.close()
  server = undefined
  if (cwd !== undefined) await rm(cwd, { recursive: true, force: true })
  cwd = undefined
})

/** The events of the one session log under a home that runs a work item; empty until it exists. */
function itemSession(home: string): Record<string, unknown>[] {
  const found = itemSessions(home)
  return found.length === 1 ? found[0] as Record<string, unknown>[] : []
}

/** The message source kind of a user message event. */
function sourceKind(event: Record<string, unknown> | undefined): unknown {
  return ((event?.data as Record<string, unknown> | undefined)?.source as Record<string, unknown> | undefined)?.kind
}

/** One SDK runtime on the case's home, its model the case's scripted endpoint. */
function runtime(workdir: string, home: string, base: string): BudMetaHarness {
  const harness = new BudMetaHarness({
    budmhBin: cli, budmhHome: home, processCwd: workdir, cwd: workdir, profile: 'sdk', initializeTimeoutMs: 120_000, requestTimeoutMs: 240_000,
    provider: 'deepseek-official', model: 'deepseek-v4-flash',
    env: {
      ...process.env, BUDMH_AGENTS_HOME: join(home, '..', '.agents'), BUDMH_POSTGRES_URL: '',
      BUDMH_TELEMETRY_DISABLED: '1', BUDMH_PERMISSION_MODE: 'danger-full-access', DEEPSEEK_API_KEY: 'sdk-takeover-e2e', DEEPSEEK_BASE_URL: base,
    },
  })
  harnesses.push(harness)
  return harness
}

describe.skipIf(!existsSync(cli))('an SDK request taken over after SIGKILL', { retry: 0 }, () => {
  it('is recovered by work/resume in a new runtime; agent/invoke with the request id then answers from the stored result', { timeout: 300_000 }, async () => {
    cwd = await mkdtemp(join(tmpdir(), 'budmh-sdk-takeover-'))
    const home = join(cwd, '.budmh')
    server = await startMockLlmServer({
      // The tool call, then answers to every later request (the recovered turn, and the session title).
      sequence: ['tool_call_success', 'success'], repeatLast: true, toolName: 'bash', toolArguments: JSON.stringify({ command: 'sleep 120', description: 'Wait two minutes' }), successText: RESULT,
    })

    // The first runtime admits the request and is killed while the item's turn runs the tool call.
    const first = runtime(cwd, home, server.baseURL)
    await first.start()
    const invoked = await first.client.invokeAgent({ requestId: REQUEST, sessionId: SESSION, contentBlocks: [{ type: 'text', text: TASK }] })
    expect(invoked).toMatchObject({ requestId: REQUEST, sessionId: SESSION, submission: 'launched' })
    const deadline = Date.now() + 180_000
    while (!itemSession(home).some(event => event.type === 'tool/call') && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 50))
    expect(itemSession(home).some(event => event.type === 'tool/call'), 'the first runtime started its tool call').toBe(true)
    const child = first.client['child'] as ChildProcess
    const exited = new Promise(resolve => child.once('exit', resolve))
    child.kill('SIGKILL')
    await exited

    // No other process lives on the home: the new runtime takes the item over.
    const second = runtime(cwd, home, server.baseURL)
    const resumed = await second.work.resume(invoked.workItemId)
    expect(resumed).toMatchObject({ workItemId: invoked.workItemId, submission: 'taken-over', sessionId: SESSION, finalResponse: RESULT })
    expect(resumed.settled).toMatchObject({ status: 'done', text: RESULT })

    const events = itemSession(home)
    const closers = events.flatMap((event, seq) => event.type === 'turn/end' ? [{ seq, kind: ((event.data as Record<string, unknown>).reason as Record<string, unknown>).kind }] : [])
    expect(closers.map(closer => closer.kind)).toEqual(['interrupted', 'completed'])
    const afterCrash = events.slice((closers[0]?.seq ?? 0) + 1).filter(event => event.type === 'user/message')
    expect(sourceKind(afterCrash[0]), 'the recovery note comes first').toBe('work-item-recovery')
    expect(events.filter(event => event.type === 'work-item/linked')).toHaveLength(1)
    const requests = server.requests.length

    // The item ended: the same request id answers from its stored result and runs nothing.
    const again = await second.invoke(TASK, { requestId: REQUEST, sessionId: SESSION })
    expect(again).toMatchObject({ workItemId: invoked.workItemId, submission: 'settled', finalResponse: RESULT })
    expect(server.requests.length).toBe(requests)

    // The same request id for another task is refused.
    await expect(second.invoke('Something else.', { requestId: REQUEST, sessionId: SESSION }))
      .rejects.toMatchObject({ data: { code: 'sdk/request-mismatch' } })
  })
})
