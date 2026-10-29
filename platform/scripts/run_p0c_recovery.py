"""Explicit read-only SSH recovery CLI; all output is restricted to V drive.

numeric: emits seven missing T30 seeds, no model calls.
cases: reads a SHA-pinned public index and writes private actual-wire evidence.
Existing files are never overwritten. This is not an experiment launcher.
"""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('numeric','cases'));p.add_argument('output',type=Path)
    p.add_argument('--index',type=Path);p.add_argument('--index-sha256')
    args=p.parse_args()
    if args.output.drive.lower()!='v:' or args.output.exists():
        raise ValueError('new V output required; no overwrite or fallback')
    if not args.output.parent.is_dir():raise ValueError('output parent must already exist on V')
    source_path=Path(__file__).with_name('p0c_read_retirement.py' if args.phase=='numeric' else 'p0c_recover_sample.py')
    source=source_path.read_bytes();input_hash=None
    if args.phase=='cases':
        if args.index is None or args.index_sha256 is None:raise ValueError('cases require external index hash')
        raw=args.index.read_bytes();input_hash=hashlib.sha256(raw).hexdigest()
        if input_hash!=args.index_sha256:raise ValueError('index SHA differs; SSH not started')
        with args.index.open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
        source=('import json\nSAMPLES=json.loads('+repr(json.dumps(rows))+')\n').encode()+source
    command=['ssh','-p','46583','-i','C:/Users/Bai Yuexi/.ssh/agent_ex_autodl_20260910',
        '-o','UserKnownHostsFile=C:/Users/BAIYUE~1/.ssh/agent-ex-autodl-52439-known_hosts',
        '-o','HostKeyAlias=[connect.weste.seetacloud.com]:52439','-o','StrictHostKeyChecking=yes',
        '-o','BatchMode=yes','root@connect.westc.seetacloud.com',
        '/root/autodl-tmp/agent-ex-sis-env-20261021/venv/bin/python -B -']
    with args.output.open('xb') as handle:
        proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        proc.stdin.write(source);proc.stdin.close()
        if args.phase=='numeric':
            with gzip.GzipFile(fileobj=handle,mode='wb',mtime=0) as compressed:
                for block in iter(lambda:proc.stdout.read(1024*1024),b''):compressed.write(block)
        else:
            for block in iter(lambda:proc.stdout.read(1024*1024),b''):handle.write(block)
        code=proc.wait()
    receipt=dict(phase=args.phase,exit_code=code,source_program_sha256=hashlib.sha256(source).hexdigest(),
        input_index_sha256=input_hash,output_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        model_calls=0,scope='read-only SQL; failed output retained, not a completion claim')
    args.output.with_suffix(args.output.suffix+'.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt))
    if code:raise SystemExit(code)


if __name__=='__main__':main()
