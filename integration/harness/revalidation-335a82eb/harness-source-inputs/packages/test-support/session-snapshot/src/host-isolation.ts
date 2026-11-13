/**
 * Keep keyless snapshot runs independent of the host: the base bundle's `reachable` local-engine routes would
 * otherwise register whenever an engine happens to listen on the host's default ports, and change the recorded
 * model catalog.
 */
import { writeFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { join } from 'node:path'
import * as yaml from 'js-yaml'

/** One profile patch row. */
export interface ProfilePatchRow {
  readonly id: string
  readonly config: Readonly<Record<string, unknown>>
}

/**
 * Rows that configure no `reachable` route: the `llm-pi-ai` row keeps only the installed catalog, as it did before
 * the base bundle shipped provider profiles. A composition that tests a local engine restates the row after them.
 */
export const HOST_ENGINE_ISOLATION_ROWS: readonly ProfilePatchRow[] = [{ id: 'llm-pi-ai', config: {} }]

/** File name {@link writeHostEngineIsolationPatch} writes. */
export const HOST_ENGINE_ISOLATION_PATCH = 'host-engine-isolation.cordis.yml'

/**
 * Write {@link HOST_ENGINE_ISOLATION_ROWS} as a profile patch.
 * @param dir - an existing directory the run owns.
 * @returns the written patch path; apply it before every composition patch.
 */
export function writeHostEngineIsolationPatch(dir: string): string {
  const path = join(dir, HOST_ENGINE_ISOLATION_PATCH)
  writeFileSync(path, yaml.dump(HOST_ENGINE_ISOLATION_ROWS))
  return path
}

/** Port the base bundle's `ollama` route probes. */
export const HOST_ENGINE_PORT = 11_434

/** Options for {@link standInHostEngine}. */
export interface HostEngineStandInOptions {
  /** The harness's product name, the first token of its `user-agent`; other clients on the host are not counted. */
  readonly harnessProduct: string
  /** The port to occupy; defaults to {@link HOST_ENGINE_PORT}. */
  readonly port?: number
}

/** A local inference engine listening where the base bundle's `ollama` route looks for one. */
export interface HostEngineStandIn {
  /**
   * Listing requests it answered from the harness, identified by its `user-agent`; `undefined` when another engine
   * already held the port and answers instead.
   */
  readonly probes: number | undefined
  /** Stop listening; idempotent, and a no-op for an engine this stand-in did not start. */
  close(): Promise<void>
}

/**
 * Make an engine answer model listings on a port for the duration of a check: start a stand-in that lists one model,
 * or use the engine already listening there after confirming that it answers a listing.
 * @param options - the harness's product name and the port.
 * @returns the stand-in, which the caller closes.
 */
export async function standInHostEngine(options: HostEngineStandInOptions): Promise<HostEngineStandIn> {
  const port = options.port ?? HOST_ENGINE_PORT
  let probes = 0
  const server = createServer((request, response) => {
    const listing = request.method === 'GET' && (request.url === '/v1/models' || request.url === '/api/tags')
    // Host applications that use a local engine (an IDE assistant, a memory service) probe it too.
    if (listing && request.headers['user-agent']?.startsWith(`${options.harnessProduct}/`) === true) probes += 1
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(JSON.stringify({ data: [{ id: 'host-engine' }], models: [{ name: 'host-engine' }] }))
  })
  // A port this stand-in cannot take must already serve an engine, or the check would prove nothing.
  const bound = await new Promise<boolean>((resolve) => {
    server.once('error', () => { resolve(false) })
    server.listen(port, '127.0.0.1', () => { resolve(true) })
  })
  if (!bound) {
    const listing = await fetch(`http://127.0.0.1:${String(port)}/v1/models`).catch((error: unknown) => error)
    if (!(listing instanceof Response) || !listing.ok) {
      throw new Error(`host-engine stand-in: port ${String(port)} is unavailable and nothing there answers a model listing`)
    }
    await listing.body?.cancel()
    return { probes: undefined, close: () => Promise.resolve() }
  }
  let closed: Promise<void> | undefined
  return {
    get probes() { return probes },
    close: () => {
      closed ??= new Promise<void>((resolve) => {
        server.close(() => { resolve() })
        server.closeAllConnections()
      })
      return closed
    },
  }
}
