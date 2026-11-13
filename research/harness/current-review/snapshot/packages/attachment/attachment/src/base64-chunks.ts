/** Base64 framing of attachment byte streams for Remote `data` items. */
import { Buffer } from 'node:buffer'

/**
 * Re-chunk a byte stream into base64 text, each part encoding at most `chunkBytes` bytes. A stream chunk larger
 * than `chunkBytes` is split; smaller chunks are encoded as they arrive, without being joined.
 * @param stream - the bytes, such as `AttachmentStore.readFileStream`'s stream.
 * @param chunkBytes - most bytes one part encodes; a positive integer.
 * @returns the base64 parts in stream order; ends when the stream ends and rethrows its failure.
 */
export async function* base64Chunks(stream: AsyncIterable<Uint8Array>, chunkBytes: number): AsyncGenerator<string> {
  for await (const chunk of stream) {
    for (let offset = 0; offset < chunk.byteLength; offset += chunkBytes) {
      const part = chunk.subarray(offset, Math.min(chunk.byteLength, offset + chunkBytes))
      yield Buffer.from(part.buffer, part.byteOffset, part.byteLength).toString('base64')
    }
  }
}
