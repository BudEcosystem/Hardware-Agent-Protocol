"""Closed installed-profile logical accounting; no physical reservation claim.

Every Journal business commit scans all installed user tables under its existing
transaction. Unknown writer schemas refuse. Row charge is exactly 512 bytes plus
UTF-8/text or blob bytes, eight per integer/real and zero per NULL. This bounds
retained values, not SQLite pages, journals, filesystem metadata or free space.
Independent finite/fixed partitions cannot spend a standing continuation quota.
"""
MIB = 1024 * 1024
MAX_LOGICAL = 16 * MIB
FIXED_LIMIT = 512 * 1024
FINITE_OWNER_LIMIT = 64 * 1024
STANDING_OWNER_LIMIT = 896 * 1024
STANDING_BASE_LIMIT = 512 * 1024
MAX_OWNERS = 16
FIXED_TABLES = frozenset(('meta','series','namespaces','resource_floors','resource_owners',
    'resource_owner_instances','claims','reg_meta','reg_types','reg_instances',
    'reg_capabilities','reg_bindings','reg_binding_history','reg_presence',
    'reg_endpoint_sessions','reg_session_history','reg_observations','reg_streams',
    'reg_stream_history','reg_grants','reg_resource_requirements','reg_resource_instances',
    'rc_catalog','rc_generations','rc_tokens','rc_proofs','sp_meta','sp_artifacts',
    'sp_evaluations','sp_decisions'))
FINITE_TABLES = {'operations':'id','replay_keys':'operation_id','events':'operation_id'}
STANDING_TABLES = {'sd_deployments':'id','sd_mutations':'deployment_id',
    'sd_activations':'deployment_id','sd_activation_versions':'deployment_id',
    'sd_conflicts':'deployment_id','sd_episodes':'deployment_id'}
STANDING_BASE = frozenset(('sd_meta','sd_route'))


def check(db, error):
    def need(value, code='STANDING_LOGICAL_CAPACITY'):
        if not value:
            raise error(code)
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    need(len(tables) <= 48 and set(tables) <= FIXED_TABLES | FINITE_TABLES.keys() |
         STANDING_TABLES.keys() | STANDING_BASE, 'STANDING_UNBOUNDED_WRITER_SCHEMA')
    fixed = base = metadata = 0
    finite, standing = {}, {}
    for table in tables:
        columns = [r[1] for r in db.execute('PRAGMA table_info("'+table+'")')]
        need(0 < len(columns) <= 16 and all(c.replace('_','').isalnum() for c in columns), 'STANDING_SCHEMA')
        count = db.execute('SELECT count(*) FROM "'+table+'"').fetchone()[0]
        need(count <= (4096 if table in ('events','sd_mutations','sd_activations','sd_activation_versions') else 1024))
        fields = ['CASE typeof("'+c+'") WHEN \'null\' THEN 0 WHEN \'integer\' THEN 8 WHEN \'real\' THEN 8 ELSE length(CAST("'+c+'" AS BLOB)) END' for c in columns]
        expression = '512+' + '+'.join(fields)
        group = FINITE_TABLES.get(table) or STANDING_TABLES.get(table)
        rows = db.execute('SELECT '+(('"'+group+'",') if group else '')+expression+' AS charge FROM "'+table+'"').fetchall()
        for item in rows:
            charge = item[-1]
            row_limit = {'events':1536,'operations':8192,'replay_keys':1024}.get(table,66*1024)
            need(type(charge) is int and charge <= row_limit)
            if table == 'meta':
                metadata += charge
            elif table in FIXED_TABLES:
                fixed += charge
            elif table in STANDING_BASE:
                base += charge
            else:
                bucket = finite if table in FINITE_TABLES else standing
                bucket[item[0]] = bucket.get(item[0],0) + charge
    need(metadata <= 16*1024 and fixed <= FIXED_LIMIT-16*1024 and base <= STANDING_BASE_LIMIT)
    fixed += metadata
    need(len(finite) <= MAX_OWNERS and len(standing) <= MAX_OWNERS)
    need(all(n <= FINITE_OWNER_LIMIT for n in finite.values()))
    need(all(n <= STANDING_OWNER_LIMIT for n in standing.values()))
    # Partitions are hard ceilings independent of live count: unused reserved
    # bytes never become ordinary capacity available to another writer family.
    need(fixed+base+sum(finite.values())+sum(standing.values()) <= MAX_LOGICAL)
    if 'events' in tables:
        need(all(row[0] <= 24 for row in db.execute('SELECT count(*) FROM events GROUP BY operation_id')))
    if 'replay_keys' in tables:
        need(all(row[0] <= 1 for row in db.execute('SELECT count(*) FROM replay_keys GROUP BY operation_id')))
    if 'resource_owners' in tables:
        need(all(row[1] <= 16 for row in db.execute('SELECT kind,count(*) FROM resource_owners GROUP BY kind')))
    return {'chargedLogicalBytes':fixed+base+sum(finite.values())+sum(standing.values()),
            'fixedBytes':fixed,'standingBaseBytes':base,'finiteOwners':finite,'standingOwners':standing,
            'maxLogicalBytes':MAX_LOGICAL,'protectedCapacity':False}
