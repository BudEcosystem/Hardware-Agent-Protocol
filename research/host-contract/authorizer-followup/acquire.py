"""Bounded acquisition of two official static documentation pages; no JS execution."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
LIMIT = 1024 * 1024
PAGES = {"set_authorizer": "https://www.sqlite.org/c3ref/set_authorizer.html",
         "action_codes": "https://www.sqlite.org/c3ref/c_alter_table.html"}


def acquire(item):
    name, url = item
    request = Request(url, headers={"User-Agent": "HMS-primary-documentation-research/1", "Accept-Encoding": "identity"})
    started = datetime.now(timezone.utc).isoformat()
    with urlopen(request, timeout=20) as response:
        final = response.geturl()
        if urlparse(final).scheme != "https" or urlparse(final).hostname not in {"www.sqlite.org", "sqlite.org"}:
            raise ValueError("unexpected acquisition destination")
        data = response.read(LIMIT + 1)
        record = {"id": name, "requestedUrl": url, "finalUrl": final, "startedUtc": started,
            "completedUtc": datetime.now(timezone.utc).isoformat(), "status": response.status,
            "headers": dict(response.headers.items()), "maximumBytes": LIMIT,
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "complete": len(data) <= LIMIT, "scope": "Raw page acquisition only; reading recorded separately."}
    with (HERE / "raw" / (name + ".html")).open("xb") as stream:
        stream.write(data)
    (HERE / "metadata" / (name + ".json")).write_text(json.dumps(record, indent=2) + "\n")
    if not record["complete"]:
        raise ValueError("page exceeded acquisition limit; bounded prefix retained")
    return record


if __name__ == "__main__":
    (HERE / "raw").mkdir()
    (HERE / "metadata").mkdir()
    with ThreadPoolExecutor(max_workers=2) as executor:
        records = list(executor.map(acquire, PAGES.items()))
    (HERE / "acquisition.json").write_text(json.dumps({"schema": "hms-primary-page-acquisition/1",
        "browserVerification": "Official URLs opened with the web tool before local acquisition.",
        "sources": records}, indent=2) + "\n")
    print(json.dumps([{key: row[key] for key in ("id", "status", "bytes", "sha256")} for row in records]))
