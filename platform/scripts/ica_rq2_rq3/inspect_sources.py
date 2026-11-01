"""Offline original-source schema inventory; never prints private reasons."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sqlite3
import tarfile

EVIDENCE=Path('V:/Agent EX/Agent-EX-evidence')
OUT=EVIDENCE/'2026-11-01/ica-rq2-rq3-v1'

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--extract-sample',action='store_true')
    args=parser.parse_args()
    if not EVIDENCE.is_dir():raise RuntimeError('V evidence unavailable; no fallback')
    OUT.mkdir(parents=True,exist_ok=True)
    metadata=Path('V:/Agent EX/Agent-EX-analysis-scratch-20261024/seed-20261201/selected.json')
    selected=json.loads(metadata.read_bytes())
    archive=EVIDENCE/'2026-10-22/core-n500-run-v1/seed-20261201.tar.gz'
    result={'archive':str(archive),'archive_expected_sha256':selected['archive_sha256'],
            'archive_bytes':archive.stat().st_size,'V_free_bytes':shutil.disk_usage(OUT).free}
    with tarfile.open(archive,'r:gz') as source:
        members=source.getmembers()
        result['members']=[{'name':m.name,'bytes':m.size} for m in members[:28]]
        if args.extract_sample:
            actual=sha(archive)
            if actual!=selected['archive_sha256']:raise ValueError('original archive SHA mismatch')
            result['archive_actual_sha256']=actual
            wanted=[r for r in selected['members'] if 'SIS-A0-B0' in r['path']
                    and (r['path'].endswith('/run.sqlite3') or r['path'].endswith('/SIS-A0-B0.json'))]
            extracted=[]
            for row in wanted:
                number=row['local'].split('.')[0]
                candidates=[m for m in members if m.isfile() and m.size==row['bytes']
                            and (m.name==row['path'] or Path(m.name).name in (number,row['local']))]
                if len(candidates)!=1:
                    raise ValueError('archive member mapping unavailable: '+row['local'])
                name='core-seed20261201-A0B0'+('.sqlite3' if row['path'].endswith('sqlite3') else '.json')
                target=OUT/name
                if target.exists():
                    if sha(target)!=row['sha256']:raise ValueError('existing sample differs; preserve and inspect')
                else:
                    if shutil.disk_usage(OUT).free<row['bytes']+2214592512:raise ValueError('V headroom insufficient')
                    digest=hashlib.sha256()
                    with source.extractfile(candidates[0]) as reader,target.open('xb') as writer:
                        while block:=reader.read(4*1024**2):digest.update(block);writer.write(block)
                    if digest.hexdigest()!=row['sha256']:raise ValueError('extracted original member SHA mismatch')
                extracted.append(dict(path=str(target),source_path=row['path'],sha256=sha(target),bytes=target.stat().st_size))
                if target.suffix=='.sqlite3':
                    db=sqlite3.connect(target.as_uri()+'?mode=ro&immutable=1',uri=True)
                    try:
                        db.execute('PRAGMA query_only=ON')
                        result['schema']={table:[col[1] for col in db.execute('PRAGMA table_info('+table+')')]
                            for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        for table,column in [('binding','manifest_payload_json'),('events','payload_json'),
                            ('private_updates','payload_json'),('event_input_evidence','payload')]:
                            value=db.execute('SELECT '+column+' FROM '+table+' LIMIT 1').fetchone()
                            if value:
                                document=json.loads(value[0]);result[table+'_keys']=list(document)
                                if table=='event_input_evidence':
                                    result['sis_input_keys']=list(document['sis_input'])
                                    result['causal_payload_keys']=list(document['causal_snapshot']['payload'])
                                if table=='binding':result['run_spec_keys']=list(document.get('run_spec',{}))
                    finally:db.close()
                else:
                    document=json.loads(target.read_bytes());result['input_keys']=list(document)
            result['extracted']=extracted
    output=OUT/'source-schema-inspection.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
