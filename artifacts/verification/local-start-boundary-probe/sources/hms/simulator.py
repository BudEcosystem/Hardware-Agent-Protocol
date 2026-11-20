"""Persistent synthetic plant with separate receipts; never opens physical I/O.

Atomic state+receipt commits are a declared simulator capability. They do not
model the weaker guarantees of arbitrary physical equipment.
"""
import json
import fcntl
import hashlib
import os
from pathlib import Path
import sqlite3
import threading
import uuid

from .contracts import SAFE_INTEGER, ContractError, canonical, identifier, intent_digest, parse_invoke
from .journal import JournalError
from .installations import (definitions_for, legacy_installation,
                            normalize_installations, resource_map)


class SimulatedPlant:
    # These entries describe actually installed synthetic handlers, not device
    # descriptions discovered in the registry. A new binding cannot install code.
    _PRIMITIVES = {"fan": "set_level", "focus": "move_absolute", "inspection": "inspect"}

    def __init__(self, path, *, create=False, installation=None):
        from .registry import validate_type_bundle
        self.installation = normalize_installations([
            legacy_installation() if installation is None else installation])[0]
        if self.installation["driver"] != "sqlite-simulation":
            raise JournalError("ADAPTER_INSTALLATION_UNSUPPORTED")
        self.adapter_id = self.installation["adapterId"]
        self._descriptor = canonical(self.installation).decode("utf-8")
        self._descriptor_digest = "sha256:" + hashlib.sha256(self._descriptor.encode("utf-8")).hexdigest()
        self._roles = {instance: role for role, instance in self.installation["instances"].items()}
        self._type_digests = {instance: validate_type_bundle(document)
                              for instance, _, document in definitions_for(self.installation)}
        self.path = Path(path)
        self.lock = threading.RLock()
        self.db = None
        self._closed = False
        self._owner_fd = os.open(str(self.path) + ".owner", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(self._owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise JournalError("OWNER_BUSY") from error
            self._initialize(create)
        except sqlite3.Error as error:
            self.close()
            raise JournalError("INVALID_SIMULATED_PLANT") from error
        except BaseException:
            self.close()
            raise

    def _initialize(self, create):
        if create:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        elif not self.path.is_file():
            raise JournalError("MISSING_SIMULATED_PLANT")
        self.db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False, timeout=0.2)
        self.db.row_factory = sqlite3.Row
        if create:
            self.db.execute("PRAGMA journal_mode=DELETE")
            self.db.execute("PRAGMA synchronous=EXTRA")
            self.db.executescript("""BEGIN IMMEDIATE;
                CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE devices(id TEXT PRIMARY KEY,value BLOB NOT NULL,effects INTEGER NOT NULL);
                CREATE TABLE receipts(id TEXT PRIMARY KEY,digest TEXT NOT NULL,state TEXT NOT NULL,intent BLOB NOT NULL,claims BLOB NOT NULL,result BLOB NOT NULL);
                CREATE TABLE fences(resource TEXT PRIMARY KEY,epoch INTEGER NOT NULL);""")
            try:
                self.db.executemany("INSERT INTO meta VALUES (?,?)", (
                    ("session", "sim-session:" + uuid.uuid4().hex),
                    ("installation", self._descriptor),
                    ("installation_digest", self._descriptor_digest)))
                for instance in self.installation["instances"].values():
                    self.db.execute("INSERT INTO devices VALUES (?, ?, 0)", (instance, canonical(0)))
                self.db.execute("COMMIT")
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                raise
        row = self.db.execute("SELECT value FROM meta WHERE key='session'").fetchone()
        if row is None:
            raise JournalError("INVALID_SIMULATED_PLANT")
        self.session = row[0]
        metadata = dict(self.db.execute("SELECT key,value FROM meta WHERE key IN ('installation','installation_digest')"))
        adopt_legacy = not metadata and self.installation == legacy_installation()
        if not adopt_legacy and metadata != {"installation": self._descriptor,
                                              "installation_digest": self._descriptor_digest}:
            raise JournalError("SIMULATOR_INSTALLATION_MISMATCH")
        inventory = {row[0] for row in self.db.execute("SELECT id FROM devices")}
        if inventory != set(self._roles):
            raise JournalError("SIMULATOR_DEVICE_INVENTORY_MISMATCH")
        # Reject a changed route or inventory before adopting an old store or
        # canceling any of its pending receipts.
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=EXTRA")
        # Effects are instantaneous at commit in this model. Pending jobs have
        # no effects; process-owner loss cancels them, never resumes implicitly.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if adopt_legacy:
                self.db.executemany("INSERT INTO meta VALUES (?,?)", (
                    ("installation", self._descriptor), ("installation_digest", self._descriptor_digest)))
            self.db.execute("UPDATE receipts SET state='canceled', result=? WHERE state='pending'",
                            (canonical({"reason": "simulator_owner_reopened", "effectCommitted": False}),))
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def close(self):
        with self.lock:
            if not self._closed:
                if self.db is not None:
                    self.db.close()
                os.close(self._owner_fd)
                self._closed = True

    def supports_binding(self, binding):
        instance = binding["instanceId"]
        role = self._roles.get(instance)
        return (role is not None and binding["adapterId"] == self.adapter_id and
                binding["mode"] == "simulation" and
                binding["typeDigest"] == self._type_digests.get(instance) and
                binding["resourceMap"] == resource_map(self.installation, instance))

    def validate_admission(self, intent, binding, resources):
        if not self.supports_binding(binding):
            raise JournalError("ADAPTER_INSTALLATION_UNSUPPORTED")
        resource = self._primitive(intent)
        if tuple(resources) != (resource,):
            raise JournalError("ADAPTER_INSTALLATION_UNSUPPORTED")

    def _primitive(self, intent):
        """Validate actual handler limits independently of installed schemas."""
        args = intent["arguments"]
        role = self._roles.get(intent["instanceId"])
        if role == "fan" and intent["actionId"] == "set_level":
            valid = (set(args) == {"level", "unit"} and args["unit"] == "percent" and
                     type(args["level"]) in {int, float} and 0 <= args["level"] <= 100)
        elif role == "focus" and intent["actionId"] == "move_absolute":
            valid = (set(args) == {"position", "unit", "frame"} and args["unit"] == "um" and
                     args["frame"] == intent["instanceId"] and type(args["position"]) in {int, float} and
                     0 <= args["position"] <= 100)
        elif role == "inspection" and intent["actionId"] == "inspect":
            valid = (set(args) == {"recipe", "partId"} and type(args["recipe"]) is int and
                     args["recipe"] in {1, 2} and type(args["partId"]) is str and 1 <= len(args["partId"]) <= 64)
        else:
            raise JournalError("SIMULATOR_ADMISSION_REFUSED")
        if not valid or intent["requiredEffect"] != "capability_completion" or intent["timing"]["maxRunMs"] > 5000:
            raise JournalError("SIMULATOR_ADMISSION_REFUSED")
        return self.installation["resources"][role]

    def _validate_operation(self, operation):
        try:
            identifier(operation["id"])
            intent = operation["intent"]
            parse_invoke(canonical({"protocol": "hms.invoke/0.1", "replayNamespace": "sim:validation",
                                    "operationKey": "sim:validation", "intent": intent}))
            if operation["digest"] != intent_digest(intent):
                raise ContractError("digest mismatch")
            resource = self._primitive(intent)
            claims = operation["claims"]
            if (type(claims) is not list or len(claims) != 1 or type(claims[0]) is not dict or
                    set(claims[0]) != {"resource", "fence"} or claims[0]["resource"] != resource or
                    type(claims[0]["fence"]) is not int or not 1 <= claims[0]["fence"] <= SAFE_INTEGER):
                raise ContractError("primitive/claim limits")
        except (KeyError, TypeError, ContractError) as error:
            raise JournalError("SIMULATOR_ADMISSION_REFUSED") from error

    def observe(self, instance):
        with self.lock:
            row = self.db.execute("SELECT value,effects FROM devices WHERE id=?", (instance,)).fetchone()
            if row is None:
                raise JournalError("SIMULATOR_INSTANCE_UNSUPPORTED")
            return {"value": json.loads(row[0]), "ready": True, "effectCount": row[1]}

    def receipt(self, operation_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM receipts WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                return None
            return dict(row) | {"intent": json.loads(row["intent"]), "claims": json.loads(row["claims"]),
                                "result": json.loads(row["result"])}

    def begin(self, operation):
        with self.lock:
            self._validate_operation(operation)
            self.db.execute("BEGIN IMMEDIATE")
            try:
                existing = self.receipt(operation["id"])
                if existing:
                    if (existing["digest"] != operation["digest"] or
                            canonical(existing["intent"]) != canonical(operation["intent"])):
                        raise JournalError("SIMULATOR_KEY_CONFLICT")
                    self.db.execute("COMMIT")
                    return existing
                intent = operation["intent"]
                if intent["endpointSession"] != self.session:
                    raise JournalError("SIMULATOR_SESSION_CHANGED")
                self.observe(intent["instanceId"])
                for claim in operation["claims"]:
                    floor = self.db.execute("SELECT epoch FROM fences WHERE resource=?", (claim["resource"],)).fetchone()
                    if floor is not None and claim["fence"] < floor[0]:
                        raise JournalError("SIMULATOR_STALE_FENCE")
                    self.db.execute("INSERT INTO fences VALUES (?,?) ON CONFLICT(resource) DO UPDATE SET epoch=MAX(epoch,excluded.epoch)",
                                    (claim["resource"], claim["fence"]))
                self.db.execute("INSERT INTO receipts VALUES (?, ?, 'pending', ?, ?, ?)",
                                (operation["id"], operation["digest"], canonical(intent), canonical(operation["claims"]), canonical({})))
                self.db.execute("COMMIT")
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                raise
            return self.receipt(operation["id"])

    def finish(self, operation_id, *, cancel_reason=None, _effect_guard=None):
        """Complete a pending synthetic effect, with an optional trusted veto.

        The installed runtime supplies its private guard while retaining the
        authority mutex. The guard runs after plant lock/BEGIN/read delays and
        immediately before the state mutation. It must not perform driver I/O
        or start an authority transaction. Exceptions roll back this receipt
        and leave it pending; they never authorize an effect.
        """
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                receipt = self.receipt(operation_id)
                if receipt is None:
                    raise JournalError("SIMULATOR_RECEIPT_MISSING")
                if receipt["state"] != "pending":
                    self.db.execute("COMMIT")
                    return receipt
                intent = receipt["intent"]
                if intent["endpointSession"] != self.session:
                    cancel_reason = "endpoint_session_changed"
                stale = any(self.db.execute("SELECT epoch FROM fences WHERE resource=?", (claim["resource"],)).fetchone()[0] != claim["fence"]
                            for claim in receipt["claims"])
                if stale:
                    cancel_reason = "superseded_fence"
                if cancel_reason is not None:
                    state = "canceled"
                    result = {"reason": cancel_reason, "effectCommitted": False}
                else:
                    args = intent["arguments"]
                    instance = intent["instanceId"]
                    role = self._roles.get(instance)
                    if role == "fan" and intent["actionId"] == "set_level":
                        value = args["level"]
                        result = {"level": value, "unit": "percent"}
                    elif role == "focus" and intent["actionId"] == "move_absolute":
                        value = args["position"]
                        result = {"position": value, "unit": "um", "frame": instance}
                    elif role == "inspection" and intent["actionId"] == "inspect":
                        value = self.observe(instance)["value"] + 1
                        result = {"partId": args["partId"], "recipe": args["recipe"], "inspection": "simulated-pass", "count": value}
                    else:
                        raise JournalError("SIMULATOR_ACTION_UNSUPPORTED")
                    reason = _effect_guard() if _effect_guard is not None else None
                    if reason is not None:
                        identifier(reason)
                        state = "canceled"
                        result = {"reason": reason, "effectCommitted": False}
                    else:
                        self.db.execute("UPDATE devices SET value=?,effects=effects+1 WHERE id=?", (canonical(value), instance))
                        state = "completed"
                        result["effectCommitted"] = True
                self.db.execute("UPDATE receipts SET state=?,result=? WHERE id=?", (state, canonical(result), operation_id))
                self.db.execute("COMMIT")
                return self.receipt(operation_id)
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                raise
