"""Unexecuted grammar proposal; install only after the preserved before regression."""
import re


def _validate_record(record, request, result):
    """Bounded retained control consistency, not producer authentication."""
    def checked(ok):
        require(ok, 'QUALIFICATION_LEDGER_INVALID')
    def closed(value, keys):
        checked(type(value) is dict and set(value) == set(keys))
    def number(value, low, high):
        checked(type(value) is int and low <= value <= high)
    def fingerprint(value):
        checked(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value) is not None)
    def reason(value):
        checked(value is None or type(value) is str and re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', value) is not None)
    closed(record, {'attemptId','state','requestDigest','lease','pid','reason','archive','history'})
    checked(type(record['attemptId']) is str and re.fullmatch(r'[0-9a-f]{32}', record['attemptId']) is not None)
    fingerprint(record['requestDigest'])
    checked(type(record['state']) is str and record['state'] in TRANSITIONS)
    history = record['history']
    checked(type(history) is list and 1 <= len(history) <= 6)
    checked(all(type(state) is str and state in TRANSITIONS for state in history))
    checked(history[0] == 'admitted' and history[-1] == record['state'])
    checked(all(after in TRANSITIONS[before] for before,after in zip(history,history[1:])))
    reason(record['reason'])
    lease = record['lease']
    checked((lease is not None) == ('launching' in history))
    if lease is not None:
        closed(lease, {'device','inode'})
        for value in lease.values():
            checked(type(value) is str and re.fullmatch(r'0|[1-9][0-9]{0,19}',value) is not None)
            checked(int(value) <= 2**64-1)
    checked((record['pid'] is not None) == ('running' in history))
    if record['pid'] is not None: number(record['pid'],1,2**31-1)
    archive = record['archive']
    checked((archive is not None) == (record['state'] == 'archived'))
    if archive is None:
        checked(result is None)
        return
    closed(archive, {'exitCode','ownerRecovered','supervisorReason','returnValidationFailure','evidenceIntegrity','usage',
        'transportComplete','semanticQualificationVerified','totalDiskQuotaEnforced','unresolvedEffects','returnDigest'})
    checked(type(archive['ownerRecovered']) is bool and type(archive['transportComplete']) is bool)
    checked(archive['semanticQualificationVerified'] is False and archive['totalDiskQuotaEnforced'] is False and
            archive['unresolvedEffects'] is None)
    reason(archive['supervisorReason']);reason(archive['returnValidationFailure'])
    if archive['exitCode'] is not None: number(archive['exitCode'],-128,255)
    else: checked(archive['ownerRecovered'] is True)
    if archive['ownerRecovered'] is False: checked('running' in history)
    checked(archive['returnDigest'] == (digest(result) if result is not None else None))
    if archive['returnDigest'] is not None:
        fingerprint(archive['returnDigest']);checked(lease is not None)
    integrity = archive['evidenceIntegrity'];usage = archive['usage']
    if integrity is not None:
        closed(integrity, {'recordCount','bytes','orderedDigest'})
        number(integrity['recordCount'],1,4096)
        number(integrity['bytes'],1,request['trust']['input']['limits']['maxOutputBytes'])
        fingerprint(integrity['orderedDigest'])
        checked(type(result) is bytes and len(result) > 0)
    if usage is not None:
        closed(usage, {'files','logicalBytes','totalDiskQuotaEnforced'})
        number(usage['files'],0,request['limits']['maxFilesPerAttempt'])
        number(usage['logicalBytes'],0,request['limits']['attemptReservationBytes'])
        checked(usage['totalDiskQuotaEnforced'] is False)
    transport = (archive['exitCode'] == 0 and archive['ownerRecovered'] is False and
        archive['supervisorReason'] is None and archive['returnValidationFailure'] is None and
        integrity is not None and usage is not None and type(result) is bytes and len(result) > 0)
    checked(archive['transportComplete'] is transport)
