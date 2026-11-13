"""Versioned local registry and policy on the journal's authority transaction.

Only trusted provisioning/adapter code calls mutation methods. Network callers
receive the service's deliberately smaller API. No external schema is fetched.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import secrets
from functools import lru_cache, wraps
from pathlib import Path
from typing import Callable

from jsonschema import Draft202012Validator, Draft7Validator
from jsonschema.exceptions import SchemaError

from .contracts import ContractError, MAX_BYTES, SAFE_INTEGER, canonical, identifier, parse_json
from .journal import Admission, Context, Evidence, Journal, JournalError
from .projections import data_schema, invoke_td_input

FEATURES = {"durable-operations/1", "binding-generations/1", "physical-evidence/1", "host-invoke/0.1"}
EVIDENCE_KINDS = {"physical_sensor", "controller_measurement", "command_echo", "estimate", "simulation"}


def provisioning_errors(method):
    @wraps(method)
    def checked(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (KeyError, TypeError, SchemaError) as error:
            raise ContractError("invalid provisioning structure") from error
    return checked


_TD_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "research/protocols/wot-artifacts/td-schema-1.1.json"
_TD_SCHEMA_BYTES = _TD_SCHEMA_PATH.read_bytes()
if hashlib.sha256(_TD_SCHEMA_BYTES).hexdigest() != "fd44f319f94c6f16f66978860ef2f9f4e0e9fd7fc5835a2f3840b9cf2002e0f1":
    raise RuntimeError("pinned informative TD schema changed")
_TD_VALIDATOR = Draft7Validator(json.loads(_TD_SCHEMA_BYTES))


def exact(obj, fields):
    if type(obj) is not dict or set(obj) != set(fields):
        raise ContractError("missing or unknown fields")


def bounded_int(value, low=0, high=SAFE_INTEGER):
    if type(value) is not int or not low <= value <= high:
        raise ContractError("integer outside profile range")
    return value


def schema_profile(schema, depth=0):
    """Small explicit executable schema profile; unknown keywords fail closed."""
    allowed = {"type", "properties", "required", "additionalProperties", "items", "minItems", "maxItems",
               "minimum", "maximum", "enum", "const", "minLength", "maxLength"}
    if type(schema) is not dict or set(schema) - allowed or depth > 12:
        raise ContractError("unsupported executable schema")
    kind = schema.get("type")
    if kind not in {"object", "array", "string", "number", "integer", "boolean", "null"}:
        raise ContractError("explicit schema type required")
    specific = {"object": {"properties", "required", "additionalProperties"},
                "array": {"items", "minItems", "maxItems"}, "string": {"minLength", "maxLength"},
                "number": {"minimum", "maximum"}, "integer": {"minimum", "maximum"},
                "boolean": set(), "null": set()}
    if set(schema) - ({"type", "enum", "const"} | specific[kind]):
        raise ContractError("schema keyword does not apply to its type")
    if kind == "object":
        if (schema.get("additionalProperties") is not False or type(schema.get("properties")) is not dict or
                type(schema.get("required")) is not list or
                set(schema["required"]) - set(schema["properties"]) or len(schema["properties"]) > 64):
            raise ContractError("closed object schema required")
        for name, child in schema["properties"].items():
            identifier(name)
            schema_profile(child, depth + 1)
    elif kind == "array":
        bounded_int(schema.get("maxItems"), 0, 256)
        schema_profile(schema.get("items"), depth + 1)
    elif kind == "string":
        bounded_int(schema.get("maxLength"), 0, 4096)
    Draft202012Validator.check_schema(schema)


def _validate(schema, value):
    if next(Draft202012Validator(schema).iter_errors(value), None) is not None:
        raise JournalError("ARGUMENT_SCHEMA_MISMATCH")


@provisioning_errors
def validate_type_bundle(document):
    """Cache only bounded immutable, type-preserving pure profile validation."""
    canonical(document)
    # JCS bytes alone are not a validation cache key: 500 and 500.0 have
    # identical JCS, while duration fields require exact integer input types.
    key = json.dumps(document, ensure_ascii=False, allow_nan=False,
                     sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(key) > MAX_BYTES:
        return _validate_type_bundle_document(document)
    return _cached_type_bundle(key)


@lru_cache(maxsize=32)
def _cached_type_bundle(key):
    # parse_json retains integral floating-point tokens. No caller-owned object
    # or authorization/context result is cached; failures never enter the LRU.
    return _validate_type_bundle_document(parse_json(key))


@provisioning_errors
def _validate_type_bundle_document(document):
    """Validate the complete published profile without changing authority state."""
    exact(document, {"profile", "td", "execution"})
    if document["profile"] != "hms.type-bundle/0.1":
        raise ContractError("unknown type bundle profile")
    td = document["td"]
    if (type(td) is not dict or td.get("@context") != ["https://www.w3.org/2022/wot/td/v1.1",
                                                      {"hms": "https://example.invalid/hms/vocab#"}]):
        raise ContractError("explicit draft WoT context required")
    if next(_TD_VALIDATOR.iter_errors(td), None) is not None:
        raise ContractError("invalid informative WoT TD shape")
    if "forms" in td or "events" in td:
        raise ContractError("bulk forms and event projection unsupported")
    for group, allowed_op in (("properties", "readproperty"), ("actions", "invokeaction")):
        for affordance in td.get(group, {}).values():
            forms = affordance.get("forms")
            if type(forms) is not list or not forms:
                raise ContractError("explicit forms required")
            for form in forms:
                operations = form.get("op")
                operations = [operations] if type(operations) is str else operations
                if type(operations) is not list or not operations or set(operations) != {allowed_op}:
                    raise ContractError("unsupported TD form operation")
    execution = document["execution"]
    exact(execution, {"profile", "requiredFeatures", "capabilities", "properties", "actions"})
    if (execution["profile"] != "hms.execution-contract/0.1" or
            type(execution["requiredFeatures"]) is not list or
            len(execution["requiredFeatures"]) != len(FEATURES) or set(execution["requiredFeatures"]) != FEATURES):
        raise ContractError("unsupported execution features")
    if type(execution["capabilities"]) is not list or not 1 <= len(execution["capabilities"]) <= 16:
        raise ContractError("capability list required")
    for capability in execution["capabilities"]:
        identifier(capability)
    for field in ("properties", "actions"):
        if type(execution[field]) is not dict or not 1 <= len(execution[field]) <= 32:
            raise ContractError("bounded properties/actions required")
    for name, prop in execution["properties"].items():
        identifier(name)
        exact(prop, {"schema", "unit", "frame"})
        schema_profile(prop["schema"])
        identifier(prop["unit"])
        if prop["frame"] is not None:
            identifier(prop["frame"])
    for name, action in execution["actions"].items():
        identifier(name)
        exact(action, {"inputSchema", "resources", "effect", "maxRunMs", "preconditions", "completionEvidence"})
        schema_profile(action["inputSchema"])
        if action["inputSchema"]["type"] != "object":
            raise ContractError("action arguments must be object")
        identifier(action["effect"])
        bounded_int(action["maxRunMs"], 1, 4294967295)
        if type(action["resources"]) is not list or not 1 <= len(action["resources"]) <= 32:
            raise ContractError("resources required")
        for resource in action["resources"]:
            identifier(resource)
        if (type(action["completionEvidence"]) is not list or not 1 <= len(action["completionEvidence"]) <= 32 or
                set(action["completionEvidence"]) - {"controller", "sensor", "simulation"}):
            raise ContractError("unknown completion evidence")
        if type(action["preconditions"]) is not list or len(action["preconditions"]) > 32:
            raise ContractError("invalid preconditions")
        for predicate in action["preconditions"]:
            exact(predicate, {"property", "equals", "maxAgeMs", "evidenceKind"})
            if predicate["property"] not in execution["properties"] or predicate["evidenceKind"] not in EVIDENCE_KINDS:
                raise ContractError("invalid precondition source")
            bounded_int(predicate["maxAgeMs"], 0, 600000)
            _validate(execution["properties"][predicate["property"]]["schema"], predicate["equals"])
    # TD is the public description projection, execution supplies strict
    # schemas and physical semantics. Both artifacts are pinned together.
    if set(td.get("actions", {})) != set(execution["actions"]) or set(td.get("properties", {})) != set(execution["properties"]):
        raise ContractError("TD/execution affordances disagree")
    schema_keywords = {"type", "properties", "required", "items", "minItems", "maxItems", "minimum", "maximum",
                       "enum", "const", "minLength", "maxLength"}
    for name, prop in execution["properties"].items():
        public = td["properties"][name]
        if (canonical({k: v for k, v in public.items() if k in schema_keywords}) != canonical(data_schema(prop["schema"])) or
                public.get("unit") != prop["unit"] or public.get("hms:coordinateFrame") != prop["frame"] or
                public.get("readOnly") is not True):
            raise ContractError("TD property semantics disagree")
    for name, action in execution["actions"].items():
        public = td["actions"][name]
        if (canonical(public.get("input")) != canonical(invoke_td_input(action["inputSchema"])) or
                public.get("safe") is not False or public.get("idempotent") is not False or
                public.get("synchronous") is not False):
            raise ContractError("TD action semantics disagree")
    encoded = canonical(document)
    digest = "sha256:" + hashlib.sha256(b"HMS-TYPE-BUNDLE-v0.1\0" + encoded).hexdigest()
    return digest


_DDL = [
    "CREATE TABLE reg_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE reg_types (digest TEXT PRIMARY KEY, document BLOB NOT NULL)",
    "CREATE TABLE reg_instances (id TEXT PRIMARY KEY, deployment TEXT NOT NULL, type_digest TEXT NOT NULL REFERENCES reg_types(digest), identity_kind TEXT NOT NULL, identity_ref TEXT NOT NULL, retired INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE reg_capabilities (instance TEXT NOT NULL REFERENCES reg_instances(id), capability TEXT NOT NULL, PRIMARY KEY(instance,capability))",
    "CREATE TABLE reg_bindings (instance TEXT PRIMARY KEY REFERENCES reg_instances(id), generation TEXT NOT NULL, document BLOB NOT NULL, active INTEGER NOT NULL)",
    "CREATE TABLE reg_binding_history (instance TEXT NOT NULL, generation TEXT NOT NULL, digest TEXT NOT NULL, document BLOB NOT NULL, PRIMARY KEY(instance,generation))",
    "CREATE TABLE reg_presence (instance TEXT PRIMARY KEY REFERENCES reg_instances(id), session TEXT NOT NULL, expires_ms INTEGER NOT NULL, adapter TEXT NOT NULL)",
    "CREATE TABLE reg_endpoint_sessions (instance TEXT PRIMARY KEY, session TEXT NOT NULL)",
    "CREATE TABLE reg_session_history (instance TEXT NOT NULL, session TEXT NOT NULL, PRIMARY KEY(instance,session))",
    "CREATE TABLE reg_observations (instance TEXT NOT NULL REFERENCES reg_instances(id), property TEXT NOT NULL, document BLOB NOT NULL, PRIMARY KEY(instance,property))",
    "CREATE TABLE reg_streams (instance TEXT NOT NULL, property TEXT NOT NULL, epoch TEXT NOT NULL, PRIMARY KEY(instance,property))",
    "CREATE TABLE reg_stream_history (instance TEXT NOT NULL, property TEXT NOT NULL, epoch TEXT NOT NULL, PRIMARY KEY(instance,property,epoch))",
    "CREATE TABLE reg_grants (principal TEXT NOT NULL, deployment TEXT NOT NULL, target TEXT NOT NULL, verb TEXT NOT NULL, PRIMARY KEY(principal,deployment,target,verb))",
    "CREATE INDEX reg_instance_deployment ON reg_instances(deployment,id)",
    "CREATE INDEX reg_capability_lookup ON reg_capabilities(capability,instance)",
]


class Registry:
    def __init__(self, journal: Journal, *, monotonic_ms: Callable[[], int], bootstrap_owner: Context | None = None):
        self.journal = journal
        self._db = journal._db  # One local authority database/lock, not a second connection.
        self.monotonic_ms = monotonic_ms
        self._last_monotonic = 0
        self._monotonic_invalid = False
        self.receipt_epoch = f"{journal.authority_id}:{journal.owner_epoch}"
        with journal._transaction():
            exists = self._db.execute("SELECT 1 FROM sqlite_master WHERE name='reg_meta' AND type='table'").fetchone()
            if not exists:
                if bootstrap_owner is None:
                    raise JournalError("REGISTRY_NOT_INITIALIZED")
                for statement in _DDL:
                    self._db.execute(statement)
                for key, value in {"version": "hms.registry/0.1", "revision": "1",
                                   "cursor_key": secrets.token_hex(32),
                                   "deployment": bootstrap_owner.deployment}.items():
                    self._db.execute("INSERT INTO reg_meta VALUES (?, ?)", (key, value))
                self._db.execute("INSERT INTO reg_grants VALUES (?, ?, '*', 'admin')",
                                 (bootstrap_owner.principal, bootstrap_owner.deployment))
            elif bootstrap_owner is not None:
                raise JournalError("REGISTRY_ALREADY_INITIALIZED")
            if self._meta("version") != "hms.registry/0.1":
                raise JournalError("UNSUPPORTED_REGISTRY")
        self.deployment = self._meta("deployment")

    def _meta(self, key):
        row = self._db.execute("SELECT value FROM reg_meta WHERE key=?", (key,)).fetchone()
        if row is None:
            raise JournalError("INVALID_REGISTRY")
        return row[0]

    def _bump(self):
        revision = int(self._meta("revision")) + 1
        if revision > SAFE_INTEGER:
            raise JournalError("REGISTRY_REVISION_EXHAUSTED")
        self._db.execute("UPDATE reg_meta SET value=? WHERE key='revision'", (str(revision),))

    def _monotonic(self):
        # Sampling belongs inside the same lock as comparison/publication. Two
        # route workers must not publish an older sample after a newer one and
        # mistake scheduling order for a physical clock regression.
        with self.journal._mutex:
            if self._monotonic_invalid:
                raise JournalError("CLOCK_MAPPING_INVALID")
            try:
                value = bounded_int(self.monotonic_ms())
                if value < self._last_monotonic:
                    raise ValueError("regressed monotonic clock")
            except Exception as error:
                self._monotonic_invalid = True
                raise JournalError("CLOCK_MAPPING_INVALID") from error
            self._last_monotonic = value
            return value

    def allowed(self, context, verb, target):
        if context.deployment != self.deployment:
            return False
        return self._db.execute("SELECT 1 FROM reg_grants WHERE principal=? AND deployment=? AND ((target=? AND verb=?) OR (target='*' AND verb='admin')) LIMIT 1",
                                (context.principal, context.deployment, target, verb)).fetchone() is not None

    def authorize(self, context, verb, target):
        with self.journal._mutex:
            allowed = self.allowed(context, verb, target)
            if verb == "invoke" and not allowed:
                allowed = self._db.execute("SELECT 1 FROM reg_grants WHERE principal=? AND deployment=? AND target=? AND verb LIKE 'invoke:%' LIMIT 1",
                                           (context.principal, context.deployment, target)).fetchone() is not None
            if not allowed:
                raise JournalError("ACCESS_DENIED")

    def grant(self, owner: Context, principal: str, target: str, verb: str, *, enabled=True):
        if type(enabled) is not bool:
            raise ContractError("grant enabled must be a boolean")
        identifier(principal)
        if target != "*":
            identifier(target)
        if verb not in {"admin", "read", "cancel", "stop", "namespace"} and not verb.startswith("invoke:"):
            raise ContractError("unsupported grant")
        if verb.startswith("invoke:"):
            identifier(verb[7:])
        with self.journal._transaction():
            self.authorize(owner, "admin", "*")
            args = (principal, owner.deployment, target, verb)
            if enabled:
                self._db.execute("INSERT OR IGNORE INTO reg_grants VALUES (?, ?, ?, ?)", args)
            else:
                self._db.execute("DELETE FROM reg_grants WHERE principal=? AND deployment=? AND target=? AND verb=?", args)
            self._bump()

    @provisioning_errors
    def publish_type(self, owner: Context, wire: bytes):
        document = parse_json(wire)
        digest = validate_type_bundle(document)
        encoded = canonical(document)
        with self.journal._transaction():
            self.authorize(owner, "admin", "*")
            self._db.execute("INSERT OR IGNORE INTO reg_types VALUES (?, ?)", (digest, encoded))
            self._bump()
        return digest

    def enroll(self, owner: Context, instance_id: str, type_digest: str, *, identity_kind: str, identity_ref: str):
        identifier(instance_id)
        identifier(identity_ref)
        if identity_kind not in {"simulation", "gateway", "device"}:
            raise ContractError("unknown identity kind")
        with self.journal._transaction():
            self.authorize(owner, "admin", "*")
            if self._db.execute("SELECT 1 FROM reg_instances WHERE id=?", (instance_id,)).fetchone():
                raise JournalError("INSTANCE_ALREADY_ENROLLED")
            document = self._type(type_digest)
            self._db.execute("INSERT INTO reg_instances VALUES (?, ?, ?, ?, ?, 0)",
                             (instance_id, owner.deployment, type_digest, identity_kind, identity_ref))
            for capability in set(document["execution"]["capabilities"]):
                self._db.execute("INSERT INTO reg_capabilities VALUES (?, ?)", (instance_id, capability))
            self._bump()

    def _type(self, digest):
        row = self._db.execute("SELECT document FROM reg_types WHERE digest=?", (digest,)).fetchone()
        if row is None:
            raise JournalError("UNKNOWN_DESCRIPTION")
        return json.loads(row[0])

    def _instance(self, instance_id):
        row = self._db.execute("SELECT * FROM reg_instances WHERE id=?", (instance_id,)).fetchone()
        if row is None:
            raise JournalError("UNKNOWN_INSTANCE")
        return dict(row)

    def _binding(self, instance_id):
        row = self._db.execute("SELECT document,active FROM reg_bindings WHERE instance=?", (instance_id,)).fetchone()
        if row is None:
            raise JournalError("BINDING_REQUIRED")
        return json.loads(row[0]), bool(row[1])

    @provisioning_errors
    def bind(self, owner: Context, wire: bytes):
        binding = parse_json(wire)
        exact(binding, {"profile", "instanceId", "generation", "typeDigest", "calibrationRevision", "controlGeneration",
                        "mode", "adapterId", "resourceMap", "argumentSchemas"})
        if binding["profile"] != "hms.binding/0.1" or binding["mode"] not in {"simulation", "uncommissioned"}:
            raise ContractError("unsupported binding mode")
        for field in ("instanceId", "generation", "calibrationRevision", "controlGeneration", "adapterId"):
            identifier(binding[field])
        with self.journal._transaction():
            self.authorize(owner, "admin", "*")
            instance = self._instance(binding["instanceId"])
            if instance["deployment"] != owner.deployment or instance["type_digest"] != binding["typeDigest"]:
                raise JournalError("DESCRIPTION_MISMATCH")
            if binding["mode"] == "simulation" and instance["identity_kind"] != "simulation":
                raise JournalError("SIMULATION_IDENTITY_REQUIRED")
            if self._db.execute("SELECT 1 FROM claims c JOIN operations o ON c.operation_id=o.id WHERE json_extract(CAST(o.intent AS TEXT),'$.instanceId')=? LIMIT 1",
                                (instance["id"],)).fetchone():
                raise JournalError("RESOURCE_CLAIMS_UNRESOLVED")
            execution = self._type(instance["type_digest"])["execution"]
            resources = {r for action in execution["actions"].values() for r in action["resources"]}
            if type(binding["resourceMap"]) is not dict or set(binding["resourceMap"]) != resources:
                raise ContractError("binding must resolve every resource role")
            for resource in binding["resourceMap"].values():
                identifier(resource)
            if type(binding["argumentSchemas"]) is not dict or set(binding["argumentSchemas"]) != set(execution["actions"]):
                raise ContractError("binding must define every action envelope")
            for schema in binding["argumentSchemas"].values():
                schema_profile(schema)
            encoded = canonical(binding)
            digest = hashlib.sha256(encoded).hexdigest()
            if self._db.execute("SELECT 1 FROM reg_binding_history WHERE instance=? AND generation=?",
                                (instance["id"], binding["generation"])).fetchone():
                raise JournalError("BINDING_GENERATION_REUSED")
            self._db.execute("INSERT INTO reg_binding_history VALUES (?, ?, ?, ?)", (instance["id"], binding["generation"], digest, encoded))
            self._db.execute("INSERT OR REPLACE INTO reg_bindings VALUES (?, ?, ?, 1)",
                             (instance["id"], binding["generation"], encoded))
            self._db.execute("DELETE FROM reg_observations WHERE instance=?", (instance["id"],))
            self._db.execute("DELETE FROM reg_streams WHERE instance=?", (instance["id"],))
            self._db.execute("DELETE FROM reg_presence WHERE instance=?", (instance["id"],))
            self._bump()

    def invalidate(self, owner: Context, instance_id: str):
        """Invalidate queued admission; running work requires its adapter policy."""
        with self.journal._transaction():
            self.authorize(owner, "admin", "*")
            self._instance(instance_id)
            self._db.execute("UPDATE reg_bindings SET active=0 WHERE instance=?", (instance_id,))
            self._db.execute("DELETE FROM reg_presence WHERE instance=?", (instance_id,))
            self._bump()

    def report_adapter_snapshot(self, adapter_id, *, presences, streams, observations):
        """Bounded trusted ingress, one durable commit; no transport or policy callback.

        All existing binding, epoch, evidence and sequence checks apply. This
        method is unavailable through the local client API. A rejected member
        rolls back the entire snapshot, including stream history.
        """
        identifier(adapter_id)
        groups = (presences, streams, observations)
        if any(type(group) is not list or len(group) > 48 for group in groups):
            raise ContractError("invalid adapter snapshot size")
        # Only original adapters construct these records. Snapshot them before
        # entering the authority transaction, and refuse mixed-owner batches.
        groups = copy.deepcopy(groups)
        if any(type(item) is not dict or item.get('adapter_id') != adapter_id
               for group in groups for item in group):
            raise JournalError("ADAPTER_SNAPSHOT_ROUTE_MISMATCH")
        with self.journal._transaction():
            # Retain the authority floor before any business mutation. All
            # presence members share this conservative expiry origin.
            now = self.journal._now() if groups[0] else None
            for item in groups[0]:
                self._report_presence(now=now, **item)
            for items, apply in zip(groups[1:], (self._start_stream, self._report_observation)):
                for item in items:
                    apply(**item)

    def report_presence(self, instance_id, *, adapter_id, endpoint_session, ttl_ms):
        with self.journal._transaction():
            return self._report_presence(instance_id, adapter_id=adapter_id, endpoint_session=endpoint_session,
                                         ttl_ms=ttl_ms, now=self.journal._now())

    def _report_presence(self, instance_id, *, adapter_id, endpoint_session, ttl_ms, now):
        identifier(endpoint_session)
        bounded_int(ttl_ms, 1, 60000)
        binding, active = self._binding(instance_id)
        if not active or adapter_id != binding["adapterId"]:
            raise JournalError("ADAPTER_BINDING_MISMATCH")
        current = self._db.execute("SELECT session FROM reg_endpoint_sessions WHERE instance=?", (instance_id,)).fetchone()
        if current is None or current[0] != endpoint_session:
            if self._db.execute("SELECT 1 FROM reg_session_history WHERE instance=? AND session=?",
                                (instance_id, endpoint_session)).fetchone():
                raise JournalError("ENDPOINT_SESSION_REUSED")
            self._db.execute("INSERT INTO reg_session_history VALUES (?, ?)", (instance_id, endpoint_session))
            self._db.execute("INSERT OR REPLACE INTO reg_endpoint_sessions VALUES (?, ?)", (instance_id, endpoint_session))
        old = self._db.execute("SELECT session FROM reg_presence WHERE instance=?", (instance_id,)).fetchone()
        if old is not None and old[0] != endpoint_session:
            self._db.execute("DELETE FROM reg_observations WHERE instance=?", (instance_id,))
            self._db.execute("DELETE FROM reg_streams WHERE instance=?", (instance_id,))
        self._db.execute("INSERT OR REPLACE INTO reg_presence VALUES (?, ?, ?, ?)",
                         (instance_id, endpoint_session, bounded_int(now + ttl_ms), adapter_id))

    def start_stream(self, instance_id, property_id, *, adapter_id, endpoint_session, binding_generation, stream_epoch):
        with self.journal._transaction():
            return self._start_stream(instance_id, property_id, adapter_id=adapter_id, endpoint_session=endpoint_session, binding_generation=binding_generation, stream_epoch=stream_epoch)

    def _start_stream(self, instance_id, property_id, *, adapter_id, endpoint_session, binding_generation, stream_epoch):
        identifier(stream_epoch)
        binding, active = self._binding(instance_id)
        presence = self._db.execute("SELECT session FROM reg_presence WHERE instance=?", (instance_id,)).fetchone()
        prop = self._type(binding["typeDigest"])["execution"]["properties"].get(property_id)
        if (not active or adapter_id != binding["adapterId"] or binding_generation != binding["generation"] or
                presence is None or presence[0] != endpoint_session or prop is None):
            raise JournalError("STREAM_BINDING_MISMATCH")
        if self._db.execute("SELECT 1 FROM reg_stream_history WHERE instance=? AND property=? AND epoch=?",
                            (instance_id, property_id, stream_epoch)).fetchone():
            raise JournalError("STREAM_EPOCH_REUSED")
        self._db.execute("INSERT INTO reg_stream_history VALUES (?, ?, ?)", (instance_id, property_id, stream_epoch))
        self._db.execute("INSERT OR REPLACE INTO reg_streams VALUES (?, ?, ?)", (instance_id, property_id, stream_epoch))
        self._db.execute("DELETE FROM reg_observations WHERE instance=? AND property=?", (instance_id, property_id))

    def report_observation(self, instance_id, property_id, *, adapter_id, endpoint_session, binding_generation, value, evidence_kind,
                           quality, stream_epoch, sequence, acquisition, acquisition_latency_bound_ms,
                           clock_uncertainty_ms, measurement_uncertainty, acquisition_host_earliest_ms=None):
        with self.journal._transaction():
            return self._report_observation(instance_id, property_id, adapter_id=adapter_id, endpoint_session=endpoint_session, binding_generation=binding_generation, value=value, evidence_kind=evidence_kind, quality=quality, stream_epoch=stream_epoch, sequence=sequence, acquisition=acquisition, acquisition_latency_bound_ms=acquisition_latency_bound_ms, clock_uncertainty_ms=clock_uncertainty_ms, measurement_uncertainty=measurement_uncertainty, acquisition_host_earliest_ms=acquisition_host_earliest_ms)

    def _report_observation(self, instance_id, property_id, *, adapter_id, endpoint_session, binding_generation, value, evidence_kind,
                           quality, stream_epoch, sequence, acquisition, acquisition_latency_bound_ms,
                           clock_uncertainty_ms, measurement_uncertainty, acquisition_host_earliest_ms=None):
        """Trusted adapter ingress; receipt clock and binding fields are server-owned."""
        if evidence_kind not in EVIDENCE_KINDS or quality not in {"valid", "stale", "invalid", "unknown"}:
            raise ContractError("unknown observation semantics")
        identifier(stream_epoch)
        bounded_int(sequence)
        for value_or_none in (acquisition_latency_bound_ms, clock_uncertainty_ms):
            if value_or_none is not None:
                bounded_int(value_or_none)
        if acquisition_host_earliest_ms is not None:
            if type(acquisition_host_earliest_ms) is not int or abs(acquisition_host_earliest_ms) > SAFE_INTEGER:
                raise ContractError("invalid acquisition host clock bound")
            if acquisition_latency_bound_ms is not None:
                raise ContractError("conflicting acquisition latency bounds")
        exact(acquisition, {"clockDomain", "clockEpoch", "ticksMs"})
        identifier(acquisition["clockDomain"])
        identifier(acquisition["clockEpoch"])
        bounded_int(acquisition["ticksMs"])
        if measurement_uncertainty is not None:
            exact(measurement_uncertainty, {"absolute", "unit", "method"})
            if (type(measurement_uncertainty["absolute"]) not in {int, float} or
                    measurement_uncertainty["absolute"] < 0):
                raise ContractError("invalid measurement uncertainty")
            identifier(measurement_uncertainty["method"])
        binding, active = self._binding(instance_id)
        instance = self._instance(instance_id)
        if not active or adapter_id != binding["adapterId"]:
            raise JournalError("ADAPTER_BINDING_MISMATCH")
        if (instance["identity_kind"] == "simulation") != (evidence_kind == "simulation"):
            raise JournalError("EVIDENCE_KIND_MISMATCH")
        presence = self._db.execute("SELECT * FROM reg_presence WHERE instance=?", (instance_id,)).fetchone()
        if presence is None:
            raise JournalError("PRESENCE_REQUIRED")
        stream = self._db.execute("SELECT epoch FROM reg_streams WHERE instance=? AND property=?",
                                  (instance_id, property_id)).fetchone()
        if (presence["session"] != endpoint_session or binding["generation"] != binding_generation or
                stream is None or stream[0] != stream_epoch):
            raise JournalError("STREAM_BINDING_MISMATCH")
        prop = self._type(instance["type_digest"])["execution"]["properties"].get(property_id)
        if prop is None:
            raise JournalError("UNKNOWN_PROPERTY")
        _validate(prop["schema"], value)
        if measurement_uncertainty is not None and measurement_uncertainty["unit"] != prop["unit"]:
            raise ContractError("uncertainty unit mismatch")
        prior = self._db.execute("SELECT document FROM reg_observations WHERE instance=? AND property=?",
                                 (instance_id, property_id)).fetchone()
        if prior:
            previous = json.loads(prior[0])
            if previous["streamEpoch"] == stream_epoch and sequence <= previous["sequence"]:
                raise JournalError("OBSERVATION_REPLAY")
        receipt = self._monotonic()
        if acquisition_host_earliest_ms is not None:
            acquisition_latency_bound_ms = max(0, receipt-acquisition_host_earliest_ms)
            bounded_int(acquisition_latency_bound_ms)
        observation = {"protocol": "hms.observation/0.1", "instanceId": instance_id,
                       "propertyId": property_id, "value": value, "unit": prop["unit"], "frame": prop["frame"],
                       "evidenceKind": evidence_kind, "source": adapter_id, "quality": quality,
                       "streamEpoch": stream_epoch, "sequence": sequence,
                       "endpointSession": presence["session"], "controlGeneration": binding["controlGeneration"],
                       "bindingGeneration": binding["generation"], "calibrationRevision": binding["calibrationRevision"],
                       "acquisition": acquisition, "receipt": {"clockDomain": "host-monotonic", "clockEpoch": self.receipt_epoch, "ticksMs": receipt},
                       "acquisitionLatencyBoundMs": acquisition_latency_bound_ms, "clockUncertaintyMs": clock_uncertainty_ms,
                       "measurementUncertainty": measurement_uncertainty}
        self._db.execute("INSERT OR REPLACE INTO reg_observations VALUES (?, ?, ?)",
                         (instance_id, property_id, canonical(observation)))

    def _observation(self, instance_id, property_id, max_age_ms=None, evidence_kind=None):
        row = self._db.execute("SELECT document FROM reg_observations WHERE instance=? AND property=?",
                               (instance_id, property_id)).fetchone()
        if row is None:
            raise JournalError("OBSERVATION_MISSING")
        result = json.loads(row[0])
        binding, active = self._binding(instance_id)
        try:
            now = self._monotonic()
        except JournalError:
            now = None
        receipt = result["receipt"]
        age = None
        if (now is not None and receipt["clockEpoch"] == self.receipt_epoch and now >= receipt["ticksMs"] and
                result["acquisitionLatencyBoundMs"] is not None and result["clockUncertaintyMs"] is not None):
            age = now - receipt["ticksMs"] + result["acquisitionLatencyBoundMs"] + result["clockUncertaintyMs"]
            if age > SAFE_INTEGER:
                age = None
        if not active or binding["generation"] != result["bindingGeneration"] or age is None:
            result["quality"] = "unknown"
        result["ageUpperBoundMs"] = age
        if max_age_ms is not None:
            bounded_int(max_age_ms, 0, 600000)
            if result["quality"] != "valid" or age is None or age > max_age_ms:
                raise JournalError("OBSERVATION_STALE")
        if evidence_kind is not None and evidence_kind != result["evidenceKind"]:
            raise JournalError("EVIDENCE_KIND_MISMATCH")
        return result

    def observe(self, context, instance_id, property_id, *, max_age_ms=None, evidence_kind=None):
        with self.journal._mutex:
            self.authorize(context, "read", instance_id)
            return self._observation(instance_id, property_id, max_age_ms, evidence_kind)

    def describe(self, context, instance_id, *, digest=None):
        with self.journal._mutex:
            self.authorize(context, "read", instance_id)
            instance = self._instance(instance_id)
            if digest is not None and digest != instance["type_digest"]:
                raise JournalError("DESCRIPTION_MISMATCH")
            binding = self._db.execute("SELECT document,active FROM reg_bindings WHERE instance=?", (instance_id,)).fetchone()
            presence = self._db.execute("SELECT session,expires_ms FROM reg_presence WHERE instance=?", (instance_id,)).fetchone()
            return {"instance": instance, "descriptionDigest": instance["type_digest"],
                    "type": self._type(instance["type_digest"]),
                    "binding": json.loads(binding[0]) if binding else None,
                    "bindingActive": bool(binding[1]) if binding else False,
                    "presence": dict(presence) if presence else None,
                    "registryRevision": int(self._meta("revision"))}

    def discover(self, context, *, capability=None, limit=20, cursor=None):
        bounded_int(limit, 1, 100)
        if capability is not None:
            identifier(capability)
        with self.journal._mutex:
            revision = int(self._meta("revision"))
            key = bytes.fromhex(self._meta("cursor_key"))
            after = ""
            if cursor is not None:
                if type(cursor) is not str or len(cursor) > 1024:
                    raise JournalError("INVALID_CURSOR")
                try:
                    raw = base64.b64decode(cursor, altchars=b'-_', validate=True)
                    body, signature = raw[:-32], raw[-32:]
                    if not hmac.compare_digest(signature, hmac.digest(key, body, "sha256")):
                        raise ValueError()
                    page = parse_json(body)
                    exact(page, {"principal", "deployment", "capability", "revision", "after"})
                    if (page["principal"], page["deployment"], page["capability"]) != (context.principal, context.deployment, capability):
                        raise ValueError()
                    if page["revision"] != revision:
                        raise JournalError("REGISTRY_CURSOR_STALE")
                    after = identifier(page["after"])
                except (ValueError, KeyError, TypeError) as error:
                    raise JournalError("INVALID_CURSOR") from error
            if context.deployment != self.deployment:
                raise JournalError("ACCESS_DENIED")
            rows = self._db.execute("""SELECT i.* FROM reg_instances i WHERE i.deployment=? AND i.id>? AND
                EXISTS(SELECT 1 FROM reg_grants g WHERE g.principal=? AND g.deployment=i.deployment AND
                ((g.target=i.id AND g.verb='read') OR (g.target='*' AND g.verb='admin'))) AND
                (? IS NULL OR EXISTS(SELECT 1 FROM reg_capabilities c WHERE c.instance=i.id AND c.capability=?))
                ORDER BY i.id LIMIT ?""", (context.deployment, after, context.principal, capability, capability, limit + 1)).fetchall()
            items = []
            for row in rows[:limit]:
                binding = self._db.execute("SELECT generation,active FROM reg_bindings WHERE instance=?", (row["id"],)).fetchone()
                presence = self._db.execute("SELECT session,expires_ms FROM reg_presence WHERE instance=?", (row["id"],)).fetchone()
                items.append({"instanceId": row["id"], "descriptionDigest": row["type_digest"],
                              "identityKind": row["identity_kind"], "retired": bool(row["retired"]),
                              "bindingGeneration": binding[0] if binding else None,
                              "bindingActive": bool(binding[1]) if binding else False,
                              "presence": dict(presence) if presence else None})
            token = None
            if len(rows) > limit:
                page = {"principal": context.principal, "deployment": context.deployment,
                        "capability": capability, "revision": revision, "after": rows[limit - 1]["id"]}
                body = canonical(page)
                token = base64.urlsafe_b64encode(body + hmac.digest(key, body, "sha256")).decode()
            return {"items": items, "cursor": token, "registryRevision": revision}


class RegistryPolicy:
    """Mandatory admission backed by the same database transaction as the journal."""
    def __init__(self, *, installed_support=None):
        self.registry = None
        # The executing runtime supplies a pure installed-handler check. A
        # standalone registry policy may model contracts without an executor.
        # Admission/recheck run under the journal authority mutex/transaction;
        # this callback may read this authority but must not perform external
        # I/O, mutate authority, or grant permissions.
        self._installed_support = installed_support

    def attach(self, registry):
        if self.registry is not None:
            raise JournalError("POLICY_ALREADY_ATTACHED")
        if registry.journal.policy is not self:
            raise JournalError("POLICY_AUTHORITY_MISMATCH")
        self.registry = registry

    def authorize(self, context, verb, target):
        if self.registry is None:
            raise JournalError("POLICY_UNINITIALIZED")
        self.registry.authorize(context, verb, "*" if verb == "namespace" else target)

    def _check(self, context, intent, now_ms):
        reg = self.registry
        instance = reg._instance(intent["instanceId"])
        binding, active = reg._binding(instance["id"])
        if instance["deployment"] != context.deployment or instance["retired"] or not active:
            raise JournalError("BINDING_INACTIVE")
        if instance["type_digest"] != intent["descriptionDigest"]:
            raise JournalError("DESCRIPTION_MISMATCH")
        for field, binding_field in [("bindingGeneration", "generation"), ("controlGeneration", "controlGeneration"),
                                     ("calibrationRevision", "calibrationRevision")]:
            if intent[field] != binding[binding_field]:
                raise JournalError("BINDING_CHANGED")
        if binding["mode"] != "simulation":
            raise JournalError("UNCOMMISSIONED")
        presence = reg._db.execute("SELECT * FROM reg_presence WHERE instance=?", (instance["id"],)).fetchone()
        if presence is None or now_ms >= presence["expires_ms"]:
            raise JournalError("DEVICE_UNAVAILABLE")
        if presence["session"] != intent["endpointSession"]:
            raise JournalError("ENDPOINT_SESSION_CHANGED")
        action = reg._type(instance["type_digest"])["execution"]["actions"].get(intent["actionId"])
        if action is None:
            raise JournalError("UNKNOWN_ACTION")
        reg.authorize(context, "invoke:" + intent["actionId"], instance["id"])
        reg.authorize(context, "read", instance["id"])
        _validate(action["inputSchema"], intent["arguments"])
        _validate(binding["argumentSchemas"][intent["actionId"]], intent["arguments"])
        if intent["timing"]["maxRunMs"] > action["maxRunMs"]:
            raise JournalError("DURATION_LIMIT")
        if intent["requiredEffect"] == "physical_verified":
            raise JournalError("PHYSICAL_EVIDENCE_UNAVAILABLE")
        for predicate in action["preconditions"]:
            observation = reg._observation(instance["id"], predicate["property"], predicate["maxAgeMs"], predicate["evidenceKind"])
            if canonical(observation["value"]) != canonical(predicate["equals"]):
                raise JournalError("PRECONDITION_FAILED")
        resources = tuple(sorted({binding["resourceMap"][r] for r in action["resources"]}))
        if self._installed_support is not None:
            self._installed_support(intent, binding, resources)
        return binding, action, resources

    def admit(self, context, intent, now_ms):
        binding, action, resources = self._check(context, intent, now_ms)
        expiry = min(intent["timing"]["latestCompletionUnixMs"], now_ms + 60000)
        return Admission(resources, "registry:" + self.registry._meta("revision"), expiry)

    def recheck(self, context, operation, now_ms):
        _, _, resources = self._check(context, operation["intent"], now_ms)
        if list(resources) != operation["admission"]["resources"]:
            raise JournalError("RESOURCE_BINDING_CHANGED")

    def evidence(self, operation, evidence: Evidence):
        # Historical evidence remains useful after current binding invalidation.
        # Only the installed simulated adapter is supported in this profile.
        historical = self.registry._db.execute("SELECT document FROM reg_binding_history WHERE instance=? AND generation=?",
                                               (operation["intent"]["instanceId"], operation["intent"]["bindingGeneration"])).fetchone()
        if historical is None:
            raise JournalError("HISTORICAL_BINDING_MISSING")
        binding = json.loads(historical[0])
        action = self.registry._type(operation["intent"]["descriptionDigest"])["execution"]["actions"][operation["intent"]["actionId"]]
        if (binding["generation"] != operation["intent"]["bindingGeneration"] or
                evidence.source != binding["adapterId"] or evidence.kind != "simulation" or
                evidence.kind not in action["completionEvidence"]):
            raise JournalError("UNTRUSTED_EVIDENCE")
