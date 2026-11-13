/**
 * Service Definition of the MCP connection seam (`ctx.mcpClients`): open a
 * supervised session to one MCP server, list and call its tools, and observe
 * tool-list changes. The tool bridge (`@budmh/mcp-client`) is one Consumer;
 * others call tools directly without registering them on `ctx.tools`.
 * @module @budmh/mcp-client/definition
 */

import { Service, type Context } from '@budmh/cordis'
import type { McpResourceProvider } from '@budmh/mcp-resources'
import type { Tool } from '@modelcontextprotocol/client'

declare module '@budmh/cordis' {
  interface Context {
    mcpClients: McpClients
  }
}

/** Automatic reconnect policy for one MCP server connection. */
export interface ReconnectConfig {
  /** Reconnect automatically after a lost connection (default true). */
  enabled?: boolean
  /** First reconnect delay in milliseconds; doubles per consecutive failed attempt (default 500). */
  initialDelayMs?: number
  /** Backoff ceiling in milliseconds; also the uptime after which the attempt budget resets (default 30000). */
  maxDelayMs?: number
  /** Consecutive failed attempts per outage before giving up for good (default 10). */
  maxAttempts?: number
}

/** Connection fields every transport shares. */
export interface McpConnectionOptions {
  /** Stable local server namespace; `[A-Za-z0-9_-]{1,32}`. It labels diagnostics and the instruction heading. */
  serverName: string
  /** Timeout per tool call or resource request in milliseconds. */
  toolCallTimeoutMs: number
  /** Maximum UTF-8 bytes of attributed server instructions (default 32768). */
  maxInstructionBytes?: number
  /** Automatic reconnect policy after a lost connection; omission uses the defaults. */
  reconnect?: ReconnectConfig
  /** Whether a progress notification restarts a call's timeout (default true). */
  progressResetsTimeout?: boolean
  /** Upper bound in milliseconds on one call however much progress it reports; omission leaves it unbounded. */
  maxTotalTimeoutMs?: number
}

/** A server started as a child process over stdio. */
export interface StdioConnectConfig extends McpConnectionOptions {
  /** Selects child-process stdio transport. */
  transport: 'stdio'
  /** Executable used to start the server. */
  command: string
  /** Arguments passed directly, without shell interpolation. */
  args: string[]
  /** Extra env vars merged on top of scrubbed ambient env. */
  env: Record<string, string>
  /** Working directory for the child process. */
  cwd: string
}

/** A server reached over Streamable HTTP. */
export interface StreamableHttpConnectConfig extends McpConnectionOptions {
  /** Selects Streamable HTTP transport. */
  transport: 'streamable-http'
  /** MCP endpoint URL. */
  url: string
  /** Additional headers attached to MCP requests. */
  headers: Record<string, string>
  /**
   * Credential reference (an environment-variable name) whose value is sent as
   * `Authorization: Bearer <value>`. It is resolved through `ctx.credentials`
   * at every connection attempt, so a rotated value applies on reconnect.
   */
  bearerCredential?: string
}

/** What {@link McpClients.connect} needs to open one session. */
export type McpConnectConfig = StdioConnectConfig | StreamableHttpConnectConfig

/** One MCP tool exactly as the server lists it. */
export type McpToolInfo = Tool

/** One progress notification of a running tool call. */
export interface McpProgress {
  /** Progress so far; increases with every notification. */
  readonly progress: number
  /** The total, when the server knows it. */
  readonly total?: number
  /** A human-readable status line, when the server sends one. */
  readonly message?: string
}

/** Per-call options of {@link McpSession.callTool}. */
export interface McpCallOptions {
  /** Cancels the call. */
  readonly signal: AbortSignal
  /** Receives each progress notification in order; omission requests no progress. */
  readonly onProgress?: (progress: McpProgress) => void
}

/** The first connection attempt's result. */
export interface McpConnectionOutcome {
  /** The failure of the first attempt, including a failed tool-list listener; absent on success. */
  error?: unknown
}

/** What a tool-list listener learns about one change. */
export interface McpToolsChange {
  /** Whether the change belongs to the session's first connection attempt. */
  readonly initial: boolean
}

/**
 * One supervised connection to an MCP server. The session survives
 * reconnects: it restarts a lost server with bounded backoff and keeps one
 * handle across connection generations.
 */
export interface McpSession {
  /** The configured server namespace. */
  readonly serverName: string
  /**
   * Settles when the first connection attempt completes; the session keeps
   * reconnecting after a failed first attempt unless reconnect is disabled.
   */
  readonly ready: Promise<McpConnectionOutcome>
  /**
   * The last connected server's attributed instructions.
   * @returns `### MCP server: <name>` followed by the server text, or an empty string.
   */
  instructions(): string
  /** Resource requests through the live connection. */
  readonly resources: McpResourceProvider
  /**
   * List the server's tools through the current connection.
   * @param options - optional cancellation.
   * @returns the tools as the server lists them; empty when it offers no tools capability.
   * @throws {Error} while no connection exists.
   */
  listTools(options?: { readonly signal?: AbortSignal }): Promise<readonly McpToolInfo[]>
  /**
   * Call one tool by its server-side name through the live connection.
   * @param rawName - the server's tool name.
   * @param args - the tool arguments.
   * @param options - cancellation and an optional progress receiver.
   * @returns the raw `CallToolResult`, unvalidated.
   * @throws {Error} while the server is disconnected, and on protocol or timeout failure.
   */
  callTool(rawName: string, args: Record<string, unknown>, options: McpCallOptions): Promise<unknown>
  /**
   * Observe tool-list changes. Listeners run one at a time, in registration
   * order: after each connection generation is established (a rejection fails
   * that attempt, so a first-attempt rejection becomes {@link ready}'s error)
   * and after each `tools/list_changed` notification (a rejection is logged).
   * A queued run is skipped once its generation is replaced.
   * @param listener - receives whether the change belongs to the first attempt.
   * @returns the disposer that removes the listener.
   */
  onToolsChanged(listener: (change: McpToolsChange) => void | Promise<void>): () => void
  /**
   * Observe the session giving up: reconnect exhausted its attempts, so the
   * server stays unavailable until the owner reconnects.
   * @param listener - called once, after queued tool-list runs.
   * @returns the disposer that removes the listener.
   */
  onUnavailable(listener: () => void): () => void
  /**
   * Stop reconnecting, close the live connection, and wait until every queued
   * listener run settled. Idempotent; scope disposal calls it too.
   * @returns when the session is quiescent.
   */
  close(): Promise<void>
}

/**
 * `ctx.mcpClients`: opens supervised MCP sessions. One provider serves a
 * process; `@budmh/mcp-client/clients` is the shipped one.
 */
export abstract class McpClients extends Service {
  /** @param ctx - the providing plugin's context. */
  constructor(ctx: Context) {
    super(ctx, 'mcpClients')
  }

  /**
   * Open a supervised session owned by the CALLER's scope: disposing that
   * scope closes the session. The first connection attempt starts at once.
   * @param config - transport, server namespace, timeouts, reconnect policy, and credential.
   * @returns the session handle.
   * @throws {Error} on an invalid reconnect policy or credential reference.
   */
  abstract connect(config: McpConnectConfig): McpSession
}
