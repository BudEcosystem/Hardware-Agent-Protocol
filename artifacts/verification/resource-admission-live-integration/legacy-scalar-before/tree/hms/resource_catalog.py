"""Trusted persistent resource proofs for single-owner Journal admission.

This library publishes quiescent configuration, not driver effects. It mounts no
Runtime/provider and grants no physical capability. Resolver callbacks read the
same authority under its mutex; they do not run code supplied by documents.
"""
from __future__ import annotations

from functools import wraps
import hashlib
import sqlite3

from .contracts import ContractError, SAFE_INTEGER, canonical, identifier, parse_json
from .journal import JournalError
from .registry import _parse_binding, bounded_int, exact
from .resource_topology import (binding_proof, generation_change_claims,
                               parse_generations, parse_topology, topology_digest)

PROFILE = "hms.resource-catalog/0.1"
ROUTE_PROFILE = "hms.resource-roots/0.1"
_DDL = (
    "CREATE TABLE reg_resource_requirements (adapter TEXT PRIMARY KEY, profile TEXT NOT NULL)",
    "CREATE TABLE reg_resource_instances (instance TEXT PRIMARY KEY, adapter TEXT NOT NULL, profile TEXT NOT NULL)",
    "CREATE TABLE rc_catalog (singleton INTEGER PRIMARY KEY CHECK(singleton=1), profile TEXT NOT NULL, topology BLOB NOT NULL, topology_digest TEXT NOT NULL, routes BLOB NOT NULL, routes_digest TEXT NOT NULL, current_revision INTEGER NOT NULL)",
    "CREATE TABLE rc_generations (revision INTEGER PRIMARY KEY, document BLOB NOT NULL, digest TEXT NOT NULL)",
    "CREATE TABLE rc_tokens (node TEXT NOT NULL, generation TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY(node,generation))",
    "CREATE TABLE rc_proofs (instance TEXT NOT NULL, generation TEXT NOT NULL, revision INTEGER NOT NULL, document BLOB NOT NULL, digest TEXT NOT NULL, binding_digest TEXT NOT NULL, PRIMARY KEY(instance,generation))",
)


class ResourceCatalogError(JournalError):
    pass


def _require(condition, code):
    if not condition:
        raise ResourceCatalogError(code)


def _errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ContractError, TypeError, KeyError, ValueError, RecursionError) as error:
            raise ResourceCatalogError("RESOURCE_INVALID_CATALOG_INPUT") from error
        except sqlite3.Error as error:
            raise ResourceCatalogError("RESOURCE_CATALOG_STORAGE") from error
    return checked


def _digest(domain, value):
    return "sha256:" + hashlib.sha256(domain + b"\0" + canonical(value)).hexdigest()


def _routes(value, topology):
    value = parse_json(value if type(value) is bytes else canonical(value))
    exact(value, {"profile", "adapters"})
    _require(value["profile"] == "hms.resource-route-inventory/0.1", "RESOURCE_ROUTE_PROFILE")
    adapters = value["adapters"]
    _require(type(adapters) is dict and 1 <= len(adapters) <= 16, "RESOURCE_ROUTE_INVENTORY")
    seen = set()
    for adapter, instances in adapters.items():
        identifier(adapter)
        _require(type(instances) is list and 1 <= len(instances) <= 128, "RESOURCE_ROUTE_INVENTORY")
        for instance in instances:
            identifier(instance)
            _require(instance not in seen, "RESOURCE_ROUTE_DUPLICATE_INSTANCE")
            seen.add(instance)
        instances.sort()
    _require(seen == {row["instanceId"] for row in topology["consumers"]}, "RESOURCE_ROUTE_CLOSURE")
    return value


def control_generation(proof):
    return "resource-control:" + proof["closureDigest"].removeprefix("sha256:")


class ResourceCatalog:
    @_errors
    def __init__(self, journal, registry, *, create=False, owner=None,
                 topology=None, generations=None, routes=None):
        _require(registry.journal is journal, "RESOURCE_AUTHORITY_MISMATCH")
        self.journal, self.registry, self._db = journal, registry, journal._db
        if create:
            topology = parse_topology(topology)
            generations = parse_generations(topology, generations)
            routes = _routes(routes, topology)
            _require(generations["revision"] == 1, "RESOURCE_INITIAL_REVISION")
            _require(topology["deployment"] == registry.deployment, "RESOURCE_DEPLOYMENT_MISMATCH")
            with journal._transaction():
                registry.authorize(owner, "admin", "*")
                _require(registry._storage_profile() == "hms.registry/0.1", "RESOURCE_ACTIVATION_PROFILE")
                _require(self._db.execute("SELECT 1 FROM sqlite_master WHERE name='rc_catalog'").fetchone() is None,
                         "RESOURCE_CATALOG_ALREADY_EXISTS")
                for instances in routes["adapters"].values():
                    for instance in instances:
                        _require(self._db.execute("SELECT 1 FROM claims c JOIN operations o ON c.operation_id=o.id WHERE json_extract(CAST(o.intent AS TEXT),'$.instanceId')=? LIMIT 1",
                                                 (instance,)).fetchone() is None, "RESOURCE_CLAIMS_UNRESOLVED")
                journal._now()  # All catalog/requirement writes follow the checkpoint.
                for statement in _DDL:
                    self._db.execute(statement)
                self._db.execute("UPDATE reg_meta SET value='hms.registry/resource-roots/0.1' WHERE key='version'")
                for adapter in routes["adapters"]:
                    old = self._db.execute("SELECT profile FROM reg_resource_requirements WHERE adapter=?", (adapter,)).fetchone()
                    _require(old is None or old["profile"] == ROUTE_PROFILE, "RESOURCE_REQUIREMENT_CONFLICT")
                    self._db.execute("INSERT OR IGNORE INTO reg_resource_requirements VALUES (?,?)", (adapter, ROUTE_PROFILE))
                    for instance in routes["adapters"][adapter]:
                        old = self._db.execute("SELECT adapter,profile FROM reg_resource_instances WHERE instance=?", (instance,)).fetchone()
                        _require(old is None or (old["adapter"] == adapter and old["profile"] == ROUTE_PROFILE),
                                 "RESOURCE_REQUIREMENT_CONFLICT")
                        self._db.execute("INSERT OR IGNORE INTO reg_resource_instances VALUES (?,?,?)", (instance, adapter, ROUTE_PROFILE))
                self._db.execute("INSERT INTO rc_catalog VALUES (1,?,?,?,?,?,1)",
                    (PROFILE, canonical(topology), topology_digest(topology), canonical(routes),
                     _digest(b"HMS-RESOURCE-ROUTES-v0.1", routes)))
                self._insert_generations(generations)
                self._db.executemany("INSERT INTO rc_tokens VALUES (?,?,1)", generations["nodes"].items())
        with journal._mutex:
            saved = self._load()
            if not create:
                _require(owner is None, "RESOURCE_REOPEN_OWNER_UNEXPECTED")
                for supplied, actual in ((topology, saved["topology"]), (generations, saved["generations"]), (routes, saved["routes"])):
                    if supplied is not None:
                        _require(canonical(supplied) == canonical(actual), "RESOURCE_CONFIGURATION_CHANGED")

    def _insert_generations(self, value):
        self._db.execute("INSERT INTO rc_generations VALUES (?,?,?)",
            (value["revision"], canonical(value), _digest(b"HMS-RESOURCE-GENERATIONS-v0.1", value)))

    def _generation_row(self, topology, revision):
        row = self._db.execute("SELECT * FROM rc_generations WHERE revision=?", (revision,)).fetchone()
        _require(row is not None, "RESOURCE_GENERATION_HISTORY_MISSING")
        value = parse_generations(topology, bytes(row["document"]))
        _require(value["revision"] == revision and canonical(value) == bytes(row["document"]) and
                 _digest(b"HMS-RESOURCE-GENERATIONS-v0.1", value) == row["digest"], "RESOURCE_GENERATION_HISTORY_INVALID")
        for node, generation in value["nodes"].items():
            token = self._db.execute("SELECT revision FROM rc_tokens WHERE node=? AND generation=?", (node, generation)).fetchone()
            _require(token is not None and 1 <= token[0] <= revision, "RESOURCE_GENERATION_HISTORY_INVALID")
        return value

    def _load(self):
        _require(self.registry._storage_profile() == "hms.registry/resource-roots/0.1", "RESOURCE_STORAGE_PROFILE")
        _require(self._db.execute("SELECT 1 FROM sqlite_master WHERE name='rc_catalog' AND type='table'").fetchone() is not None,
                 "RESOURCE_CATALOG_REQUIRED")
        row = self._db.execute("SELECT * FROM rc_catalog WHERE singleton=1").fetchone()
        _require(row is not None and row["profile"] == PROFILE, "RESOURCE_CATALOG_INVALID")
        topology = parse_topology(bytes(row["topology"]))
        _require(topology["deployment"] == self.registry.deployment and canonical(topology) == bytes(row["topology"]) and
                 topology_digest(topology) == row["topology_digest"], "RESOURCE_TOPOLOGY_INVALID")
        routes = _routes(bytes(row["routes"]), topology)
        _require(canonical(routes) == bytes(row["routes"]) and _digest(b"HMS-RESOURCE-ROUTES-v0.1", routes) == row["routes_digest"],
                 "RESOURCE_ROUTE_INVENTORY_INVALID")
        for adapter in routes["adapters"]:
            requirement = self._db.execute("SELECT profile FROM reg_resource_requirements WHERE adapter=?", (adapter,)).fetchone()
            _require(requirement is not None and requirement[0] == ROUTE_PROFILE, "RESOURCE_REQUIREMENT_MISSING")
            for instance in routes["adapters"][adapter]:
                requirement = self._db.execute("SELECT adapter,profile FROM reg_resource_instances WHERE instance=?", (instance,)).fetchone()
                _require(requirement is not None and requirement["adapter"] == adapter and requirement["profile"] == ROUTE_PROFILE,
                         "RESOURCE_REQUIREMENT_MISSING")
        revision = bounded_int(row["current_revision"], 1)
        return {"topology": topology, "routes": routes,
                "generations": self._generation_row(topology, revision), "revision": revision}

    @staticmethod
    def _adapter(saved, instance):
        adapters = [adapter for adapter, instances in saved["routes"]["adapters"].items() if instance in instances]
        _require(len(adapters) == 1, "RESOURCE_INSTANCE_UNREGISTERED")
        return adapters[0]

    def _validate_binding(self, saved, binding, proof):
        instance = binding["instanceId"]
        _require(binding["adapterId"] == self._adapter(saved, instance), "RESOURCE_ROUTE_MISMATCH")
        _require(binding["generation"] == proof["bindingGeneration"] and binding["controlGeneration"] == control_generation(proof),
                 "RESOURCE_BINDING_GENERATION_MISMATCH")
        execution = self.registry._type(binding["typeDigest"])["execution"]
        _require(set(execution["actions"]) == set(proof["actionRoots"]), "RESOURCE_ACTION_CLOSURE")
        roles = {role for action in execution["actions"].values() for role in action["resources"]}
        _require(set(binding["resourceMap"]) == roles, "RESOURCE_ROLE_CLOSURE")
        for action_id, action in execution["actions"].items():
            roots = sorted({binding["resourceMap"][role] for role in action["resources"]})
            _require(roots == proof["actionRoots"][action_id], "RESOURCE_ROOT_MISMATCH")

    def _insert_proof(self, saved, binding, proof):
        self._db.execute("INSERT INTO rc_proofs VALUES (?,?,?,?,?,?)",
            (binding["instanceId"], binding["generation"], saved["revision"], canonical(proof),
             _digest(b"HMS-RESOURCE-BINDING-PROOF-v0.1", proof), hashlib.sha256(canonical(binding)).hexdigest()))

    def _retained_proof(self, saved, instance, generation):
        row = self._db.execute("SELECT * FROM rc_proofs WHERE instance=? AND generation=?", (instance, generation)).fetchone()
        _require(row is not None, "RESOURCE_PROOF_REQUIRED")
        generations = self._generation_row(saved["topology"], row["revision"])
        expected = binding_proof(saved["topology"], generations, instance)
        _require(canonical(expected) == bytes(row["document"]) and
                 _digest(b"HMS-RESOURCE-BINDING-PROOF-v0.1", expected) == row["digest"], "RESOURCE_PROOF_INVALID")
        historical = self._db.execute("SELECT document,digest FROM reg_binding_history WHERE instance=? AND generation=?",
                                      (instance, generation)).fetchone()
        _require(historical is not None, "RESOURCE_BINDING_HISTORY_MISSING")
        binding = _parse_binding(bytes(historical["document"]))
        digest = hashlib.sha256(canonical(binding)).hexdigest()
        _require(digest == row["binding_digest"] == historical["digest"] and
                 canonical(binding) == bytes(historical["document"]), "RESOURCE_BINDING_HISTORY_INVALID")
        self._validate_binding(saved, binding, expected)
        return expected, binding

    @_errors
    def bind(self, owner, binding):
        """Admin-only atomic Registry binding and immutable proof publication."""
        binding = _parse_binding(binding if type(binding) is bytes else canonical(binding))
        with self.journal._transaction():
            self.registry.authorize(owner, "admin", "*")
            saved = self._load()
            proof = binding_proof(saved["topology"], saved["generations"], binding["instanceId"])
            self._validate_binding(saved, binding, proof)
            self.journal._now()
            self.registry._bind_in_tx(owner, binding)
            self._insert_proof(saved, binding, proof)
        return proof

    @_errors
    def resolve(self, context, intent, binding, action, *, live=True):
        """Read-only exact proof resolution; Registry already checks grants/args."""
        _require(type(live) is bool, "RESOURCE_INVALID_RESOLUTION_PHASE")
        with self.journal._mutex:
            _require(context.deployment == self.registry.deployment, "ACCESS_DENIED")
            self.registry.authorize(context, "read", intent["instanceId"])
            self.registry.authorize(context, "invoke:" + intent["actionId"], intent["instanceId"])
            saved = self._load()
            if (intent["instanceId"] not in {item for rows in saved["routes"]["adapters"].values() for item in rows} and
                    binding["adapterId"] not in saved["routes"]["adapters"]):
                # Explicit legacy compatibility; the policy retains its one
                # original flat-resource formula. No managed path returns None.
                return None
            proof, historical = self._retained_proof(saved, intent["instanceId"], intent["bindingGeneration"])
            _require(canonical(binding) == canonical(historical), "RESOURCE_BINDING_CHANGED")
            current = binding_proof(saved["topology"], saved["generations"], intent["instanceId"])
            _require(canonical(current) == canonical(proof), "RESOURCE_DEPENDENCY_CHANGED")
            expected_action = self.registry._type(binding["typeDigest"])["execution"]["actions"][intent["actionId"]]
            _require(canonical(action) == canonical(expected_action), "RESOURCE_ACTION_CHANGED")
            return tuple(proof["expandedClaims"][intent["actionId"]])

    @_errors
    def snapshot(self, owner):
        with self.journal._mutex:
            self.registry.authorize(owner, "admin", "*")
            return self._load()

    @_errors
    def history(self, context, instance, generation):
        identifier(instance); identifier(generation)
        with self.journal._mutex:
            self.registry.authorize(context, "read", instance)
            proof, binding = self._retained_proof(self._load(), instance, generation)
            return {"proof": proof, "binding": binding}

    @_errors
    def publish_generation(self, owner, target, expected_generation, new_generation, *, expected_revision):
        """Publish quiescent configuration atomically, never a driver effect.

        This admin API has no operation key, provider receipt or physical stop
        guarantee. Actual lifecycle execution needs a separate admitted worker.
        """
        identifier(target); identifier(expected_generation); identifier(new_generation)
        bounded_int(expected_revision, 1, SAFE_INTEGER - 1)
        with self.journal._transaction():
            self.registry.authorize(owner, "admin", "*")
            saved = self._load()
            _require(saved["revision"] == expected_revision and saved["generations"]["nodes"].get(target) == expected_generation,
                     "RESOURCE_GENERATION_CONFLICT")
            scope = generation_change_claims(saved["topology"], target)
            _require(self._db.execute("SELECT 1 FROM rc_tokens WHERE node=? AND generation=?", (target, new_generation)).fetchone() is None,
                     "RESOURCE_GENERATION_REUSED")
            placeholders = ",".join("?" for _ in scope["claims"])
            _require(self._db.execute("SELECT 1 FROM claims WHERE deployment=? AND resource IN (" + placeholders + ") LIMIT 1",
                                     (owner.deployment, *scope["claims"])).fetchone() is None, "RESOURCE_CLAIMS_UNRESOLVED")
            affected = sorted({row["instanceId"] for row in scope["affectedConsumers"]})
            value = parse_json(canonical(saved["generations"]))
            value["revision"] += 1
            value["nodes"][target] = new_generation
            next_saved = saved | {"generations": value, "revision": value["revision"]}
            updates = []
            for instance in affected:
                binding, active = self.registry._binding(instance)
                _require(active, "RESOURCE_BINDING_INACTIVE")
                proof, historical = self._retained_proof(saved, instance, binding["generation"])
                _require(canonical(binding) == canonical(historical) and
                         canonical(proof) == canonical(binding_proof(saved["topology"], saved["generations"], instance)),
                         "RESOURCE_DEPENDENCY_CHANGED")
                # Retain Registry's per-instance claim rule as well as alias
                # exclusion; neither accepted nor unknown work is cleared.
                _require(self._db.execute("SELECT 1 FROM claims c JOIN operations o ON c.operation_id=o.id WHERE json_extract(CAST(o.intent AS TEXT),'$.instanceId')=? LIMIT 1",
                                         (instance,)).fetchone() is None, "RESOURCE_CLAIMS_UNRESOLVED")
                new_proof = binding_proof(saved["topology"], value, instance)
                binding = binding | {"generation": new_proof["bindingGeneration"], "controlGeneration": control_generation(new_proof)}
                self._validate_binding(next_saved, binding, new_proof)
                updates.append((binding, new_proof))
            self.journal._now()
            self._insert_generations(value)
            self._db.execute("INSERT INTO rc_tokens VALUES (?,?,?)", (target, new_generation, value["revision"]))
            self._db.execute("UPDATE rc_catalog SET current_revision=? WHERE singleton=1", (value["revision"],))
            for binding, proof in updates:
                self.registry._bind_in_tx(owner, binding)
                self._insert_proof(next_saved, binding, proof)
            return {"revision": value["revision"], "target": target, "generation": new_generation,
                    "affectedInstances": affected, "scope": scope,
                    "publicationKind": "quiescent_configuration", "driverEffectExecuted": False}
