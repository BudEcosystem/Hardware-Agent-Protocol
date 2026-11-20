"""Shared local authority with explicitly installed synthetic adapter routes."""
from __future__ import annotations

import copy
import json
import os
import socket
import threading
import time

from .adapter_catalog import AdapterCatalog
from .api_contracts import METHOD_RESULTS, validate_params, validate_result
from .contracts import ContractError, canonical, identifier, intent_digest, parse_invoke
from .installations import (LEGACY_COMPACT, definitions_for, normalize_installations, plant_filename)
from .journal import Context, Journal, JournalError, PresenceAgeExpired, TERMINAL
from .local_adapter import LocalSimulation
from .procedures import ProcedureStore
from .registry import Registry, RegistryPolicy, bounded_int, exact, validate_type_bundle
from .simulator import SimulatedPlant
from .state_path import private_state_directory


class UnavailableAdapter:
    """A known installation that could not mount; never route its work elsewhere."""
    def __init__(self, runtime, installation, code):
        self.runtime, self.installation = runtime, copy.deepcopy(installation)
        self.adapter_id, self.code = installation['adapterId'], code

    def validate_admission(self, intent, binding, resources):
        raise JournalError('ADAPTER_OFFLINE')

    def refresh(self, *, force=False):
        raise JournalError(self.code)

    def tick(self):
        accepted = self.runtime.work_items(self.adapter_id, ('accepted',))
        now = self.runtime.journal.authority_time() if accepted else None
        for op in accepted:
            if now >= min(op['intent']['timing']['latestStartUnixMs'], op['admission']['lease_expires_ms']):
                self.runtime.journal.reject_before_dispatch(op['id'], 'start_or_lease_expired')
        raise JournalError(self.code)

    def result(self, operation_id):
        return None

    def close(self):
        pass


class Runtime:
    def __init__(self, state_dir, *, create=False, owner=None, wall_clock_ms=None,
                 monotonic_ms=None, endpoint_fd=None, installations=None, endpoint_fds=None):
        configurations = normalize_installations(installations) if installations is not None else None
        if configurations is not None:
            for configuration in configurations:
                for _instance, _action, document in definitions_for(configuration):
                    validate_type_bundle(document)
        self.wall_clock_ms = wall_clock_ms or (lambda: time.time_ns() // 1_000_000)
        self.monotonic_ms = monotonic_ms or (lambda: time.monotonic_ns() // 1_000_000)
        self.policy = RegistryPolicy(installed_support=self._check_installed_support,
                                     installed_plan_support=self._check_installed_plan_support)
        self._stop = threading.Event()
        self._threads = {}
        self._thread = None  # Compatibility for the single-route lifecycle.
        self._procedure_thread = None
        self._tick_lock = threading.Lock()
        self._route_locks = {}
        self._errors_lock = threading.Lock()
        self.last_worker_error = None
        self.last_procedure_error = None
        self.route_errors = {}
        self.journal = self.plant = self.compact = None
        self.procedures = None
        self.adapters = {}
        deployment = ('simulation:multi' if configurations is not None else
                      'simulation:compact' if endpoint_fd is not None else 'simulation:local')
        if create and (owner is None or owner.deployment != deployment):
            raise JournalError('EXPLICIT_SIMULATION_OWNER_REQUIRED')
        if endpoint_fd is not None and configurations is not None:
            raise JournalError('AMBIGUOUS_ENDPOINT_ROUTE')
        if endpoint_fds is not None and type(endpoint_fds) is not dict:
            raise JournalError('INVALID_ENDPOINT_ROUTES')
        streams = dict(endpoint_fds or {})
        if endpoint_fd is not None:
            if LEGACY_COMPACT in streams:
                raise JournalError('DUPLICATE_ENDPOINT_ROUTE')
            streams[LEGACY_COMPACT] = endpoint_fd
        self._validate_streams(streams)
        self.directory = private_state_directory(state_dir, create=create)
        try:
            self.journal = Journal(self.directory / 'authority.db', self.policy,
                                   clock_ms=self.wall_clock_ms, create=create)
            self.registry = Registry(self.journal, monotonic_ms=self.monotonic_ms,
                                     bootstrap_owner=owner if create else None)
            self.policy.attach(self.registry)
            self.deployment = self.registry.deployment
            self.catalog = AdapterCatalog(self.journal, self.registry, create=create, owner=owner,
                installations=configurations, legacy_compact=endpoint_fd is not None)
            if not self.catalog.legacy and self.deployment != 'simulation:multi':
                raise JournalError('INSTALLATION_DEPLOYMENT_MISMATCH')
            compact_ids = {item['adapterId'] for item in self.catalog.installations
                           if item['driver'] == 'compact-simulation'}
            if set(streams) - compact_ids:
                raise JournalError('UNKNOWN_ENDPOINT_ROUTE')
            if self.catalog.legacy and compact_ids and not streams:
                raise JournalError('ENDPOINT_STREAM_REQUIRED')
            if not self.catalog.legacy and endpoint_fd is not None:
                raise JournalError('AMBIGUOUS_ENDPOINT_ROUTE')
            names = [plant_filename(item) for item in self.catalog.installations
                     if item['driver'] == 'sqlite-simulation' and not self.catalog.legacy]
            private_state_directory(self.directory, database_names=names)
            if compact_ids:
                from .endpoint_binding import CompactSimulation, ensure_endpoint_schema
                ensure_endpoint_schema(self.journal)
            for installation in self.catalog.installations:
                adapter_id = installation['adapterId']
                self._route_locks[adapter_id] = threading.RLock()
                plant = None
                backend = None
                try:
                    if installation['driver'] == 'sqlite-simulation':
                        path = self.directory / plant_filename(installation, legacy=self.catalog.legacy)
                        new_store = not self.catalog.ready[adapter_id] and not path.exists()
                        plant = SimulatedPlant(path, create=new_store, installation=installation)
                        if not self.catalog.ready[adapter_id]:
                            self.catalog.provision_local_registry(installation)
                        backend = LocalSimulation(self, installation, plant)
                        self.catalog.mark_ready(adapter_id)
                    else:
                        backend = CompactSimulation(self, streams.get(adapter_id),
                            create=not self.catalog.ready[adapter_id], owner=self.catalog.owner,
                            installation=installation, allow_offline=not self.catalog.legacy)
                        if backend._state()['installed']:
                            self.catalog.mark_ready(adapter_id)
                    self.adapters[adapter_id] = backend
                    if self.catalog.legacy:
                        self.plant = plant
                        self.compact = backend if installation['driver'] == 'compact-simulation' else None
                    if installation['driver'] == 'sqlite-simulation':
                        backend.refresh(force=True)
                    self._record_route_error(adapter_id, getattr(backend, 'startup_error', None))
                except (JournalError, ContractError, OSError) as error:
                    if backend is not None:
                        backend.close()
                    elif plant is not None:
                        plant.close()
                    if self.catalog.legacy:
                        raise
                    code = getattr(error, 'code', 'ADAPTER_START_FAILED')
                    self.adapters[adapter_id] = UnavailableAdapter(self, installation, code)
                    with self.journal._transaction():
                        self.journal._db.execute('DELETE FROM reg_presence WHERE adapter=?', (adapter_id,))
                    self._record_route_error(adapter_id, code)
                except BaseException:
                    # A partially mounted route is not yet in adapters.
                    if backend is not None:
                        backend.close()
                    elif plant is not None:
                        plant.close()
                    raise
            # Recovery interrupts continuation before either scheduler starts.
            # Child evidence/reconciliation remain owned by the adapter routes.
            self.procedures = ProcedureStore(self.journal)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _validate_streams(streams):
        seen = set()
        for adapter, fd in streams.items():
            identifier(adapter)
            if type(fd) is not int or fd < 0:
                raise JournalError('INVALID_ENDPOINT_STREAM')
            try:
                info = os.fstat(fd)
                identity = (info.st_dev, info.st_ino)
                if identity in seen:
                    raise JournalError('DUPLICATE_ENDPOINT_STREAM')
                with socket.socket(fileno=os.dup(fd)) as stream:
                    if stream.family != socket.AF_UNIX or stream.type != socket.SOCK_STREAM:
                        raise JournalError('INVALID_ENDPOINT_STREAM')
                    stream.getpeername()
                seen.add(identity)
            except OSError as error:
                raise JournalError('INVALID_ENDPOINT_STREAM') from error

    def _record_route_error(self, adapter_id, code):
        with self._errors_lock:
            if code is None:
                self.route_errors.pop(adapter_id, None)
            else:
                self.route_errors[adapter_id] = code
            self.last_worker_error = next(iter(self.route_errors.values()), self.last_procedure_error)

    def _record_procedure_error(self, code):
        with self._errors_lock:
            self.last_procedure_error = code
            self.last_worker_error = next(iter(self.route_errors.values()), code)

    def start(self):
        if self._threads or self._stop.is_set():
            raise JournalError('RUNTIME_ALREADY_STARTED')
        for adapter_id in self.adapters:
            thread = threading.Thread(target=self._run_route, args=(adapter_id,),
                                      name='hms-adapter-' + str(len(self._threads)), daemon=False)
            self._threads[adapter_id] = thread
            thread.start()
        self._thread = next(iter(self._threads.values()), None)
        self._procedure_thread = threading.Thread(target=self._run_procedures,
                                                 name='hms-procedures', daemon=False)
        self._procedure_thread.start()

    def close(self):
        self._stop.set()
        if self._procedure_thread is not None:
            self._procedure_thread.join()
            self._procedure_thread = None
        for thread in self._threads.values():
            thread.join()
        self._threads.clear()
        self._thread = None
        errors = []
        for backend in self.adapters.values():
            try:
                backend.close()
            except Exception as error:
                errors.append(error)
        self.adapters.clear()
        self.plant = self.compact = None
        if self.journal is not None:
            try:
                self.journal.close()
            finally:
                self.journal = None
        if errors:
            raise errors[0]

    def _run_procedures(self):
        while not self._stop.is_set():
            try:
                self.procedures.tick()
                self._record_procedure_error(None)
            except (JournalError, ContractError) as error:
                self._record_procedure_error(getattr(error, 'code', 'CONTRACT_ERROR'))
            except Exception:
                self._record_procedure_error('PROCEDURE_WORKER_FAILURE')
            self._stop.wait(0.02)

    def _run_route(self, adapter_id):
        while not self._stop.is_set():
            try:
                self._reject_uninstalled_work()
                with self._route_locks[adapter_id]:
                    self.adapters[adapter_id].tick()
                self._record_route_error(adapter_id, None)
            except (JournalError, ContractError) as error:
                self._record_route_error(adapter_id, getattr(error, 'code', 'CONTRACT_ERROR'))
            except Exception:
                self._record_route_error(adapter_id, 'WORKER_FAILURE')
            self._stop.wait(0.02)

    def _check_installed_support(self, intent, binding, resources):
        backend = self.adapters.get(binding['adapterId'])
        if backend is None:
            raise JournalError('ADAPTER_INSTALLATION_UNSUPPORTED')
        backend.validate_admission(intent, binding, resources)

    def _check_installed_plan_support(self, intent, binding, resources):
        backend = self.adapters.get(binding['adapterId'])
        if backend is None:
            raise JournalError('ADAPTER_INSTALLATION_UNSUPPORTED')
        if backend.installation['driver'] == 'compact-simulation' and not isinstance(backend, UnavailableAdapter):
            backend.validate_admission(intent, binding, resources, require_online=False)
        else:
            backend.validate_admission(intent, binding, resources)

    def route_for_operation(self, operation):
        with self.journal._mutex:
            intent = operation['intent']
            row = self.journal._db.execute('SELECT document FROM reg_binding_history WHERE instance=? AND generation=?',
                (intent['instanceId'], intent['bindingGeneration'])).fetchone()
            if row is None:
                return None
            return json.loads(row[0])['adapterId']

    def _reject_uninstalled_work(self):
        # An accepted item has no handoff ticket. Unknown historical routes
        # cannot execute it; preserve all handed-off work and its claims.
        with self.journal._mutex:
            rows = self.journal._db.execute(
                "SELECT o.id FROM operations o LEFT JOIN reg_binding_history b ON "
                "b.instance=json_extract(CAST(o.intent AS TEXT),'$.instanceId') AND "
                "b.generation=json_extract(CAST(o.intent AS TEXT),'$.bindingGeneration') "
                "LEFT JOIN rt_adapters a ON a.adapter=json_extract(CAST(b.document AS TEXT),'$.adapterId') "
                "WHERE o.state='accepted' AND a.adapter IS NULL ORDER BY o.rowid LIMIT 64").fetchall()
            for row in rows:
                self.journal.reject_before_dispatch(row[0], 'adapter_installation_unavailable')

    def work_items(self, adapter_id, states, *, limit=64, claims_only=False, startable_ms=None,
                   skip_paused=False, expired_ms=None):
        """Route via immutable binding history, filtering BEFORE the row limit."""
        identifier(adapter_id)
        allowed = {'accepted', 'dispatching', 'running', 'outcome_unknown'} | TERMINAL
        if (type(states) is not tuple or not states or set(states) - allowed or
                type(limit) is not int or not 1 <= limit <= 256 or type(claims_only) is not bool or
                type(skip_paused) is not bool):
            raise JournalError('INVALID_WORK_QUERY')
        clauses = ["json_extract(CAST(b.document AS TEXT),'$.adapterId')=?",
                   'o.state IN (' + ','.join('?' for _ in states) + ')']
        parameters = [adapter_id, *states]
        if claims_only:
            clauses.append('EXISTS(SELECT 1 FROM claims c WHERE c.operation_id=o.id)')
        if skip_paused:
            # Filter before LIMIT so an interrupted procedure cannot starve
            # unrelated accepted work on the same installed route. Expiry is
            # processed separately, including paused children.
            clauses.append("NOT EXISTS(SELECT 1 FROM pr_steps s JOIN pr_procedures p "
                           "ON p.id=s.procedure_id WHERE s.operation_id=o.id AND p.state='interrupted')")
        if startable_ms is not None:
            bounded_int(startable_ms)
            clauses.append("json_extract(CAST(o.intent AS TEXT),'$.timing.notBeforeUnixMs')<=?")
            parameters.append(startable_ms)
        if expired_ms is not None:
            bounded_int(expired_ms)
            clauses.append("(json_extract(CAST(o.intent AS TEXT),'$.timing.latestStartUnixMs')<=? OR "
                           "json_extract(CAST(o.admission AS TEXT),'$.lease_expires_ms')<=?)")
            parameters.extend((expired_ms, expired_ms))
        with self.journal._mutex:
            rows = self.journal._db.execute("SELECT o.id FROM operations o JOIN reg_binding_history b ON "
                "b.instance=json_extract(CAST(o.intent AS TEXT),'$.instanceId') AND "
                "b.generation=json_extract(CAST(o.intent AS TEXT),'$.bindingGeneration') WHERE " +
                ' AND '.join(clauses) + ' ORDER BY o.rowid LIMIT ?', (*parameters, limit)).fetchall()
            return [self.journal._operation(row[0]) for row in rows]

    def expire_unstarted(self, adapter_id):
        """Bounded expiry pass including paused work; never authorizes handoff."""
        with self.journal._mutex:
            accepted = self.work_items(adapter_id, ('accepted',), limit=1)
            if not accepted:
                return False
            try:
                now = self.journal.authority_time()
            except JournalError:
                return True
            for operation in self.work_items(adapter_id, ('accepted',), expired_ms=now):
                self.journal.reject_before_dispatch(operation['id'], 'start_or_lease_expired')
            return True

    def _refresh(self, *, force=False):
        errors = []
        for adapter_id, backend in self.adapters.items():
            try:
                with self._route_locks[adapter_id]:
                    backend.refresh(force=force)
            except (JournalError, ContractError) as error:
                self._record_route_error(adapter_id, getattr(error, 'code', 'CONTRACT_ERROR'))
                errors.append(error)
        if errors:
            raise errors[0]

    def tick(self):
        """Drive every route despite a local failure; no cross-route time bound."""
        errors = []
        with self._tick_lock:
            try:
                self.procedures.tick()
                self._record_procedure_error(None)
            except (JournalError, ContractError) as error:
                self._record_procedure_error(getattr(error, 'code', 'CONTRACT_ERROR'))
                errors.append(error)
            except Exception as error:
                self._record_procedure_error('PROCEDURE_WORKER_FAILURE')
                errors.append(error)
            self._reject_uninstalled_work()
            for adapter_id, backend in self.adapters.items():
                try:
                    with self._route_locks[adapter_id]:
                        backend.tick()
                    self._record_route_error(adapter_id, None)
                except (JournalError, ContractError) as error:
                    self._record_route_error(adapter_id, getattr(error, 'code', 'CONTRACT_ERROR'))
                    errors.append(error)
                except Exception as error:
                    self._record_route_error(adapter_id, 'WORKER_FAILURE')
                    errors.append(error)
            try:
                self.procedures.tick()
                self._record_procedure_error(None)
            except (JournalError, ContractError) as error:
                self._record_procedure_error(getattr(error, 'code', 'CONTRACT_ERROR'))
                errors.append(error)
            except Exception as error:
                self._record_procedure_error('PROCEDURE_WORKER_FAILURE')
                errors.append(error)
        if errors:
            raise errors[0]

    def operation(self, context, operation_id):
        with self.journal._mutex:
            op = self.journal.status(context, operation_id)
            intent = op['intent']
            backend = self.adapters.get(self.route_for_operation(op))
            return {'protocol': 'hms.operation/0.1', 'operationId': op['id'], 'requestDigest': op['digest'],
                    'instanceId': intent['instanceId'], 'actionId': intent['actionId'],
                    'executionState': op['state'], 'cancellationState': op['cancel_state'],
                    'effectVerification': op['verification'], 'mayHaveActed': op['may_have_acted'],
                    'eventSequence': op['sequence'], 'resourceClaims': copy.deepcopy(op['claims']),
                    'result': backend.result(op['id']) if backend is not None else None}

    def _submit_invoke(self, context, wire):
        """One authorized observation attempt for a fresh, expired presence.

        Ordinary submit resolves retained replay and static authorization and
        identity refusals first. Prepare and managed procedure admission do not
        use this path. Live preconditions and resource conflicts can still fail.
        Every failed submit has exited its transaction before transport I/O.
        """
        try:
            return self.journal.submit(context, wire)
        except PresenceAgeExpired as expired:
            adapter_id = expired.adapter_id
        backend = self.adapters.get(adapter_id)
        refresh = getattr(backend, 'refresh_for_admission', None)
        lock = self._route_locks.get(adapter_id)
        if refresh is None or lock is None:
            raise PresenceAgeExpired(adapter_id)
        # Match worker order. The route lock also protects the stream while a
        # worker exchange is outside an individual authority transaction.
        with lock, self.journal._mutex:
            try:
                return self.journal.submit(context, wire)
            except PresenceAgeExpired as expired:
                if expired.adapter_id != adapter_id:
                    raise
            # Recheck above handles concurrent replay, revocation, changed
            # binding/session and expiry without duplicating Journal rules.
            refresh()
            return self.journal.submit(context, wire)

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
        if method == "procedure_submit":
            exact(params, {"request"})
            return self.procedures.submit(context, params["request"])
        if method in {"procedure_status", "procedure_cancel", "procedure_resume"}:
            exact(params, {"procedureId"})
            handler = {"procedure_status": self.procedures.status,
                       "procedure_cancel": self.procedures.cancel,
                       "procedure_resume": self.procedures.resume}[method]
            return handler(context, identifier(params["procedureId"]))
        if method == "procedure_events":
            return self.procedures.events(context, identifier(params["procedureId"]),
                after=params.get("after", 0), limit=params.get("limit", 100))
        if method == "invoke":
            exact(params, {"request"})
            op = self._submit_invoke(context, canonical(params["request"]))
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


def open_runtime(state_dir, *, create=False, owner=None, wall_clock_ms=None,
                 monotonic_ms=None, endpoint_fd=None, installations=None,
                 endpoint_fds=None, io_simulation=False, io_installation=None):
    """Open one explicitly selected installed runtime with the shared API.

    The I/O profile uses its own persistent catalog and shared board. It cannot
    be combined implicitly with the older route inventory or endpoint streams.
    Reopening requires the same explicit profile; no failed-profile fallback
    creates, resets, or tries another provider.
    """
    if type(io_simulation) is not bool:
        raise JournalError('INVALID_RUNTIME_PROFILE')
    if io_simulation:
        if installations is not None or endpoint_fd is not None or endpoint_fds is not None:
            raise JournalError('AMBIGUOUS_RUNTIME_CONFIGURATION')
        # IoRuntime subclasses Runtime; importing only after this module has
        # initialized avoids a partially initialized superclass import cycle.
        from .synthetic_io_runtime import IoRuntime
        return IoRuntime(state_dir, create=create, owner=owner, installation=io_installation,
                         wall_clock_ms=wall_clock_ms, monotonic_ms=monotonic_ms)
    if io_installation is not None:
        raise JournalError('INVALID_RUNTIME_PROFILE')
    return Runtime(state_dir, create=create, owner=owner, wall_clock_ms=wall_clock_ms,
                   monotonic_ms=monotonic_ms, endpoint_fd=endpoint_fd,
                   installations=installations, endpoint_fds=endpoint_fds)
