/**
 * Types of keyed delivery: the request a producer hands `deliverOnce`, its
 * outcomes, the `delivery/keyed` Session event and the `deliveries`
 * projection state.
 * @module @budmh/session-delivery/types
 */

import type { ContentBlock, MessageId, MessageSource } from '@budmh/llm'
import type {} from '@budmh/session'
import type {} from '@budmh/session-projection'
import type { DeliveryKey } from './key.ts'

/** The inbox operation a keyed message uses: `followup` and `steer` wake the driver, `inject` does not. */
export type DeliveryTarget = 'followup' | 'steer' | 'inject'

/** One logical message a producer delivers into a Session at most once per key and generation. */
export interface KeyedDelivery {
  /** The producer's namespace, matching `^[a-z][a-z0-9-]*$`, such as `schedule`. */
  readonly namespace: string
  /** Stable per logical message: every retry of one message passes the same key. */
  readonly key: DeliveryKey
  /** The exact model-facing blocks. */
  readonly content: readonly ContentBlock[]
  /** The producer's own `MessageSourceMap` kind. */
  readonly source: MessageSource
  /** Batch form: every producer key this one message carries; each is recognised by `deliveryState` afterwards. */
  readonly memberKeys?: readonly DeliveryKey[]
  /** The inbox operation; `followup` queues a turn, `steer` the nearest step, `inject` the nearest step without a wake. */
  readonly target: DeliveryTarget
  /**
   * `tail` (the default) sends through the Agent and may wake it; `head` prepends to the target's list without a
   * wake, for `agent/created` listeners whose message must be the first input of the turn AgentLoop starts after them.
   */
  readonly position?: 'tail' | 'head'
  /** Copy number, 0 by default: a key whose latest copy was discarded at a lower generation is delivered again under this one. */
  readonly generation?: number
  /** Checked before anything is appended; `false` refuses the delivery as `unauthorized`. */
  readonly authorize?: () => boolean | Promise<boolean>
}

/** What `deliverOnce` did. */
export type DeliveryOutcome =
  /** This call appended the message and the flush acknowledged it. */
  | { readonly kind: 'delivered'; readonly messageId: MessageId }
  /** An earlier call already put this key in the Session; this call flushed and appended nothing. */
  | { readonly kind: 'already'; readonly messageId: MessageId; readonly state: 'pending' | 'claimed' | 'consumed' }
  /** The latest copy of this key was discarded (a Stop, or a turn that ended before the model received it); nothing was sent. */
  | { readonly kind: 'discarded'; readonly messageId: MessageId; readonly generation: number }
  /** Nothing was appended: the Session is never stored, or `authorize` answered false. */
  | { readonly kind: 'refused'; readonly reason: 'unauthorized' | 'memory-session' }

/**
 * Where one keyed message is:
 * - `pending`: in the inbox;
 * - `claimed`: taken by the open turn, which has not logged it as a `user/message` yet;
 * - `consumed`: logged as a `user/message`;
 * - `discarded`: removed by a canceling splice (Stop), or claimed by a turn that ended without logging it;
 * - `lost`: no copy remains for the model, because a crash interrupted the turn that claimed it before it was logged,
 *   or because its inbox insertion never reached the log.
 */
export type DeliveryState = 'pending' | 'claimed' | 'consumed' | 'discarded' | 'lost'

/** The latest copy of one keyed message, as the `deliveries` projection folds it. */
export interface DeliveryRecord {
  /** The copy's message id, `deliveryMessageId(sessionId, namespace, key, generation)`. */
  readonly messageId: MessageId
  /** The producer namespace. */
  readonly namespace: string
  /** The producer key. */
  readonly key: DeliveryKey
  /** The copy number. */
  readonly generation: number
  /** Where the copy is. */
  readonly state: DeliveryState
}

/**
 * The `delivery/keyed` Session event payload: the producer identity of one
 * keyed message, appended ignorable immediately before the message's inbox
 * insertion. No model request depends on it.
 */
export interface DeliveryKeyed {
  /** The message id the following inbox insertion carries. */
  readonly messageId: MessageId
  /** The producer namespace. */
  readonly namespace: string
  /** The producer key. */
  readonly key: DeliveryKey
  /** The copy number. */
  readonly generation: number
  /** Every producer key the message carries, in the batch form. */
  readonly memberKeys?: readonly DeliveryKey[]
}

/** Plain-JSON state of the `deliveries` projection. */
export interface DeliveriesState {
  /** The fork-inherited prefix length; `delivery/keyed` events below it belong to the parent. */
  readonly inheritedEventCount: number
  /** Message ids of both inbox lists, in order, mirroring the `inbox` projection. */
  readonly mirror: { readonly 'next-turn': readonly string[]; readonly 'next-step': readonly string[] }
  /** Keyed message ids the open turn claimed and has not logged. */
  readonly claimed: readonly string[]
  /** Latest copy per message id. */
  readonly records: Readonly<Record<string, DeliveryRecord>>
  /** Message id of the latest copy carrying each `<namespace>\u0000<key>`, member keys included. */
  readonly keys: Readonly<Record<string, string>>
}

declare module '@budmh/session/types' {
  interface SessionEventMap {
    /** The producer namespace and key of the keyed message the next inbox insertion carries; ignorable. */
    'delivery/keyed': DeliveryKeyed
  }
}

declare module '@budmh/session-projection/types' {
  interface SessionProjectionStateMap {
    /** Where every keyed message of the Session is, by producer key. */
    deliveries: DeliveriesState
  }
}
