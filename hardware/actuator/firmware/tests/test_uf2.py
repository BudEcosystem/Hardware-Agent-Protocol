"""bin2uf2: the UF2 container round-trips and has the exact block layout BOOTSEL expects."""
import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import bin2uf2  # noqa: E402


class Uf2(unittest.TestCase):
    def test_round_trip_and_layout(self):
        data = bytes(range(256)) * 3 + b"tail"
        uf2 = bin2uf2.encode(data)
        self.assertEqual(len(uf2), 512 * 4)  # 3 full blocks + 1 padded
        back = bin2uf2.decode(uf2)
        self.assertEqual(back[:len(data)], data)
        self.assertEqual(back[len(data):], b"\xff" * (len(back) - len(data)))
        first = struct.unpack("<8I", uf2[:32])
        self.assertEqual(first[0], 0x0A324655)
        self.assertEqual(first[3], 0x10000000)   # flash base
        self.assertEqual(first[7], 0xE48BFF56)   # RP2040 family
        self.assertEqual(first[6], 4)            # block count

    def test_empty(self):
        self.assertEqual(bin2uf2.encode(b""), b"")


if __name__ == "__main__":
    unittest.main()
