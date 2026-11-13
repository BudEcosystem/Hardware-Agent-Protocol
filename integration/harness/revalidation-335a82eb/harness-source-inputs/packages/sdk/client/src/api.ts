/**
 * High-level run API over {@link HarnessClient}: `BudMetaHarness` owns one
 * runtime subprocess across many sessions; `HarnessSession.run` sends a
 * prompt and settles when the whole agent next becomes idle.
 *
 * @module @budmh/sdk-client/api
 */

import { randomUUID } from 'node:crypto'
import { resolve } from 'node:path'
import type { SessionEvent, TurnEndReason } from '@budmh/session'
import { createProcessHarnessClient, HarnessClient, isRecord, SdkProtocolError } from './client.ts'
import type { RuntimeProcessOptions } from './launch.ts'
import type { ContentBlock, BudMetaHarnessOptions, HarnessNotification, RunResult, SdkPromptContentBlock } from './types.ts'
import type { VoiceCallRequest } from '@budmh/api-voice/types'
import { VoiceCall } from './voice.ts'
import { VoiceCallDriver, type VoiceCallDriverOptions, type VoiceScript } from './voice-driver.ts'
import {
  HarnessTriggers, HarnessWork, isSettledPayload,
  type FollowOptions, type InvokeOptions, type InvokeResult, type ItemStart, type WorkRunResult,
} from './work.ts'

/**
 * Reusable SDK for running Bud Meta Harness agent turns in a runtime
 * subprocess. The subprocess starts lazily on first use and stays owned by
 * this instance until {@link close}; always close (or `await using`) so the
 * child is reaped.
 */
export class BudMetaHarness implements AsyncDisposable {
  private clientInstance: HarnessClient
  private readonly createClient: () => HarnessClient
  private readonly cwd: string
  private readonly provider: string
  private readonly model: string
  private readonly reasoningEffort: BudMetaHarnessOptions['reasoningEffort']
  private readonly maxTokens: number | undefined
  private initialized: Promise<void> | undefined
  private closed = false

  /** @param options - budmh launch configuration plus the session route, effort, and output cap. */
  constructor(options?: BudMetaHarnessOptions)
  constructor(options: BudMetaHarnessOptions = {}, clientFactory?: () => HarnessClient) {
    this.createClient = clientFactory ?? (() => new HarnessClient(options))
    this.clientInstance = this.createClient()
    // Absolute before the handshake: the child spawns relative to THIS
    // process's cwd, but the wire cwd is resolved again inside the child — a
    // relative value would double-resolve (e.g. `worker` → `worker/worker`).
    this.cwd = resolve(options.cwd ?? options.processCwd ?? process.cwd())
    this.provider = options.provider ?? 'deepseek-official'
    this.model = options.model ?? 'deepseek-v4-flash'
    this.reasoningEffort = options.reasoningEffort
    this.maxTokens = options.maxTokens
  }

  /**
   * The underlying JSON-RPC client (exposed for low-level access). A failed
   * handshake swaps in a fresh instance only after cleanup proves the runtime
   * exited; cleanup failure retains this client, so do not cache it across a
   * failed {@link start}.
   * @returns the client currently owning the runtime subprocess.
   */
  get client(): HarnessClient {
    return this.clientInstance
  }

  /**
   * Start the subprocess and perform the `initialize` handshake once. On
   * failure, successful SDK-owned cleanup reaps the runtime and installs a
   * fresh client (`HarnessClient.close` is permanent), so a later call retries
   * with a new subprocess unless {@link close} already ended this harness. If
   * cleanup also fails, rejects with an `AggregateError` whose ordered errors
   * preserve both causes and retains the failed client rather than spawning
   * alongside a process whose exit was not proved.
   * @returns settlement of the (memoized) handshake.
   */
  start(): Promise<void> {
    this.initialized ??= (async () => {
      try {
        this.clientInstance.start()
        await this.clientInstance.initialize({
          cwd: this.cwd,
          provider: this.provider,
          model: this.model,
          ...this.reasoningEffort === undefined ? {} : { reasoningEffort: this.reasoningEffort },
          ...this.maxTokens === undefined ? {} : { maxTokens: this.maxTokens },
        })
      } catch (error) {
        this.initialized = undefined
        try {
          await this.clientInstance.close()
        } catch (cleanupError: unknown) {
          throw new AggregateError(
            [error, cleanupError],
            'Bud Meta Harness initialization and cleanup failed',
          )
        }
        if (!this.closed) this.clientInstance = this.createClient()
        throw error
      }
    })()
    return this.initialized
  }

  /**
   * Open a session handle (no wire traffic; the runtime creates the session
   * on its first prompt or working-directory operation).
   * @param sessionId - explicit id to reuse; omitted mints a fresh one.
   * @returns the session handle.
   */
  session(sessionId?: string): HarnessSession {
    return new HarnessSession(this, sessionId ?? `session-${randomUUID().replaceAll('-', '')}`)
  }

  /**
   * Start the runtime and restore a persisted session without sending input.
   * The configured Harness home must contain its history; missing or occupied sessions reject.
   * @param sessionId - exact persisted identity to continue.
   * @returns a handle ready to run new prompts on the restored history.
   */
  async resumeSession(sessionId: string): Promise<HarnessSession> {
    await this.start()
    await this.client.resumeSession(sessionId)
    return new HarnessSession(this, sessionId)
  }

  /**
   * Voice calls of this runtime's sessions; the runtime's profile must mount `@budmh/api-voice/sdk` and a speech
   * pipeline provider.
   * @returns `start` opens a call; `drive` opens one under a {@link VoiceCallDriver} script.
   */
  get voice(): HarnessVoice {
    return {
      start: async (sessionId, request) => {
        await this.start()
        return VoiceCall.start(this.client, sessionId, request)
      },
      drive: async (sessionId, request, script, options) => {
        await this.start()
        return VoiceCallDriver.start(this.client, sessionId, request, script, options)
      },
    }
  }

  /**
   * Run one request as a work item (`agent/invoke`) and follow it until it ends. The item adopts the named SDK
   * session (composed when unknown) or a session the runtime mints; a repeated request id continues the item the
   * first call admitted. While the item waits for a person, `work/attention` arrives through `onNotification`, and
   * {@link work}`.answer` from another task answers it.
   * @param input - task text, or content blocks sent verbatim.
   * @param options - request id, session, agent of a new session, and observer.
   * @returns the item's run, with its request id and `work/settled` notification.
   */
  async invoke(input: string | SdkPromptContentBlock[], options: InvokeOptions = {}): Promise<InvokeResult> {
    await this.start()
    const client = this.client
    let requestId = options.requestId
    const run = await this.follow(async () => {
      const result = await client.invokeAgent({
        contentBlocks: normalizeInput(input),
        ...options.requestId === undefined ? {} : { requestId: options.requestId },
        ...options.sessionId === undefined ? {} : { sessionId: options.sessionId },
        ...options.agent === undefined ? {} : { agent: options.agent },
      })
      requestId = result.requestId
      return result
    }, options)
    /* v8 ignore next -- the follower returns only after the start resolved */
    if (requestId === undefined) throw new SdkProtocolError('agent/invoke returned no request id')
    return { ...run, requestId }
  }

  /**
   * Work items of this runtime, read and operated on as `budmh work` does.
   * @returns `get`, `list`, `answer`, `cancel`, `retry`, `route`, and `resume`, which takes an item over.
   */
  get work(): HarnessWork {
    return new HarnessWork(async () => {
      await this.start()
      return this.client
    }, async (start, options) => {
      await this.start()
      return this.follow(start, options)
    })
  }

  /**
   * Trigger rules of this runtime, read and overridden as `budmh trigger` does, and generic trigger admission.
   * @returns `rules`, `override`, `clearOverride`, `explain` and `admit`.
   */
  get triggers(): HarnessTriggers {
    return new HarnessTriggers(async () => {
      await this.start()
      return this.client
    })
  }

  /**
   * Start an item and follow it until its `work/settled`. The subscription opens before the request, so session
   * events and a settlement that precede the response are kept.
   */
  private async follow(start: ItemStart, options: FollowOptions = {}): Promise<WorkRunResult> {
    const subscription = this.client.subscribe()
    try {
      const started = await start()
      const events: SessionEvent[] = []
      const notifications: HarnessNotification[] = []
      for (;;) {
        const notification = await subscription.next()
        const { method, params } = notification
        const ofSession = started.sessionId !== undefined && params.sessionId === started.sessionId
          && (method === 'session.event' || method === 'session.status')
        const ofItem = (method === 'work/settled' || method === 'work/attention') && params.workItemId === started.workItemId
        if (!ofSession && !ofItem) continue
        if (method === 'session.event') events.push(validatedSessionEvent(params.event))
        notifications.push(notification)
        options.onNotification?.(notification)
        if (method !== 'work/settled') continue
        if (!isSettledPayload(params)) throw new SdkProtocolError(`work/settled carried no settled item: ${JSON.stringify(params)}`)
        return {
          sessionId: started.sessionId ?? '',
          // An item that had ended streamed no turn here; its stored result is the answer.
          finalResponse: events.some(event => event.type === 'assistant/message') ? finalResponse(events) : params.text,
          events,
          notifications,
          workItemId: started.workItemId,
          submission: started.submission,
          settled: params,
        }
      }
    } finally {
      subscription.close()
    }
  }

  /**
   * Run one prompt on a fresh (or named) session.
   * @param input - prompt text, or content blocks sent verbatim.
   * @param options - optional session id and per-notification observer.
   * @returns the owned activity interval.
   */
  run(input: string | SdkPromptContentBlock[], options?: RunOptions): Promise<RunResult> {
    return this.session(options?.sessionId).run(input, options)
  }

  /**
   * Shut down and reap the runtime subprocess. Idempotent and terminal —
   * a closed harness no longer retries a failed handshake.
   * @returns settlement of the complete teardown.
   */
  close(): Promise<void> {
    this.closed = true
    return this.clientInstance.close()
  }

  /**
   * `await using` support: {@link close}.
   * @returns settlement of the teardown.
   */
  [Symbol.asyncDispose](): Promise<void> {
    return this.close()
  }
}

/** Construct the high-level API against a generic process for package-local fake-runtime tests. */
export function createProcessBudMetaHarness(
  runtime: RuntimeProcessOptions,
  options: BudMetaHarnessOptions = {},
): BudMetaHarness {
  const Constructor = BudMetaHarness as new (
    publicOptions: BudMetaHarnessOptions,
    clientFactory: () => HarnessClient,
  ) => BudMetaHarness
  return new Constructor({
    ...runtime.cwd === undefined ? {} : { processCwd: runtime.cwd },
    ...options,
  }, () => createProcessHarnessClient(runtime))
}

/** The voice calls of a {@link BudMetaHarness}. */
export interface HarnessVoice {
  /**
   * Open a voice call of a session.
   * @param sessionId - the SDK session; an unknown id creates it.
   * @param request - transport, language, provider, voice, formats and barge-in.
   * @returns the open call.
   */
  start(sessionId: string, request: VoiceCallRequest): Promise<VoiceCall>
  /**
   * Open a voice call of a session under a scripted caller.
   * @param sessionId - the SDK session; an unknown id creates it.
   * @param request - the call request.
   * @param script - the caller's script.
   * @param options - step bounds.
   * @returns the driver; `run()` plays the script.
   */
  drive(sessionId: string, request: VoiceCallRequest, script: VoiceScript, options?: VoiceCallDriverOptions): Promise<VoiceCallDriver>
}

/** Per-run options: target session and streaming observer. */
export interface RunOptions {
  /** Session id to run on; omitted mints a fresh session per call. */
  sessionId?: string
  /** Observer invoked with every notification for this session tree, in wire order. */
  onNotification?: (notification: HarnessNotification) => void
}

/**
 * One SDK session: a stable id plus owned activity intervals.
 */
export class HarnessSession {
  /**
   * @param harness - the owning harness (supplies the client and handshake).
   * @param id - the wire session id this handle runs on.
   */
  constructor(readonly harness: BudMetaHarness, readonly id: string) {}

  /**
   * Read the effective directory and recover a missing directory to the Session origin.
   * @returns the absolute directory used by new independent operations.
   */
  async getWorkingDirectory(): Promise<string> {
    await this.harness.start()
    return this.harness.client.getWorkingDirectory(this.id)
  }

  /**
   * Change the effective directory without moving existing processes or changing permissions.
   * @param path - absolute or Session-current-directory-relative directory.
   * @returns the validated absolute directory.
   */
  async setWorkingDirectory(path: string): Promise<string> {
    await this.harness.start()
    return this.harness.client.setWorkingDirectory(this.id, path)
  }

  /**
   * Queue one prompt, then observe the whole session through its next idle.
   * @param input - prompt text, or content blocks sent verbatim.
   * @param options - optional per-notification observer.
   * @returns the owned activity interval; rejects on transport loss, timeout,
   * or a protocol error.
   */
  async run(input: string | SdkPromptContentBlock[], options?: Pick<RunOptions, 'onNotification'>): Promise<RunResult> {
    await this.harness.start()
    const client = this.harness.client
    const contentBlocks = normalizeInput(input)
    const events: SessionEvent[] = []
    const notifications: HarnessNotification[] = []

    const subscription = client.subscribeSessionTree(this.id)
    const collect = (notification: HarnessNotification): void => {
      if (notification.method === 'session.event' && notification.params.sessionId === this.id) {
        // Wire boundary: the envelope feeds the typed RunResult, so a
        // malformed runtime surfaces as a protocol error, not as type-invalid
        // data (or a TypeError out of finalResponse).
        const event = validatedSessionEvent(notification.params.event)
        notifications.push(notification)
        options?.onNotification?.(notification)
        events.push(event)
        return
      }
      notifications.push(notification)
      options?.onNotification?.(notification)
    }
    try {
      const messageId = await client.prompt(this.id, contentBlocks)
      let received = false
      while (true) {
        const notification = await subscription.next()
        if (!received) {
          if (notification.method !== 'session.event'
            || notification.params.sessionId !== this.id
            || !isInboxReceipt(notification.params.event, messageId)) continue
          received = true
        }
        collect(notification)
        if (notification.method === 'session.status'
          && notification.params.sessionId === this.id
          && notification.params.status === 'idle') break
      }
    } finally {
      subscription.close()
    }

    return {
      sessionId: this.id,
      finalResponse: finalResponse(events),
      events,
      notifications,
    }
  }
}

/**
 * Normalize run input: a string becomes one text block; blocks pass verbatim.
 * @param input - prompt text or content blocks.
 * @returns the content blocks to send.
 */
export function normalizeInput(input: string | SdkPromptContentBlock[]): SdkPromptContentBlock[] {
  return typeof input === 'string' ? [{ type: 'text', text: input }] : input
}

/** Validate the provider-read fields of one wire turn-end reason. */
function validatedTurnEndReason(value: unknown): TurnEndReason {
  if (!isRecord(value) || typeof value.kind !== 'string') {
    throw new SdkProtocolError(`turn/end carried no reason envelope: ${JSON.stringify(value)}`)
  }
  if (value.kind === 'aborted') {
    if (!isRecord(value.reason) || typeof value.reason.kind !== 'string') {
      throw new SdkProtocolError(`turn/end carried a malformed aborted reason: ${JSON.stringify(value)}`)
    }
    switch (value.reason.kind) {
      case 'user':
      case 'parent':
      case 'disposed':
      case 'legacy':
        break
      case 'hook':
        if (typeof value.reason.reason !== 'string') {
          throw new SdkProtocolError(`turn/end carried a malformed hook abort reason: ${JSON.stringify(value)}`)
        }
        break
      default:
        throw new SdkProtocolError(`turn/end carried an unknown abort reason: ${JSON.stringify(value)}`)
    }
  }
  return value as TurnEndReason
}

/**
 * Validate the event envelope and assistant/turn fields consumed by SDK readers.
 * @param value - the raw `session.event` event payload.
 * @returns the event, or throws a protocol error for malformed consumed fields.
 */
export function validatedSessionEvent(value: unknown): SessionEvent {
  if (!isRecord(value) || typeof value.type !== 'string') {
    throw new SdkProtocolError(`session.event carried no event envelope: ${JSON.stringify(value)}`)
  }
  // The one variant this module reads into (finalResponse) must carry
  // kind-tagged content blocks; other variants pass through under their
  // envelope shape.
  if (value.type === 'assistant/message') {
    const message = isRecord(value.data) ? value.data.message : undefined
    const content = isRecord(message) ? message.content : undefined
    if (!Array.isArray(content) || !content.every(block => isRecord(block) && typeof block.type === 'string')) {
      throw new SdkProtocolError(`assistant/message event carried malformed content: ${JSON.stringify(value)}`)
    }
  }
  if (value.type === 'turn/end') {
    const data = isRecord(value.data) ? value.data : undefined
    if (data === undefined) {
      throw new SdkProtocolError(`turn/end event carried malformed data: ${JSON.stringify(value)}`)
    }
    validatedTurnEndReason(data.reason)
  }
  return value as SessionEvent
}

/** Whether a raw session event is the durable enqueue receipt for `messageId`. */
function isInboxReceipt(value: unknown, messageId: string): boolean {
  if (!isRecord(value) || value.type !== 'agent/inbox/spliced' || !isRecord(value.data)) return false
  const inserted = value.data.inserted
  return Array.isArray(inserted) && inserted.some(message => isRecord(message) && message.id === messageId)
}

/**
 * Extract the concatenated text of the last assistant message.
 * @param events - the activity interval's `session.event` payloads in wire order.
 * @returns the final response text, or `''` when no assistant message exists.
 */
export function finalResponse(events: SessionEvent[]): string {
  for (let index = events.length - 1; index >= 0; index--) {
    const event = events[index]
    if (event?.type !== 'assistant/message') continue
    return event.data.message.content
      .filter((block): block is ContentBlock & { type: 'text' } => block.type === 'text')
      .map(block => block.text)
      .join('')
  }
  return ''
}
