import { expect, it } from 'vitest'
import { decodeBridgeReply } from '../src/reply.ts'
it.each([
  '{', 'null', '{"ok":true}', '{"ok":true,"result":{},"extra":1}',
  '{"ok":false,"error":{"code":"arbitrary text"},"outcome":"unconfirmed"}',
  '{"ok":false,"error":{"code":"DENIED","detail":"private"},"outcome":"unconfirmed"}',
  '{"ok":false,"error":{"code":"DENIED"},"outcome":"unconfirmed","extra":1}',
  '{"ok":false,"error":{"code":"DENIED"},"outcome":"no_effect"}',
])('contains malformed bridge output %s', (text) => {
  expect(decodeBridgeReply(text)).toEqual({ ok: false, error: { code: 'INVALID_RESPONSE' }, outcome: 'unconfirmed' })
})
it('retains only a closed typed error and unmodified checked success', () => {
  expect(decodeBridgeReply('{"ok":false,"error":{"code":"KEY_CONFLICT"},"outcome":"unconfirmed"}')).toEqual({ ok: false, error: { code: 'KEY_CONFLICT' }, outcome: 'unconfirmed' })
  expect(decodeBridgeReply('{"ok":true,"result":{"mayHaveActed":true,"effectVerification":"unverified"}}')).toEqual({ ok: true, result: { mayHaveActed: true, effectVerification: 'unverified' } })
})
