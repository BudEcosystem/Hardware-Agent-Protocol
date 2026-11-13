/**
 * Expected output of every SDK work-item method and notification, from the
 * TypeScript client against the built `budmh --profile sdk`: one runtime
 * replays the recorded `snapshots/sdk/work-item-invoke` turn for
 * `agent/invoke`, then reads and operates on that item and on an unrouted
 * trigger of a webhook-kind Source (`tests/fixtures/work-items.cordis.yml`).
 * Each method's normalized result, and the ordered `work/settled` and
 * `work/attention` notifications, are compared with
 * `expected/work-items/<method>.json`; the Python SDK compares its own run
 * with the same files in `python/sdk/tests/expected/work-items`
 * (`pnpm run test:expected:refresh` rewrites them).
 */

import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir, userInfo } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { BudMetaHarness, type HarnessNotification, type NotificationSubscription } from '../src/index.ts'

const root = fileURLToPath(new URL('../../../../', import.meta.url))
const cli = join(root, 'apps/cli/lib/bin.js')
const scenario = join(root, 'snapshots/sdk/work-item-invoke')
const composition = join(root, 'snapshots/sdk/bash-tool')
const patch = fileURLToPath(new URL('./fixtures/work-items.cordis.yml', import.meta.url))
const expectedDir = fileURLToPath(new URL('./expected/work-items/', import.meta.url))
const pythonExpectedDir = join(root, 'python/sdk/tests/expected/work-items')
const refresh = process.env.BUDMH_SNAPSHOT === 'refresh'

const SESSION_ID = 'fixture-root-session'

/** Volatile values of the run, replaced by tokens: the home, the incarnation and the workspace. */
const tokens = new Map<string, string>()
/** Derived ids (work items `wi_`, routing decisions `rd_`) in order of first appearance across the run. */
const derived = new Map<string, string>()
/** The token kind of each derived-id prefix. */
const DERIVED_KINDS: Readonly<Record<string, string>> = { wi: 'item', rd: 'decision' }

/**
 * Normalize one wire value: ids, times, the operator and paths become tokens. The Python twin applies the same
 * rules in the same order, so both languages produce one expected file per method.
 */
function normalize(value: unknown): unknown {
  let text = JSON.stringify(value)
  for (const [raw, token] of tokens) text = text.replaceAll(raw, token)
  text = text.replace(/\b(wi|rd)_[a-z2-7]{26}\b/gu, (id, prefix: string) => {
    const kind = DERIVED_KINDS[prefix] as string
    if (!derived.has(id)) derived.set(id, `{{${kind}:${String([...derived.values()].filter(token => token.startsWith(`{{${kind}:`)).length + 1)}}}`)
    return derived.get(id) as string
  })
  text = text
    .replace(/"(at|since|[A-Za-z]+At|[A-Za-z]+Ms)":\d+/gu, '"$1":0')
    .replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z/gu, '{{time}}')
  const parsed: unknown = JSON.parse(text)
  return parsed
}

/** Compare one normalized output with its expected file, or rewrite both languages' files on refresh. */
function check(name: string, value: unknown): void {
  const normalized = normalize(value)
  const file = `${name}.json`
  const text = `${JSON.stringify(normalized, null, 2)}\n`
  if (refresh) {
    writeFileSync(join(expectedDir, file), text)
    writeFileSync(join(pythonExpectedDir, file), text)
  }
  expect(normalized, name).toEqual(JSON.parse(readFileSync(join(expectedDir, file), 'utf8')))
}

/** Wait for the first notification of a method about an item, keeping every notification read meanwhile. */
async function notificationOf(
  subscription: NotificationSubscription, seen: HarnessNotification[], method: string, workItemId: string,
): Promise<void> {
  const found = (): boolean => seen.some(entry => entry.method === method && entry.params.workItemId === workItemId)
  while (!found()) seen.push(await subscription.next())
}

let workdir: string
let harness: BudMetaHarness

beforeAll(() => {
  workdir = realpathSync.native(mkdtempSync(join(tmpdir(), 'budmh-sdk-work-items-')))
  mkdirSync(expectedDir, { recursive: true })
  mkdirSync(pythonExpectedDir, { recursive: true })
  const fixture = readFileSync(join(scenario, 'session.v4.jsonl'), 'utf8').replaceAll('{{cwd}}', workdir)
  const replay = join(workdir, '.replay-fixtures', 'session.v4.jsonl')
  mkdirSync(join(workdir, '.replay-fixtures'))
  writeFileSync(replay, fixture)
  // The replay composition names the test package @budmh/llm-replay, which the built profile cannot resolve by name.
  const replayPatch = join(workdir, '.snapshot-patches', 'cordis.snapshot.yml')
  mkdirSync(join(workdir, '.snapshot-patches'))
  writeFileSync(replayPatch, readFileSync(join(composition, 'cordis.snapshot.yml'), 'utf8')
    .replace("name: '@budmh/llm-replay'", `name: '${pathToFileURL(join(root, 'packages/test-support/llm-replay/lib/index.js')).href}'`))
  tokens.set(workdir, '{{cwd}}')
  // The operator the runtime acts for is the account that runs it.
  tokens.set(`sdk:${userInfo().username}`, 'sdk:{{user}}')
  harness = new BudMetaHarness({
    budmhBin: cli, budmhHome: join(workdir, '.budmh'), processCwd: workdir, cwd: workdir, profile: 'sdk',
    patches: [join(composition, 'cordis.yml'), replayPatch, patch],
    provider: 'deepseek-official', model: 'deepseek-v4-flash', initializeTimeoutMs: 110_000, requestTimeoutMs: 110_000,
    env: {
      ...process.env,
      BUDMH_SNAPSHOT: 'replay', BUDMH_SNAPSHOT_FILE: replay, BUDMH_SNAPSHOT_PROVIDER: 'deepseek-official', BUDMH_SNAPSHOT_MODEL: 'deepseek-v4-flash',
      BUDMH_PERMISSION_MODE: 'danger-full-access', BUDMH_TELEMETRY_DISABLED: '1', BUDMH_AGENTS_HOME: join(workdir, '.agents'), BUDMH_POSTGRES_URL: '',
      NODE_OPTIONS: [process.env.NODE_OPTIONS, '--disable-warning=ExperimentalWarning'].filter(Boolean).join(' '),
    },
  })
})

afterAll(async () => {
  await harness.close()
  rmSync(workdir, { recursive: true, force: true })
})

describe.skipIf(!existsSync(cli))('SDK work-item methods', { timeout: 300_000 }, () => {
  it('answers every method and notification as the expected outputs pin', async () => {
    await harness.start()
    const client = harness.client
    const subscription = client.subscribe(notification => notification.method === 'work/settled' || notification.method === 'work/attention')
    const seen: HarnessNotification[] = []
    try {
      const task = JSON.parse(readFileSync(join(scenario, 'session.v4.jsonl'), 'utf8').split('\n')
        .find(line => line.includes('"type":"user/message"')) as string) as { data: { content: { type: 'text'; text: string }[] } }
      const invoked = await client.invokeAgent({ requestId: 'expected-invoke', sessionId: SESSION_ID, contentBlocks: task.data.content })
      await notificationOf(subscription, seen, 'work/settled', invoked.workItemId)
      const detail = await client.getWorkItem(invoked.workItemId)
      const { placement } = detail.item
      tokens.set(placement.home, '{{home}}')
      if (placement.incarnation !== undefined) tokens.set(placement.incarnation, '{{incarnation}}')
      check('agent-invoke', invoked)
      check('work-get', detail)
      check('work-resume', await client.resumeWorkItem(invoked.workItemId))
      check('work-retry', await client.retryWorkItem({ workItemId: invoked.workItemId }))
      check('trigger-rules', await client.triggerRules())

      const admission = await client.admitTrigger({
        sourceInstance: 'ops-hook', kind: 'event', event: 'close.quarter', nativeKey: 'delivery-1',
        contentBlocks: [{ type: 'text', text: 'Close the first quarter.' }],
      })
      check('trigger-admit', admission)
      if (admission.kind !== 'admitted') throw new Error('the trigger was not admitted')
      const unrouted = admission.items[0]?.itemId as string
      await notificationOf(subscription, seen, 'work/attention', unrouted)
      check('trigger-explain', await client.explainTrigger('ops-hook:delivery-1'))
      check('trigger-override', await client.overrideTrigger({ rule: 'config:close', patch: { kinds: ['event'] }, reason: 'only events close the month' }))
      check('trigger-clear-override', await client.clearTriggerOverride('config:close', 'the override was a trial'))
      check('work-list', await client.listWorkItems({ by: 'attention' }))
      check('work-answer', await client.answerWorkItem({ workItemId: unrouted, answer: { kind: 'text', text: 'Use the Q1 ledger.' }, key: 'expected-answer' }))
      check('work-route', await client.routeWorkItem(unrouted, 'ledger'))
      check('work-cancel', await client.cancelWorkItem(unrouted, 'closed by hand'))
      await notificationOf(subscription, seen, 'work/settled', unrouted)
      check('work-settled', seen.filter(entry => entry.method === 'work/settled').map(entry => entry.params))
      check('work-attention', seen.filter(entry => entry.method === 'work/attention').map(entry => entry.params))
    } finally {
      subscription.close()
    }
  })
})
