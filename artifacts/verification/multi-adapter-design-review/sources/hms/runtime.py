"""Local HMS runtime with an explicitly synthetic adapter and durable authority."""
from __future__ import annotations

import copy
import threading
import time
import uuid

from .api_contracts import METHOD_RESULTS, validate_params, validate_result
from .contracts import ContractError, canonical, identifier, intent_digest, parse_invoke
from .demo import install
from .journal import Context, Evidence, Journal, JournalError, TERMINAL
from .registry import Registry, RegistryPolicy, bounded_int, exact
from .simulator import SimulatedPlant
from .state_path import private_state_directory


class Runtime:
    def __init__(self, state_dir, *, create=False, owner=None, wall_clock_ms=None, monotonic_ms=None, endpoint_fd=None):
        self.wall_clock_ms = wall_clock_ms or (lambda: time.time_ns() // 1_000_000)
        self.monotonic_ms = monotonic_ms or (lambda: time.monotonic_ns() // 1_000_000)
        self.policy = RegistryPolicy(installed_support=self._check_installed_support)
        self._stop = threading.Event()
        self._thread = None
        self._tick_lock = threading.Lock()
        self._pending = {}
        self._streams = {}
        self._last_sample = None
        self.last_worker_error = None
        self.journal = None
        self.plant = None
        self.compact = None
        deployment = "simulation:compact" if endpoint_fd is not None else "simulation:local"
        if create and (owner is None or owner.deployment != deployment):
            raise JournalError("EXPLICIT_SIMULATION_OWNER_REQUIRED")
        self.directory = private_state_directory(state_dir, create=create)
        try:
            self.journal = Journal(self.directory / "authority.db", self.policy, clock_ms=self.wall_clock_ms, create=create)
            self.registry = Registry(self.journal, monotonic_ms=self.monotonic_ms, bootstrap_owner=owner if create else None)
            self.policy.attach(self.registry)
            self.deployment = self.registry.deployment
            if endpoint_fd is not None:
                from .endpoint_binding import CompactSimulation
                self.compact = CompactSimulation(self, endpoint_fd, create=create, owner=owner)
            elif self.journal._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ep_state'").fetchone():
                raise JournalError("ENDPOINT_STREAM_REQUIRED")
            elif create:
                install(self.registry, owner)
            if self.compact is None:
                self.plant = SimulatedPlant(self.directory / "simulated-plant.db", create=create)
                self._refresh(force=True)
        except BaseException:
            self.close()
            raise

    def start(self):
        if self._thread is not None:
            raise JournalError("RUNTIME_ALREADY_STARTED")
        self._thread = threading.Thread(target=self._run, name="hms-simulation-worker", daemon=False)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        if self.plant is not None:
            self.plant.close()
            self.plant = None
        if self.compact is not None:
            self.compact.close()
            self.compact = None
        if self.journal is not None:
            self.journal.close()
            self.journal = None

    def _run(self):
        while not self._stop.is_set():
            try:
                self.tick()
                self.last_worker_error = None
            except (JournalError, ContractError) as error:
                self.last_worker_error = getattr(error, "code", "CONTRACT_ERROR")
            except Exception:
                self.last_worker_error = "WORKER_FAILURE"
            self._stop.wait(0.02)

    def _check_installed_support(self, intent, binding, resources):
        """Check the selected installed executor without performing a handoff.

        This is inside RegistryPolicy admission and dispatch recheck, never
        ahead of the journal's retained-operation replay lookup. Historical
        receipt reconciliation does not depend on present installation support.
        Multiple coexisting adapters still require route-scoped scheduling and
        recovery; this runtime continues to select one installed backend.
        """
        backend = self.compact if self.compact is not None else self.plant
        if backend is None:
            raise JournalError("ADAPTER_INSTALLATION_UNSUPPORTED")
        backend.validate_admission(intent, binding, resources)

    def _refresh(self, *, force=False):
        if self.compact is not None:
            return self.compact.refresh(force=force)
        mono = self.registry._monotonic()
        if not force and self._last_sample is not None and mono - self._last_sample < 200:
            return
        with self.journal._mutex:
            rows = self.journal._db.execute("SELECT id FROM reg_instances WHERE identity_kind='simulation' AND retired=0 ORDER BY id").fetchall()
            for row in rows:
                instance_id = row[0]
                binding, active = self.registry._binding(instance_id)
                if not active or not self.plant.supports_binding(binding):
                    continue
                sample = self.plant.observe(instance_id)
                self.registry.report_presence(instance_id, adapter_id="simulator:local", endpoint_session=self.plant.session, ttl_ms=3000)
                for property_id in ("value", "ready"):
                    key = (instance_id, property_id, binding["generation"], self.plant.session)
                    if key not in self._streams:
                        epoch = "sim-stream:" + uuid.uuid4().hex
                        self.registry.start_stream(instance_id, property_id, adapter_id="simulator:local",
                                                   endpoint_session=self.plant.session, binding_generation=binding["generation"], stream_epoch=epoch)
                        self._streams[key] = [epoch, 0]
                    stream = self._streams[key]
                    stream[1] += 1
                    self.registry.report_observation(instance_id, property_id, adapter_id="simulator:local",
                        endpoint_session=self.plant.session, binding_generation=binding["generation"], value=sample[property_id],
                        evidence_kind="simulation", quality="valid", stream_epoch=stream[0], sequence=stream[1],
                        acquisition={"clockDomain": "simulator-monotonic", "clockEpoch": self.registry.receipt_epoch, "ticksMs": mono},
                        acquisition_latency_bound_ms=0, clock_uncertainty_ms=0,
                        measurement_uncertainty={"absolute": 0, "unit": "1" if property_id == "ready" else self.registry._type(binding["typeDigest"])["execution"]["properties"][property_id]["unit"],
                                                 "method": "synthetic_exact_state"})
        self._last_sample = mono

    def _evidence(self, operation_id, *assertions):
        return Evidence("simulation", "simulator:local", "sim-receipt:" + operation_id, assertions)

    def _settle(self, operation, receipt, ticket=None):
        if receipt is None or receipt["state"] == "pending":
            return
        if receipt["state"] == "completed":
            state, assertion = "completed", "completed"
        elif receipt["state"] == "canceled":
            reason = receipt["result"].get("reason")
            if reason in {"client_cancel", "simulator_owner_reopened"}:
                state, assertion = "canceled", "terminated"
            else:
                state, assertion = "failed", "failed"
        else:
            raise JournalError("INVALID_SIMULATOR_RECEIPT")
        if receipt["digest"] != operation["digest"] or canonical(receipt["intent"]) != canonical(operation["intent"]):
            raise JournalError("SIMULATOR_RECEIPT_CONFLICT")
        if operation["state"] == "outcome_unknown":
            self.journal.reconcile(operation["id"], state, self._evidence(operation["id"], assertion))
        elif operation["state"] not in TERMINAL:
            if ticket is None:
                raise JournalError("MISSING_DISPATCH_TICKET")
            self.journal.record_execution(ticket, state, self._evidence(operation["id"], assertion))
        current = self.journal._operation(operation["id"])
        if current["claims"]:
            self.journal.release_resources(operation["id"], self._evidence(operation["id"], "resources_quiescent"))

    def tick(self):
        """Bounded synthetic scheduler step; tests may drive it with virtual clocks."""
        with self._tick_lock:
            if self.compact is not None:
                return self.compact.tick()
            refresh_error = None
            try:
                self._refresh()
            except (JournalError, ContractError) as error:
                # Lost clock/sampling authority must not prevent cancellation
                # or reconciliation of already recorded simulator receipts.
                refresh_error = error
            for operation in self.journal.work_items(("outcome_unknown",)):
                with self.journal._mutex:
                    self._settle(operation, self.plant.receipt(operation["id"]))
            for operation in self.journal.work_items(("accepted",)):
                with self.journal._mutex:
                    try:
                        started = self.registry._monotonic()
                        ticket = self.journal.claim_dispatch(operation["id"])
                    except JournalError as error:
                        if error.code in {"NOT_YET_STARTABLE", "NOT_DISPATCHABLE"}:
                            continue
                        self.journal.reject_before_dispatch(operation["id"], error.code)
                        continue
                    if ticket is None:
                        continue
                    operation = self.journal._operation(operation["id"])
                    try:
                        receipt = self.plant.begin(operation)
                    except Exception:
                        self.journal.mark_unknown(ticket, "adapter_acceptance_unknown")
                        continue
                    if receipt["state"] != "pending":
                        self._settle(operation, receipt, ticket)
                        continue
                    self._pending[operation["id"]] = {"ticket": ticket, "started": started, "due": started + 50}
                    self.journal.record_execution(ticket, "running", self._evidence(operation["id"], "running"))
            for operation_id, pending in list(self._pending.items())[:64]:
                with self.journal._mutex:
                    operation = self.journal._operation(operation_id)
                    reason = None
                    mono = now = None
                    timing = operation["intent"]["timing"]
                    if operation["cancel_state"] == "requested":
                        self.journal.acknowledge_cancel(pending["ticket"], True, self._evidence(operation_id, "cancel_ack"))
                        reason = "client_cancel"
                    else:
                        try:
                            mono = self.registry._monotonic()
                            now = self.journal.authority_time()
                        except JournalError:
                            reason = "clock_authority_lost"
                    if reason is None and refresh_error is not None:
                        reason = "observation_authority_lost"
                    if reason is None and (mono - pending["started"] >= timing["maxRunMs"] or now >= timing["latestCompletionUnixMs"]):
                        reason = "execution_deadline"
                    elif reason is None and now >= operation["admission"]["lease_expires_ms"]:
                        reason = "lease_expired"
                    elif reason is None:
                        try:
                            # Same authority mutex through simulated effect commit.
                            self.policy.authorize(Context(operation["principal"], operation["deployment"]), "invoke", operation["intent"]["instanceId"])
                            self.policy.recheck(Context(operation["principal"], operation["deployment"]), operation, now)
                        except JournalError:
                            reason = "authority_or_precondition_lost"
                    if reason is None and mono < pending["due"]:
                        continue
                    receipt = self.plant.finish(operation_id, cancel_reason=reason)
                    self._settle(operation, receipt, pending["ticket"])
                    del self._pending[operation_id]
                    if refresh_error is None:
                        try:
                            self._refresh(force=True)
                        except (JournalError, ContractError) as error:
                            refresh_error = error
            # A crash may occur after completion evidence but before claim release.
            with self.journal._mutex:
                rows = self.journal._db.execute("SELECT DISTINCT o.id FROM operations o JOIN claims c ON c.operation_id=o.id WHERE o.state IN ('completed','failed','canceled') LIMIT 64").fetchall()
                for row in rows:
                    op = self.journal._operation(row[0])
                    self._settle(op, self.plant.receipt(op["id"]))
            if refresh_error is not None:
                raise refresh_error

    def operation(self, context, operation_id):
        with self.journal._mutex:
            op = self.journal.status(context, operation_id)
            receipt = self.plant.receipt(operation_id) if self.plant is not None else None
            intent = op["intent"]
            return {"protocol": "hms.operation/0.1", "operationId": op["id"], "requestDigest": op["digest"],
                    "instanceId": intent["instanceId"], "actionId": intent["actionId"],
                    "executionState": op["state"], "cancellationState": op["cancel_state"],
                    "effectVerification": op["verification"], "mayHaveActed": op["may_have_acted"],
                    "eventSequence": op["sequence"], "resourceClaims": copy.deepcopy(op["claims"]),
                    "result": (self.compact.result(operation_id) if self.compact is not None else
                        {"evidenceKind": "simulation", "output": receipt["result"]} if receipt and receipt["state"] != "pending" else None)}

    def request(self, context: Context, method: str, params: dict):
        if method not in METHOD_RESULTS:
            raise JournalError("UNKNOWN_METHOD")
        # Establish one immutable caller snapshot before policy, dispatch and
        # result correlation. In-process callers can otherwise mutate aliases.
        canonical(params)
        params = copy.deepcopy(params)
        validate_params(method, params)
        return validate_result(method, self._request(context, method, params), params)

    def _request(self, context: Context, method: str, params: dict):
        if type(params) is not dict:
            raise ContractError("params must be an object")
        if context.deployment != self.deployment:
            raise JournalError("ACCESS_DENIED")
        # Exact parameter allowlists prevent model claims from becoming authority.
        if method == "discover":
            if set(params) - {"capability", "limit", "cursor"}:
                raise ContractError("unknown discovery parameter")
            return self.registry.discover(context, capability=params.get("capability"), limit=params.get("limit", 20), cursor=params.get("cursor"))
        if method == "describe":
            if set(params) - {"instanceId", "digest"} or "instanceId" not in params:
                raise ContractError("invalid description parameters")
            return self.registry.describe(context, identifier(params["instanceId"]), digest=params.get("digest"))
        if method == "observe":
            if set(params) - {"instanceId", "property", "maxAgeMs", "evidenceKind"} or not {"instanceId", "property"} <= set(params):
                raise ContractError("invalid observation parameters")
            return self.registry.observe(context, identifier(params["instanceId"]), identifier(params["property"]),
                                         max_age_ms=params.get("maxAgeMs"), evidence_kind=params.get("evidenceKind"))
        if method == "namespace":
            exact(params, {"expiresUnixMs"})
            return self.journal.issue_namespace(context, params["expiresUnixMs"])
        if method == "invoke":
            exact(params, {"request"})
            op = self.journal.submit(context, canonical(params["request"]))
            return self.operation(context, op["id"])
        if method in {"operation", "cancel"}:
            exact(params, {"operationId"})
            operation_id = identifier(params["operationId"])
            if method == "cancel":
                self.journal.request_cancel(context, operation_id)
            return self.operation(context, operation_id)
        if method == "events":
            if set(params) - {"operationId", "after", "limit"} or "operationId" not in params:
                raise ContractError("invalid event parameters")
            return self.journal.events(context, identifier(params["operationId"]), after=params.get("after", 0), limit=params.get("limit", 100))
        if method == "prepare":
            exact(params, {"instanceId", "actionId", "arguments", "operationKey", "replayNamespace", "timing", "requiredEffect"})
            with self.journal._mutex:
                description = self.registry.describe(context, identifier(params["instanceId"]))
                binding = description["binding"]
                presence = description["presence"]
                if not binding or not presence:
                    raise JournalError("DEVICE_UNAVAILABLE")
                intent = {"instanceId": params["instanceId"], "actionId": params["actionId"],
                          "endpointSession": presence["session"], "controlGeneration": binding["controlGeneration"],
                          "descriptionDigest": description["descriptionDigest"], "bindingGeneration": binding["generation"],
                          "calibrationRevision": binding["calibrationRevision"], "arguments": params["arguments"],
                          "timing": params["timing"], "requiredEffect": params["requiredEffect"]}
                request = {"protocol": "hms.invoke/0.1", "replayNamespace": params["replayNamespace"],
                           "operationKey": params["operationKey"], "intent": intent}
                parse_invoke(canonical(request))
                self.policy.admit(context, intent, self.journal.authority_time())
            return {"request": request,
                    "requestDigest": intent_digest(intent), "admitted": False}
        raise JournalError("UNKNOWN_METHOD")
