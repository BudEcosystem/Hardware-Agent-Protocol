"""Checked one-attempt local client. Transport loss is never a new operation."""
from pathlib import Path

from .api_contracts import validate_params, validate_result
from .contracts import canonical, parse_json
from .ipc import call


class Client:
    def __init__(self, socket_path):
        self.socket_path = Path(socket_path)

    def request(self, method, params):
        # JCS normalizes 1.0 to 1. Check exact-type input constraints before that
        # normalization, as well as checking the immutable wire snapshot below.
        validate_params(method, params)
        # Snapshot before sending, so later caller mutation cannot alter the
        # response correlation or immutable operation identity.
        snapshot = parse_json(canonical(params))
        validate_params(method, snapshot)
        result = call(self.socket_path, method, snapshot)
        return validate_result(method, result, snapshot)
