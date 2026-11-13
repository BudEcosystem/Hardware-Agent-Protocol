"""Principals, scopes and policy (spec/bhms/07-leases-and-authority.md §7.4, 13-security.md).

A :class:`Principal` is what the transport established (BHMS-AUTH-001, BHMS-SEC-001) plus the scopes a
:class:`Policy` grants it. Nothing in a request — arguments, ``_meta``, ``clientInfo``, device text — can change either.

Scope checks follow §7.4: ``read``; ``invoke:<deviceGlob>/<actionGlob>`` (split at the last ``/``) or
``invoke:cap:<capabilityGlob>``, where a hazardous action is granted only by a literal action name or ``admin``
(BHMS-AUTH-003); ``lease``; ``stop`` / ``stop:<deviceGlob>``; ``programs:run``; ``programs:register``; ``admin``.
``*`` matches any sequence of characters (and nothing else is special).

:class:`Policy` maps transport peers to principals:

* stdio — the parent process is the only principal (``stdio``, scopes ``admin``; BHMS-SEC-003);
* Unix socket — a principal whose ``uids`` lists the peer uid; otherwise, with ``trust_same_uid`` (default), a peer
  with the server's own uid is ``uid:<n>`` with ``admin``;
* WebSocket — the bearer token, compared in constant time against stored ``sha256`` digests only (BHMS-SEC-002);
* TCP — this SDK has no TCP credential, so a TCP peer gets no principal (requests other than ``server/discover`` are
  refused, BHMS-SEC-001).

A policy document is the ``GatewayPolicy`` of the schema (``{"principals": {name: {tokens?, uids?, scopes, bounds?}}}``);
``bounds`` narrow numeric/enumerated arguments per ``"<deviceId>/<action>"`` (BHMS-AUTH-010).

Example::

    policy = Policy.from_document({"principals": {
        "agent": {"tokens": [token_digest("s3cret")], "scopes": ["read", "invoke:stage-*/move_to"],
                  "bounds": {"stage-z/move_to": {"target": {"maximum": 100}}}},
        "operator": {"uids": [1000], "scopes": ["admin"]}}})

Thread-safety: immutable after construction.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from bhms.protocol import types
from bhms.protocol.errors import BhmsError
from bhms.transport.base import Peer


@lru_cache(maxsize=1024)
def _glob(pattern: str) -> re.Pattern[str]:
    return re.compile("^" + ".*".join(re.escape(part) for part in pattern.split("*")) + "$")


def glob_match(pattern: str, text: str) -> bool:
    """``*`` matches any sequence of characters; everything else is literal (§7.4)."""
    return bool(_glob(pattern).match(text))


def token_digest(token: str) -> str:
    """The stored form of a bearer token (BHMS-SEC-002): ``"sha256:" + hex``."""
    return "sha256:" + hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Principal:
    """An authenticated caller and its effective scopes."""

    id: str
    scopes: tuple[str, ...]
    bounds: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    gateway: bool = False

    def wire(self) -> dict[str, Any]:
        return {"id": self.id, "scopes": list(self.scopes)}

    @property
    def admin(self) -> bool:
        return "admin" in self.scopes

    def has(self, scope: str) -> bool:
        return self.admin or scope in self.scopes

    @property
    def can_read(self) -> bool:
        return self.has("read")

    @property
    def operations_all(self) -> bool:
        """Whether the principal sees every principal's operations (``admin`` or ``operations:read``, §7.4)."""
        return self.admin or "operations:read" in self.scopes

    def can_invoke(self, device_id: str, name: str, capabilities: tuple[str, ...] | list[str],
                   hazardous: bool = False) -> bool:
        """Whether an ``invoke`` scope covers ``<device_id>/<name>`` (an action, or a property for fresh
        ``transaction`` reads, BHMS-AUTH-012)."""
        if self.admin:
            return True
        for scope in self.scopes:
            if not scope.startswith("invoke:"):
                continue
            pattern = scope[len("invoke:"):]
            if pattern.startswith("cap:"):
                if not hazardous and any(glob_match(pattern[4:], cap) for cap in capabilities):
                    return True
                continue
            device_glob, sep, action_glob = pattern.rpartition("/")
            if not sep:
                continue
            if hazardous and "*" in action_glob:
                continue  # BHMS-AUTH-003: hazardous actions need a literal action name
            if glob_match(device_glob, device_id) and glob_match(action_glob, name):
                return True
        return False

    @property
    def may_stop_any(self) -> bool:
        """Whether any stop scope is granted (``stop``, ``stop:<glob>`` or ``admin``)."""
        return self.admin or any(s == "stop" or s.startswith("stop:") for s in self.scopes)

    def can_stop(self, device_id: str) -> bool:
        if self.admin or "stop" in self.scopes:
            return True
        return any(s.startswith("stop:") and glob_match(s[5:], device_id) for s in self.scopes)

    def bounds_for(self, device_id: str, action: str) -> dict[str, dict[str, Any]] | None:
        return self.bounds.get(f"{device_id}/{action}")


STDIO_PRINCIPAL = Principal("stdio", ("admin",))


@dataclass(frozen=True)
class _Entry:
    name: str
    token_digests: tuple[str, ...]
    uids: tuple[int, ...]
    principal: Principal


class Policy:
    """Maps a transport :class:`~bhms.transport.base.Peer` to a :class:`Principal`; see the module docstring.

    Args:
        principals: ``{name: {"tokens"?: [sha256 digests], "uids"?: [int], "scopes": [...], "bounds"?: {...},
            "gateway"?: bool}}``.
        trust_same_uid: grant ``admin`` to Unix peers running as the server's uid that no entry names.
        stdio_scopes: scopes of the stdio parent.
    """

    def __init__(self, principals: dict[str, dict[str, Any]] | None = None, *, trust_same_uid: bool = True,
                 stdio_scopes: tuple[str, ...] = ("admin",)) -> None:
        entries = []
        for name, spec in sorted((principals or {}).items()):
            gateway = bool(spec.get("gateway", False))
            body = {k: v for k, v in spec.items() if k != "gateway"}
            parsed = types.PolicyPrincipal.model_validate(body)
            bounds = {key: {member: types.to_wire(bound) for member, bound in members.items()}
                      for key, members in (parsed.bounds or {}).items()}
            entries.append(_Entry(name, tuple(parsed.tokens or ()), tuple(parsed.uids or ()),
                                  Principal(name, tuple(parsed.scopes), bounds, gateway)))
        self._entries = tuple(entries)
        self.trust_same_uid = trust_same_uid
        self.stdio = Principal("stdio", stdio_scopes, gateway=True)  # a launching gateway may use g- keys (OPS-037)

    @classmethod
    def from_document(cls, document: dict[str, Any], **kw: Any) -> Policy:
        """Build from a ``GatewayPolicy`` document (validated against the schema)."""
        types.GatewayPolicy.model_validate({"principals": {
            n: {k: v for k, v in p.items() if k != "gateway"} for n, p in document.get("principals", {}).items()}})
        return cls(document.get("principals", {}), **kw)

    @classmethod
    def with_token(cls, token: str, *, scopes: tuple[str, ...] = ("admin",), name: str = "token") -> Policy:
        """A policy with one bearer-token principal (plus stdio and same-uid defaults)."""
        return cls({name: {"tokens": [token_digest(token)], "scopes": list(scopes)}})

    @property
    def principals(self) -> tuple[Principal, ...]:
        return tuple(e.principal for e in self._entries)

    def by_token(self, token: str | None) -> Principal | None:
        """The principal holding ``token`` (constant-time comparison of digests, BHMS-SEC-002)."""
        if not token:
            return None
        presented = token_digest(token)
        found = None
        for entry in self._entries:
            for stored in entry.token_digests:
                if hmac.compare_digest(stored, presented):
                    found = entry.principal
        return found

    def resolve(self, peer: Peer) -> Principal | None:
        """The principal of ``peer``, or None when the peer carries no valid credential."""
        if peer.kind == "stdio":
            return self.stdio
        if peer.kind == "unix" and peer.uid is not None:
            for entry in self._entries:
                if peer.uid in entry.uids:
                    return entry.principal
            if self.trust_same_uid and peer.uid == os.getuid():
                return Principal(f"uid:{peer.uid}", ("admin",), gateway=True)
            return None
        if peer.kind in ("ws", "http"):
            return self.by_token(peer.token)
        return None

    def check_bounds(self, describe: Any, *, allow_unknown: bool = False) -> None:
        """Reject bounds that would widen a device bound (BHMS-SEC-011); ``describe(device_id)`` returns a
        description or None. Bounds for unknown devices/actions are rejected too, unless ``allow_unknown`` (a gateway
        whose upstream has not been described yet; the effective envelope is an intersection, so it never widens)."""
        from bhms.server.validation import effective_bounds

        for principal in self.principals:
            for key, members in principal.bounds.items():
                device_id, _, action = key.rpartition("/")
                desc = describe(device_id)
                if desc is None and allow_unknown:
                    continue
                if desc is None or action not in desc["actions"]:
                    raise ValueError(f"policy bounds for {principal.id!r} name unknown action {key!r}")
                schema = desc["actions"][action]["input"].get("properties", {})
                for member, bound in members.items():
                    node = schema.get(member)
                    if node is None:
                        raise ValueError(f"policy bounds for {principal.id!r}: {key} has no argument {member!r}")
                    for keyword in ("minimum", "maximum"):
                        if keyword in bound and keyword in node:
                            wider = bound[keyword] < node[keyword] if keyword == "minimum" else \
                                bound[keyword] > node[keyword]
                            if wider:
                                raise ValueError(f"policy bound {key}.{member}.{keyword}={bound[keyword]} widens the "
                                                 f"device bound {node[keyword]} (BHMS-SEC-011)")
                    if "enum" in bound and "enum" in node and not set(map(repr, bound["enum"])) <= \
                            set(map(repr, node["enum"])):
                        raise ValueError(f"policy bound {key}.{member}.enum widens the device enum (BHMS-SEC-011)")
                    effective_bounds(node, bound)  # validates the shape


class Authenticator:
    """Resolves and caches the principal of each connection from the *current* policy (BHMS-SEC-001).

    A server and a gateway both own one: ``authenticate(ctx)`` is what every handler calls first; ``reset()`` drops the
    cache when the policy changes so that new requests follow it at once (BHMS-SEC-012).
    """

    def __init__(self, policy: Callable[[], Policy]) -> None:
        self._policy = policy
        self._principals: weakref.WeakKeyDictionary[Any, Principal | None] = weakref.WeakKeyDictionary()

    def principal_of(self, ctx: Any) -> Principal | None:
        """The principal of ``ctx.session`` (None when its transport carries no valid credential)."""
        session = ctx.session
        if session in self._principals:
            return self._principals[session]
        found = self._policy().resolve(ctx.peer)
        self._principals[session] = found
        return found

    def authenticate(self, ctx: Any) -> Principal:
        """The request's principal, or ``UNAUTHORIZED`` when the transport carries no valid credential."""
        found = self.principal_of(ctx)
        if found is None:
            raise BhmsError("UNAUTHORIZED", "this connection carries no valid credential",
                            hint="connect over stdio or a permitted Unix socket, or present a bearer token "
                                 "(BHMS-SEC-001)")
        return found

    def reset(self) -> None:
        self._principals.clear()


__all__ = ["STDIO_PRINCIPAL", "Authenticator", "Policy", "Principal", "glob_match", "token_digest"]
