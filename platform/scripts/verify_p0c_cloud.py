"""Verify both P0-C archives and run isolated public recomputation on Linux."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import zipfile

root=Path('/root/autodl-tmp/agent-ex-p0c-delivery-20261029-v1')
expected={'p0c-public-results-v1.zip':'46b5c7c53b473efa59b8f01ed4ef5d5062cd284b00bb200e51aa9d8c01a16059',
          'p0c-private-evidence-v1.zip':'32b279b43268266141ea565e055b1ee2f895350d363b8ea7e4f613b1e0c5059a'}
proof=[]
for name,pin in expected.items():
    path=root/name;receipt=json.loads(path.with_suffix(path.suffix+'.receipt.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=pin or receipt['sha256']!=pin:
        raise ValueError('externally pinned archive differs')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None or set(z.namelist())!=set(receipt['members']) or len(z.namelist())!=len(receipt['members']):
            raise ValueError('archive CRC/exact cover differs')
        for member,entry in receipt['members'].items():
            data=z.read(member)
            if hashlib.sha256(data).hexdigest()!=entry['sha256'] or len(data)!=entry['bytes']:
                raise ValueError('archive member differs')
    proof.append(dict(name=name,sha256=pin,members=len(receipt['members']),whole_member_crc_passed=True))
public=root/'public-restored-v1';public.mkdir(exist_ok=False)
with zipfile.ZipFile(root/'p0c-public-results-v1.zip') as z:
    for name in z.namelist():
        target=public/name
        if not target.resolve().is_relative_to(public.resolve()):raise ValueError('unsafe member')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
completed=subprocess.run([sys.executable,'-B',str(public/'verify_public.py'),str(public),
    '--manifest-sha256','34f5e8b7ec00c77bfa32a594d2d5ede42beb204cc0a00ee6ed647882f6a78991'],
    check=True,capture_output=True,text=True)
numeric=json.loads(completed.stdout)
if not numeric['verified'] or numeric['events']!=1890000 or numeric['sampled_events']!=331:
    raise ValueError('public recomputation failed')
disk=os.statvfs(root);free=disk.f_bavail*disk.f_frsize
if free<2*1024**3+64*1024**2:raise ValueError('cloud free space below protected floor')
result=dict(schema='p0c.cloud.delivery.v1',passed=True,archives=proof,
    linux_public_recompute=numeric,cloud_free_bytes=free,model_calls=0,
    scientific_sources_unchanged='separate original read-only source proofs; no runtime/service changes')
path=root/'cloud-delivery-verification.json'
with path.open('x') as f:json.dump(result,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps(dict(passed=True,archives=proof,events=numeric['events'],sampled_events=numeric['sampled_events'],cloud_free_bytes=free)))
