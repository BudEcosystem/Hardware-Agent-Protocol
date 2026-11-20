"""Read-only evidence checks followed by exclusive stage inventory creation."""
import ast
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "research/host-contract/littlefs-core"
ATTEMPT = HERE / "attempt01"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text())


def inventory(base):
    rows = []
    for p in sorted(base.rglob("*")):
        assert not p.is_symlink(), p
        if p.is_file() and p != base / "index.json":
            rows.append({"path": str(p.relative_to(base)), "bytes": p.stat().st_size, "sha256": sha(p)})
    return rows


def save(path, data):
    with path.open("x") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def old_seal(relative, expected):
    base = ROOT / relative
    assert sha(base / "index.json") == expected
    rows = read(base / "index.json")["files"]
    assert rows == inventory(base)
    return {"path": relative, "sha256": expected, "verifiedFiles": len(rows)}


def main():
    assert not (HERE / "AUDIT.json").exists()
    assert not (HERE / "index.json").exists()
    assert not (SOURCE / "index.json").exists()
    prior = [old_seal("artifacts/implementation/fixed-block-storage",
                      "f294c785dbe9d966e06a1c3b6b88dc5e14850027c39293fc9afda1cb67611972"),
             old_seal("research/host-contract/fixed-block-storage",
                      "b6fb69fe4bc77b8184e6e426093c1d9cae7292ee055238f2eddf73ab78144467")]
    acq = read(SOURCE / "acquisition.json")
    assert acq["archiveSha256"] == sha(SOURCE / "littlefs.tar.gz")
    assert acq["archiveBytes"] == (SOURCE / "littlefs.tar.gz").stat().st_size == 280264
    assert len(acq["files"]) == 69
    expected = []
    for row in acq["files"]:
        p = SOURCE / "repo" / row["path"]
        assert p.read_bytes().count(b"\n") == row["lfLines"]
        expected.append({k: row[k] for k in ["path", "bytes", "sha256"]})
    assert sorted(expected, key=lambda r: r["path"]) == inventory(SOURCE / "repo")
    assert sum(row["bytes"] for row in expected) == acq["expandedBytes"] == 1896639
    coverage = read(SOURCE / "reading-coverage.json")
    assert len(coverage["files"]) == 11 and len(coverage["remainingUnreadFiles"]) == 58
    assert sum(r["lfLines"] for r in coverage["files"]) == 12041
    assert sum(r["lfLines"] for r in coverage["files"] if r["readStage"] == 83) == 11674
    selected = set()
    for row in coverage["files"]:
        assert row["path"] not in selected
        selected.add(row["path"])
        original = next(r for r in acq["files"] if r["path"] == row["path"])
        assert all(row[k] == original[k] for k in original)
        cursor = 1
        for start, stop in row["ranges"]:
            assert start == cursor and stop >= start
            cursor = stop+1
        assert cursor == row["lfLines"]+1
    assert set(r["path"] for r in coverage["remainingUnreadFiles"]) == set(r["path"] for r in acq["files"]) - selected
    for name in ["README.md", "LICENSE.md"]:
        assert (SOURCE / "repo" / name).read_bytes() == (ROOT / "research/host-contract/fixed-block-storage/littlefs" / name).read_bytes()
    for row in read(SOURCE / "assets/acquisition.json"):
        p = SOURCE / "assets" / row["path"]
        assert sha(p) == row["sha256"] and p.stat().st_size == row["bytes"]
    for row in read(SOURCE / "assets/renders.json")["files"]:
        assert sha(SOURCE / "assets" / row["render"]) == row["sha256"]

    receipt = read(ATTEMPT / "observations.json")
    assert receipt["status"] == "observed" and receipt["inputsStable"] is True
    assert all(receipt[k] is False for k in ["hardwareTested", "sqliteTested", "physicalPowerLossTested", "serviceStorageQualified"])
    inputs = read(ATTEMPT / "inputs.json")
    assert len(inputs["files"]) == 9
    for row in inputs["files"]:
        assert sha(ROOT / row["path"]) == sha(ATTEMPT / "frozen-inputs" / row["frozen"]) == row["sha256"]
    assert sha(Path(inputs["compiler"])) == inputs["compilerSha256"]
    assert sha(ATTEMPT / "probe") == receipt["binarySha256"]
    terminal = []
    for name in ["compiler-version", "build", "prefix", "tail", "handles", "unmount"]:
        scope = ATTEMPT / name
        result = read(scope / "result.json")
        intent = read(scope / "intent.json")
        started = read(scope / "started.json")
        assert result["returnCode"] == 0 and not result["timedOut"] and result["reaped"]
        assert result["elapsedSeconds"] < intent["wallSeconds"]
        assert not Path(f"/proc/{started['pid']}").exists()
        assert (scope / "stderr.txt").stat().st_size == 0
        if name in receipt["observations"]:
            assert read(scope / "stdout.txt") == receipt["observations"][name]
        terminal.append({"scope": name, "pid": started["pid"], "absentAtAudit": True,
                         "elapsedSeconds": result["elapsedSeconds"]})
    assert (ATTEMPT / "posix-comparison.bin").read_bytes() == b"B"*16
    assert receipt["posixComparison"] == {"bytes": 16, "existingHandleByte": 66, "sameView": True}
    for row in receipt["images"]:
        p = ATTEMPT / row["path"]
        assert p.stat().st_size == row["bytes"] == 2097152 and sha(p) == row["sha256"]
    assert len(receipt["images"]) == 4
    runtime = ROOT / "artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json"
    assert sha(runtime) == "dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e"
    rows = read(runtime)["files"]
    assert len(rows) == 244 and all(sha(ROOT / r["path"]) == r["sha256"] for r in rows)

    documents = [ROOT / p for p in ["README.md", "PROGRESS.md", "docs/control-storage.md", "docs/io-driver-hub-control.md"]]
    documents += sorted(HERE.glob("*.md")) + sorted(SOURCE.glob("*.md"))
    links = 0
    missing = []
    planned = {HERE / "AUDIT.json", HERE / "index.json", SOURCE / "index.json"}
    for doc in documents:
        for dest in re.findall(r"\]\(([^)]+)\)", doc.read_text()):
            if "://" in dest or dest.startswith(("#", "mailto:")):
                continue
            dest = unquote(dest.split("#", 1)[0].split(" \"", 1)[0].strip("<>"))
            if not dest:
                continue
            target = (doc.parent / dest).resolve()
            links += 1
            if not target.exists() and target not in planned:
                missing.append({"document": str(doc.relative_to(ROOT)), "target": dest})
    assert not missing, missing
    ast.parse((HERE / "run_probe.py").read_text())
    ast.parse(Path(__file__).read_text())
    source_rows = inventory(SOURCE)
    save(SOURCE / "index.json", {"schema": "hms.exact-file-index/1", "files": source_rows})
    audit = {"schema": "hms.littlefs-semantic-audit/1", "auditedUnix": time.time(),
             "reviewer": "primary agent only", "priorSeals": prior,
             "researchIndexSha256": sha(SOURCE / "index.json"), "researchIndexedFiles": len(source_rows),
             "acquiredFilesExact": 69, "fullyReadFiles": 11, "fullyReadLfLines": 12041,
             "newlyReadLfLines": 11674, "remainingUnreadFiles": 58, "frozenInputsExact": 9,
             "scopes": terminal, "semanticScopesCompleted": 4, "posixComparisonVerified": True,
             "imagesVerified": receipt["images"], "publicRuntimeFilesExact": 244,
             "existingPublicTestsPassed": 866, "publicSuiteRerun": False,
             "documentsChecked": len(documents), "localLinksChecked": links, "missingLinks": [],
             "documents": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in documents],
             "filesystemIntegrated": False, "sqliteTested": False, "physicalPowerLossTested": False,
             "serviceStorageQualified": False, "backedControlCapacity": False, "totalDiskQuotaEnforced": False}
    save(HERE / "AUDIT.json", audit)
    stage_rows = inventory(HERE)
    assert sum(r["bytes"] for r in stage_rows) < 256*1024**2
    assert max(r["bytes"] for r in stage_rows) <= 16*1024**2
    save(HERE / "index.json", {"schema": "hms.exact-file-index/1", "files": stage_rows})
    assert read(HERE / "index.json")["files"] == inventory(HERE)
    assert read(SOURCE / "index.json")["files"] == inventory(SOURCE)
    print(json.dumps({"stageIndexSha256": sha(HERE / "index.json"), "stageIndexedFiles": len(stage_rows),
                      "researchIndexSha256": sha(SOURCE / "index.json"), "researchIndexedFiles": len(source_rows),
                      "documentsChecked": len(documents), "localLinksChecked": links,
                      "publicRuntimeFilesExact": 244, "semanticScopesCompleted": 4}, sort_keys=True))


if __name__ == "__main__":
    main()
