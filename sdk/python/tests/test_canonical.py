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
        assert ei.value.bhms_code == "INVALID_ARGUMENT"


def test_unserializable_rejected_as_invalid_argument():
    with pytest.raises(BhmsError) as ei:
        canonical({"x": object()})
    assert ei.value.bhms_code == "INVALID_ARGUMENT"


# --------------------------------------------------------------------------- fast path == reference (Task 4)

import rfc8785  # noqa: E402
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

_json = st.recursive(
    st.none() | st.booleans() | st.integers(min_value=-(2 ** 53) + 1, max_value=2 ** 53 - 1)
    | st.floats(allow_nan=False, allow_infinity=False) | st.text(),
    lambda children: st.lists(children, max_size=5) | st.dictionaries(st.text(), children, max_size=5),
    max_leaves=30)


@given(_json)
@settings(max_examples=2000, deadline=None)
def test_fast_path_is_byte_identical_to_the_reference(value):
    try:
        expected = rfc8785.dumps(value)
    except rfc8785.CanonicalizationError:
        with pytest.raises(BhmsError):
            canonical(value)
        return
    assert canonical(value) == expected


@pytest.mark.parametrize("value", [5.0, -0.0, 1e-4, 9.999e15, 1e16, 2 ** 53 + 0.0, 123456789012345680000.0, 0.1,
                                   1 / 3, 50.1, -7.25e-5, {"퟿": 1, "": 2, "\U0001f600": 3, "a": 4}])
def test_fast_path_edge_values(value):
    assert canonical(value) == rfc8785.dumps(value)
