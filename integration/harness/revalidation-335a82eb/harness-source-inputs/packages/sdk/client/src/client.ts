/**
 * Low-level JSON-RPC client for a Bud Meta Harness SDK runtime subprocess.
 * {@link HarnessClient} owns the child process: it spawns the runtime, speaks
 * the `@budmh/sdk-protocol` wire over the child's stdio, fans
 * server notifications out to subscriptions, and tears the child down to
 * quiescence through a private EOF → SIGTERM → SIGKILL ladder. The design
 * twin is the Python SDK's `HarnessClient` (`python/sdk`); both drive the
 * same runtime protocol. This client runs OUTSIDE any harness context, so it
 * spawns directly rather than through the `budmh-subprocess` service — the
 * seam's documented exception for SDK-managed transports.
 *
 * @module @budmh/sdk-client/client
 */

import { spawn, type ChildProcess } from 'node:child_process'
import {
  JsonRpcLineTransport,
  JsonRpcResponseError,
  type AgentInvokeParams,
  type InitializeParams,
  type InitializeResult,
  type SessionPromptParams,
  type SdkPromptContentBlock,
  type SdkRequestMethod,
  type SdkRequestResult,
  type TriggerAdmitParams,
  type TriggerOverrideParams,
  type TriggerRulesParams,
  type WorkAnswerParams,
  type WorkListParams,
  type WorkRetryParams,
} from '@budmh/sdk-protocol'
import { disposeRuntimeProcess } from './dispose.ts'
import { resolveBudmhLaunch, type RuntimeProcessOptions } from './launch.ts'
import type { HarnessClientOptions, HarnessNotification, NotificationFilter } from './types.ts'

/** Retained stderr lines used to diagnose an unexpected runtime death. */
const STDERR_TAIL_LIMIT = 400

/** Grace for the runtime's stdio streams to settle after its exit edge. */
const STREAM_SETTLE_MS = 100

/**
 * The runtime subprocess is gone or unusable: it exited, its stdio closed, or
 * it was never launchable. The message carries the exit code and a stderr
 * tail when available.
 */
export class TransportClosedError extends Error {
  /** @param message - the failure description, including any stderr tail. */
  constructor(message: string) {
    super(message)
    this.name = 'TransportClosedError'
  }
}

/** A request exceeded {@link HarnessClientOptions.requestTimeoutMs}. */
export class RequestTimeoutError extends Error {
  /** @param message - which method timed out. */
  constructor(message: string) {
    super(message)
    this.name = 'RequestTimeoutError'
  }
}

/**
 * The runtime answered outside its documented protocol (for example a
 * `session/prompt` response without `accepted: true`).
 */
export class SdkProtocolError extends Error {
  /** @param message - the protocol violation description. */
  constructor(message: string) {
    super(message)
    this.name = 'SdkProtocolError'
  }
}

interface SubscriptionState {
  readonly queue: HarnessNotification[]
  readonly waiters: { resolve: (item: HarnessNotification) => void; reject: (error: Error) => void }[]
  readonly filter: NotificationFilter | undefined
  failure: Error | undefined
}

/** One client-side notification stream returned by {@link HarnessClient.subscribe}. */
export interface NotificationSubscription extends AsyncIterable<HarnessNotification> {
  /**
   * Await the next matching notification.
   * @returns the notification; after the runtime died, drains what was
   * already delivered and then rejects; after {@link close}, rejects
   * immediately (the queue is dropped).
   */
  next(): Promise<HarnessNotification>

  /**
   * Drain one already-delivered notification without waiting.
   * @returns the next queued notification, or `undefined` when none is queued.
   */
  tryNext(): HarnessNotification | undefined

  /** Detach from the client; queued items drop and pending waiters reject. */
  close(): void
}

/** Internal producer side of a public notification subscription. */
class NotificationSubscriptionImpl implements NotificationSubscription {
  constructor(
    private readonly state: SubscriptionState,
    private readonly unsubscribe: () => void,
  ) {}

  /**
   * Await the next matching notification.
   * @returns the notification; after the runtime died, drains what was
   * already delivered and then rejects; after {@link close}, rejects
   * immediately (the queue is dropped).
   */
  next(): Promise<HarnessNotification> {
    const queued = this.state.queue.shift()
    if (queued !== undefined) return Promise.resolve(queued)
    if (this.state.failure !== undefined) return Promise.reject(this.state.failure)
    return new Promise((resolve, reject) => {
      this.state.waiters.push({ resolve, reject })
    })
  }

  /**
   * Drain one already-delivered notification without waiting.
   * @returns the next queued notification, or `undefined` when none is queued.
   */
  tryNext(): HarnessNotification | undefined {
    return this.state.queue.shift()
  }

  /** Detach from the client; queued items drop and pending waiters reject. */
  close(): void {
    this.unsubscribe()
    // The drop is part of this method's contract; a runtime-death fail() keeps
    // the queue so already-delivered notifications remain drainable.
    this.state.queue.length = 0
    this.fail(new TransportClosedError('notification subscription closed'))
  }

  /**
   * Reject pending and future waits (delivery stops; the first failure wins).
   * Already-queued notifications remain drainable via {@link next}/{@link tryNext}.
   * @param error - the terminal failure delivered to waiters.
   */
  fail(error: Error): void {
    this.state.failure ??= error
    for (const waiter of this.state.waiters.splice(0)) waiter.reject(this.state.failure)
  }

  /**
   * Deliver one notification to a waiter or the queue when the filter
   * matches. A throwing filter fails only THIS subscription (detached, the
   * throw becomes its terminal error) — it never disturbs sibling
   * subscriptions or the transport's read loop.
   * @param notification - the wire notification to deliver.
   */
  push(notification: HarnessNotification): void {
    let matches: boolean
    try {
      matches = this.state.filter === undefined || this.state.filter(notification)
    } catch (error) {
      this.unsubscribe()
      this.fail(error instanceof Error ? error : new Error(String(error)))
      return
    }
    if (!matches) return
    const waiter = this.state.waiters.shift()
    if (waiter !== undefined) waiter.resolve(notification)
    else this.state.queue.push(notification)
  }

  /**
   * Iterate notifications until the subscription or runtime closes (the
   * terminating rejection propagates).
   * @returns an async iterator over {@link next} results.
   */
  async * [Symbol.asyncIterator](): AsyncIterator<HarnessNotification> {
    for (;;) yield await this.next()
  }
}

/**
 * JSON-RPC client for the Bud Meta Harness SDK runtime over subprocess stdio.
 *
 * The subprocess starts lazily on {@link start} and is owned by this instance
 * until {@link close}, which requests protocol `shutdown` and then walks the
 * shared EOF → SIGTERM → SIGKILL dispose ladder to quiescence. There is no
 * wire-level cancel: a timed-out request stays running server-side until the
 * runtime is closed.
 */
export class HarnessClient {
  /** Original public budmh launch and timeout options for this client. */
  readonly options: HarnessClientOptions
  private readonly runtime: RuntimeProcessOptions
  private child: ChildProcess | undefined
  private transport: JsonRpcLineTransport | undefined
  private readonly stderrTail: string[] = []
  private readonly subscriptions = new Map<string, NotificationSubscriptionImpl>()
  private readonly sessionParents = new Map<string, string>()
  private subscriptionSerial = 0
  private exitCode: number | null | undefined
  private spawnError: Error | undefined
  private streamsSettled: Promise<void> = Promise.resolve()
  private closeTask: Promise<void> | undefined

  /** @param options - budmh profile, patch, home, process, environment, and timeout options. */
  constructor(options?: HarnessClientOptions)
  constructor(options: HarnessClientOptions = {}, runtime?: RuntimeProcessOptions) {
    this.options = options
    this.runtime = runtime ?? resolveBudmhLaunch(options)
  }

  /**
   * Spawn the runtime subprocess and start reading frames. Idempotent while
   * the process is live; rejects reuse after {@link close}.
   */
  start(): void {
    if (this.closeTask !== undefined) throw new TransportClosedError('Bud Meta Harness runtime client is closed')
    if (this.child !== undefined) return
    const child = spawn(this.runtime.command, this.runtime.args, {
      cwd: this.runtime.cwd,
      env: this.runtime.environment(),
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.child = child
    child.once('error', (error) => {
      this.spawnError = error
      // A spawn failure destroys the pipes without an input 'end' edge, so the
      // transport's pending requests must be failed here.
      this.transport?.close()
      this.failSubscriptions(this.closedError('Bud Meta Harness runtime failed to start'))
    })
    // Writes racing the runtime's death EPIPE on stdin; the exit edge below is
    // the real signal, so the stream-level error only needs to be non-fatal.
    // The timing of that race is not deterministically reproducible.
    /* v8 ignore next */
    child.stdin.on('error', () => {})
    let stderrBuffer = ''
    child.stderr.setEncoding('utf8')
    child.stderr.on('data', (chunk: string) => {
      stderrBuffer += chunk
      const newline = stderrBuffer.lastIndexOf('\n')
      if (newline >= 0) {
        this.appendStderr(stderrBuffer.slice(0, newline).split('\n'))
        stderrBuffer = stderrBuffer.slice(newline + 1)
      }
    })
    let signalStreamsSettled!: () => void
    this.streamsSettled = new Promise((resolve) => { signalStreamsSettled = resolve })
    const settled = { stderr: false, exited: false }
    const maybeSettle = (): void => {
      if (settled.stderr && settled.exited) signalStreamsSettled()
    }
    child.stderr.once('close', () => {
      if (stderrBuffer.length > 0) this.appendStderr([stderrBuffer])
      settled.stderr = true
      maybeSettle()
    })
    child.once('exit', (code) => {
      this.exitCode = code
      settled.exited = true
      maybeSettle()
      this.failSubscriptions(this.closedError('Bud Meta Harness runtime exited'))
    })
    child.once('close', () => {
      // All stdio has settled: stdout 'end' already drained every tail frame,
      // so closing now cannot drop responses — it only fails requests that
      // will never be answered.
      this.transport?.close()
    })
    const transport = new JsonRpcLineTransport(child.stdout, child.stdin)
    transport.onNotification((method, params) => { this.dispatchNotification({ method, params }) })
    transport.start()
    this.transport = transport
  }

  /**
   * Perform the process-wide handshake.
   * @param params - workspace cwd plus the provider/model route.
   * @returns the runtime's wire identity.
   */
  async initialize(params: InitializeParams): Promise<InitializeResult> {
    const result = await this.request('initialize', { ...params }, this.runtime.initializeTimeoutMs)
    if (!isRecord(result) || !isRecord(result.serverInfo)
      || typeof result.serverInfo.name !== 'string' || typeof result.serverInfo.version !== 'string') {
      throw new SdkProtocolError(`initialize returned no server identity: ${JSON.stringify(result)}`)
    }
    return { serverInfo: { name: result.serverInfo.name, version: result.serverInfo.version } }
  }

  /**
   * Queue one prompt and return its durable inbox identity.
   * @param sessionId - target session; an unknown id creates it.
   * @param contentBlocks - the user message, sent verbatim.
   * @returns the queued message id.
   */
  async prompt(sessionId: string, contentBlocks: SdkPromptContentBlock[]): Promise<string> {
    const params: SessionPromptParams = { sessionId, contentBlocks }
    const result = await this.request('session/prompt', { ...params })
    if (!isRecord(result) || typeof result.messageId !== 'string') {
      throw new SdkProtocolError(`session/prompt returned no message id: ${JSON.stringify(result)}`)
    }
    return result.messageId
  }

  /**
   * Restore persisted history without sending a prompt; failures propagate without creating a session.
   * @param sessionId - persisted identity in this runtime's configured persistence store.
   * @returns after the session is ready for prompts.
   */
  async resumeSession(sessionId: string): Promise<void> {
    await this.request('session/resume', { sessionId })
  }

  /**
   * Read a Session's effective working directory, recovering it if missing.
   * @param sessionId - target Session; an unknown id creates it.
   * @returns the absolute effective directory.
   */
  getWorkingDirectory(sessionId: string): Promise<string> {
    return this.workingDirectoryRequest('session/working-directory/get', { sessionId })
  }

  /**
   * Change a Session's effective directory without changing origin or permissions.
   * @param sessionId - target Session; an unknown id creates it.
   * @param path - absolute or Session-current-directory-relative path.
   * @returns the validated absolute directory.
   */
  setWorkingDirectory(sessionId: string, path: string): Promise<string> {
    return this.workingDirectoryRequest('session/working-directory/set', { sessionId, path })
  }

  /**
   * Run one request as a work item (`agent/invoke`). The response arrives once the item's task reached its session;
   * `work/settled` carries the result.
   * @param params - the content, and optionally the request id, the SDK session and the agent of a new session.
   * @returns the request id, the item, its session and what the request did.
   */
  invokeAgent(params: AgentInvokeParams): Promise<SdkRequestResult<'agent/invoke'>> {
    return this.call('agent/invoke', params, value => isRecord(value) && hasStrings(value, 'requestId', 'workItemId', 'sessionId', 'submission'))
  }

  /**
   * Admit one trigger through intake (`trigger/admit`); every item the admission created is launched.
   * @param params - the trigger: its key, content and the optional routing fields.
   * @returns the admission.
   */
  admitTrigger(params: TriggerAdmitParams): Promise<SdkRequestResult<'trigger/admit'>> {
    return this.call('trigger/admit', params, isTagged)
  }

  /**
   * Read one item with its history, inputs and questions (`work/get`).
   * @param workItemId - the item.
   * @returns the item and its rows.
   */
  getWorkItem(workItemId: string): Promise<SdkRequestResult<'work/get'>> {
    return this.call('work/get', { workItemId }, value => isRecord(value) && isRecord(value.item)
      && Array.isArray(value.history) && Array.isArray(value.inputs) && Array.isArray(value.questions))
  }

  /**
   * Read one page of items from one index (`work/list`).
   * @param params - the index (`open`, `attention`, `closed`), a status, the cursor and the page size.
   * @returns the items and the next page's cursor.
   */
  listWorkItems(params: WorkListParams = {}): Promise<SdkRequestResult<'work/list'>> {
    return this.call('work/list', params, value => isRecord(value) && Array.isArray(value.items))
  }

  /**
   * Answer an item's question, or queue the answer as input when no question takes it (`work/answer`).
   * @param params - the item, the answer, and optionally the question and the answer's key.
   * @returns what was admitted, or why nothing was.
   */
  answerWorkItem(params: WorkAnswerParams): Promise<SdkRequestResult<'work/answer'>> {
    return this.call('work/answer', params, isTagged)
  }

  /**
   * Cancel an item and its children (`work/cancel`).
   * @param workItemId - the item.
   * @param reason - why, recorded on its history.
   * @returns the applied change, or why nothing changed.
   */
  cancelWorkItem(workItemId: string, reason: string): Promise<SdkRequestResult<'work/cancel'>> {
    return this.call('work/cancel', { workItemId, reason }, isTagged)
  }

  /**
   * Run an item again in a new attempt (`work/retry`).
   * @param params - the item, and optionally a fresh session or another agent.
   * @returns the applied change, or why nothing changed.
   */
  retryWorkItem(params: WorkRetryParams): Promise<SdkRequestResult<'work/retry'>> {
    return this.call('work/retry', params, isTagged)
  }

  /**
   * Give an item an agent (`work/route`).
   * @param workItemId - the item.
   * @param agent - the agent reference.
   * @returns the applied change, or why nothing changed.
   */
  routeWorkItem(workItemId: string, agent: string): Promise<SdkRequestResult<'work/route'>> {
    return this.call('work/route', { workItemId, agent }, isTagged)
  }

  /**
   * Take an open item over in this runtime (`work/resume`), as a CLI re-run of its request id does.
   * @param workItemId - the item.
   * @returns whether it was taken over or had ended, its session and its status.
   */
  resumeWorkItem(workItemId: string): Promise<SdkRequestResult<'work/resume'>> {
    return this.call('work/resume', { workItemId }, value => isRecord(value) && hasStrings(value, 'workItemId', 'submission', 'status'))
  }

  /**
   * Read the resolved trigger rules (`trigger/rules`).
   * @param params - only rules of an agent, or in some states.
   * @returns the rules, sorted by id.
   */
  triggerRules(params: TriggerRulesParams = {}): Promise<SdkRequestResult<'trigger/rules'>> {
    return this.call('trigger/rules', params, value => Array.isArray(value) && value.every(isRule))
  }

  /**
   * Write a runtime override of one rule (`trigger/override`); a field the config file sets is refused.
   * @param params - the rule, `enabled` or a merge `patch`, an optional version pin, and the reason.
   * @returns the rule after the change.
   */
  overrideTrigger(params: TriggerOverrideParams): Promise<SdkRequestResult<'trigger/override'>> {
    return this.call('trigger/override', params, isRule)
  }

  /**
   * Remove the runtime override of one rule (`trigger/clear-override`).
   * @param rule - the rule id.
   * @param reason - why, recorded on its history.
   * @returns the rule after the change, or null when the override named a rule that no longer exists.
   */
  clearTriggerOverride(rule: string, reason: string): Promise<SdkRequestResult<'trigger/clear-override'>> {
    return this.call('trigger/clear-override', { rule, reason }, value => value === null || isRule(value))
  }

  /**
   * Explain why each rule matched a stored trigger or not (`trigger/explain`).
   * @param intakeKey - the trigger's key, `<sourceInstance>:<nativeKey>`.
   * @param rule - one rule; every rule of the trigger's table when absent.
   * @returns per rule, `matched` or the first step it failed.
   */
  explainTrigger(intakeKey: string, rule?: string): Promise<SdkRequestResult<'trigger/explain'>> {
    return this.call('trigger/explain', { intakeKey, ...rule === undefined ? {} : { rule } },
      value => Array.isArray(value) && value.every(entry => isRecord(entry) && typeof entry.rule === 'string' && isRecord(entry.outcome)))
  }

  /** Send one request and check the fields of its result the SDK reads. */
  private async call<M extends SdkRequestMethod>(
    method: M, params: object, check: (value: unknown) => boolean,
  ): Promise<SdkRequestResult<M>> {
    const result = await this.request(method, { ...params })
    // The wire-boundary narrowing: `check` accepted the fields of the result the SDK reads.
    const accepted = (value: unknown): value is SdkRequestResult<M> => check(value)
    if (!accepted(result)) throw new SdkProtocolError(`${method} returned an unexpected result: ${JSON.stringify(result)}`)
    return result
  }

  private async workingDirectoryRequest(method: string, params: object): Promise<string> {
    const result = await this.request(method, params)
    if (!isRecord(result) || typeof result.cwd !== 'string') {
      throw new SdkProtocolError(`${method} returned no working directory: ${JSON.stringify(result)}`)
    }
    return result.cwd
  }

  /**
   * Send one JSON-RPC request and await its result.
   * @param method - the wire method name.
   * @param params - the params object; omitted params send `{}`.
   * @param timeoutMs - per-call override of {@link HarnessClientOptions.requestTimeoutMs}.
   * @returns the raw result; rejects with {@link JsonRpcResponseError} on a
   * protocol error response, {@link RequestTimeoutError} on timeout, and
   * {@link TransportClosedError} when the runtime is gone.
   */
  async request(method: string, params?: object, timeoutMs?: number): Promise<unknown> {
    this.start()
    // A dead runtime cannot answer; fail with process context instead of
    // writing into a destroyed pipe and hanging until the timeout.
    if (this.exitCode !== undefined || this.spawnError !== undefined) {
      await this.settleStreams()
      throw this.closedError('Bud Meta Harness runtime is not running')
    }
    const transport = this.transport
    /* v8 ignore next -- start() either sets the transport or throws */
    if (transport === undefined) throw new TransportClosedError('Bud Meta Harness runtime is not running')
    const timeout = timeoutMs ?? this.runtime.requestTimeoutMs
    try {
      if (timeout === undefined) return await transport.request(method, params ?? {})
      // The abort signal makes the timeout an abandonment: the transport drops
      // its pending entry, so repeated bounded requests against a hung method
      // retain no per-call state (the server-side work still runs to close).
      const abandon = new AbortController()
      const timer = setTimeout(() => {
        const stderr = this.stderrTail.length === 0 ? '' : `; stderr tail:\n${this.stderrTail.join('\n')}`
        abandon.abort(new RequestTimeoutError(`${method} timed out after ${timeout}ms waiting for ${this.runtime.description}${stderr}`))
      }, timeout)
      try {
        return await transport.request(method, params ?? {}, abandon.signal)
      } finally {
        clearTimeout(timer)
      }
    } catch (error) {
      if (error instanceof JsonRpcResponseError || error instanceof RequestTimeoutError) throw error
      // Transport-level failures gain process context: exit code + stderr tail.
      await this.settleStreams()
      throw this.closedError(errorMessage(error))
    }
  }

  /**
   * Send one client notification; it has no response.
   * @param method - the wire method name, such as `voice/audio`.
   * @param params - the params object.
   * @throws TransportClosedError when the runtime is gone or the write failed.
   */
  notify(method: string, params: object): void {
    this.start()
    const transport = this.transport
    if (this.exitCode !== undefined || this.spawnError !== undefined || transport === undefined) {
      throw this.closedError('Bud Meta Harness runtime is not running')
    }
    try {
      transport.notify(method, params)
    } catch (error) {
      /* v8 ignore next -- a write to a live child's stdin pipe throws only after the pipe was destroyed */
      throw this.closedError(errorMessage(error))
    }
  }

  /**
   * Subscribe to server notifications.
   * @param filter - optional predicate; omitted means every notification.
   * @returns the subscription handle; close it to stop delivery. After
   * {@link close} or runtime death the handle is born failed — there is no
   * producer left, so `next()` rejects instead of waiting forever.
   */
  subscribe(filter?: NotificationFilter): NotificationSubscription {
    const id = String(this.subscriptionSerial++)
    const state: SubscriptionState = { queue: [], waiters: [], filter, failure: undefined }
    const subscription = new NotificationSubscriptionImpl(state, () => { this.subscriptions.delete(id) })
    if (this.closeTask !== undefined || this.exitCode !== undefined || this.spawnError !== undefined) {
      subscription.fail(this.closedError('Bud Meta Harness runtime closed'))
      return subscription
    }
    this.subscriptions.set(id, subscription)
    return subscription
  }

  /**
   * Subscribe to one session and the descendants discovered from
   * `subagent.started` lineage edges. The runtime notifies for every session
   * in its context, so this client applies the scope.
   * @param sessionId - the root session id.
   * @returns the filtered subscription handle.
   */
  subscribeSessionTree(sessionId: string): NotificationSubscription {
    return this.subscribe((notification) => {
      const params = notification.params
      if (notification.method === 'subagent.started' || notification.method === 'subagent.finished') {
        const parentId = params.parentSessionId
        if (typeof parentId === 'string' && this.isDescendantOf(parentId, sessionId)) return true
        return params.childSessionId === sessionId
      }
      const relatedId = params.sessionId
      return typeof relatedId === 'string' && this.isDescendantOf(relatedId, sessionId)
    })
  }

  /**
   * Shut the runtime down and reap it: a best-effort protocol `shutdown`
   * bounded by `shutdownTimeoutMs`, then the shared stdin-EOF → SIGTERM →
   * SIGKILL ladder until the process actually exited. Idempotent.
   * @returns settlement of the complete teardown.
   */
  close(): Promise<void> {
    this.closeTask ??= this.performClose()
    return this.closeTask
  }

  private async performClose(): Promise<void> {
    const child = this.child
    if (child === undefined) return
    try {
      await this.request('shutdown', undefined, this.runtime.shutdownTimeoutMs ?? 1_000)
    } catch (error) {
      // Diagnostic only: the dispose ladder below is the authoritative teardown
      // for a runtime that cannot answer shutdown anymore.
      this.appendStderr([`shutdown request failed: ${errorMessage(error)}`])
    }
    await disposeRuntimeProcess(child, {
      disposeEofGraceMs: this.runtime.disposeEofGraceMs ?? 6_000,
      disposeGraceMs: this.runtime.disposeGraceMs ?? 3_000,
    })
    this.transport?.close()
    this.failSubscriptions(this.closedError('Bud Meta Harness runtime closed'))
  }

  private dispatchNotification(notification: HarnessNotification): void {
    this.recordSessionRelationship(notification)
    for (const subscription of this.subscriptions.values()) subscription.push(notification)
  }

  private recordSessionRelationship(notification: HarnessNotification): void {
    if (notification.method !== 'subagent.started') return
    const parentId = notification.params.parentSessionId
    const childId = notification.params.childSessionId
    if (typeof parentId === 'string' && parentId !== '' && typeof childId === 'string' && childId !== '' && parentId !== childId) {
      this.sessionParents.set(childId, parentId)
    }
  }

  private isDescendantOf(sessionId: string, rootSessionId: string): boolean {
    const visited = new Set<string>()
    let current = sessionId
    while (!visited.has(current)) {
      if (current === rootSessionId) return true
      visited.add(current)
      const parent = this.sessionParents.get(current)
      if (parent === undefined) return false
      current = parent
    }
    // The parent map only ever extends chains upward, so a cycle cannot form.
    /* v8 ignore next */
    return false
  }

  private failSubscriptions(error: Error): void {
    for (const subscription of this.subscriptions.values()) subscription.fail(error)
  }

  /**
   * The runtime's most recent stderr lines (at most 400), including startup
   * warnings such as a plugin entry that did not activate. Lines arrive
   * asynchronously, so a live runtime's tail may still be growing; after
   * {@link close} resolves it holds everything the runtime wrote.
   * @returns a copy of the retained lines, oldest first.
   */
  recentStderr(): readonly string[] {
    return [...this.stderrTail]
  }

  private appendStderr(lines: string[]): void {
    const kept = lines.filter(line => line.length > 0)
    this.stderrTail.push(...kept)
    if (this.stderrTail.length > STDERR_TAIL_LIMIT) {
      this.stderrTail.splice(0, this.stderrTail.length - STDERR_TAIL_LIMIT)
    }
  }

  private settleStreams(): Promise<void> {
    return Promise.race([
      this.streamsSettled,
      new Promise<void>((resolve) => { setTimeout(resolve, STREAM_SETTLE_MS) }),
    ])
  }

  private closedError(reason: string): TransportClosedError {
    const parts = [`${this.runtime.description}: ${reason}`]
    if (this.spawnError !== undefined) parts.push(`spawn error: ${this.spawnError.message}`)
    if (this.exitCode !== undefined) parts.push(`exit code: ${String(this.exitCode)}`)
    if (this.stderrTail.length > 0) parts.push(`stderr tail:\n${this.stderrTail.join('\n')}`)
    return new TransportClosedError(parts.join('\n'))
  }
}

/** Construct the transport against a generic process for package-local fake-runtime tests. */
export function createProcessHarnessClient(options: RuntimeProcessOptions): HarnessClient {
  const Constructor = HarnessClient as new (
    publicOptions: HarnessClientOptions,
    runtime: RuntimeProcessOptions,
  ) => HarnessClient
  return new Constructor({}, options)
}

/**
 * Whether `value` is a plain JSON object (the wire-boundary shape probe).
 * @param value - the wire value to probe.
 * @returns `true` iff `value` is a non-null, non-array object.
 */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Whether every named field of a wire object is a string. */
function hasStrings(value: Record<string, unknown>, ...fields: string[]): boolean {
  return fields.every(field => typeof value[field] === 'string')
}

/** Whether a wire value is an object tagged by a string `kind`, as admissions and applied changes are. */
function isTagged(value: unknown): boolean {
  return isRecord(value) && typeof value.kind === 'string'
}

/** Whether a wire value is a resolved trigger rule: its binding and its state. */
function isRule(value: unknown): boolean {
  return isRecord(value) && isRecord(value.binding) && isRecord(value.state)
}

/** The message of a thrown value (the transport only throws `Error`s; `String` covers the rest). */
function errorMessage(error: unknown): string {
  /* v8 ignore next -- the transport and dispose ladder reject only with Errors */
  return error instanceof Error ? error.message : String(error)
}
