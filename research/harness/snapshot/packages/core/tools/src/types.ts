/**
 * Durable Tool event vocabulary shared with type-only consumers.
 *
 * @module @budmh/tools/types
 */

import type { ToolCallId } from '@budmh/llm/brand'
import type { ContentBlock } from '@budmh/llm/types'
import type { JsonValue } from '@budmh/util-values'

/** Payload recorded when one nested PTC mode Tool dispatch starts. */
export interface PtcDispatchStartEventData {
  rootCallId: ToolCallId
  parentCallId: ToolCallId
  subCallId: ToolCallId
  name: string
  arguments: unknown
}

/** Payload recorded when one nested PTC mode Tool dispatch settles. */
export interface PtcDispatchEventData extends PtcDispatchStartEventData {
  isError: boolean
  content: ContentBlock[]
  /** Replayable tool-owned presentation metadata, separate from model content. */
  meta?: JsonValue
  /** Optional failure identity and raw user-facing detail, outside model-facing content. */
  error?: { name: string; code: string; reason?: string }
}

/**
 * Payload recorded when `tools/pre-execute` policy replaced the arguments one
 * call executes with. `arguments` is the complete replacement value and `by`
 * names every rewriter in application order.
 */
export interface ToolArgumentsReplacedEventData {
  callId: ToolCallId
  /** Root model call owning a nested (PTC sub-call) execution; absent for a root call. */
  rootCallId?: ToolCallId
  arguments: JsonValue
  by: string[]
}

declare module '@budmh/session/types' {
  interface SessionEventMap {
    /**
     * The arguments one call executes with after `tools/pre-execute` policy
     * replaced the model's arguments. Follows the `tool/call` (native) or
     * `tool/ptc-dispatch-start` (PTC sub-call) whose call id it carries and
     * precedes that call's approval request and result. The paired call event
     * keeps the model's arguments; this event records what guards, approval,
     * dispatch, the tool body, post-execute policy, and presentation received.
     * Required on read: a reader that skipped it would present the model's
     * arguments as the executed ones. Log-only: `deriveMessages()` ignores
     * it, so the model never sees the replacement.
     */
    'tool/arguments-replaced': ToolArgumentsReplacedEventData
    /**
     * One sub-dispatch STARTING inside a `run_code` program: the parent
     * `run_code` call id, the opaque sub-call id (new calls use
     * `<parent>:ptc:<n>`, numbered in submission order), and the tool `name` with its
     * JSON-normalized `arguments` — the exact value dispatched, normalized
     * BEFORE dispatch, so this append can never fail on payload shape.
     * Appended when the scheduler actually starts the call (not at
     * submission), so a start means the tool body pipeline was entered; a
     * call abandoned in the queue logs nothing. Log-only: `deriveMessages()`
     * ignores it; UIs use it for live per-sub-call running state and pair it
     * with `tool/ptc-dispatch` by `subCallId` (timing = the two events'
     * `time` fields).
     */
    'tool/ptc-dispatch-start': PtcDispatchStartEventData
    /**
     * One bridged sub-dispatch SETTLING: the pairing ids (matching the
     * `tool/ptc-dispatch-start` with the same `subCallId`), the tool `name`
     * with the same JSON-normalized `arguments`, and the sub-call's complete
     * durable outcome in `tool/result`'s own vocabulary (`content` + `isError`
     * + optional presentation `meta` and structured `error`), so UIs and SDKs
     * render a sub-call through the exact path used for a native call. Every started sub-call settles
     * with exactly one of these (abort included: the aborted pipeline result
     * is an `isError` outcome).
     * Log-only: `deriveMessages()` ignores it, so sub-calls never re-enter
     * model context; persistence and UIs get every call. Appended inside the
     * parent `run_code`'s execution (the bridge drains in-flight dispatches
     * before returning), so its execution-enclosure relation holds by
     * construction.
     */
    'tool/ptc-dispatch': PtcDispatchEventData
  }
}
