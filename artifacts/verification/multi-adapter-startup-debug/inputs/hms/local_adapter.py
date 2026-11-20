"""One installed SQLite simulation route under the runtime's Journal authority."""
import json
import threading
import uuid

from .contracts import ContractError, canonical
from .installations import ROLES, normalize_installations
from .journal import Context, Evidence, JournalError, TERMINAL


class LocalSimulation:
    def __init__(self, runtime, installation, plant):
        self.installation = normalize_installations([installation])[0]
        if (self.installation["driver"] != "sqlite-simulation" or
                self.installation != plant.installation):
            raise JournalError("ADAPTER_INSTALLATION_UNSUPPORTED")
        self.adapter_id = self.installation["adapterId"]
        self.runtime = runtime
        self.journal = runtime.journal
        self.registry = runtime.registry
        self.policy = runtime.policy
        self.plant = plant
        self._pending = {}
        self._streams = {}
        self._last_sample = None
        self._tick_lock = threading.Lock()

    def close(self):
        self.plant.close()

    def validate_admission(self, intent, binding, resources):
        self.plant.validate_admission(intent, binding, resources)

    def refresh(self, *, force=False):
        with self.journal._mutex:
            mono = self.registry._monotonic()
            if not force and self._last_sample is not None and mono - self._last_sample < 200:
                return
            for role in ROLES:
                instance_id = self.installation["instances"][role]
                instance = self.registry._instance(instance_id)
                if instance["retired"] or instance["identity_kind"] != "simulation":
                    continue
                binding, active = self.registry._binding(instance_id)
                if not active or not self.plant.supports_binding(binding):
                    continue
                sample = self.plant.observe(instance_id)
                self.registry.report_presence(instance_id, adapter_id=self.adapter_id,
                                              endpoint_session=self.plant.session, ttl_ms=3000)
                for property_id in ("value", "ready"):
                    key = (instance_id, property_id, binding["generation"], self.plant.session)
                    if key not in self._streams:
                        epoch = "sim-stream:" + uuid.uuid4().hex
                        self.registry.start_stream(instance_id, property_id, adapter_id=self.adapter_id,
                            endpoint_session=self.plant.session, binding_generation=binding["generation"],
                            stream_epoch=epoch)
                        self._streams[key] = [epoch, 0]
                    stream = self._streams[key]
                    stream[1] += 1
                    unit = ("1" if property_id == "ready" else
                            self.registry._type(binding["typeDigest"])["execution"]["properties"][property_id]["unit"])
                    self.registry.report_observation(instance_id, property_id, adapter_id=self.adapter_id,
                        endpoint_session=self.plant.session, binding_generation=binding["generation"],
                        value=sample[property_id], evidence_kind="simulation", quality="valid",
                        stream_epoch=stream[0], sequence=stream[1],
                        acquisition={"clockDomain": "simulator-monotonic", "clockEpoch": self.registry.receipt_epoch,
                                     "ticksMs": mono},
                        acquisition_latency_bound_ms=0, clock_uncertainty_ms=0,
                        measurement_uncertainty={"absolute": 0, "unit": unit, "method": "synthetic_exact_state"})
            self._last_sample = mono

    def _evidence(self, operation_id, *assertions):
        return Evidence("simulation", self.adapter_id, "sim-receipt:" + operation_id, assertions)

    def _validate_receipt(self, operation, receipt):
        """Validate historical ownership, even if the current binding changed."""
        intent = operation["intent"]
        historical = self.journal._db.execute(
            "SELECT document FROM reg_binding_history WHERE instance=? AND generation=?",
            (intent["instanceId"], intent["bindingGeneration"])).fetchone()
        if historical is None:
            raise JournalError("HISTORICAL_BINDING_MISSING")
        if json.loads(historical[0])["adapterId"] != self.adapter_id:
            raise JournalError("ADAPTER_OPERATION_ROUTE_MISMATCH")
        if receipt is not None:
            if (receipt["digest"] != operation["digest"] or
                    canonical(receipt["intent"]) != canonical(intent)):
                raise JournalError("SIMULATOR_RECEIPT_CONFLICT")
            if receipt["state"] not in {"pending", "completed", "canceled"}:
                raise JournalError("INVALID_SIMULATOR_RECEIPT")

    def _settle(self, operation, receipt, ticket=None):
        if receipt is None:
            return
        self._validate_receipt(operation, receipt)
        if receipt["state"] == "pending":
            return
        if receipt["state"] == "completed":
            state, assertion = "completed", "completed"
        else:
            reason = receipt["result"].get("reason")
            if reason in {"client_cancel", "simulator_owner_reopened"}:
                state, assertion = "canceled", "terminated"
            else:
                state, assertion = "failed", "failed"
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
        """Bounded work selection for this route; shared authority may block."""
        with self._tick_lock:
            refresh_error = None
            try:
                self.refresh()
            except (JournalError, ContractError) as error:
                # Sampling failure cannot suppress cancellation or recovery.
                refresh_error = error
            for operation in self.runtime.work_items(self.adapter_id, ("outcome_unknown",)):
                with self.journal._mutex:
                    self._settle(operation, self.plant.receipt(operation["id"]))
            for operation in self.runtime.work_items(self.adapter_id, ("accepted",)):
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
                    if reason is None and (mono - pending["started"] >= timing["maxRunMs"] or
                                           now >= timing["latestCompletionUnixMs"]):
                        reason = "execution_deadline"
                    elif reason is None and now >= operation["admission"]["lease_expires_ms"]:
                        reason = "lease_expired"
                    elif reason is None:
                        try:
                            # Keep the shared authority lock through the effect.
                            context = Context(operation["principal"], operation["deployment"])
                            self.policy.authorize(context, "invoke", operation["intent"]["instanceId"])
                            self.policy.recheck(context, operation, now)
                        except JournalError:
                            reason = "authority_or_precondition_lost"
                    if reason is None and mono < pending["due"]:
                        continue
                    receipt = self.plant.finish(operation_id, cancel_reason=reason)
                    self._settle(operation, receipt, pending["ticket"])
                    del self._pending[operation_id]
                    if refresh_error is None:
                        try:
                            self.refresh(force=True)
                        except (JournalError, ContractError) as error:
                            refresh_error = error
            # The historical route filter precedes LIMIT, including recovery
            # after completion evidence was committed but claim release was not.
            for operation in self.runtime.work_items(self.adapter_id, ("completed", "failed", "canceled"),
                                                     claims_only=True):
                with self.journal._mutex:
                    self._settle(operation, self.plant.receipt(operation["id"]))
            if refresh_error is not None:
                raise refresh_error

    def result(self, operation_id):
        with self.journal._mutex:
            operation = self.journal._operation(operation_id)
            receipt = self.plant.receipt(operation_id)
            self._validate_receipt(operation, receipt)
            if receipt is None or receipt["state"] == "pending":
                return None
            return {"evidenceKind": "simulation", "output": receipt["result"]}
