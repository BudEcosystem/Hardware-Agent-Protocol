import copy
import hashlib
import json
from pathlib import Path
import struct
import unittest

from hms._vendor import rfc8785
from hms.contracts import (ContractError, DIGEST_PREFIX, canonical, intent_digest,
                           parse_invoke, parse_json)
from journal_support import request


class ContractTests(unittest.TestCase):
    def test_identity_is_semantic_order_and_numeric_spelling(self):
        first = parse_invoke(request("ns:fixture"))["intent"]
        second = dict(reversed(list(first.items())))
        second["arguments"] = {"unit": "um", "frame": "stage", "distance": 5.0}
        self.assertEqual(intent_digest(first), intent_digest(second))
        changed = copy.deepcopy(first)
        changed["endpointSession"] = "session:2"
        self.assertNotEqual(intent_digest(first), intent_digest(changed))
        self.assertEqual(intent_digest(first), "sha256:" + hashlib.sha256(DIGEST_PREFIX + canonical(first)).hexdigest())

    def test_all_pinned_intent_fields_change_digest(self):
        first = parse_invoke(request("ns:fixture"))["intent"]
        replacements = {"instanceId": "other", "actionId": "other", "endpointSession": "other",
                        "controlGeneration": "other", "descriptionDigest": "sha256:" + "b" * 64,
                        "bindingGeneration": "other", "calibrationRevision": "other",
                        "arguments": {"distance": 6}, "requiredEffect": "physical_verified",
                        "timing": first["timing"] | {"maxRunMs": 501}}
        for key, value in replacements.items():
            with self.subTest(key=key):
                self.assertNotEqual(intent_digest(first), intent_digest(first | {key: value}))

    def test_malformed_json_and_precision_are_rejected(self):
        invalid = [b'{"a":1,"a":2}', b'{"a":1,"\\u0061":2}', b'NaN', b'Infinity',
                   b'-Infinity', b'-0', b'-0.0', b'-0e+10', b'1e999', b'1e-999',
                   b'1.0000000000000001', b'9007199254740993', b'9007199254740992.0',
                   b'1e9999999999999999999999999', b'0e-999999999999999999999999',
                   b'"\\udead"', b'"\xff"', b'\xef\xbb\xbf{}', b'{} trailing',
                   b'1' * 129, b'[' * 1200 + b'0' + b']' * 1200]
        for data in invalid:
            with self.subTest(data=data[:50]), self.assertRaises(ContractError):
                parse_json(data)
        self.assertEqual(parse_json(b'[0.1,1.0,1e-6,9007199254740991]'), [0.1, 1, 1e-6, 9007199254740991])

    def test_bounds_and_in_memory_coercion(self):
        for value in [(1, 2), {1: "bad"}, {"a": float("nan")}, -0.0, b'bad', "\udead", {"\udead": 1}]:
            with self.subTest(value=repr(value)), self.assertRaises(ContractError):
                canonical(value)
        for data in [b' ' * 65537, b'[' * 34 + b'0' + b']' * 34,
                     b'[' + b'0,' * 16384 + b'0]']:
            with self.assertRaises(ContractError):
                parse_json(data)

    def test_schema_and_timing_refuse_unknown_authority_and_fields(self):
        base = json.loads(request("ns:fixture"))
        for replacement in [base | {"confirmed": True}, base | {"principal": "admin"},
                            base | {"protocol": "hms.invoke/1.0"}]:
            with self.assertRaises(ContractError):
                parse_invoke(json.dumps(replacement).encode())
        for field, value in [("latestStartUnixMs", True), ("latestStartUnixMs", 999),
                             ("maxRunMs", 0), ("notBeforeUnixMs", 1000.0)]:
            sample = copy.deepcopy(base)
            sample["intent"]["timing"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ContractError):
                parse_invoke(json.dumps(sample).encode())

    def test_schema_rejects_trailing_line_terminators_on_all_identities(self):
        base = json.loads(request("ns:fixture"))
        paths = [("operationKey",), ("replayNamespace",)] + [
            ("intent", key) for key in ("instanceId", "endpointSession", "controlGeneration", "actionId",
                                        "descriptionDigest", "bindingGeneration", "calibrationRevision")]
        for path in paths:
            for suffix in ("\n", "\r", "\r\n", "\u2028", "\u2029"):
                sample = copy.deepcopy(base)
                obj = sample if len(path) == 1 else sample[path[0]]
                obj[path[-1]] += suffix
                with self.subTest(path=path, suffix=repr(suffix)), self.assertRaises(ContractError):
                    parse_invoke(json.dumps(sample).encode())

    def test_jcs_unicode_order_no_normalization(self):
        value = {"€": "Euro", "\r": "CR", "דּ": "Hebrew", "1": "One",
                 "😀": "Emoji", "\u0080": "Control", "ö": "Latin"}
        self.assertEqual(list(json.loads(canonical(value)).values()),
                         ["CR", "One", "Control", "Latin", "Euro", "Emoji", "Hebrew"])
        self.assertNotEqual(canonical("é"), canonical("e\u0301"))
        self.assertEqual(canonical({"a": "\x0f\b\t\n\f\r\\\"/"}), b'{"a":"\\u000f\\b\\t\\n\\f\\r\\\\\\\"/"}')

    def test_rfc_appendix_b_library_vectors(self):
        # RFC 8785 Appendix B, all finite entries; the host input profile
        # intentionally rejects negative zero and unsafe integral magnitudes.
        vectors = {
            "0000000000000000": "0", "8000000000000000": "0",
            "0000000000000001": "5e-324", "8000000000000001": "-5e-324",
            "7fefffffffffffff": "1.7976931348623157e+308", "ffefffffffffffff": "-1.7976931348623157e+308",
            "4340000000000000": "9007199254740992", "c340000000000000": "-9007199254740992",
            "4430000000000000": "295147905179352830000", "44b52d02c7e14af5": "9.999999999999997e+22",
            "44b52d02c7e14af6": "1e+23", "44b52d02c7e14af7": "1.0000000000000001e+23",
            "444b1ae4d6e2ef4e": "999999999999999700000", "444b1ae4d6e2ef4f": "999999999999999900000",
            "444b1ae4d6e2ef50": "1e+21", "3eb0c6f7a0b5ed8c": "9.999999999999997e-7",
            "3eb0c6f7a0b5ed8d": "0.000001", "41b3de4355555553": "333333333.3333332",
            "41b3de4355555554": "333333333.33333325", "41b3de4355555555": "333333333.3333333",
            "41b3de4355555556": "333333333.3333334", "41b3de4355555557": "333333333.33333343",
            "becbf647612f3696": "-0.0000033333333333333333", "43143ff3c1cb0959": "1424953923781206.2",
        }
        for bits, text in vectors.items():
            with self.subTest(bits=bits):
                self.assertEqual(rfc8785.dumps(struct.unpack('>d', bytes.fromhex(bits))[0]), text.encode())
        for bits in ("7fffffffffffffff", "7ff0000000000000"):
            with self.assertRaises(rfc8785.CanonicalizationError):
                rfc8785.dumps(struct.unpack('>d', bytes.fromhex(bits))[0])

    def test_retained_digest_fixtures(self):
        fixtures = json.loads((Path(__file__).parent / "fixtures/host-intents.json").read_text())
        for item in fixtures:
            parsed = parse_invoke(item["wire"].encode())
            self.assertEqual(canonical(parsed["intent"]).decode(), item["canonicalIntent"])
            self.assertEqual(intent_digest(parsed["intent"]), item["digest"])
