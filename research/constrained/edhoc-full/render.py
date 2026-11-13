#!/usr/bin/env python3
"""Reproduce selected PDF views as data; this grants no reading credit."""
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
PAGES = (6, 8, 10, 11, 16, 20, 26, 35, 36, 37, 38, 49, 50, 51,
         52, 53, 55, 62, 63, 65, 66, 68, 69, 79, 81)

if __name__ == "__main__":
    source = BASE / "raw/rfc9528-pdf.pdf"
    subprocess.run(["pdftotext", "-layout", str(source),
                    str(BASE / "text/rfc9528-pdf-layout.txt")], check=True)
    for page in PAGES:
        subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page),
                        "-singlefile", "-scale-to", "1500", "-png", str(source),
                        str(BASE / f"figures/rfc9528-page-{page:02d}")], check=True)
    print("Rendered 25 selected pages; visual review remains a reader assertion.")
