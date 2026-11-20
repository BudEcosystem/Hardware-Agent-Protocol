"""Prepare exact bounded follow-up acquisitions; no project imports."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path('artifacts/implementation/pat-io-conflict-history'); prior=BASE/'results/attempt01/acquire.py'
before=prior.read_text()
for number,harness,count,runtime,attempt,pin,target in [
    ('02','02',48,9,'attempt02-conflict48','4b717fa60a5a9592de1ee6e952c4ffb8c38c34e5579ff881d0e74d93b74cfc1a','083ba21385798a11695c84f9a9f34258ec54b045fc7806438ffd0536b5879cb0'),
    ('03','03',4,4,'attempt03-legacy4','ad97585d532ed6cdd9a1d3b2ee71f5af1b483f4b2fc7ae4ea839abca44117444','9d03a9e7089749c44851edd784aa57ca0cc31046cff0598d7158b3dbcd0a21c5')]:
    out=BASE/('results/attempt'+number); out.mkdir(exist_ok=False)
    after=before.replace('terminal conflict52','terminal conflict'+str(count))
    after=after.replace('harness01/attempts/attempt01-conflict52','harness'+harness+'/attempts/'+attempt)
    after=after.replace("OUT=BASE/'results/attempt01'","OUT=BASE/'results/attempt"+number+"'")
    after=after.replace("BASE/'harness01'","BASE/'harness"+harness+"'")
    after=after.replace('1874885a7b2c42dd8a721505f16fb36a619cc8b7d6afcaee04ef56ae61569ac5',pin)
    after=after.replace('a7dbc697f01b13f86ffbf56fe68066bb348a8f08ed7501a62574d2797366bb65',target)
    after=after.replace("result['counts']['testsRun']==52","result['counts']['testsRun']=="+str(count))
    after=after.replace('len(set(targets))==52','len(set(targets))=='+str(count))
    after=after.replace('Ran 52 tests','Ran '+str(count)+' tests').replace('testsRun=52,','testsRun='+str(count)+',')
    start=after.index('assert not passed and result'); end=after.index('runtime=[t',start)
    after=after[:start]+"assert passed and sum(r['bytes'] for r in raw_rows)<=16*1024*1024\nassert raw_rows==inventory(SOURCE/'scratch')==read(SOURCE/'scratch-index.json')\n"+after[end:]
    after=after.replace('assert len(runtime)==13','assert len(runtime)=='+str(runtime))
    after=after.replace('retained=raw/method','retained=SOURCE/\'scratch\'/method')
    after=after.replace('len(actual_connections)==26','len(actual_connections)=='+str(2*runtime))
    after=after.replace('exactDatabasePathsChecked=26','exactDatabasePathsChecked='+str(2*runtime))
    after=after.replace('if passed:\n    attacks=', 'if passed and '+str(count==48)+':\n    attacks=')
    scope=('48 selected tests:39 inherited pure transcript methods and nine new conflict/replay captures' if count==48 else 'Four unchanged configured runtime tests:GPIO,PWM,reopen and sixteen-step capture')
    after=after.replace('Actual52 selected tests:39 inherited pure transcript tests, four inherited runtime cases and nine new conflict/replay captures.',scope+'.')
    after=after.replace('rawScratchCopied=False,rawScratchHashInventoryRetained=True,retentionLimitExceeded=True,',
        'rawScratchCopied=True,rawScratchHashInventoryRetained=True,retentionLimitExceeded=False,')
    ast.parse(after); (out/'acquire.py').write_text(after)
    (out/'acquire.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str(prior),tofile=str(out/'acquire.py'))))
    print(json.dumps(dict(result=number,tests=count,sha256=hashlib.sha256(after.encode()).hexdigest())))
