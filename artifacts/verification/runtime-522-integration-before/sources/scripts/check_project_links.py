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
        ROOT/'integration/harness/revalidation-a1626788/README.md',
        ROOT/'integration/harness/installed-support/README.md', ROOT/'integration/harness/multi-adapter/README.md',
        ROOT/'integration/harness/procedure-design/README.md',
        ROOT/'artifacts/verification/avr-clock-review/README.md',
        ROOT/'artifacts/verification/pat-catalog-review/README.md',
        ROOT/'artifacts/verification/pat-execution-review/README.md',
        ROOT/'artifacts/verification/runtime-424-diagnosis/README.md',
        ROOT/'artifacts/verification/runtime-availability-diagnosis/README.md',
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
