"""Held-vault evidence must remain valid through the Journal business commit."""
import unittest
from unittest.mock import patch
from test_business_precommit import BusinessCommitTests, TABLES


class VaultCommitTests(BusinessCommitTests):
    """Selected methods only; the runner avoids repeating inherited controls."""
    def vault(self):
        from hms_qualification.evidence_vault import EvidenceVault, descriptor
        from hms_qualification.evidence_vault.contracts import sha
        parent = self.root/'vault'; parent.mkdir(mode=0o700)
        vault = EvidenceVault(parent/'evidence.db', descriptor(self.journal.authority_id, max_pages=64), create=True)
        intent, binding = sha(b'byte retention fixture'), sha(b'original fixture association')
        vault.seal(intent, binding, {'fixture/bytes': b'identity only; not qualification'})
        return vault, intent, binding

    def test_held_vault_lease_checks_after_admission_writes(self):
        vault, intent, binding = self.vault()
        with vault:
            with vault.snapshot(intent, binding) as lease:
                def check():
                    self.assertEqual(self.counts(), dict.fromkeys(TABLES, 1))
                    lease.check(vault)
                    self.record()
                self.arm(check)
                self.submit()
        self.assertEqual(self.calls, ['checked'])

    def test_vault_expiry_between_initial_validation_and_commit_rolls_back(self):
        vault, intent, binding = self.vault()
        clock = [1000]
        with vault, patch('hms_qualification.evidence_vault.connection.time.monotonic_ns', side_effect=lambda: clock[0]):
            with vault.snapshot(intent, binding, lifetime_ms=1) as lease:
                lease.check(vault)
                self.arm(lambda: lease.check(vault))
                self.late(lambda: clock.__setitem__(0, 1001000))
                self.code('PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE', self.submit)
                self.empty()
                # Restore the test clock only to allow the held fixture to exit.
                clock[0] = 1000

    def test_replaced_vault_lease_cannot_authorize_commit(self):
        vault, intent, binding = self.vault()
        with vault:
            with vault.snapshot(intent, binding) as lease:
                self.arm(lambda: lease.check(vault))
                self.late(lambda: setattr(vault, '_lease', object()))
                try:
                    self.code('PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE', self.submit)
                    self.empty()
                finally:
                    vault._lease = lease

    def test_released_vault_lease_cannot_authorize_commit(self):
        vault, intent, binding = self.vault()
        with vault:
            with vault.snapshot(intent, binding) as lease:
                lease.check(vault)
            self.arm(lambda: lease.check(vault))
            self.code('PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE', self.submit)
            self.empty()

    def test_wrong_vault_owner_cannot_authorize_commit(self):
        vault, intent, binding = self.vault()
        with vault:
            with vault.snapshot(intent, binding) as lease:
                self.arm(lambda: lease.check(object()))
                self.code('PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE', self.submit)
                self.empty()


def load_tests(loader, tests, pattern):
    """Run exactly the five vault methods; inherited checks already run separately."""
    names = ('test_held_vault_lease_checks_after_admission_writes', 'test_vault_expiry_between_initial_validation_and_commit_rolls_back', 'test_replaced_vault_lease_cannot_authorize_commit', 'test_released_vault_lease_cannot_authorize_commit', 'test_wrong_vault_owner_cannot_authorize_commit')
    return unittest.TestSuite(VaultCommitTests(name) for name in names)
