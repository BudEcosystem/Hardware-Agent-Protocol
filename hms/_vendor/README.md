# Vendored JSON canonicalization

`rfc8785/` contains unmodified `src/rfc8785/__init__.py`, `src/rfc8785/_impl.py` and `LICENSE` from [Trail of Bits rfc8785.py v0.1.4](https://github.com/trailofbits/rfc8785.py/tree/4d9b161f6054301d98d0566e813d020fb019ee10), commit `4d9b161f6054301d98d0566e813d020fb019ee10`. License: Apache-2.0. Its implementation also attributes portions to Andrew Rundgren's Apache-2.0 reference implementation. The retained source checkout is under `research/host-contract/repos/`.

Both Python files and the license were read completely before use. This is the first acquired library executed by the host prototype; the earlier research firmware/controller repositories remain unexecuted. HMS wraps the library with stricter parsing, size/depth limits and rejection of negative zero (RFC 8785 verified erratum 7920). HMS does not modify its internals or claim a complete independent cryptographic audit.
