# Normalize borrowed validation exceptions

The first pure160 run has159passes and one error. A malformed boolean supervisor
limit is correctly refused, but the borrowed integer validator raises
`EvidenceError: PAT_EVIDENCE_INVALID`. The original exception adapter only wrapped
ordinary parsing exceptions, so the fan-specific exception escaped the new I/O
supervisor boundary. The test requires the supervisor's own refusal type.

Source02 adds `JournalError` to that adapter's wrapped exception tuple, after its
existing `SupervisorError` pass-through. Other borrowed evidence/PAT validation
errors now become `SupervisorError: QUALIFICATION_INVALID`; existing explicit
supervisor errors and their codes remain unchanged. No guard, bound or test is
weakened. All237project files except this one line remain byte-identical. The
complete failed run, original raw fixtures and acquired copy are retained.
The exact160pure methods and the actual process method will use fresh harnesses.
