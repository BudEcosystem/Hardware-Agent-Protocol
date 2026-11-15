"""TLS from the gateway's configuration, and "a scheme is a promise" (spec/bhms/13-security.md BHMS-SEC-004, BHMS-SEC-007).

Task 14 learnings 9 and 10: the gateway TOML had no TLS options (TLS only through the Python API), and ``wss://`` /
``https://`` listeners on loopback served plain text. The gateway now takes ``tls_cert``/``tls_key`` in ``[gateway]``,
refuses a TLS scheme without them, refuses TLS options that no listener uses, and refuses TLS under a plain scheme.
"""

from __future__ import annotations

import shutil
import ssl
import subprocess

import pytest

from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig
from bhms.gateway.config import ConfigError
from bhms.runtime.authority import token_digest

TOKEN = "gateway-tls-token"
PRINCIPALS = {"admin": {"tokens": [token_digest(TOKEN)], "scopes": ["admin"]}}


def certificate(tmp_path):
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert),
                    "-days", "1", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                   check=True, capture_output=True)
    return cert, key


def test_a_tls_scheme_needs_tls_configuration_and_tls_needs_a_tls_listener(tmp_path):
    with pytest.raises(ConfigError, match="promises TLS"):
        GatewayConfig(state_dir=tmp_path, listen=("wss://127.0.0.1:9",), principals=PRINCIPALS)
    with pytest.raises(ConfigError, match="go together"):
        GatewayConfig(state_dir=tmp_path, listen=("wss://127.0.0.1:9",), principals=PRINCIPALS, tls_cert=tmp_path / "c.pem")
    with pytest.raises(ConfigError, match="no listener uses"):
        GatewayConfig(state_dir=tmp_path, listen=("ws://127.0.0.1:9",), principals=PRINCIPALS, tls_cert=tmp_path / "c.pem",
                      tls_key=tmp_path / "k.pem")


def test_tls_paths_come_from_the_toml_file(tmp_path):
    document = {"gateway": {"listen": ["https://127.0.0.1:9/bhms"], "tls_cert": "tls/cert.pem", "tls_key": "tls/key.pem"},
                "principals": PRINCIPALS}
    config = GatewayConfig.from_dict(document, base_dir=tmp_path)
    assert config.tls_cert == tmp_path / "tls" / "cert.pem" and config.tls_key == tmp_path / "tls" / "key.pem"


async def test_a_gateway_serves_wss_with_its_configured_certificate(tmp_path, unused_tcp_port):
    cert, key = certificate(tmp_path)
    url = f"wss://127.0.0.1:{unused_tcp_port}"
    gateway = Gateway(GatewayConfig(state_dir=tmp_path / "state", listen=(url,), principals=PRINCIPALS, tls_cert=cert,
                                    tls_key=key, connect_wait_ms=100), memory=True)
    listener = await gateway.listen(url)
    try:
        context = ssl.create_default_context(cafile=str(cert))
        from bhms.transport import connect_websocket

        transport = await connect_websocket(url, token=TOKEN, ssl=context)
        client = await Client.from_transport(transport)
        try:
            assert (await client.discover()).principal.id == "admin"
        finally:
            await client.close()
        with pytest.raises(ValueError, match="use wss://"):
            await gateway.listen(f"ws://127.0.0.1:{unused_tcp_port + 1}", ssl=gateway.config.tls_context())
    finally:
        await listener.close()
        await gateway.close()
