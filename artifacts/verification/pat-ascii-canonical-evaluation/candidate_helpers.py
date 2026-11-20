from types import FunctionType as _FunctionType

_FAST_IMPL = rfc8785._impl


def _fast_anchor(function):
    if type(function) is not _FunctionType:
        return None
    keywords = function.__kwdefaults__
    return (function, function.__code__, function.__defaults__, keywords,
            None if keywords is None else tuple(keywords.items()))


def _fast_same(function, anchor):
    matched = (anchor is not None and type(function) is _FunctionType and
            function is anchor[0] and function.__code__ is anchor[1] and
            function.__defaults__ is anchor[2] and function.__kwdefaults__ is anchor[3])
    if not matched or anchor[4] is None:
        return matched
    keywords = function.__kwdefaults__
    return (type(keywords) is dict and len(keywords) == len(anchor[4]) and
            all(type(key) is str for key in keywords) and
            all(key in keywords and keywords[key] is value for key, value in anchor[4]))


_FAST_FUNCTIONS = tuple((namespace, name, _fast_anchor(namespace[name]))
    for namespace, names in (
        (globals(), ('check_tree',)),
        (vars(rfc8785), ('dumps', 'dump')),
        (vars(_FAST_IMPL), ('dumps', 'dump', '_serialize_str', '_serialize_float')),
        (vars(json.JSONEncoder), ('__init__', 'default', 'encode', 'iterencode')))
    for name in names)
_FAST_CONSTANTS = (MAX_BYTES, MAX_DEPTH, MAX_NODES, SAFE_INTEGER,
                   _FAST_IMPL._INT_MIN, _FAST_IMPL._INT_MAX)
_FAST_ESCAPES = tuple(_FAST_IMPL._ESCAPE_DCT.items())
_FAST_IDENTITIES = tuple((namespace, name, namespace[name])
    for namespace, names in (
        (vars(_FAST_IMPL), ('_ESCAPE', 'BytesIO')),
        (vars(json), ('JSONEncoder',)),
        (vars(json.encoder), ('JSONEncoder', 'c_make_encoder', 'encode_basestring')))
    for name in names)


def _fast_allowed():
    if json.encoder.c_make_encoder is None:
        return False
    constants = (MAX_BYTES, MAX_DEPTH, MAX_NODES, SAFE_INTEGER,
                 _FAST_IMPL._INT_MIN, _FAST_IMPL._INT_MAX)
    if any(type(value) is not int for value in constants) or constants != _FAST_CONSTANTS:
        return False
    if any(not _fast_same(namespace.get(name), anchor) for namespace, name, anchor in _FAST_FUNCTIONS):
        return False
    if any(namespace.get(name) is not expected for namespace, name, expected in _FAST_IDENTITIES):
        return False
    escapes = _FAST_IMPL._ESCAPE_DCT
    if type(escapes) is not dict or len(escapes) != len(_FAST_ESCAPES):
        return False
    if not all(type(key) is str and type(value) is str for key, value in escapes.items()):
        return False
    return all(escapes.get(key) == value for key, value in _FAST_ESCAPES)


class _UseReference(Exception):
    pass


def _integer_tree(value):
    kind = type(value)
    if kind is dict:
        # The original check_tree has already bounded and validated every key.
        return {key: _integer_tree(value[key])
                for key in sorted(value, key=lambda key: key.encode('utf-16be'))}
    if kind is list:
        return [_integer_tree(child) for child in value]
    if value is None or kind in (bool, int, str):
        return value
    # A float anywhere sends the whole original value to the original encoder.
    raise _UseReference


class _UseUtf16Order(Exception):
    pass


def _ascii_integer_tree(value):
    """Detach validated containers whose field names use ASCII ordering."""
    kind = type(value)
    if kind is dict:
        if not all(key.isascii() for key in value):
            raise _UseUtf16Order
        return {key: _ascii_integer_tree(child) for key, child in value.items()}
    if kind is list:
        return [_ascii_integer_tree(child) for child in value]
    if value is None or kind in (bool, int, str):
        return value
    raise _UseReference


def _canonical_bytes(value):
    if not _fast_allowed():
        return rfc8785.dumps(value)
    try:
        try:
            ordered = _ascii_integer_tree(value)
            sort_keys = True
        except _UseUtf16Order:
            ordered = _integer_tree(value)
            sort_keys = False
    except _UseReference:
        return rfc8785.dumps(value)
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False,
        check_circular=True, sort_keys=sort_keys, skipkeys=False, separators=(',', ':'))
    return encoder.encode(ordered).encode('utf-8')
