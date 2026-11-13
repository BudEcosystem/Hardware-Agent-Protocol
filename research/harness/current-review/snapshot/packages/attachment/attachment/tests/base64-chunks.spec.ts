import { Buffer } from 'node:buffer'
import { describe, expect, it } from 'vitest'
import { base64Chunks } from '../src/index.ts'

async function* bytes(...chunks: Uint8Array[]): AsyncGenerator<Uint8Array> {
  for (const chunk of chunks) yield chunk
}

async function collect(stream: AsyncIterable<string>): Promise<string[]> {
  const parts: string[] = []
  for await (const part of stream) parts.push(part)
  return parts
}

describe('base64Chunks', () => {
  it('splits a chunk larger than the limit and encodes smaller chunks as they arrive', async () => {
    const parts = await collect(base64Chunks(bytes(Buffer.from('abcdefg'), Buffer.from('hi')), 3))
    expect(parts.map(part => Buffer.from(part, 'base64').toString('utf8'))).toEqual(['abc', 'def', 'g', 'hi'])
  })

  it('encodes only the viewed bytes of a subarray', async () => {
    const backing = Buffer.from('xxpayloadxx')
    const parts = await collect(base64Chunks(bytes(backing.subarray(2, 9)), 64))
    expect(parts).toEqual([Buffer.from('payload').toString('base64')])
  })

  it('yields nothing for empty chunks and rethrows the stream failure', async () => {
    const failure = new Error('read failed')
    async function* failing(): AsyncGenerator<Uint8Array> {
      yield new Uint8Array(0)
      throw failure
    }
    const parts: string[] = []
    await expect((async () => { for await (const part of base64Chunks(failing(), 4)) parts.push(part) })()).rejects.toBe(failure)
    expect(parts).toEqual([])
  })
})
