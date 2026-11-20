def check_tree(value):
    """Validate in-memory JSON before canonicalization; reject implicit coercion."""
    stack = [(value, 0)]
    count = 0
    string_bytes = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > MAX_DEPTH or count > MAX_NODES:
            raise ContractError("JSON depth/node limit exceeded")
        if type(item) is dict:
            if count + len(stack) + 2 * len(item) > MAX_NODES:
                raise ContractError("JSON node limit exceeded")
            for key, child in item.items():
                if type(key) is not str:
                    raise ContractError("JSON object keys must be strings")
                stack.append((key, depth + 1))
                stack.append((child, depth + 1))
        elif type(item) is list:
            if count + len(stack) + len(item) > MAX_NODES:
                raise ContractError("JSON node limit exceeded")
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            if len(item) > MAX_BYTES:
                raise ContractError("string exceeds host byte limit")
            try:
                string_bytes += len(item.encode("utf-8"))
            except UnicodeEncodeError as error:
                raise ContractError("lone Unicode surrogate") from error
            if string_bytes > MAX_BYTES:
                raise ContractError("strings exceed host byte limit")
        elif type(item) is int:
            if abs(item) > SAFE_INTEGER:
                raise ContractError("integer exceeds exact interoperable range")
        elif type(item) is float:
            if (not math.isfinite(item) or
                    (item == 0 and math.copysign(1, item) < 0) or
                    (item.is_integer() and abs(item) > SAFE_INTEGER)):
                raise ContractError("number exceeds host numeric profile")
        elif item is not None and type(item) is not bool:
            raise ContractError("unsupported JSON value")
