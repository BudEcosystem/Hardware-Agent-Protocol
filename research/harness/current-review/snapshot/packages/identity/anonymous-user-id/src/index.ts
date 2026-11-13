/**
 * Per-harness-home anonymous user id shared by telemetry and feedback.
 *
 * The id is a random UUID persisted as a bare line in `.anonymous-user-id` inside the
 * harness home resolved by {@link resolveBudmhHome} (`$BUDMH_HOME` > `~/.budmh`),
 * and never derived from the hostname, network address, git remote, or any
 * other identifying source. It is scoped to the harness home, not the
 * machine: every process sharing one `$BUDMH_HOME` reports the same id, and
 * deleting the file mints a fresh identity on the next launch.
 *
 * The file is owner-only (`0600`) on POSIX at every write, including the
 * replacement of a corrupt one: a replacement is staged as an
 * exclusive-create sibling and renamed over the target, so the committed
 * inode always carries the stated mode instead of inheriting an existing
 * file's wider bits, and no write ever follows a link out of the home. A path
 * that is a symbolic link is refused outright, and an existing file whose bits
 * reach beyond its owner is rewritten narrow. Windows expresses no POSIX
 * mode, so the guarantee there is the exclusive create alone.
 *
 * Reads and writes are synchronous so boot-time and command consumers can
 * use one API. The result is memoized per resolved file path: one process
 * touches the disk once, and a file deleted mid-run keeps the process's id
 * until the next launch.
 *
 * @module @budmh/anonymous-user-id
 */

import { randomBytes, randomUUID } from 'node:crypto'
import { chmodSync, lstatSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync, type Stats } from 'node:fs'
import { dirname, join } from 'node:path'
import type { Branded } from '@budmh/brand'
import { resolveBudmhHome } from '@budmh/home-paths'

/** A harness-home-scoped anonymous user id (random UUID v4). */
export type AnonymousUserId = Branded<'AnonymousUserId'>

/** File inside the harness home storing the id: a bare UUID line, no wrapper format. */
export const ANONYMOUS_USER_ID_FILE_NAME = '.anonymous-user-id'

/**
 * Owner-only mode for the id file, matching the credential document's `0600`:
 * the id is a stable per-install identifier, so no other account on a shared
 * host may read or replace it. Stamped explicitly after every create, because
 * the process umask masks a creation mode but never a `chmod`.
 */
const OWNER_ONLY_FILE_MODE = 0o600

/** Owner-only creation mode for the harness home directory, matching the credential store's `0700`. */
const OWNER_ONLY_DIR_MODE = 0o700

/** Permission bits reachable by an account other than the file's owner. */
const GROUP_OTHER_BITS = 0o077

/** Random bytes in a staged replacement's name; enough that two writers never collide. */
const TEMP_NAME_BYTES = 6

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Ambient hooks for locating and generating the id; every field has a default. */
export interface AnonymousUserIdOptions {
  /** Environment consulted for `BUDMH_HOME`; defaults to `process.env`. */
  env?: NodeJS.ProcessEnv
  /** UUID generator; defaults to `crypto.randomUUID` (test hook). */
  randomUUID?: () => string
}

/** Process-lifetime memo keyed by resolved file path, so distinct test homes never share an id. */
const memo = new Map<string, AnonymousUserId>()

/**
 * Inspect the id path without following it. A symbolic link is refused rather
 * than read or replaced: on a shared or group-writable home it would otherwise
 * redirect the harness's read to an attacker-chosen file, and the pre-atomic
 * writer truncated whatever it pointed at.
 * @param file - the id path to inspect.
 * @returns whether an existing file's bits reach beyond its owner; `false` when nothing is there.
 * @throws when the path is a symbolic link.
 */
function isWiderThanOwner(file: string): boolean {
  let entry: Stats
  try {
    entry = lstatSync(file)
  } catch {
    // Absent or unstattable: nothing exists to narrow, and the caller mints.
    return false
  }
  if (entry.isSymbolicLink()) {
    throw new Error(`anonymous-user-id: ${file} is a symbolic link; refusing to read or replace it`)
  }
  // Windows reports 0666 for every file, so the repair would rewrite the id on
  // every launch; this branch cannot execute on the POSIX coverage lane.
  /* v8 ignore next */
  if (process.platform === 'win32') return false
  return (entry.mode & GROUP_OTHER_BITS) !== 0
}

/** Read a valid persisted id from the file, or `undefined` when absent/corrupt. */
function readPersistedId(file: string): AnonymousUserId | undefined {
  let text: string
  try {
    text = readFileSync(file, 'utf8')
  } catch {
    // Absent or unreadable: the caller mints and persists a fresh id.
    return undefined
  }
  const value = text.trim()
  return UUID_PATTERN.test(value) ? (value as AnonymousUserId) : undefined
}

/**
 * Replace the id file with a fresh owner-only inode. The content is staged as
 * an exclusive-create sibling, stamped `0600` past the umask, then renamed
 * over the target, so a replacement never inherits an existing file's wider
 * bits and never writes through a link. Persistence is best-effort: an
 * unwritable home leaves the caller's in-memory id in place, and a
 * replacement that never commits leaves no staged file behind.
 */
function persistId(file: string, id: AnonymousUserId): void {
  const staged = `${file}.${randomBytes(TEMP_NAME_BYTES).toString('hex')}.tmp`
  try {
    writeFileSync(staged, `${id}\n`, { encoding: 'utf8', flag: 'wx', mode: OWNER_ONLY_FILE_MODE })
  } catch {
    // Nothing was staged (read-only home, missing parent): keep the id in memory.
    return
  }
  try {
    chmodSync(staged, OWNER_ONLY_FILE_MODE)
    renameSync(staged, file)
  } catch {
    // The replacement never committed; drop the staged inode rather than
    // leaving a second copy of the id in the home.
    rmSync(staged, { force: true })
  }
}

/**
 * Create the id file, or adopt whatever already occupies the path. The
 * exclusive create settles a concurrent first launch and, for a corrupt or
 * unreadable file, hands over to the replacement writer.
 */
function mintId(file: string, generate: () => string): AnonymousUserId {
  const created = generate() as AnonymousUserId
  try {
    mkdirSync(dirname(file), { recursive: true, mode: OWNER_ONLY_DIR_MODE })
    writeFileSync(file, `${created}\n`, { encoding: 'utf8', flag: 'wx', mode: OWNER_ONLY_FILE_MODE })
    chmodSync(file, OWNER_ONLY_FILE_MODE)
    return created
  } catch {
    // A wx refusal (EEXIST) covers both a concurrent winner and a
    // pre-existing corrupt file: the reread adopts a valid winner, and an
    // invalid reread falls through to the replacement below. Non-EEXIST
    // failures (read-only home) land there too, accepted best-effort.
  }
  const winner = readPersistedId(file)
  if (winner !== undefined) return winner
  persistId(file, created)
  return created
}

/**
 * Return the harness home's anonymous user id, creating and persisting one on
 * first use. A concurrent first launch is settled by an exclusive-create
 * write: the loser rereads the winner's id. (A reread landing in the winner's
 * narrow create-to-write window can still yield two per-process ids for that
 * run; the next launch converges on the persisted one.) An id left
 * group-or-other-readable by an older install is rewritten owner-only.
 * Persistence is best-effort — a write failure (read-only home) still returns
 * a usable id for the current run so feedback and telemetry are never blocked.
 * @param options - home-location and UUID-generation seams.
 * @returns the stable per-harness-home anonymous user id.
 * @throws when the id path is a symbolic link.
 */
export function getOrCreateAnonymousUserId(options: AnonymousUserIdOptions = {}): AnonymousUserId {
  const file = join(resolveBudmhHome(undefined, options.env ?? process.env), ANONYMOUS_USER_ID_FILE_NAME)
  const cached = memo.get(file)
  if (cached !== undefined) return cached

  // One `lstat` governs both refusals: a symbolic link is refused outright,
  // and the mode of a real file decides whether it must be re-narrowed.
  const widerThanOwner = isWiderThanOwner(file)
  const persisted = readPersistedId(file)
  let id: AnonymousUserId
  if (persisted === undefined) {
    id = mintId(file, options.randomUUID ?? randomUUID)
  } else {
    id = persisted
    if (widerThanOwner) persistId(file, id)
  }
  memo.set(file, id)
  return id
}
