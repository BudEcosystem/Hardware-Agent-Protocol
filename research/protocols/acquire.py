#!/usr/bin/env python3
"""Acquire the protocol research corpus without representing downloads as reading."""
from pathlib import Path
import concurrent.futures, datetime, hashlib, json, subprocess
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parent
SOURCES={
 'wot-td11':'https://www.w3.org/TR/2023/REC-wot-thing-description11-20231205/',
 'wot-architecture11':'https://www.w3.org/TR/2023/REC-wot-architecture11-20231205/',
 'wot-discovery':'https://www.w3.org/TR/2023/REC-wot-discovery-20231205/',
 'opcua-overview':'https://reference.opcfoundation.org/specs/OPC-10000-1/4.2',
 'ros2-qos':'https://raw.githubusercontent.com/ros2/ros2_documentation/rolling/source/Concepts/Intermediate/About-Quality-of-Service-Settings.rst',
 'ros2-actions':'https://design.ros2.org/articles/actions.html',
 'micro-ros-features':'https://micro.vulcanexus.org/docs/overview/features/',
 'micro-ros-rtos':'https://micro.vulcanexus.org/docs/overview/rtos/',
 'micro-ros-executor':'https://micro.vulcanexus.org/docs/concepts/client_library/execution_management/',
 'mqtt5':'https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html',
 'sparkplug3':'https://www.eclipse.org/tahu/spec/sparkplug_spec.pdf',
 'matter15':'https://csa-iot.org/newsroom/matter-1-5-introduces-cameras-closures-and-enhanced-energy-management-capabilities/',
 'zephyr-shell':'https://docs.zephyrproject.org/latest/services/shell/index.html',
 'coap-rfc7252':'https://www.rfc-editor.org/rfc/rfc7252.txt',
 'lwm2m-core12':'https://www.openmobilealliance.org/release/LightweightM2M/V1_2-20201110-A/OMA-TS-LightweightM2M_Core-V1_2-20201110-A.pdf',
}
def fetch(item):
 key,url=item
 entry={'id':key,'url':url,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reading_status':'not_read'}
 try:
  r=requests.get(url,timeout=60)
  entry.update(http_status=r.status_code, final_url=r.url)
  r.raise_for_status()
  suffix='.pdf' if r.content[:4]==b'%PDF' else '.html' if '<html' in r.text[:1000].lower() or '<!doctype' in r.text[:1000].lower() else '.txt'
  raw=ROOT/'raw'/f'{key}{suffix}';raw.write_bytes(r.content)
  entry.update(raw_path=str(raw.relative_to(ROOT)),sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content))
  txt=ROOT/'text'/f'{key}.txt'
  if suffix=='.pdf': subprocess.run(['pdftotext','-layout',str(raw),str(txt)],check=True)
  elif suffix=='.html':
   soup=BeautifulSoup(r.content,'html.parser')
   for x in soup(['script','style','nav','header','footer']):x.decompose()
   content=soup.find('main') or soup.find('article') or soup
   txt.write_text(content.get_text('\n',strip=True))
  else:txt.write_bytes(r.content)
  entry.update(text_path=str(txt.relative_to(ROOT)),text_sha256=hashlib.sha256(txt.read_bytes()).hexdigest(),text_chars=len(txt.read_text()))
  entry['status']='acquired'
 except Exception as e:entry.update(status='failed',error=str(e))
 return entry
if __name__=='__main__':
 if (ROOT/'manifest.json').exists(): raise SystemExit('Existing corpus snapshot: refusing to overwrite reading records. Import fetch() for new entries and append explicitly.')
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: entries=list(pool.map(fetch,SOURCES.items()))
 (ROOT/'manifest.json').write_text(json.dumps({'sources':entries,'note':'Status tracks acquisition and actual reading separately. Mutable sources are timestamped; repository commits are recorded separately.'},indent=2)+'\n')
 for e in entries:print(e['id'],e['status'],e.get('text_chars',''),e.get('error',''))
