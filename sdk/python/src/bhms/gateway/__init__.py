"""The BHMS gateway: aggregation, policy, cross-device leases, isolation, stop fan-out and serving.

``Gateway(GatewayConfig(...))`` or ``python -m bhms.gateway gateway.toml``; see :mod:`bhms.gateway.gateway` for the model
and ``examples/bhms/gateway.toml`` for a runnable configuration.
"""

from bhms.gateway.config import ConfigError, GatewayConfig, UpstreamConfig, load_config
from bhms.gateway.gateway import Gateway
from bhms.gateway.journal import upstream_key

__all__ = ["ConfigError", "Gateway", "GatewayConfig", "UpstreamConfig", "load_config", "upstream_key"]
