/**
 * Deterministic identities of keyed delivery: the `DeliveryKey` brand and
 * the message id every copy of one key carries.
 * @module @budmh/session-delivery/key
 */

import { createHash } from 'node:crypto'
import { brandString, type Branded } from '@budmh/brand'
import { MessageId } from '@budmh/llm/brand'
import type { SessionId } from '@budmh/session'

/** A producer's stable key for one logical message within its namespace. */
export type DeliveryKey = Branded<'DeliveryKey'>

/** RFC 4648 base32 alphabet, lowercase. */
const BASE32 = 'abcdefghijklmnopqrstuvwxyz234567'

/** Characters of the digest kept in an id: 130 bits. */
const DIGEST_CHARS = 26

/** Namespaces are lowercase words joined by hyphens. */
const NAMESPACE = /^[a-z][a-z0-9-]*$/

/**
 * Brand a producer key.
 * @param value - a non-empty key, stable per logical message.
 * @returns the same string with the delivery-key brand.
 */
export function DeliveryKey(value: string): DeliveryKey {
  return brandString<DeliveryKey>(value)
}

/**
 * Check a producer namespace.
 * @param namespace - the namespace to check.
 * @throws TypeError when it does not match `^[a-z][a-z0-9-]*$`.
 */
export function assertDeliveryNamespace(namespace: string): void {
  if (!NAMESPACE.test(namespace)) {
    throw new TypeError(`session-delivery: namespace ${JSON.stringify(namespace)} does not match ${String(NAMESPACE)}`)
  }
}

/**
 * The first 26 lowercase RFC 4648 base32 characters (130 bits) of the SHA-256
 * of a text's UTF-8 bytes. Identities derived from content use it: delivery
 * message ids here, and the key chain of `@budmh/work-store`.
 * @param text - the text to digest.
 * @returns 26 characters of `[a-z2-7]`.
 * @example
 * keyDigest('') // '4oymiquy7qobjgx36tejs35zeq'
 */
export function keyDigest(text: string): string {
  return base32Prefix(createHash('sha256').update(text).digest())
}

/** The first {@link DIGEST_CHARS} lowercase base32 characters of a SHA-256 digest (32 bytes hold 51 whole characters). */
function base32Prefix(digest: Uint8Array): string {
  let bits = 0
  let value = 0
  let out = ''
  for (const byte of digest) {
    value = ((value << 8) | byte) & 0xfff
    bits += 8
    while (bits >= 5) {
      out += BASE32.charAt((value >>> (bits - 5)) & 31)
      bits -= 5
    }
    if (out.length >= DIGEST_CHARS) break
  }
  return out.slice(0, DIGEST_CHARS)
}

/**
 * The message id of one copy of a keyed message: `dlv-` and the first 26
 * lowercase base32 characters of SHA-256 over the JSON array
 * `[sessionId, namespace, key, generation]`. Every retry of one copy names
 * the same id, and ids of different Sessions, keys or copies differ.
 * @param sessionId - the receiving Session.
 * @param namespace - the producer namespace.
 * @param key - the producer key.
 * @param generation - the copy number, 0 for the first copy.
 * @returns the deterministic message id.
 * @throws TypeError when the namespace is malformed, the key is empty, or the generation is not a non-negative safe integer.
 */
export function deliveryMessageId(sessionId: SessionId, namespace: string, key: DeliveryKey, generation = 0): MessageId {
  assertDeliveryNamespace(namespace)
  if (key.length === 0) throw new TypeError('session-delivery: a delivery key must not be empty')
  if (!Number.isSafeInteger(generation) || generation < 0) {
    throw new TypeError(`session-delivery: generation must be a non-negative safe integer, got ${String(generation)}`)
  }
  return MessageId(`dlv-${keyDigest(JSON.stringify([sessionId, namespace, key, generation]))}`)
}
