/**
 * Type surface of `ctx.streams`: stream and handler identity, track kinds,
 * frames, the live connection a transport provides, bindings, handlers,
 * attachments, failures, and the `stream/opened` and `stream/closed`
 * Session events.
 * @module @budmh/streams/types
 */

import type { Branded } from '@budmh/brand'
import type { Agent } from '@budmh/agent'
import type { SpecDiagnostic } from '@budmh/agent-spec'
import type { SessionId } from '@budmh/session'
import type { JsonValue } from '@budmh/util-values'

/** One live stream: `str_` and a random UUID from {@link newStreamId}, or a transport's own id of at most 128 characters. */
export type StreamId = Branded<'StreamId'>

/** A registered stream handler, such as `voice-turns` or `realtime`: lowercase letters, digits and `-`. */
export type StreamHandlerId = Branded<'StreamHandlerId'>

/** One `@budmh/streams` provider instance, which is one process: `inc-` and a random UUID. */
export type StreamIncarnation = Branded<'StreamIncarnation'>

/** A JSON object, such as a handler spec. */
export type JsonObject = { [key: string]: JsonValue }

/**
 * Kinds of track and the parameters each declares. Merge-extensible: a
 * transport or handler package adds a kind by declaration merging. Every
 * parameter value is JSON, because tracks are logged in `stream/opened`.
 */
export interface StreamKindMap {
  /** Audio frames. */
  voice: { readonly codec: string; readonly sampleRate: number }
  /** Video frames. */
  video: { readonly codec: string }
  /** Sensor or state samples in a named schema. */
  telemetry: { readonly schema: string; readonly rateHz?: number }
  /** Commands at a fixed rate in a named schema. */
  control: { readonly schema: string; readonly rateHz: number }
  /** Turn events of a transport that recognizes speech itself; the frames are JSON whose fields the handler package defines. */
  'speech-turns': Record<string, never>
  /** Text the transport synthesizes into speech itself; the frames are JSON whose fields the handler package defines. */
  'speech-text': Record<string, never>
  /** Application data messages, such as room data messages; `schema` names their format when the transport declares one. */
  data: { readonly schema?: string }
}

/** A track kind. */
export type StreamKind = keyof StreamKindMap

/** One track of a connection, discriminated by `kind`; switch on `kind` and fall through unknown kinds. */
export type StreamTrack = {
  [K in StreamKind]: {
    /** Unique within the connection. */
    readonly name: string
    /** `in` carries frames from the transport to the handler, `out` the reverse. */
    readonly direction: 'in' | 'out'
    readonly kind: K
    readonly params: StreamKindMap[K]
  }
}[StreamKind]

/** One frame of a track, at a time on the connection's media clock. */
export type StreamFrame =
  | { readonly kind: 'bytes'; readonly atMs: number; readonly bytes: Uint8Array }
  | { readonly kind: 'json'; readonly atMs: number; readonly json: JsonValue }

/** What the transport tells a handler about the other end. */
export interface StreamTransportInfo {
  /** Transport kind: `browser-pcm`, `sdk-pcm`, `livekit`, `sip`, or a plugin's kind. */
  readonly kind: string
  /** Whether the person or system at the other end can read text the agent shows. */
  readonly screen: boolean
  /** Who is at the other end, as far as the transport knows. */
  readonly peer?: { readonly from?: string; readonly to?: string; readonly identity?: string }
}

/**
 * A live connection a transport provides. Frames are not exactly once: a
 * frame lost in a crash is gone. Implementations never buffer without bound;
 * the transport owns its back-pressure.
 */
export interface StreamConnection {
  /** Unique among the streams of every process sharing the store. */
  readonly id: StreamId
  /** Tracks, with unique names. */
  readonly tracks: readonly StreamTrack[]
  /** The transport and its peer. */
  readonly transport: StreamTransportInfo
  /**
   * The media clock in milliseconds: inbound samples received on audio tracks, wall time for connections without audio.
   * @returns the current media time.
   */
  now(): number
  /**
   * Frames of one `in` track until the track or the connection ends.
   * @param track - the name of an `in` track.
   * @returns the frames, in arrival order.
   */
  inbound(track: string): AsyncIterable<StreamFrame>
  /**
   * Queue one frame on an `out` track.
   * @param track - the name of an `out` track.
   * @param frame - the frame.
   * @returns resolution once the transport accepted the frame.
   */
  send(track: string, frame: StreamFrame): Promise<void>
  /**
   * Drop the queued outbound frames of an `out` track at once, such as a reply the caller talked over.
   * @param track - the name of an `out` track.
   */
  interrupt(track: string): void
  /**
   * Close the connection; idempotent.
   * @param reason - why, for the transport's own log.
   * @returns resolution once closed.
   */
  close(reason: string): Promise<void>
  /** Aborts when the connection closed, from either end. */
  readonly closed: AbortSignal
}

/**
 * What a stream is bound to. Merge-extensible: a package that binds streams
 * to another owner, such as a work item, adds its member.
 */
export interface StreamBindingMap {
  /** A live Session: the stream joins the conversation of this Agent. */
  session: { readonly kind: 'session'; readonly agent: Agent }
}

/** One binding, discriminated by `kind`. */
export type StreamBinding = StreamBindingMap[keyof StreamBindingMap]

/**
 * How a handler shares its Session: a Session holds at most one live
 * `conversation` floor (one speaking channel) and any number of `none`
 * handlers (telemetry, video, data).
 */
export type StreamFloor = 'conversation' | 'none'

/**
 * Why a stream closed. Merge-extensible: a handler package adds its reasons
 * (such as `delivery-failed`) by declaration merging.
 */
export interface StreamCloseReasonMap {
  /** The handler finished. */
  ended: true
  /** The connection closed from the transport's side. */
  hangup: true
  /** The attaching caller detached the stream, or cancelled `attach` before the handler held the connection. */
  detached: true
  /** The handler failed. */
  failed: true
  /** The holding process stopped renewing the stream's row, which another process then closed. */
  'host-lost': true
  /** The stream registry, the handler or the bound Agent was disposed. */
  disposed: true
}

/** A close reason. */
export type StreamCloseReason = keyof StreamCloseReasonMap

/** A handler's or transport's failure, as logged. */
export interface StreamCloseError {
  /** Stable code. */
  readonly code: string
  /** Description. */
  readonly message: string
}

/** How a handler's run ended. */
export interface StreamOutcome {
  /** Why it ended; a handler that finished its work returns `ended`. */
  readonly reason: StreamCloseReason
  /** The failure, when the run ended on one. */
  readonly error?: StreamCloseError
}

/** One registered handler: what a stream does once attached. */
export interface StreamHandler {
  /** Unique id, named by `attach` requests. */
  readonly id: StreamHandlerId
  /** The floor its streams hold. */
  readonly floor: StreamFloor
  /**
   * Check a spec before anything is written.
   * @param spec - the attach request's spec.
   * @returns every diagnostic; empty when the spec is valid.
   */
  validate(spec: JsonObject): readonly SpecDiagnostic[]
  /**
   * The spec as logged in `stream/opened`, with every secret removed.
   * @param spec - a valid spec.
   * @returns the logged spec.
   */
  redact(spec: JsonObject): JsonObject
  /**
   * Serve the connection until the work ends, the connection closes or `run.signal` aborts.
   * @param run - the binding, the connection, the spec and the run's controls.
   * @returns how the run ended.
   */
  run(run: StreamRun): Promise<StreamOutcome>
}

/** What a handler's run receives. */
export interface StreamRun {
  /** What the stream is bound to. */
  readonly binding: StreamBinding
  /** The live connection. */
  readonly connection: StreamConnection
  /** The validated spec. */
  readonly spec: JsonObject
  /** The attachment the run serves. */
  readonly attachment: StreamAttachmentInfo
  /** Aborts on detach, a hang-up, a lost row, and disposal of the registry, the handler or the Agent; its reason is a `StreamsAbort`. */
  readonly signal: AbortSignal
  /** Report that the handler holds the connection; `attach` resolves at the first call, or when the run settles. */
  holding(): void
}

/** Facts of one attachment. */
export interface StreamAttachmentInfo {
  /** The stream. */
  readonly streamId: StreamId
  /** The bound Session. */
  readonly sessionId: SessionId
  /** The handler serving it. */
  readonly handler: StreamHandlerId
  /** The handler's floor. */
  readonly floor: StreamFloor
  /** The transport. */
  readonly transport: StreamTransportInfo
  /** The connection's tracks. */
  readonly tracks: readonly StreamTrack[]
  /** The external key the stream claimed, such as `room:<name>`. */
  readonly claimKey?: string
  /** The process holding the connection. */
  readonly incarnation: StreamIncarnation
  /** When the row was written, on the store's clock, in epoch milliseconds. */
  readonly startedAt: number
}

/** How an attachment closed: the payload of `stream/closed`. */
export interface StreamClosed {
  /** The stream. */
  readonly streamId: StreamId
  /** Why it closed. */
  readonly reason: StreamCloseReason
  /**
   * How long it was attached, in milliseconds on the connection's media clock; for a stream another process closed,
   * from its row's start to its last heartbeat on the store's clock.
   */
  readonly durationMs: number
  /** The failure, when it closed on one. */
  readonly error?: StreamCloseError
}

/** A held attachment. */
export interface StreamAttachment extends StreamAttachmentInfo {
  /** Resolves once the attachment closed, its rows were deleted and its pin was released; never rejects. */
  readonly closed: Promise<StreamClosed>
  /**
   * Stop the handler and close the attachment; idempotent.
   * @returns how it closed.
   */
  detach(): Promise<StreamClosed>
}

/**
 * How a detach request went: `detached` when this process held the stream and
 * closed it, `requested` when another process holds it and was asked to
 * detach it, `unknown` when no live stream has the id.
 */
export type StreamDetachOutcome = 'detached' | 'requested' | 'unknown'

/** One `attach` request before the handler validates it. */
export interface StreamAttachRequest {
  /** The handler that serves the stream. */
  readonly handler: StreamHandlerId
  /** The handler's spec. */
  readonly spec: JsonObject
  /** An external key only one live stream may hold, such as `room:<auth-normalized room>`; at most 512 UTF-8 bytes. */
  readonly claimKey?: string
}

/** Why `attach` refused or failed, discriminated by `code`. */
export type StreamsFailure =
  | { readonly code: 'streams/floor-taken'; readonly holder: StreamId }
  | { readonly code: 'streams/claimed'; readonly holder: StreamId; readonly incarnation: StreamIncarnation }
  | { readonly code: 'streams/no-handler'; readonly handler: StreamHandlerId }
  | { readonly code: 'streams/invalid-spec'; readonly diagnostics: readonly SpecDiagnostic[] }
  | { readonly code: 'streams/invalid-request'; readonly what: string }
  | { readonly code: 'streams/memory-session' }
  | { readonly code: 'streams/duplicate-stream'; readonly streamId: StreamId }
  | { readonly code: 'streams/connection-closed'; readonly streamId: StreamId }
  | { readonly code: 'streams/handler-failed'; readonly handler: StreamHandlerId }
  | { readonly code: 'streams/disposed' }

/** A failure code. */
export type StreamsFailureCode = StreamsFailure['code']

/** The payload of `stream/opened`. */
export interface StreamOpened {
  /** The stream. */
  readonly streamId: StreamId
  /** The handler serving it. */
  readonly handler: StreamHandlerId
  /** The handler's floor. */
  readonly floor: StreamFloor
  /** The transport. */
  readonly transport: StreamTransportInfo
  /** The connection's tracks. */
  readonly tracks: readonly StreamTrack[]
  /** The spec, after the handler's `redact`. */
  readonly spec: JsonObject
  /** The claimed external key. */
  readonly claimKey?: string
}

declare module '@budmh/session/types' {
  interface SessionEventMap {
    /** A live stream was attached to this Session; ignorable. */
    'stream/opened': StreamOpened
    /** A stream attached to this Session closed; ignorable. A reader keeps the first `stream/closed` of a stream. */
    'stream/closed': StreamClosed
  }
}
