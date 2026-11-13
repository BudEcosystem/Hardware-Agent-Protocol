#!/usr/bin/env python3
"""Compute the BHMS description digest and the C initialiser for `digest8`.

    bhms_digest.py sidecar.json            # prints sha256:... and the C bytes
    bhms_digest.py sidecar.json --check    # also validates the description
                                           # against the BHMS device model

digest = sha256 over the JCS form of the description without `digest`
(BHMS-DEV-021); digest8 is its first 8 bytes (spec 11.2 HELLO). The canonical
form is the reference implementation's (sdk/python), imported read-only.
"""
import argparse
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sdk" / "python" / "src"))

from bhms.protocol.canonical import canonical  # noqa: E402


def digest_of(description: dict) -> bytes:
    body = {k: v for k, v in description.items() if k != "digest"}
    return hashlib.sha256(canonical(body)).digest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sidecar")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    description = json.loads(pathlib.Path(args.sidecar).read_text())
    raw = digest_of(description)
    if args.check:
        from bhms.protocol.types import DeviceDescription

        DeviceDescription.model_validate({**description, "digest": "sha256:" + raw.hex()})
    print("sha256:" + raw.hex())
    print("{" + ", ".join(f"0x{b:02x}" for b in raw[:8]) + "}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
