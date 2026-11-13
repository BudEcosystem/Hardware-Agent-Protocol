"""RFC 8785 canonical JSON and content digests (sole owner of canonicalization)."""

from __future__ import annotations

import hashlib
from typing import Any

import rfc8785

from bhms.protocol.errors import BhmsError


def canonical(obj: Any) -> bytes:
    """Return the RFC 8785 (JCS) UTF-8 encoding of ``obj``.

    Raises INVALID_ARGUMENT for NaN/Infinity or values JSON cannot represent.
    Pure; thread-safe.
    """
    try:
        return rfc8785.dumps(obj)
    except (rfc8785.CanonicalizationError, TypeError) as exc:
        raise BhmsError("INVALID_ARGUMENT", f"value is not canonical-JSON serializable: {exc}",
                        hint="use finite numbers and JSON types only (null, bool, int, float, str, list, dict)") from exc


def digest(obj: Any) -> str:
    """Return ``"sha256:<hex>"`` over the canonical form of ``obj``."""
    return "sha256:" + hashlib.sha256(canonical(obj)).hexdigest()
