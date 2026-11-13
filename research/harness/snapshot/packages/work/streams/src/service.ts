/**
 * The `ctx.streams` Service Definition: live connections (voice calls,
 * speech to speech, sensor and control links) bound to a Session and served
 * by a registered handler.
 * @module @budmh/streams/service
 */

import { Context, Service } from '@budmh/cordis'
import type {} from '@budmh/agent-residency'
import type {} from '@budmh/agent-session'
import type { StreamAttachmentRow } from './repositories.ts'
import type {
  StreamAttachment, StreamAttachRequest, StreamBinding, StreamConnection, StreamDetachOutcome, StreamHandler, StreamId,
} from './types.ts'

declare module '@budmh/cordis' {
  interface Context {
    /** Live streams bound to Sessions and the handlers that serve them. */
    streams: Streams
  }
}

declare module '@budmh/agent-residency' {
  interface ResidencyPinReasonMap {
    /** A live stream is attached to the Session. */
    stream: true
  }
}

/**
 * Abstract registry of stream handlers and live attachments.
 *
 * Providers honor these semantics:
 * - Handlers are keyed by id; a duplicate id fails without replacing the
 *   original, and each registration is an effect of the calling context.
 * - A Session holds at most one live `conversation` floor and any number of
 *   `none` handlers; an external `claimKey` is held by at most one live
 *   stream across every process sharing the store.
 * - `attach` refuses a Session whose storage is `memory`, because a stream
 *   must be logged.
 * - While attached, the bound Agent is pinned resident with reason `stream`;
 *   the Session log holds the ignorable `stream/opened` and `stream/closed`
 *   pair. Everything a handler makes model-visible goes through logged
 *   channels (keyed `user/message` deliveries, the loop's own turns).
 */
export abstract class Streams extends Service {
  constructor(ctx: Context) {
    // `abstract` erases at runtime; a composition row naming this class would register no registry. Fail loud at load.
    if (new.target === Streams) {
      throw new Error('Streams is the abstract stream seam; load @budmh/streams\'s default export instead')
    }
    super(ctx, 'streams')
  }

  /**
   * Register one handler as an effect of the calling context.
   * @param handler - the handler.
   * @returns idempotent disposer that withdraws the handler, closes its attachments with reason `disposed` and waits for them.
   * @throws Error when a handler with the same id is registered, or the id is malformed.
   */
  abstract registerHandler(handler: StreamHandler): () => Promise<void>

  /**
   * Bind a live connection to a live Session: claim its floor and `claimKey`,
   * pin residency, write the shared-store row, append `stream/opened` and run
   * the handler.
   * @param binding - what the stream joins.
   * @param connection - the live connection; the attachment closes it when it ends.
   * @param request - the handler, its spec and an optional claim key.
   * @param signal - cancels the attach until the handler holds the connection.
   * @returns the attachment, once the handler holds the connection.
   * @throws StreamsError with a `StreamsFailure` code when the attach is refused or the handler fails before
   *   holding the connection.
   */
  abstract attach(
    binding: StreamBinding, connection: StreamConnection, request: StreamAttachRequest, signal: AbortSignal,
  ): Promise<StreamAttachment>

  /**
   * The attachments this process holds.
   * @returns them in attach order, excluding those still opening or already closing.
   */
  abstract attachments(): readonly StreamAttachment[]

  /**
   * The connection of a stream this process holds.
   * @param id - the stream.
   * @returns the connection, or undefined when this process holds no such stream.
   */
  abstract connection(id: StreamId): StreamConnection | undefined

  /**
   * Every live stream of every process sharing the store, as its rows show it; a row whose holder stopped renewing
   * stays listed until a sweep closes it.
   * @param signal - cancels the read.
   * @returns the rows, ordered by their latest renewal; empty without opening the store when it holds no state yet.
   */
  abstract liveRows(signal: AbortSignal): Promise<readonly StreamAttachmentRow[]>

  /**
   * Detach a stream wherever it is held: here at once, or by asking the holding process, which detaches it when the
   * notice arrives or, when it missed the notice, at its next heartbeat.
   * @param id - the stream.
   * @param signal - cancels the request.
   * @returns how the request went.
   */
  abstract requestDetach(id: StreamId, signal: AbortSignal): Promise<StreamDetachOutcome>
}
