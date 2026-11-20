"""Finite, single-attempt host-RAM semantic observations; no deployment effects."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPO = ROOT / "research/host-contract/littlefs-core/repo"
BASE = ROOT / "artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json"
BASE_HASH = "dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e"
ATTEMPT = HERE / "attempt01"
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8") as out:
        json.dump(value, out, indent=2, sort_keys=True)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())


def baseline():
    if digest(BASE) != BASE_HASH:
        raise ValueError("baseline receipt changed")
    rows = json.loads(BASE.read_text())["files"]
    if len(rows) != 244 or len({row["path"] for row in rows}) != 244:
        raise ValueError("baseline inventory changed")
    changed = [row["path"] for row in rows if digest(ROOT / row["path"]) != row["sha256"]]
    if changed:
        raise ValueError(f"public inputs changed: {changed}")
    return {"receiptSha256": BASE_HASH, "exactFiles": len(rows)}


def child_limits(cpu):
    os.umask(0o077)
    for key, limit in [(resource.RLIMIT_CPU, cpu), (resource.RLIMIT_AS, 512*1024**2),
                       (resource.RLIMIT_FSIZE, 16*1024**2), (resource.RLIMIT_NOFILE, 64),
                       (resource.RLIMIT_CORE, 0)]:
        resource.setrlimit(key, (limit, limit))


def run(name, argv, wall=20, cpu=10):
    scope = ATTEMPT / name
    scope.mkdir(mode=0o700)
    save(scope / "intent.json", {"argv": argv, "wallSeconds": wall, "cpuSeconds": cpu,
                                "cwd": str(scope), "environment": ENV})
    start = time.monotonic()
    with (scope / "stdout.txt").open("xb") as out, (scope / "stderr.txt").open("xb") as err:
        proc = subprocess.Popen(argv, cwd=scope, env=ENV, stdout=out, stderr=err,
                                start_new_session=True, preexec_fn=lambda: child_limits(cpu))
        save(scope / "started.json", {"pid": proc.pid, "processGroup": proc.pid,
                                     "startedUnix": time.time()})
        timed_out = False
        try:
            code = proc.wait(timeout=wall)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait(timeout=5)
        out.flush()
        err.flush()
        os.fsync(out.fileno())
        os.fsync(err.fileno())
    result = {"returnCode": code, "timedOut": timed_out,
              "elapsedSeconds": time.monotonic()-start, "reaped": True}
    save(scope / "result.json", result)
    if code != 0 or timed_out:
        raise RuntimeError(f"{name}: failed or inconclusive; retained, no retry")
    return scope


def main():
    os.umask(0o077)
    before = baseline()
    acquisition = json.loads((REPO.parent / "acquisition.json").read_text())
    if acquisition["archiveSha256"] != "4803faf6db6c60093558a315a10c50926d2cfa5668a3f03fa2523fd09b10b747":
        raise ValueError("unexpected source archive identity")
    if digest(REPO.parent / "littlefs.tar.gz") != acquisition["archiveSha256"]:
        raise ValueError("source archive changed")
    for row in acquisition["files"]:
        if digest(REPO / row["path"]) != row["sha256"]:
            raise ValueError("acquired source changed")
    ATTEMPT.mkdir(mode=0o700)
    compiler = Path("/usr/bin/cc").resolve(strict=True)
    source_paths = [HERE / name for name in ["PLAN.md", "REVIEW.md", "probe.c", "run_probe.py"]]
    source_paths += [REPO / name for name in ["lfs.c", "lfs.h", "lfs_util.c", "lfs_util.h", "LICENSE.md"]]
    frozen = ATTEMPT / "frozen-inputs"
    frozen.mkdir(mode=0o700)
    inputs = []
    for src in source_paths:
        dest = frozen / src.name
        data = src.read_bytes()
        with dest.open("xb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        inputs.append({"path": str(src.relative_to(ROOT)), "frozen": src.name,
                       "bytes": len(data), "sha256": digest(dest)})
    compiler_hash = digest(compiler)
    save(ATTEMPT / "inputs.json", {"files": inputs, "compiler": str(compiler),
                                  "compilerSha256": compiler_hash, "baselineBefore": before})
    report = {"schema": "hms.littlefs-semantics/1", "status": "incomplete",
              "observations": {}, "hardwareTested": False, "sqliteTested": False,
              "physicalPowerLossTested": False, "serviceStorageQualified": False}
    try:
        run("compiler-version", [str(compiler), "--version"], wall=30, cpu=20)
        binary = ATTEMPT / "probe"
        run("build", [str(compiler), "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                      "-DLFS_NO_MALLOC", "-DLFS_NO_DEBUG", "-DLFS_NO_WARN", "-DLFS_NO_ERROR",
                      "-I", str(frozen), str(frozen / "probe.c"), str(frozen / "lfs.c"),
                      str(frozen / "lfs_util.c"), "-o", str(binary)], wall=30, cpu=20)
        report["binarySha256"] = digest(binary)
        for name in ["prefix", "tail", "handles", "unmount"]:
            scope = run(name, [str(binary), name])
            raw = (scope / "stdout.txt").read_bytes()
            if len(raw) > 4096 or (scope / "stderr.txt").stat().st_size:
                raise ValueError("unexpected output")
            data = json.loads(raw)
            keys = {
                "prefix": {"scenario", "fileBytes", "changedBytes", "offset", "readCalls", "readBytes",
                           "programCalls", "programBytes", "erases", "syncCalls"},
                "handles": {"scenario", "existingHandleByte", "freshHandleByte", "sameView"},
                "unmount": {"scenario", "unmountSyncCalls", "reopenedByte", "pendingWriteVisible"}}
            expected = keys["prefix" if name == "tail" else name]
            if set(data) != expected or data["scenario"] != name:
                raise ValueError("unexpected observation shape")
            for key, val in data.items():
                if key == "scenario":
                    continue
                if key in {"sameView", "pendingWriteVisible"}:
                    if type(val) is not bool:
                        raise ValueError("unexpected boolean")
                elif type(val) is not int or not 0 <= val <= 2**40:
                    raise ValueError("unexpected count")
            image = scope / "image.bin"
            if image.stat().st_size != 2*1024**2:
                raise ValueError("unexpected image length")
            report["observations"][name] = data
            report.setdefault("images", []).append({"path": str(image.relative_to(ATTEMPT)),
                                                     "bytes": image.stat().st_size, "sha256": digest(image)})
        # Native local descriptor visibility comparison, isolated from all project databases.
        path = ATTEMPT / "posix-comparison.bin"
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        other = None
        try:
            if os.write(fd, b"A"*16) != 16:
                raise OSError("short initial write")
            os.fsync(fd)
            other = os.open(path, os.O_RDONLY)
            if os.pwrite(fd, b"B"*16, 0) != 16:
                raise OSError("short replacement write")
            os.fsync(fd)
            observed = os.pread(other, 16, 0)
            if observed != b"B"*16:
                raise ValueError("local descriptor visibility differs")
            report["posixComparison"] = {"bytes": 16, "existingHandleByte": observed[0], "sameView": True}
        finally:
            if other is not None:
                os.close(other)
            os.close(fd)
        for row in inputs:
            if digest(ROOT / row["path"]) != row["sha256"] or digest(frozen / row["frozen"]) != row["sha256"]:
                raise ValueError("probe input changed")
        if digest(compiler) != compiler_hash or digest(binary) != report["binarySha256"]:
            raise ValueError("compiler or binary changed")
        report["baselineAfter"] = baseline()
        files = [p for p in ATTEMPT.rglob("*") if p.is_file()]
        size = sum(p.stat().st_size for p in files)
        if size >= 256*1024**2 or any(p.stat().st_size > 16*1024**2 for p in files):
            raise ValueError("retained experiment exceeded bound")
        report["retainedBytesBeforeResult"] = size
        report["status"] = "observed"
        report["inputsStable"] = True
    except BaseException as exc:
        report["status"] = "failed-or-inconclusive"
        report["error"] = f"{type(exc).__name__}: {exc}"
        save(ATTEMPT / "observations.json", report)
        raise
    save(ATTEMPT / "observations.json", report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
