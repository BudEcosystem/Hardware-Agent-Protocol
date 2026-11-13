#!/usr/bin/env python3
"""Convert a flat RP2040 binary (flash image at 0x10000000) to a UF2 file for BOOTSEL drag-and-drop.

    bin2uf2.py bhms_arm.bin bhms_arm.uf2

The pico-sdk normally does this with picotool, which needs git and network access at configure
time; the UF2 container is small enough to write directly (256-byte payloads, family RP2040).
"""
import struct
import sys

FLASH_BASE = 0x10000000
RP2040_FAMILY = 0xE48BFF56
MAGIC0, MAGIC1, MAGIC_END = 0x0A324655, 0x9E5D5157, 0x0AB16F30
FLAG_FAMILY = 0x00002000
PAYLOAD = 256


def encode(data: bytes, base: int = FLASH_BASE) -> bytes:
    blocks = [data[i:i + PAYLOAD] for i in range(0, len(data), PAYLOAD)]
    out = bytearray()
    for n, chunk in enumerate(blocks):
        chunk = chunk.ljust(PAYLOAD, b"\xff")
        header = struct.pack("<8I", MAGIC0, MAGIC1, FLAG_FAMILY, base + n * PAYLOAD, PAYLOAD, n,
                             len(blocks), RP2040_FAMILY)
        out += header + chunk.ljust(476, b"\x00") + struct.pack("<I", MAGIC_END)
    return bytes(out)


def decode(uf2: bytes) -> bytes:
    """Inverse of encode (used by the test): the payloads in block order."""
    out = bytearray()
    for off in range(0, len(uf2), 512):
        m0, m1, flags, addr, size, n, total, fam = struct.unpack("<8I", uf2[off:off + 32])
        assert (m0, m1) == (MAGIC0, MAGIC1) and flags == FLAG_FAMILY and fam == RP2040_FAMILY
        assert struct.unpack("<I", uf2[off + 508:off + 512])[0] == MAGIC_END
        assert addr == FLASH_BASE + n * PAYLOAD and size == PAYLOAD and total * 512 == len(uf2)
        out += uf2[off + 32:off + 32 + size]
    return bytes(out)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    data = open(sys.argv[1], "rb").read()
    open(sys.argv[2], "wb").write(encode(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
