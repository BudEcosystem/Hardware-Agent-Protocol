/**
 * Resolve the public SDK launch configuration to one budmh subprocess.
 * @module @budmh/sdk-client/launch
 */

import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { HarnessClientOptions } from './types.ts'

/** Default bound for a profile to answer the SDK initialize handshake. */
export const DEFAULT_INITIALIZE_TIMEOUT_MS = 10_000

/** Internal generic process launch used by the transport and fake-runtime tests. */
export interface RuntimeProcessOptions {
  command: string
  args: string[]
  cwd?: string
  /** Materialize the complete child environment when the client starts its subprocess. */
  environment: () => NodeJS.ProcessEnv
  description: string
  initializeTimeoutMs: number
  requestTimeoutMs?: number
  shutdownTimeoutMs?: number
  disposeEofGraceMs?: number
  disposeGraceMs?: number
}

/** Node argv plus internal profile patches required by one resolved budmh entry. */
export interface BudmhNodeLaunch {
  /** Arguments before the profile selector. */
  nodeArgs: string[]
  /** Internal patches applied below caller-supplied patches. */
  patches: string[]
  /** Environment values required by the resolved entry mode. */
  environment: NodeJS.ProcessEnv
}

interface PackageManifest {
  version?: unknown
  bin?: unknown
}

/** Read a package manifest from one resolved package.json URL. */
function manifest(url: string): PackageManifest {
  return JSON.parse(readFileSync(fileURLToPath(url), 'utf8')) as PackageManifest
}

/**
 * Resolve and version-check a budmh executable from package manifests.
 * @param budmhManifestUrl - resolved URL of the budmh package manifest.
 * @param clientManifestUrl - resolved URL of the SDK client manifest.
 * @returns the absolute budmh executable path.
 */
export function resolveBudmhBinFromManifests(budmhManifestUrl: string, clientManifestUrl: string): string {
  const budmhManifest = manifest(budmhManifestUrl)
  const clientManifest = manifest(clientManifestUrl)
  if (typeof budmhManifest.version !== 'string' || budmhManifest.version !== clientManifest.version) {
    throw new Error(`budmh SDK client ${String(clientManifest.version)} requires the same budmh version, got ${String(budmhManifest.version)}`)
  }
  const bin = typeof budmhManifest.bin === 'object' && budmhManifest.bin !== null
    ? (budmhManifest.bin as Record<string, unknown>).budmh
    : budmhManifest.bin
  if (typeof bin !== 'string' || bin === '') throw new Error('@budmh/cli declares no budmh executable')
  return resolve(dirname(fileURLToPath(budmhManifestUrl)), bin)
}

/**
 * Resolve and version-check the built budmh executable installed with this SDK.
 * @returns the absolute built executable path, whether or not it exists in a source checkout.
 */
export function installedBudmhBin(): string {
  return resolveBudmhBinFromManifests(
    import.meta.resolve('@budmh/cli/package.json'),
    new URL('../package.json', import.meta.url).href,
  )
}

/**
 * Resolve the Node launch for one same-version budmh package.
 * @param budmhManifestUrl - resolved URL of the budmh package manifest.
 * @param clientManifestUrl - resolved URL of the SDK client manifest.
 * @param sourceLoaderUrl - optional absolute tsx loader URL for deterministic tests.
 * @returns built output, or the source entry plus its compatibility patch and tsx environment.
 */
export function resolveBudmhNodeLaunchFromManifests(
  budmhManifestUrl: string,
  clientManifestUrl: string,
  sourceLoaderUrl?: string,
): BudmhNodeLaunch {
  const bin = resolveBudmhBinFromManifests(budmhManifestUrl, clientManifestUrl)
  if (existsSync(bin)) return { nodeArgs: [bin], patches: [], environment: {} }

  const packageDir = dirname(fileURLToPath(budmhManifestUrl))
  const sourceBin = resolve(packageDir, 'src/bin.ts')
  const sourcePatch = resolve(packageDir, 'src/sdk-source.cordis.patch.yml')
  const sourceTsconfig = resolve(packageDir, 'tsconfig.json')
  if (!existsSync(sourceBin) || !existsSync(sourcePatch) || !existsSync(sourceTsconfig)) {
    throw new Error(
      `@budmh/cli is missing its built executable ${bin} and complete source launch files ${sourceBin}, ${sourcePatch}, ${sourceTsconfig}`,
    )
  }
  const loader = sourceLoaderUrl ?? import.meta.resolve('tsx/esm')
  return {
    nodeArgs: ['--import', loader, sourceBin],
    patches: [sourcePatch],
    environment: { TSX_TSCONFIG_PATH: sourceTsconfig },
  }
}

/**
 * Resolve the installed budmh package to a built or source Node launch.
 * @returns the launch descriptor for the current checkout or installed package.
 */
function installedBudmhNodeLaunch(): BudmhNodeLaunch {
  return resolveBudmhNodeLaunchFromManifests(
    import.meta.resolve('@budmh/cli/package.json'),
    new URL('../package.json', import.meta.url).href,
  )
}

/**
 * Resolve caller-relative filesystem inputs and construct canonical budmh argv.
 * @param options - public SDK launch options.
 * @param callerCwd - parent-process directory used for lexical resolution.
 * @returns one generic subprocess spec for the JSON-RPC transport.
 */
export function resolveBudmhLaunch(
  options: HarnessClientOptions = {},
  callerCwd: string = process.cwd(),
): RuntimeProcessOptions {
  const profile = options.profile ?? 'sdk'
  const budmhLaunch = options.budmhBin === undefined
    ? installedBudmhNodeLaunch()
    : { nodeArgs: [resolve(callerCwd, options.budmhBin)], patches: [], environment: {} }
  const patches = [
    ...budmhLaunch.patches,
    ...(options.patches ?? []).map(path => resolve(callerCwd, path)),
  ]
  const budmhHome = options.budmhHome === undefined ? undefined : resolve(callerCwd, options.budmhHome)
  return {
    command: process.execPath,
    args: [...budmhLaunch.nodeArgs, '--profile', profile, ...patches.flatMap(path => ['--patch', path])],
    ...options.processCwd === undefined ? {} : { cwd: resolve(callerCwd, options.processCwd) },
    environment: () => ({
      ...(options.env ?? process.env),
      ...budmhLaunch.environment,
      ...budmhHome === undefined ? {} : { BUDMH_HOME: budmhHome },
    }),
    description: `budmh profile ${JSON.stringify(profile)}`,
    initializeTimeoutMs: options.initializeTimeoutMs ?? DEFAULT_INITIALIZE_TIMEOUT_MS,
    ...options.requestTimeoutMs === undefined ? {} : { requestTimeoutMs: options.requestTimeoutMs },
    ...options.shutdownTimeoutMs === undefined ? {} : { shutdownTimeoutMs: options.shutdownTimeoutMs },
    ...options.disposeEofGraceMs === undefined ? {} : { disposeEofGraceMs: options.disposeEofGraceMs },
    ...options.disposeGraceMs === undefined ? {} : { disposeGraceMs: options.disposeGraceMs },
  }
}
