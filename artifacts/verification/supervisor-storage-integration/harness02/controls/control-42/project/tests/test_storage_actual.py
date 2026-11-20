"""The unchanged complete actual oracle with an explicitly split fixture."""
from hms_qualification.supervisor.io_service_execution import BoundQualificationSupervisor
from hms_qualification.supervisor.storage_binding import install_binding
from test_io_service_runs import IoServiceRunTests, business
from test_vault_catalog_process import VaultCatalogProcessTests


class SplitVaultCatalogProcessTests(VaultCatalogProcessTests):
    def setUp(self):
        IoServiceRunTests.setUp(self)
        IoServiceRunTests.create(self)
        self.original=self.reserve()
        self.binding=install_binding(self.parent/'supervisor-control',self.parent/'supervisor-bulk')
        self.bound=BoundQualificationSupervisor(self.parent/'supervisor-control',create=True,storage_binding=self.binding)
        self.supervisor_id=self.bound.ledger.authority_id
        self.addCleanup(self.close_bound)
        self.before_business=business(self.runtime)
        self.emit('storage-binding',self.binding)
