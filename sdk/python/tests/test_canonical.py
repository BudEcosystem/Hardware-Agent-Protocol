import hashlib

import pytest

from bhms.protocol.canonical import canonical, digest
from bhms.protocol.errors import BhmsError


def test_rfc8785_number_formatting():
    # Vectors from RFC 8785 section 3.2.2.3 and Appendix B.
    assert canonical(1e30) == b"1e+30"
    assert canonical(4.5) == b"4.5"
    assert canonical(0.002) == b"0.002"
    assert canonical(1e-7) == b"1e-7"
    assert canonical(-0.0) == b"0"
    assert canonical(333333333.33333329) == b"333333333.3333333"
    assert canonical(1e21) == b"1e+21"
    assert canonical(123456789012345680000.0) == b"123456789012345680000"
    assert canonical(0.000001) == b"0.000001"


def test_rfc8785_section_3_2_3_example():
    obj = {
        "numbers": [333333333.33333329, 1e30, 4.5, 2e-3, 0.000000000000000000000000001],
        "string": "\u20ac$\u000f\u000aA'\u0042\u0022\u005c\\\"/",
        "literals": [None, True, False],
    }
    expected = (
        '{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
        '"string":"\u20ac$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
    ).encode()
    assert canonical(obj) == expected


def test_unicode_key_ordering_is_utf16_code_units():
    # U+1F600 (surrogates D83D DE00) sorts before U+FF5E (FF5E) under UTF-16 ordering.
    obj = {"～": 1, "\U0001f600": 2, "b": 3, "a": 4}
    assert canonical(obj) == '{"a":4,"b":3,"😀":2,"～":1}'.encode()


def test_whitespace_and_key_order_are_irrelevant():
    assert canonical({"b": 1, "a": [1, 2]}) == canonical({"a": [1, 2], "b": 1}) == b'{"a":[1,2],"b":1}'


def test_digest_format_and_stability():
    d = digest({"a": 1})
    assert d == "sha256:" + hashlib.sha256(b'{"a":1}').hexdigest()
    assert digest({"a": 1}) == digest({"a": 1})
    assert digest({"a": 1}) != digest({"a": 2})


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_rejected(bad):
    for fn in (canonical, digest):
        with pytest.raises(BhmsError) as ei:
            fn({"x": [bad]})
        assert ei.value.code == "INVALID_ARGUMENT"


def test_unserializable_rejected_as_invalid_argument():
    with pytest.raises(BhmsError) as ei:
        canonical({"x": object()})
    assert ei.value.code == "INVALID_ARGUMENT"
