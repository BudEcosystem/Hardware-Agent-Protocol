"""Minimal S-expression reader/writer for KiCad files.

Atoms are kept as Python ``str`` (symbols and numbers, verbatim) or
``Q`` (quoted strings), so a parse -> dump round trip preserves KiCad's
distinction between ``(layer F.Cu)`` and ``(layer "F.Cu")``.
"""

from __future__ import annotations

from typing import Iterator, Union


class Q(str):
    """A quoted string atom."""


Node = Union[str, Q, list]


def _tokens(text: str) -> Iterator[str | Q]:
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "()":
            yield c
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    nxt = text[j + 1]
                    buf.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, "\\" + nxt))
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            yield Q("".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            yield text[i:j]
            i = j


def loads(text: str) -> list:
    stack: list[list] = [[]]
    for tok in _tokens(text):
        if tok == "(" and not isinstance(tok, Q):
            stack.append([])
        elif tok == ")" and not isinstance(tok, Q):
            node = stack.pop()
            stack[-1].append(node)
        else:
            stack[-1].append(tok)
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError("unbalanced s-expression")
    return stack[0][0]


def _atom(a) -> str:
    if isinstance(a, Q):
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(a, bool):
        return "yes" if a else "no"
    if isinstance(a, float):
        s = f"{a:.6f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(a)


def dumps(node: Node, indent: int = 0) -> str:
    if not isinstance(node, list):
        return _atom(node)
    # Short lists of atoms stay on one line; others break per child list.
    if all(not isinstance(x, list) for x in node) or (len(node) <= 4 and sum(isinstance(x, list) for x in node) <= 1
                                                      and len(_flat(node)) < 80):
        return "(" + " ".join(dumps(x) for x in node) + ")"
    pad = "\t" * (indent + 1)
    head = []
    rest = []
    for x in node:
        (rest if isinstance(x, list) or rest else head).append(x)
    out = "(" + " ".join(dumps(x) for x in head)
    for x in rest:
        out += "\n" + pad + dumps(x, indent + 1)
    return out + "\n" + "\t" * indent + ")"


def _flat(node: list) -> str:
    return "(" + " ".join(_flat(x) if isinstance(x, list) else _atom(x) for x in node) + ")"


def find(node: list, key: str) -> list | None:
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(node: list, key: str) -> list[list]:
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def walk(node: list) -> Iterator[list]:
    yield node
    for x in node:
        if isinstance(x, list):
            yield from walk(x)
