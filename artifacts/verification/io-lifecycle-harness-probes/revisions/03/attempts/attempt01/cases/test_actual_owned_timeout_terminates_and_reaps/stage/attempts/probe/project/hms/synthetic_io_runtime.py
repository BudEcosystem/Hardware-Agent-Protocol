"""Staged I/O bootstrap reusing original Runtime scheduling/API and Journal logic.

This explicit class accepts only the new shared-board installation. It is not
mounted in the stock daemon, CLI, MCP or existing installation profile.
"""
import threading
import time

from .journal import Journal, JournalError
from .procedures import ProcedureStore
from .registry import Registry
from .runtime import Runtime
from .state_path import private_state_directory
from .synthetic_io_adapter import IoRegistryPolicy, IoRouteAdapter
from .synthetic_io_board import SyntheticIoBoard
from .synthetic_io_catalog import IoAdapterCatalog
from .synthetic_io_installation import normalize_installation, require


class IoRuntime(Runtime):
    def __init__(self, state_dir, *, create=False, owner=None, installation=None,
                 wall_clock_ms=None, monotonic_ms=None):
        document = normalize_installation(installation) if installation is not None else None
        if create:
            require(document is not None and owner is not None and owner.deployment == document['topology']['deployment'],
                    'EXPLICIT_IO_SIMULATION_OWNER_REQUIRED')
        self.wall_clock_ms = wall_clock_ms or (lambda: time.time_ns() // 1_000_000)
        self.monotonic_ms = monotonic_ms or (lambda: time.monotonic_ns() // 1_000_000)
        self.policy = IoRegistryPolicy(installed_support=self._check_installed_support,
            installed_plan_support=self._check_installed_plan_support)
        # Bootstrap plumbing only. All inherited dispatch, route selection,
        # procedure, cancellation and API behavior remains original Runtime.
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
            self.catalog = IoAdapterCatalog(self.journal,self.registry,create=create,owner=owner,installation=document)
            self.policy.attach_resource_resolver(self.catalog.resources.resolve)
            filename = self.catalog.board_filename()
            private_state_directory(self.directory,database_names=[filename])
            path = self.directory/filename
            new_board = not any(self.catalog.ready.values()) and not path.exists()
            if new_board:
                require(self.journal._db.execute('SELECT 1 FROM operations WHERE may_have_acted=1 LIMIT 1').fetchone() is None,
                        'IO_BOARD_MISSING_WITH_EFFECT_HISTORY')
            self.io_board = SyntheticIoBoard(path,self.catalog.document,create=new_board,
                authority_id=self.journal.authority_id,owner_epoch=self.journal.owner_epoch,clock_epoch=self.registry.receipt_epoch)
            # One board object and one recovery pass, regardless of route count.
            for route in self.catalog.installations:
                adapter = route['adapterId']; self._route_locks[adapter] = threading.RLock()
                backend = IoRouteAdapter(self,route,self.io_board)
                self.adapters[adapter] = backend; self.policy.io_backends[adapter] = backend
                backend.refresh(force=True)
                self.catalog.mark_ready(adapter)
            self.procedures = ProcedureStore(self.journal)
        except BaseException:
            self.close(); raise

    def close(self):
        try:
            super().close()
        finally:
            if self.io_board is not None:
                self.io_board.close(); self.io_board = None
