#!/usr/bin/env python3
"""Render selected official-PDF pages for visual corroboration."""
from pathlib import Path
import subprocess,json,re
BASE=Path(__file__).resolve().parent
pages=BASE.joinpath('text/rfc9177-pdf.txt').read_text().split('\f')
selected=[]
for number,page in enumerate(pages,1):
 labels=re.findall(r'\b(?:Figure|Table) \d+:.*',page)
 if labels:
  selected.append(dict(pdf_page=number,captions=labels))
  subprocess.run(['pdftoppm','-f',str(number),'-l',str(number),'-scale-to','1400','-png','-singlefile',str(BASE/'raw/rfc9177-pdf.pdf'),str(BASE/'figures'/f'rfc9177-page-{number:02}')],check=True)
(BASE/'notes/figure-inventory.json').write_text(json.dumps(selected,indent=2)+'\n')
print(json.dumps(selected,indent=2))
