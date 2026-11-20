"""Explicit isolated lifecycle bootstrap; no stock/public profile mounting."""
import threading
import time

from .journal import Journal
from .procedures import ProcedureStore
from .registry import Registry
from .runtime import Runtime
from .state_path import private_state_directory
from .synthetic_io_adapter import IoRegistryPolicy, IoRouteAdapter
from .synthetic_io_installation import require
from .synthetic_lifecycle_adapter import LifecycleRouteAdapter
from .synthetic_lifecycle_board import LifecycleBoard
from .synthetic_lifecycle_catalog import LifecycleCatalog
from .synthetic_lifecycle_contracts import DRIVER, normalize


class LifecycleRuntime(Runtime):
    def __init__(self, state_dir, *, create=False, owner=None, installation=None,
                 wall_clock_ms=None, monotonic_ms=None):
        document = normalize(installation) if installation is not None else None
        if create:
            require(document is not None and owner is not None and owner.deployment == document['io']['topology']['deployment'],
                'EXPLICIT_LIFECYCLE_SIMULATION_OWNER_REQUIRED')
        self.wall_clock_ms = wall_clock_ms or (lambda: time.time_ns() // 1_000_000)
        self.monotonic_ms = monotonic_ms or (lambda: time.monotonic_ns() // 1_000_000)
        self.policy = IoRegistryPolicy(installed_support=self._check_installed_support,
            installed_plan_support=self._check_installed_plan_support)
        self._stop = threading.Event(); self._threads = {}; self._thread = None; self._procedure_thread = None
        self._tick_lock = threading.Lock(); self._route_locks = {}; self._errors_lock = threading.Lock()
        self.last_worker_error = None; self.last_procedure_error = None; self.route_errors = {}
        self.journal = self.plant = self.compact = self.procedures = self.io_board = None
        self.adapters = {}
        self.directory = private_state_directory(state_dir,create=create)
        try:
            self.journal = Journal(self.directory/'authority.db',self.policy,clock_ms=self.wall_clock_ms,create=create)
            self.registry = Registry(self.journal,monotonic_ms=self.monotonic_ms,bootstrap_owner=owner if create else None)
            self.policy.attach(self.registry); self.deployment = self.registry.deployment
            self.catalog = LifecycleCatalog(self.journal,self.registry,create=create,owner=owner,installation=document)
            self.policy.attach_resource_resolver(self.catalog.resolve)
            filename = self.catalog.board_filename()
            private_state_directory(self.directory,database_names=[filename])
            path = self.directory/filename
            new_board = not any(self.catalog.ready.values()) and not path.exists()
            if new_board:
                require(self.journal._db.execute('SELECT 1 FROM operations WHERE may_have_acted=1 LIMIT 1').fetchone() is None,
                    'IO_BOARD_MISSING_WITH_EFFECT_HISTORY')
            self.io_board = LifecycleBoard(path,self.catalog.document,create=new_board,
                authority_id=self.journal.authority_id,owner_epoch=self.journal.owner_epoch,clock_epoch=self.registry.receipt_epoch)
            for route in self.catalog.installations:
                adapter = route['adapterId']; self._route_locks[adapter] = threading.RLock()
                backend_type = LifecycleRouteAdapter if route['driver'] == DRIVER else IoRouteAdapter
                backend = backend_type(self,route,self.io_board)
                self.adapters[adapter] = backend; self.policy.io_backends[adapter] = backend
                backend.refresh(force=True)
                self.catalog.mark_ready(adapter)
            self.procedures = ProcedureStore(self.journal)
        except BaseException:
            self.close(); raise

    def _reject_uninstalled_work(self):
        # Only this explicit profile recognizes its validated retained lifecycle
        # inventory. Existing Runtime and all older profiles keep their exact path.
        with self.journal._mutex:
            self.catalog._load()
            rows = self.journal._db.execute(
                "SELECT o.id FROM operations o LEFT JOIN reg_binding_history b ON "
                "b.instance=json_extract(CAST(o.intent AS TEXT),'$.instanceId') AND "
                "b.generation=json_extract(CAST(o.intent AS TEXT),'$.bindingGeneration') "
                "LEFT JOIN rt_adapters a ON a.adapter=json_extract(CAST(b.document AS TEXT),'$.adapterId') "
                "LEFT JOIN lc_routes l ON l.adapter=json_extract(CAST(b.document AS TEXT),'$.adapterId') "
                "WHERE o.state='accepted' AND a.adapter IS NULL AND l.adapter IS NULL ORDER BY o.rowid LIMIT 64").fetchall()
            for row in rows:
                self.journal.reject_before_dispatch(row[0],'adapter_installation_unavailable')

    def close(self):
        try:
            super().close()
        finally:
            if self.io_board is not None:
                self.io_board.close(); self.io_board = None
