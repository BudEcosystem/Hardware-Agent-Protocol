"""Reproduce the retained serialized-size observation using only JSON and arithmetic."""
import base64
import hashlib
import json
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
DATASET_SHA='475f09d59534a09b6094707def7112709c050548b958b776362bf0ce86ee0a46'


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')


def encoded_metadata_bytes(identity,size,bitmap_bytes):
    body=dict(id=identity,kind='file',size=size,chunks=base64.b64encode(bytes(bitmap_bytes)).decode('ascii'))
    envelope=dict(body=body,sha256=hashlib.sha256(canonical(body)).hexdigest())
    return len(canonical(envelope))


def calculate(dataset,dataset_sha):
    files=dataset['files'];directories=dataset['directories']
    assert len(files)==4270 and len(directories)==169
    assert len({row['path'] for row in files})==len(files) and len(set(directories))==len(directories)
    assert all(type(row['bytes']) is int and 0<=row['bytes']<=16*1024**2 for row in files)
    assert sum(row['bytes'] for row in files)==35508922
    classes=dict(empty=0,oneTo4096=0,**{'4097To16384':0,'16385To65536':0,'above65536':0})
    current=[];hypothetical=[];chunks_total=0
    for ordinal,row in enumerate(files):
        size=row['bytes']
        # Root is inode 1. The original complete writer creates all directories
        # before creating file inodes in exactly the dataset order.
        identity=2+len(directories)+ordinal
        chunks=(size+4095)//4096;chunks_total+=chunks
        bitmap_bytes=(chunks+7)//8
        assert 0<=bitmap_bytes<=512
        current.append(encoded_metadata_bytes(identity,size,512))
        hypothetical.append(encoded_metadata_bytes(identity,size,bitmap_bytes))
        key=('empty' if size==0 else 'oneTo4096' if size<=4096 else
             '4097To16384' if size<=16384 else '16385To65536' if size<=65536 else 'above65536')
        classes[key]+=1
    return dict(schema='hms.storage-shape-observation/0.1',datasetSha256=dataset_sha,
        files=len(files),directories=len(directories),payloadBytes=sum(row['bytes'] for row in files),
        maximumFileBytes=max(row['bytes'] for row in files),dataChunksAt4096=chunks_total,logicalSizeClasses=classes,
        currentFullBitmapMetadata=dict(bitmapBytes=512,minEncodedBytes=min(current),maxEncodedBytes=max(current),
            within512Bytes=sum(size<=512 for size in current)),
        hypotheticalBitmapSizedToDeclaredFile=dict(minEncodedBytes=min(hypothetical),maxEncodedBytes=max(hypothetical),
            within512Bytes=sum(size<=512 for size in hypothetical),outside512Bytes=sum(size>512 for size in hypothetical)),
        limitations=[
            'Pure serialized-size calculation; no new storage implementation or performance measurement.',
            'Bitmap content does not affect base64 length; zero bytes are used solely for size calculation.',
            'Final file sizes and sequential IDs assume the original successful complete writer order.',
            'Shrinking, sparse bits, extension, recovery and profile migration are not established by this calculation.',
            'The existing disk format still requires exactly 512 bitmap bytes; no current validation may be weakened.'])


def main():
    source=Path(__file__).resolve();script_sha=digest(source)
    dataset_path=HERE/'attempt01/frozen-inputs/dataset.json';dataset_sha=digest(dataset_path)
    assert dataset_sha==DATASET_SHA
    dataset=json.loads(dataset_path.read_text())
    observation_path=HERE/'dataset-shape.json';observation_sha=digest(observation_path)
    observed=json.loads(observation_path.read_text())
    computed=calculate(dataset,dataset_sha)
    assert computed==observed
    assert digest(source)==script_sha and digest(dataset_path)==dataset_sha and digest(observation_path)==observation_sha
    receipt=dict(schema='hms.storage-shape-verification/0.1',matchesRetainedObservation=True,
        scriptSha256=script_sha,datasetSha256=dataset_sha,observationSha256=observation_sha,
        files=computed['files'],directories=computed['directories'],metadataOnly=True,
        storageImplementationImported=False,storageImagesOpened=False,newStorageFormatImplemented=False)
    with (HERE/'shape-verification.json').open('x') as stream:
        json.dump(receipt,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps(receipt,sort_keys=True),flush=True)


if __name__=='__main__':main()
