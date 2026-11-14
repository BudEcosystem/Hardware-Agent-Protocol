"""Gateway configuration: one TOML document (spec/bhms/13-security.md §13.2 for the policy part).

A gateway is configured by one file (``tomllib``), validated when it is loaded so a typo fails at start-up with the
key it concerns, never at the first request::

    [gateway]
    id = "lab-gw"                      # identity used to derive upstream idempotency keys (BHMS-AUTH-014)
    state_dir = "state"                # the forwarding journal lives here (relative paths: next to this file)
    listen = ["unix:gateway.sock", "ws://127.0.0.1:8765", "http://127.0.0.1:8766/bhms"]   # and/or "stdio"
    upstream_timeout_ms = 10000        # per-call timeout on every upstream (BHMS-SEC-061)

    [[upstream]]                       # one per device server; ``name`` prefixes its device ids: name/deviceId
    name = "bench"
    stdio = "{python} servers/stage.py"      # spawned over stdio; {python} and {config_dir} are expanded
    # url = "unix:/run/pump.sock"      # or connect to a running server (ws://host:port needs token_env)
    # token_env = "PUMP_TOKEN"

    [principals.lab-agent]             # GatewayPolicy: tokens are sha256 digests, never plaintext (BHMS-SEC-002)
    tokens = ["sha256:<hex of the token>"]
    scopes = ["read", "lease", "invoke:bench/*/*", "stop:bench/*"]   # <deviceGlob>/<actionGlob>, split at the last "/";
                                       # an agent can stop what it can move (authority.agent_scopes); check with
                                       # ``bhms gateway check-policy <this file>``
    bounds = {"bench/stage-z/move_to" = {target = {maximum = 100}}}

Every ``[gateway]`` key has a default; see :class:`GatewayConfig`. :func:`load_config` reads a file,
:meth:`GatewayConfig.from_dict` an already-parsed table (tests, embedding).

Thread-safety: configuration objects are immutable after loading.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
import tomllib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bhms.protocol import types
from bhms.transport.base import Transport

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
Connector = Callable[[], Awaitable[Transport]]


class ConfigError(ValueError):
    """The configuration is invalid; the message names the offending key."""


@dataclass(frozen=True)
class UpstreamConfig:
    """One upstream device server.

    ``name`` is the namespace prefix (``[A-Za-z0-9._-]{1,32}``, no ``/``): its device ``stage-z`` becomes
    ``<name>/stage-z``. Exactly one of ``stdio`` (command line, spawned and restarted by the gateway), ``url``
    (``unix:<path>``, ``ws[s]://host:port``) or ``connector`` (an async callable returning a
    :class:`~bhms.transport.base.Transport`; embedding and tests) is given.

    ``timeout_ms`` bounds every call (BHMS-SEC-061); ``queue_size`` bounds the calls waiting behind ``max_inflight``
    running ones, beyond which the gateway answers ``BUSY``; ``health_interval_ms`` is the liveness probe period (a probe
    that is not answered within ``health_timeout_ms`` marks the upstream's devices unavailable).
    """

    name: str
    stdio: str | None = None
    url: str | None = None
    connector: Connector | None = field(default=None, compare=False)
    token: str | None = field(default=None, repr=False)
    timeout_ms: int = 10_000
    queue_size: int = 64
    max_inflight: int = 32
    health_interval_ms: int = 2_000
    health_timeout_ms: int = 2_000
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None

    def __post_init__(self) -> None:
        if not NAME.match(self.name):
            raise ConfigError(f"upstream name {self.name!r} must be 1-32 characters of [A-Za-z0-9._-] "
                              "(it prefixes device ids and cannot contain '/')")
        if sum(x is not None for x in (self.stdio, self.url, self.connector)) != 1:
            raise ConfigError(f"upstream {self.name!r}: give exactly one of stdio, url or connector")
        for key in ("timeout_ms", "queue_size", "max_inflight", "health_interval_ms", "health_timeout_ms"):
            if getattr(self, key) < 1:
                raise ConfigError(f"upstream {self.name!r}: {key} must be at least 1")

    @property
    def target(self) -> str:
        """What ``bhms.client.client.open_transport`` connects to (``stdio:<cmd>`` or the url)."""
        return f"stdio:{self.stdio}" if self.stdio is not None else (self.url or "")


@dataclass(frozen=True)
class GatewayConfig:
    """The gateway's settings; every field has a default except ``upstreams`` and ``principals``.

    ``principals`` is a ``GatewayPolicy`` document's ``principals`` table (tokens as ``sha256:`` digests).
    ``durability`` is the store mode of :mod:`bhms.runtime.store` (``dispatch``: fsync before every dispatch, which for a gateway is the pending-forward row written before an invoke is sent).
    ``trust_same_uid`` grants ``admin`` to Unix-socket peers with the gateway's uid that no principal names.
    """

    id: str = "gateway"
    state_dir: Path = Path("state")
    durability: str = "dispatch"
    listen: tuple[str, ...] = ()
    upstreams: tuple[UpstreamConfig, ...] = ()
    principals: dict[str, dict[str, Any]] = field(default_factory=dict)
    trust_same_uid: bool = True
    instructions: str | None = None
    key_retention_s: int = 7 * 86400
    event_retention_s: int = 7 * 86400
    max_wait_ms: int = 60_000
    max_page_size: int = 500
    lease_min_ttl_ms: int = 1000
    lease_max_ttl_ms: int = 600_000
    lease_max_wait_ms: int = 30_000
    stop_deadline_ms: int = 3000
    connect_wait_ms: int = 10_000
    upstream_timeout_ms: int = 10_000
    observation_min_interval_ms: int = 50
    http_path: str = "/bhms"
    source: Path | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not NAME.match(self.id):
            raise ConfigError(f"gateway id {self.id!r} must be 1-32 characters of [A-Za-z0-9._-]")
        if self.durability not in ("dispatch", "full", "process"):
            raise ConfigError(f"durability {self.durability!r} must be dispatch, full or process")
        names = [u.name for u in self.upstreams]
        if len(set(names)) != len(names):
            raise ConfigError(f"upstream names must be unique, got {sorted(n for n in names if names.count(n) > 1)}")
        if self.key_retention_s < 86_400:
            raise ConfigError("key_retention_s must be at least 86400 (BHMS-OPS-034)")
        try:
            types.GatewayPolicy.model_validate({"principals": {
                n: {k: v for k, v in p.items() if k != "gateway"} for n, p in self.principals.items()}})
        except ValueError as exc:
            raise ConfigError(f"[principals] is not a valid GatewayPolicy: {exc}") from None

    @classmethod
    def from_dict(cls, document: dict[str, Any], *, base_dir: Path | None = None,
                  source: Path | None = None) -> GatewayConfig:
        """Build from a parsed TOML table; relative ``state_dir``/``cwd`` resolve against ``base_dir``."""
        base = base_dir or Path.cwd()
        unknown = set(document) - {"gateway", "upstream", "principals"}
        if unknown:
            raise ConfigError(f"unknown top-level table(s) {sorted(unknown)}; expected [gateway], [[upstream]], "
                              "[principals.<name>]")
        section = dict(document.get("gateway", {}))
        known = set(cls.__dataclass_fields__) - {"upstreams", "principals", "source"}
        bad = set(section) - known
        if bad:
            raise ConfigError(f"unknown [gateway] key(s) {sorted(bad)}; known: {sorted(known)}")
        if "state_dir" in section:
            section["state_dir"] = _path(section["state_dir"], base)
        else:
            section["state_dir"] = base / "state"
        if "listen" in section:
            section["listen"] = tuple(_listen(item, base) for item in section["listen"])
        timeout = int(section.get("upstream_timeout_ms", 10_000))
        upstreams = tuple(_upstream(entry, base, timeout) for entry in document.get("upstream", []))
        return cls(upstreams=upstreams, principals=dict(document.get("principals", {})), source=source, **section)


def _path(value: str, base: Path) -> Path:
    path = Path(os.path.expanduser(value))
    return path if path.is_absolute() else base / path


def _listen(item: str, base: Path) -> str:
    if item.startswith("unix:") and not item[5:].startswith(("/", "//")):
        return f"unix:{base / item[5:]}"
    return item


def _expand(text: str, base: Path, *, quote: bool = True) -> str:
    """Expand ``{python}`` (this interpreter) and ``{config_dir}`` (the directory of the configuration file); shell-quoted
    for command lines, verbatim for environment values."""
    wrap = shlex.quote if quote else str
    return text.replace("{python}", wrap(sys.executable)).replace("{config_dir}", wrap(str(base)))


def _upstream(entry: dict[str, Any], base: Path, default_timeout_ms: int) -> UpstreamConfig:
    entry = {"timeout_ms": default_timeout_ms, **entry}
    where = f"upstream {entry.get('name', '?')!r}"
    known = {"name", "stdio", "url", "token_env", "token_file", "timeout_ms", "queue_size", "max_inflight",
             "health_interval_ms", "health_timeout_ms", "env", "cwd"}
    bad = set(entry) - known
    if bad:
        raise ConfigError(f"{where}: unknown key(s) {sorted(bad)}; known: {sorted(known)}")
    token = None
    if "token_env" in entry:
        token = os.environ.get(entry.pop("token_env"))
        if not token:
            raise ConfigError(f"{where}: token_env names an unset environment variable")
    if "token_file" in entry:
        token = _path(entry.pop("token_file"), base).read_text().strip()
    if "stdio" in entry:
        entry["stdio"] = _expand(entry["stdio"], base)
    if "url" in entry and entry["url"].startswith("unix:") and not entry["url"][5:].startswith(("/", "//")):
        entry["url"] = f"unix:{base / entry['url'][5:]}"
    if "env" in entry:
        entry["env"] = {k: _expand(str(v), base, quote=False) for k, v in entry["env"].items()}
    entry.setdefault("cwd", str(base))
    return UpstreamConfig(token=token, **entry)


def load_config(path: str | os.PathLike[str]) -> GatewayConfig:
    """Read and validate a gateway TOML file."""
    file = Path(path).resolve()
    try:
        document = tomllib.loads(file.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{file}: {exc}") from None
    return GatewayConfig.from_dict(document, base_dir=file.parent, source=file)


__all__ = ["ConfigError", "Connector", "GatewayConfig", "UpstreamConfig", "load_config"]
