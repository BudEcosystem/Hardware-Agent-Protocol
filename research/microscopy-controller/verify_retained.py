"""Verify retained research bytes and reading ranges without running acquired code."""
from pathlib import Path
import hashlib
import json
import subprocess


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest = json.loads((HERE / "manifest.json").read_text())
    for item in manifest["files"]:
        path = ROOT / item["path"]
        assert digest(path) == item["sha256"], item["path"]
        assert path.stat().st_size == item["bytes"], item["path"]

    acquisition = json.loads((HERE / "acquisition.json").read_text())
    for item in acquisition:
        if "path" in item:
            assert digest(ROOT / item["path"]) == item["sha256"], item["id"]

    pins = json.loads((HERE / "pins.json").read_text())
    repositories = {r["id"]: r for r in pins["repositories"]}
    for repo in repositories.values():
        path = ROOT / repo["retainedCheckout"]
        head = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        assert head == repo["verifiedCurrentHead"], repo["id"]
        assert not subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True).strip(), repo["id"]

    selected = json.loads((HERE / "selected-files.json").read_text())
    complete = partial_lines = complete_lines = 0
    for item in selected:
        path = ROOT / item["retainedPath"]
        assert digest(path) == item["sha256"], item["path"]
        assert len(path.read_bytes().splitlines()) == item["lines"], item["path"]
        repo = repositories[item["repository"]]
        assert item["commit"] == repo["verifiedCurrentHead"], item["path"]
        pinned = subprocess.check_output([
            "git", "-C", str(ROOT / repo["retainedCheckout"]),
            "show", item["commit"] + ":" + item["path"],
        ])
        assert pinned == path.read_bytes(), item["path"]
        ranges = item["readLineRangesInclusive"]
        previous_end = 0
        for start, end in ranges:
            assert previous_end < start <= end <= item["lines"], item["path"]
            previous_end = end
        if item["readingStatus"] == "full-file-read":
            assert ranges == [[1, item["lines"]]], item["path"]
            complete += 1
            complete_lines += item["lines"]
        else:
            partial_lines += sum(end - start + 1 for start, end in ranges)

    coverage = json.loads((HERE / "coverage.json").read_text())
    source = coverage["sourceFiles"]
    assert source["sha256"] == digest(HERE / "selected-files.json")
    assert (complete, complete_lines, partial_lines) == (
        source["completeFiles"], source["completeFileLines"], source["selectedCompleteFunctionLines"]
    )
    for document in coverage["documents"]:
        assert digest(ROOT / document["retainedPath"]) == document["sha256"], document["id"]
        if "textPath" in document:
            assert digest(ROOT / document["textPath"]) == document["textSha256"], document["id"]
        for figure in document.get("figures", []):
            assert digest(ROOT / figure["path"]) == figure["sha256"], figure["path"]

    report = {
        "status": "passed",
        "scope": "Retained-byte hashes, git pins, selected source byte equality and declared coverage counts; not independent proof of reading or hardware correctness",
        "retainedFilesVerified": len(manifest["files"]),
        "acquisitionRecordsVerified": len(acquisition),
        "repositoryPinsVerified": len(repositories),
        "selectedSourceFilesVerified": len(selected),
        "completeSourceFiles": complete,
        "completeSourceLines": complete_lines,
        "selectedCompleteFunctionLines": partial_lines,
        "acquiredCodeExecuted": False,
        "acquiredTestsExecuted": False,
        "deviceOrServiceContacted": False,
        "inputsSha256": {name: digest(HERE / name) for name in [
            "manifest.json", "acquisition.json", "pins.json", "selected-files.json",
            "coverage.json", "source-notes.md", "README.md", "verify_retained.py",
        ]},
        "bindingDocumentSha256": digest(ROOT / "docs/microscope-controller-binding.md"),
    }
    (HERE / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
