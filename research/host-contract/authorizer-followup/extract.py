"""Extract every meaningful body block after SQLite's API keyword marker."""
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import textwrap
from urllib.parse import urljoin

HERE = Path(__file__).resolve().parent


class Body(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.buffer, self.links, self.images = [], [], [], []
        self.pre = False

    def flush(self):
        raw = "".join(self.buffer)
        self.buffer = []
        text = raw.strip("\n") if self.pre else " ".join(raw.split())
        if text.strip():
            self.blocks.append(text if self.pre else textwrap.fill(text, 100, break_long_words=False))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"p", "h2", "h3", "li", "blockquote", "pre"}:
            self.flush()
        if tag == "pre":
            self.pre = True
        if tag == "li":
            self.buffer.append("- ")
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
        if tag == "img":
            self.images.append(attrs)

    def handle_endtag(self, tag):
        if tag in {"p", "h2", "h3", "li", "blockquote", "pre"}:
            self.flush()
        if tag == "pre":
            self.pre = False

    def handle_data(self, data):
        self.buffer.append(data)


if __name__ == "__main__":
    output = HERE / "text"
    output.mkdir()
    rows = []
    for source in json.loads((HERE / "acquisition.json").read_text())["sources"]:
        raw = (HERE / "raw" / (source["id"] + ".html")).read_text()
        start = raw.index("<!-- keywords:")
        start = raw.index("-->", start) + 3
        parser = Body()
        parser.feed(raw[start:])
        parser.flush()
        text = "\n\n".join(parser.blocks).strip() + "\n"
        path = output / (source["id"] + ".txt")
        path.write_text(text)
        rows.append({"id": source["id"], "rawSha256": source["sha256"],
            "textPath": str(path.relative_to(HERE)), "bytes": len(text.encode()),
            "sha256": hashlib.sha256(text.encode()).hexdigest(), "lfLines": text.count("\n"),
            "scope": "Complete API body through final See also links; site navigation and non-executed scripts excluded.",
            "bodyImages": parser.images,
            "linksNotAcquiredOrReadByThisLane": sorted({urljoin(source["finalUrl"], url) for url in parser.links})})
    (HERE / "extraction.json").write_text(json.dumps({"schema": "hms-body-extraction/1", "sources": rows}, indent=2) + "\n")
    print(json.dumps([{key: row[key] for key in ("id", "lfLines", "sha256")} for row in rows]))
