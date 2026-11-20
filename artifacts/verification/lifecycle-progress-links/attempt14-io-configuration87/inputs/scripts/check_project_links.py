#!/usr/bin/env python3
"""Check selected project-authored Markdown paths, not upstream/network links."""
import datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = sorted(set([ROOT/'README.md', ROOT/'PROGRESS.md', *ROOT.glob('docs/*.md'),
        *ROOT.glob('spec/*.md'), ROOT/'research/PLAN.md', ROOT/'integration/harness/README.md',
        ROOT/'integration/harness/revalidation-335a82eb/README.md', ROOT/'protocol/serial/README.md',
        ROOT/'integration/harness/compact-endpoint/README.md', ROOT/'protocol/platform/README.md',
        ROOT/'research/constrained/clock-boot-platform/README.md',
        ROOT/'research/deployment/gb10-followup/README.md', ROOT/'research/constrained/edhoc-full/README.md',
        ROOT/'research/constrained/qblock-full/README.md',
        ROOT/'research/planning/README.md', ROOT/'research/planning/pat-learning/README.md',
        ROOT/'research/planning/pat-learning/notes/critique.md',
        ROOT/'research/planning/pat-learning/notes/figures.md',
        ROOT/'research/planning/lrll-full/README.md',
        ROOT/'research/planning/lrll-full/notes/critique.md',
        ROOT/'research/planning/lrll-full/notes/figures.md',
        ROOT/'research/host-contract/README.md',
        ROOT/'research/host-contract/authorizer-followup/NOTES.md',
        ROOT/'artifacts/verification/io-driver-hub-resource-design/DESIGN.md',
        ROOT/'schemas/README.md',
        ROOT/'artifacts/implementation/resource-topology/README.md',
        ROOT/'artifacts/implementation/resource-topology/DESIGN-ADDENDUM.md',
        ROOT/'artifacts/implementation/pat-simulation-evidence/README.md',
        ROOT/'artifacts/implementation/pat-evidence-fast-verification/README.md',
        ROOT/'artifacts/implementation/pat-evidence-fast-verification/ATTESTATION-ALTERNATIVE.md',
        ROOT/'artifacts/implementation/io-resource-admission/README.md',
        ROOT/'artifacts/verification/pat-evidence-live-integration/README.md',
        ROOT/'artifacts/verification/pat-memo-live-integration/README.md',
        ROOT/'artifacts/verification/resource-admission-live-integration/README.md',
        ROOT/'artifacts/verification/io-provider-current-integration/README.md',
        ROOT/'artifacts/verification/io-provider-live-integration/README.md',
        ROOT/'artifacts/verification/io-provider-runtime-integration/README.md',
        ROOT/'artifacts/verification/io-runtime-entry-review/README.md',
        ROOT/'artifacts/verification/io-response-contract-diagnosis/README.md',
        ROOT/'artifacts/verification/io-response-contract-resolution-review/README.md',
        ROOT/'artifacts/verification/io-transport-session-resolution/README.md',
        ROOT/'artifacts/verification/io-status-read-timeout-diagnosis/README.md',
        ROOT/'artifacts/verification/io-status-read-timeout-resolution/README.md',
        ROOT/'artifacts/verification/io-status-read-timeout-resolution-review/README.md',
        ROOT/'artifacts/verification/modbus-serial-full-read/README.md',
        ROOT/'artifacts/verification/modbus-serial-full-read/CRITIQUE.md',
        ROOT/'artifacts/verification/io-lifecycle-settlement-review/README.md',
        ROOT/'artifacts/verification/io-lifecycle-preliminary-review/01/README.md',
        ROOT/'artifacts/verification/io-lifecycle-preliminary-review/02/README.md',
        ROOT/'artifacts/verification/io-lifecycle-source-preparation-review/FINDINGS.md',
        ROOT/'artifacts/verification/io-lifecycle-harness-remediation-review/04/README.md',
        ROOT/'artifacts/verification/io-lifecycle-harness-remediation-review/05/README.md',
        ROOT/'artifacts/implementation/io-lifecycle-settlement/review-inputs/05/README.md',
        ROOT/'artifacts/implementation/io-lifecycle-settlement/review-inputs/05/ACCEPTANCE-PLAN.md',
        ROOT/'artifacts/implementation/io-lifecycle-settlement/review-inputs/05/HARNESS-REPRODUCTION-PLAN.md',
        ROOT/'artifacts/verification/io-pat-qualification-design/README.md',
        ROOT/'artifacts/verification/io-pat-qualification-design/DESIGN.md',
        ROOT/'artifacts/implementation/pat-fixed-schema-units/results/pure34-01/README.md',
        ROOT/'artifacts/implementation/pat-fixed-schema-units/supplements/01/ERRATUM.md',
        ROOT/'artifacts/implementation/pat-io-binding-resolver/implementation02/README.md',
        ROOT/'artifacts/implementation/pat-io-binding-resolver/results/focused-purity-01/README.md',
        ROOT/'artifacts/implementation/pat-io-binding-resolver/results/focused-purity-01/ERRATUM.md',
        ROOT/'artifacts/verification/io-lifecycle-boundary-results/attempt01-three-root-retention/README.md',
        ROOT/'artifacts/implementation/pat-io-timing-oracle-design/README.md',
        ROOT/'artifacts/implementation/pat-io-timing-oracle-design/DESIGN.md',
        ROOT/'artifacts/implementation/pat-io-timing-oracle-design/SOURCE-NOTES.md',
        ROOT/'artifacts/implementation/pat-io-timing/implementation01/README.md',
        ROOT/'artifacts/implementation/pat-io-timing/implementation02/README.md',
        ROOT/'artifacts/implementation/pat-io-timing/harness01/README.md',
        ROOT/'artifacts/implementation/pat-io-timing/harness01/SCOPE.md',
        ROOT/'artifacts/implementation/pat-io-timing/harness02/README.md',
        ROOT/'artifacts/implementation/pat-io-timing/harness02/SCOPE.md',
        ROOT/'artifacts/implementation/pat-io-timing/results/attempt01-failed65/README.md',
        ROOT/'artifacts/implementation/pat-io-timing/results/attempt02-passed65/README.md',
        ROOT/'artifacts/implementation/pat-io-trial-engine/implementation01/README.md',
        ROOT/'artifacts/implementation/pat-io-trial-engine/harness01/README.md',
        ROOT/'artifacts/implementation/pat-io-trial-engine/harness01/SCOPE.md',
        ROOT/'artifacts/implementation/pat-io-trial-engine/results/attempt01-passed20/README.md',
        ROOT/'artifacts/implementation/pat-io-transcript/implementation01/README.md',
        ROOT/'artifacts/implementation/pat-io-transcript/harness01/README.md',
        ROOT/'artifacts/implementation/pat-io-transcript/harness01/SCOPE.md',
        ROOT/'artifacts/implementation/pat-io-transcript/results/attempt01-passed39/README.md',
        ROOT/'artifacts/implementation/pat-io-board-history/implementation01/README.md',
        ROOT/'artifacts/implementation/pat-io-board-history/harness01/README.md',
        ROOT/'artifacts/implementation/pat-io-board-history/harness01/SCOPE.md',
        ROOT/'artifacts/implementation/pat-io-board-history/results/attempt01-passed74/README.md',
        ROOT/'artifacts/implementation/pat-io-operation-history/implementation01/README.md',
        ROOT/'artifacts/implementation/pat-io-operation-history/harness01/README.md',
        ROOT/'artifacts/implementation/pat-io-operation-history/harness01/SCOPE.md',
        ROOT/'artifacts/implementation/pat-io-operation-history/results/attempt01-passed112/README.md',
        ROOT/'artifacts/implementation/pat-io-procedure-history/implementation01/README.md',
        ROOT/'artifacts/implementation/pat-io-procedure-history/harness01/README.md',
        ROOT/'artifacts/implementation/pat-io-procedure-history/harness01/SCOPE.md',
        ROOT/'artifacts/implementation/pat-io-procedure-history/results/attempt01-passed146/README.md',
        ROOT/'artifacts/implementation/pat-io-correspondence/implementation01/README.md',
        ROOT/'artifacts/implementation/pat-io-correspondence/harness01/README.md',
        ROOT/'artifacts/implementation/pat-io-correspondence/harness01/SCOPE.md',
        ROOT/'artifacts/implementation/pat-io-correspondence/results/attempt01-passed41/README.md',
        ROOT/'artifacts/implementation/pat-io-configuration-capture/implementation01/README.md',
        ROOT/'artifacts/implementation/pat-io-configuration-capture/harness01/README.md',
        ROOT/'artifacts/implementation/pat-io-configuration-capture/harness01/SCOPE.md',
        ROOT/'artifacts/implementation/pat-io-configuration-capture/results/attempt01-passed32/README.md',
        ROOT/'artifacts/implementation/pat-io-configuration-history/implementation01/README.md',
        ROOT/'artifacts/implementation/pat-io-configuration-history/harness01/README.md',
        ROOT/'artifacts/implementation/pat-io-configuration-history/harness01/SCOPE.md',
        ROOT/'artifacts/implementation/pat-io-configuration-history/results/attempt01-failed87/README.md',
        ROOT/'artifacts/implementation/pat-io-configuration-history/implementation02/README.md',
        ROOT/'artifacts/implementation/pat-io-configuration-history/harness02/README.md',
        ROOT/'artifacts/implementation/pat-io-configuration-history/harness02/SCOPE.md',
        ROOT/'artifacts/implementation/pat-io-configuration-history/results/attempt02-passed87/README.md',
        ROOT/'artifacts/implementation/pat-qualification-supervisor/README.md',
        ROOT/'artifacts/verification/pat-supervisor-review/final/README.md',
        ROOT/'artifacts/verification/pat-supervisor-current-integration/README.md',
        ROOT/'artifacts/verification/pat-supervisor-current-integration/storage-design/ASSESSMENT.md',
        ROOT/'artifacts/implementation/io-synthetic-provider/README.md',
        ROOT/'artifacts/implementation/io-lifecycle-settlement-design/DESIGN.md',
        ROOT/'artifacts/implementation/io-lifecycle-settlement-design/AMENDMENT-01.md',
        ROOT/'artifacts/implementation/io-lifecycle-settlement-design/AMENDMENT-02.md',
        ROOT/'artifacts/verification/pat-bounded-evidence/README.md',
        ROOT/'artifacts/verification/pat-evaluation-integrity/README.md',
        ROOT/'artifacts/verification/pat-current-combined/README.md',
        ROOT/'artifacts/verification/resource-topology-integration/README.md',
        ROOT/'integration/harness/revalidation-a1626788/README.md',
        ROOT/'integration/harness/installed-support/README.md', ROOT/'integration/harness/multi-adapter/README.md',
        ROOT/'integration/harness/procedure-design/README.md',
        ROOT/'artifacts/verification/avr-clock-review/README.md',
        ROOT/'artifacts/verification/pat-catalog-review/README.md',
        ROOT/'artifacts/verification/pat-execution-review/README.md',
        ROOT/'artifacts/verification/pat-service-design/PLAN.md',
        ROOT/'artifacts/verification/pat-service-review/README.md',
        ROOT/'artifacts/implementation/pat-environment-extraction/README.md',
        ROOT/'artifacts/verification/runtime-424-diagnosis/README.md',
        ROOT/'artifacts/verification/runtime-availability-diagnosis/README.md',
        ROOT/'artifacts/verification/runtime-522-observer-diagnosis/README.md',
        ROOT/'artifacts/verification/endpoint-cli-failure-capture/README.md',
        ROOT/'artifacts/verification/endpoint-cli-observation-semantics/README.md',
        ROOT/'artifacts/verification/endpoint-cli-aged-observation/README.md',
        ROOT/'artifacts/verification/compact-availability-before/README.md',
        ROOT/'artifacts/verification/compact-admission-design/README.md',
        ROOT/'artifacts/verification/compact-admission-after/README.md',
        ROOT/'protocol/endpoint/README.md', ROOT/'research/mcp/README.md',
        ROOT/'research/microscopy-controller/README.md', ROOT/'research/constrained/README.md']))
    missing, checked = [], 0
    for path in paths:
        for match in re.finditer(r'\[[^\]\n]*\]\(([^)\n]+)\)', path.read_text()):
            target = match[1].strip().split(' "',1)[0].strip('<>')
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            checked += 1
            destination = (path.parent / unquote(parsed.path)).resolve()
            if not destination.exists():
                missing.append({'source':str(path.relative_to(ROOT)),'target':target})
    report = {'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'command':'python3 scripts/check_project_links.py',
        'scope':'Selected project-authored inline Markdown path links; not archived upstream links, anchors or remote URL availability',
        'project_markdown_files':len(paths),'local_links_checked':checked,'missing':missing,
        'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'files':[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}
    (ROOT/'artifacts/verification/project-links.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('project_markdown_files','local_links_checked','missing')}))
    if missing:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
