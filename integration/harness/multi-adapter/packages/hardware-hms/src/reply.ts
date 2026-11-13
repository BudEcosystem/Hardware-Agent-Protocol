/** Decode the trusted checked-client bridge's bounded JSON carrier. */
import type { HardwareReply } from '@budmh/experimental-hardware'
export function unconfirmed(code: string): HardwareReply { return { ok: false, error: { code }, outcome: 'unconfirmed' } }
/** Malformed output never becomes operation success or a displayable arbitrary error string. */
export function decodeBridgeReply(text: string): HardwareReply {
  let reply: unknown
  try { reply = JSON.parse(text) } catch { return unconfirmed('INVALID_RESPONSE') }
  if (typeof reply !== 'object' || reply === null || !('ok' in reply)) return unconfirmed('INVALID_RESPONSE')
  if (reply.ok === true && 'result' in reply && Object.keys(reply).length === 2) return reply as HardwareReply
  if (reply.ok === false && Object.keys(reply).length === 3 && 'outcome' in reply && reply.outcome === 'unconfirmed'
    && 'error' in reply && typeof reply.error === 'object' && reply.error !== null && Object.keys(reply.error).length === 1
    && 'code' in reply.error && typeof reply.error.code === 'string' && /^[A-Z][A-Z0-9_]{0,63}$/.test(reply.error.code)) return unconfirmed(reply.error.code)
  return unconfirmed('INVALID_RESPONSE')
}
