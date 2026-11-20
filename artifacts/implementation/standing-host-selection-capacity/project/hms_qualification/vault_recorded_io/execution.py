"""Complete relevant evidence inventory through deterministic PAT admission."""
import threading

from hms.journal import JournalError
from hms.pat_contracts import PatError, pat_digest, parse_pat, matches_static
from hms.pat_execution import PatExecutionStore, parse_run, _DDL
from .catalog import VaultRecordedPatCatalog
from .contracts import require, checked

PROFILE = 'hms.pat.io-vault-execution/0.1'


class VaultRecordedPatExecutionStore(PatExecutionStore):
    def __init__(self, journal, catalog, procedures):
        require(type(catalog) is VaultRecordedPatCatalog and catalog.journal is journal and
                procedures.journal is journal, 'AUTHORITY_MISMATCH')
        self.journal,self.catalog,self.procedures = journal,catalog,procedures
        self._db,self.resolver = journal._db,catalog.resolve
        self._selection = threading.local()
        with journal._transaction():
            expected={'px_meta','px_instances','px_triggers'}
            present={row[0] for row in self._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'px_*'")}
            if present and present!=expected:raise PatError('INCOMPLETE_PAT_EXECUTION')
            if not present:
                for statement in _DDL:self._db.execute(statement)
                self._db.execute("INSERT INTO px_meta VALUES ('version',?)",(PROFILE,))
            version=self._db.execute("SELECT value FROM px_meta WHERE key='version'").fetchone()
            if version is None or version[0]!=PROFILE:raise PatError('UNSUPPORTED_PAT_EXECUTION')

    def _source_access(self, context, artifact, receipt):
        try:
            for role,instance in receipt['applicability']['roleInstances'].items():
                self.journal.policy.authorize(context,'read',instance)
                for action in artifact['roles'][role]['actions']:
                    self.journal.policy.authorize(context,'invoke:'+action,instance)
        except JournalError as error:
            if error.code=='ACCESS_DENIED':return False
            raise
        return True

    def _inventory(self, context, request):
        rows=self.catalog._selection_rows(context);keys=set()
        for digest,state,evaluation,decision,conflict in rows:
            if state!='active':continue
            artifact=parse_pat(self.catalog._artifact(digest))
            if (artifact['taskKind'],artifact['inputProfile'])!=(request['taskKind'],request['inputProfile']):continue
            try:
                matched=matches_static(artifact,request['parameters'],task_kind=request['taskKind'],
                    input_profile=request['inputProfile'],evidence_mode=request['evidenceMode'])
            except PatError as error:
                if error.code in {'PAT_INVALID_PARAMETERS','PAT_PARAMETER_OUT_OF_DOMAIN'}:continue
                raise
            if not matched:continue
            if evaluation is None or conflict:raise PatError('PAT_EVALUATION_INVALID')
            receipt=self.catalog._stored_evaluation(context.deployment,evaluation,digest)
            if not self._source_access(context,artifact,receipt):continue
            original=receipt['invocation']['original']
            keys.add((original['evaluatorId'],original['runId']))
        return dict(rows=rows,keys=tuple(sorted(keys)),revision=self.catalog._revision(context.deployment),
            registryRevision=self._db.execute("SELECT value FROM main.reg_meta WHERE key='revision'").fetchone()[0])

    def _assignments(self, context, request, artifact):
        entry=self.catalog._entry(context.deployment,pat_digest(artifact))
        if entry['state']!='active' or entry['evaluation'] is None or entry['evaluation_conflict']:
            raise PatError('PAT_EVALUATION_INVALID')
        receipt=self.catalog._stored_evaluation(context.deployment,entry['evaluation'],entry['artifact'])
        if not self._source_access(context,artifact,receipt):return []
        valid,reason=self.catalog._eligible(context,entry)
        if not valid:raise PatError(reason or 'PAT_SELECTION_UNAVAILABLE')
        return super()._assignments(context,request,artifact)

    def _select(self, context, request, now):
        expected=getattr(self._selection,'inventory',None)
        require(expected is not None and self._inventory(context,request)==expected,'SELECTION_CHANGED')
        selected=super()._select(context,request,now)
        held=self.catalog.bridge._held
        require(held is not None,'SNAPSHOT_UNAVAILABLE')
        def final_inventory():
            require(self.catalog._selection_rows(context)==expected['rows'] and
                self.catalog._revision(context.deployment)==expected['revision'] and
                self._db.execute("SELECT value FROM main.reg_meta WHERE key='revision'").fetchone()[0]==expected['registryRevision'],
                'SELECTION_CHANGED')
            require(self.catalog.bridge._held is held and set(held.verified)==set(expected['keys']), 'SELECTION_CHANGED')
            held.lease.check(self.catalog.bridge.vault)
        self.journal._require_at_commit(final_inventory)
        return selected

    @checked
    def run(self, context, value):
        request=parse_run(value)
        with self.journal._transaction():
            self.journal._namespace(context,request['replayNamespace'])
            prior=self._db.execute('SELECT instance_id FROM px_triggers WHERE namespace=? AND run_key=?',
                (request['replayNamespace'],request['runKey'])).fetchone()
            if prior is None:inventory=self._inventory(context,request)
        # The inherited path authenticates and reconciles the original request.
        # It executes no fresh selection, preparation or vault access on replay.
        if prior is not None:return super().run(context,request)
        require(getattr(self._selection,'inventory',None) is None,'SNAPSHOT_REENTRY')
        self._selection.inventory=inventory
        try:
            if not inventory['keys']:return super().run(context,request)
            with self.catalog.bridge.hold(context,inventory['keys']):
                return super().run(context,request)
        finally:
            self._selection.inventory=None
