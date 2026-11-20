"""Recorded-profile selection checks applicability before legacy filtering."""
from hms.journal import JournalError
from hms.pat_contracts import PatError, pat_digest
from hms.pat_execution import PatExecutionStore
from .catalog import RecordedPatCatalog
from .contracts import require

class RecordedPatExecutionStore(PatExecutionStore):
    def __init__(self, journal, catalog, procedures):
        require(type(catalog) is RecordedPatCatalog, 'AUTHORITY_MISMATCH')
        super().__init__(journal, catalog, procedures, resolver=catalog.resolve)

    def _assignments(self, context, request, artifact):
        assignments = super()._assignments(context, request, artifact)
        entry = self.catalog._entry(context.deployment, pat_digest(artifact))
        if entry['state'] != 'active' or entry['evaluation'] is None or entry['evaluation_conflict'] != 0:
            raise PatError('PAT_EVALUATION_INVALID')
        receipt = self.catalog._stored_evaluation(context.deployment, entry['evaluation'], entry['artifact'])
        # Authorization precedes access to the original source environment.
        # Another authorized assignment must not disclose inaccessible devices.
        try:
            for role, instance in receipt['applicability']['roleInstances'].items():
                self.journal.policy.authorize(context, 'read', instance)
                for action in artifact['roles'][role]['actions']:
                    self.journal.policy.authorize(context, 'invoke:' + action, instance)
        except JournalError as error:
            if error.code == 'ACCESS_DENIED':
                return assignments
            raise
        valid, reason = self.catalog._eligible(context, entry)
        if not valid:
            # All failures here concern an active, statically relevant source
            # assignment this principal may use. Preserve it as unavailable;
            # neither a different environment nor an empty live inventory may
            # turn it into an omitted candidate and manufacture novelty.
            raise PatError(reason or 'PAT_SELECTION_UNAVAILABLE')
        return assignments
