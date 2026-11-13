/**
 * Exactly-once delivery of keyed messages into a Session. A producer whose
 * queue retries (a durable timer, a work-item lane) calls `deliverOnce` on
 * every attempt; the Session's `deliveries` projection recognises a key that
 * an earlier attempt already appended, so each logical message lands in the
 * durable log once, and the producer commits its own state only after
 * `deliverOnce` resolves.
 *
 * @module @budmh/session-delivery
 */

import type { Agent } from '@budmh/agent'
import type { Context } from '@budmh/cordis'
import { freezeMessage } from '@budmh/llm'
import { assertNever } from '@budmh/util-values'
import type { UserMessage } from '@budmh/llm'
import type { SessionId } from '@budmh/session'
import { assertDeliveryNamespace, deliveryMessageId, type DeliveryKey } from './key.ts'
import { deliveriesProjection, keyIndex } from './projection.ts'
import type { DeliveryOutcome, DeliveryRecord, KeyedDelivery } from './types.ts'

export type * from './types.ts'
export { DeliveryKey, deliveryMessageId, keyDigest } from './key.ts'
export { deliveriesProjection, deliveriesStateSchema } from './projection.ts'

/** The Session flush reported that no durability listener ran, so the delivered messages are not stored. */
export class DeliveryNotDurable extends Error {
  override readonly name = 'DeliveryNotDurable'

  /**
   * @param sessionId - the Session the flush covered.
   */
  constructor(readonly sessionId: SessionId) {
    super(`session-delivery: no session persistence acknowledged the deliveries of Session "${sessionId}"`)
  }
}

/**
 * Durably store every keyed message already appended to an Agent's Session.
 * A producer that finds all its keys through `deliveryState` and sends
 * nothing calls this before committing its own state, so a message an
 * earlier attempt appended but failed to flush is stored first.
 * @param agent - the Agent whose Session is flushed.
 * @returns resolution after the flush.
 * @throws DeliveryNotDurable when no durability listener ran; the flush's own failure otherwise.
 */
export async function flushDeliveries(agent: Agent): Promise<void> {
  if (!await agent.ctx.sessions.flush(agent.session)) throw new DeliveryNotDurable(agent.session.id)
}

/**
 * Register the `deliveries` projection and the resume wake for restored keyed
 * deliveries on a producer's context. A resumed Session whose restored
 * next-turn list holds a keyed delivery that is still `pending` (a copy a
 * crashed process stored but never ran) starts one turn once initialization
 * ends; that turn claims next-turn rows in order, so user rows queued ahead
 * of the delivery run first. Restored lists without a pending keyed delivery
 * stay queued, editable and removable.
 * @param ctx - the producer context that owns both registrations.
 * @returns a disposer removing both registrations.
 */
export function registerDeliveries(ctx: Context): () => void {
  const projection = ctx.sessionProjections.register(deliveriesProjection)
  const wake = ctx.on('agent/resume-wake', ({ agent, messages }) => restoredDeliveryPending(agent, messages) ? true : undefined)
  return () => {
    wake()
    projection()
  }
}

/**
 * Whether restored input holds a keyed delivery that no turn has claimed yet.
 * @param agent - the Agent whose Session holds the messages.
 * @param messages - restored next-turn messages.
 * @returns true when any message is a `pending` copy in the `deliveries` projection.
 */
export function restoredDeliveryPending(agent: Agent, messages: readonly UserMessage[]): boolean {
  const state = agent.ctx.sessionProjections.stateOf(agent.session, 'deliveries')
  return state !== undefined && messages.some(message => state.records[message.id]?.state === 'pending')
}

/**
 * Read the latest copy of one producer key in an Agent's Session, member
 * keys of batch messages included.
 * @param agent - the Agent whose Session is read.
 * @param namespace - the producer namespace.
 * @param key - the producer key.
 * @returns the copy, or undefined when the Session never received the key.
 * @throws Error when no `deliveries` projection is registered; a producer registers `deliveriesProjection` first.
 */
export function deliveryState(agent: Agent, namespace: string, key: DeliveryKey): DeliveryRecord | undefined {
  const state = agent.ctx.sessionProjections.stateOf(agent.session, 'deliveries')
  if (state === undefined) {
    throw new Error('session-delivery: the deliveries projection is not registered; register deliveriesProjection with ctx.sessionProjections')
  }
  const messageId = state.keys[keyIndex(namespace, key)]
  return messageId === undefined ? undefined : state.records[messageId]
}

/** The first copy any key of the delivery names: its own key first, then each member key in order. */
function existingCopy(agent: Agent, delivery: KeyedDelivery): DeliveryRecord | undefined {
  for (const key of [delivery.key, ...delivery.memberKeys ?? []]) {
    const record = deliveryState(agent, delivery.namespace, key)
    if (record !== undefined) return record
  }
  return undefined
}

/**
 * Deliver one keyed message into the Agent's Session unless an earlier
 * attempt already did, then flush the Session.
 *
 * Between the lookup and the inbox insertion nothing is awaited, so callers
 * that share one live Agent in one process cannot both append the key. The
 * single-writer premise across processes is the Session persistence lease.
 *
 * - A copy that is `pending`, `claimed` or `consumed` returns `already` after a flush, which also stores a copy an
 *   earlier attempt appended but failed to flush.
 * - A copy `discarded` at the requested generation or later returns `discarded` without sending; the caller decides
 *   whether to deliver again under a higher generation.
 * - A `lost` copy of the same key and generation is sent again under its message id; any other absent or lost key
 *   sends a new copy under `deliveryMessageId(sessionId, namespace, key, generation)`.
 *
 * A sent copy appends `delivery/keyed` (ignorable) and the inbox insertion in one synchronous block. `tail` sends
 * through the Agent, so `followup` and `steer` wake an idle driver; `head` prepends without a wake.
 * @param agent - the live Agent that holds the receiving Session.
 * @param delivery - the message, its producer key and its inbox operation.
 * @param signal - aborts before anything is appended; after the append, the flush always runs.
 * @returns what happened; the caller commits its own state only after this resolves.
 * @throws DeliveryNotDurable when the flush reports that no durability listener ran.
 * @throws the flush's own failure, or the signal's reason when it aborted before the append.
 */
export async function deliverOnce(agent: Agent, delivery: KeyedDelivery, signal: AbortSignal): Promise<DeliveryOutcome> {
  assertDeliveryNamespace(delivery.namespace)
  const generation = delivery.generation ?? 0
  // Computing the id first validates the key and generation before any state is read.
  const minted = deliveryMessageId(agent.session.id, delivery.namespace, delivery.key, generation)
  if (agent.session.storage === 'memory') return { kind: 'refused', reason: 'memory-session' }
  if (delivery.authorize !== undefined && !await delivery.authorize()) return { kind: 'refused', reason: 'unauthorized' }
  signal.throwIfAborted()
  const existing = existingCopy(agent, delivery)
  if (existing !== undefined) {
    const { messageId, state } = existing
    switch (state) {
      case 'pending':
      case 'claimed':
      case 'consumed':
        await flushDeliveries(agent)
        return { kind: 'already', messageId, state }
      case 'discarded':
        if (existing.generation >= generation) return { kind: 'discarded', messageId, generation: existing.generation }
        break
      case 'lost':
        break
      /* v8 ignore next -- DeliveryState is a closed union */
      default: assertNever(state)
    }
  }
  const message: UserMessage = freezeMessage({ id: minted, role: 'user', content: delivery.content, source: delivery.source })
  agent.session.append('delivery/keyed', {
    messageId: minted, namespace: delivery.namespace, key: delivery.key, generation,
    ...delivery.memberKeys === undefined ? {} : { memberKeys: delivery.memberKeys },
  }, { ignorable: true })
  if (delivery.position === 'head') {
    agent.inbox.prepend(delivery.target === 'followup' ? 'next-turn' : 'next-step', message)
  } else {
    switch (delivery.target) {
      case 'followup': agent.followup(message); break
      case 'steer': agent.steer(message); break
      case 'inject': agent.inject(message); break
      /* v8 ignore next -- DeliveryTarget is a closed union */
      default: assertNever(delivery.target)
    }
  }
  await flushDeliveries(agent)
  return { kind: 'delivered', messageId: minted }
}
