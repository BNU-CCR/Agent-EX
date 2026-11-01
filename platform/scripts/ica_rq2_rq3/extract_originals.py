"""Bounded streaming extraction and ORIGINAL-only normalization CLI.

All newly generated caches live under the explicitly selected V evidence root.
At most six database images are materialized per archive; temporary extraction
is removed only after all SQLite readers close and their hashes are rechecked.
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

from sources import normalize_database,save_canonical,load_canonical,sha256

EVIDENCE=Path('V:/Agent EX/Agent-EX-evidence')
OUTPUT=EVIDENCE/'2026-11-01/ica-rq2-rq3-v1'
HEADROOM=2*1024**3+64*1024**2
CELLS=[f'SIS-A{a}-B{b}' for a in range(2) for b in range(3)]


@contextmanager
def extracted_members(archive, members, output_root, *, expected_archive_sha256=None, headroom=HEADROOM):
    archive=Path(archive);output_root=Path(output_root)
    if sum(r['member'].endswith('.sqlite3') or r.get('database',False) for r in members)>6:
        raise ValueError('maximum six database images per extraction')
    if len({r['member'] for r in members})!=len(members):raise ValueError('duplicate requested member')
    before=sha256(archive)
    if expected_archive_sha256 and before!=expected_archive_sha256:raise ValueError('archive SHA-256 mismatch')
    needed=sum(r['bytes'] for r in members)
    if shutil.disk_usage(output_root).free<needed+headroom:raise ValueError('V evidence headroom insufficient')
    temporary=Path(tempfile.mkdtemp(prefix='ica-original-',dir=output_root)).resolve()
    paths={};expected={r['member']:r for r in members}
    try:
        with tarfile.open(archive,'r|gz') as source:
            for member in source:
                if member.name not in expected:continue
                if member.name in paths:raise ValueError('duplicate actual tar member')
                spec=expected[member.name]
                if not member.isfile() or member.size!=spec['bytes']:raise ValueError('member type/size mismatch')
                target=temporary/(str(len(paths))+('.sqlite3' if spec.get('database') or member.name.endswith('.sqlite3') else '.data'))
                with source.extractfile(member) as reader,target.open('xb') as writer:
                    shutil.copyfileobj(reader,writer,4*1024**2)
                if sha256(target)!=spec['sha256']:raise ValueError('member SHA-256 mismatch')
                paths[member.name]=target
        if set(paths)!=set(expected):raise ValueError('requested archive member missing')
        yield paths
    finally:
        # Restrict cleanup to this invocation's newly created, validated directory.
        if temporary.parent!=output_root.resolve() or not temporary.name.startswith('ica-original-'):
            raise ValueError('unsafe temporary cleanup target')
        shutil.rmtree(temporary)
        if sha256(archive)!=before:raise ValueError('archive changed during read')


def destination(topic,seed,cell,horizon):
    return OUTPUT/'canonical'/topic/str(seed)/cell/('T'+str(horizon))


def core_seed(seed):
    selected=json.loads(Path(f'V:/Agent EX/Agent-EX-analysis-scratch-20261024/seed-{seed}/selected.json').read_bytes())
    archive=EVIDENCE/f'2026-10-22/core-n500-run-v1/seed-{seed}.tar.gz'
    wanted=[]
    for row in selected['members']:
        if row['path'].endswith('/run.sqlite3'):
            wanted.append(dict(row,member='evidence/'+row['local'].split('.')[0],database=True))
    if len(wanted)!=6:raise ValueError('core six-cell database set incomplete')
    with extracted_members(archive,wanted,OUTPUT,expected_archive_sha256=selected['archive_sha256']) as files:
        for row in wanted:
            cell=next(c for c in CELLS if '/'+c+'/' in row['path']);target=destination('retirement',seed,cell,30)
            if target.exists():
                load_canonical(target);continue
            run=normalize_database(files[row['member']],topic_key='retirement',cohort='retirement_t30_10seeds',horizon=30,
                expected_sha256=row['sha256'],provenance=dict(archive=str(archive),archive_sha256=selected['archive_sha256'],member=row['member'],original_source_path=row['path']))
            save_canonical(run,target)
            print(json.dumps(dict(topic='retirement',seed=seed,cell=cell,horizon=30,events=len(run['events']))),flush=True)


def tail_seed(seed):
    rows=json.loads(Path(f'V:/Agent EX/Agent-EX-t60-process-scratch-v1/seed-{seed}/sources.json').read_bytes())
    archive=EVIDENCE/f'2026-10-25/temporal-extension-v1/seed-{seed}.tar.gz'
    verified=json.loads(Path(str(archive)+'.verified.json').read_bytes())
    expected_hash=verified.get('sha256') or verified.get('archive_sha256')
    if not expected_hash:raise ValueError('tail expected archive digest missing')
    wanted=[dict(r,member=r['path'],database=True) for r in rows if r['role']=='tail' and r['path'].endswith('extension.sqlite3')]
    if len(wanted)!=6:raise ValueError('tail six-cell database set incomplete')
    with extracted_members(archive,wanted,OUTPUT,expected_archive_sha256=expected_hash) as files:
        for row in wanted:
            cell=next(c for c in CELLS if '/'+c+'/' in row['path']);target=destination('retirement',seed,cell,60)
            if target.exists():load_canonical(target);continue
            parent=load_canonical(destination('retirement',seed,cell,30),include_reasons=True)
            # The core binding is preserved in its archived input source, but the
            # normalized parent provides the exact graph/roster and ordinal labels
            # are read from a verified matching input file extracted below.
            binding=parent['binding']
            run=normalize_database(files[row['member']],topic_key='retirement',cohort='retirement_t60_3seeds',horizon=60,
                binding=binding,parent=parent,expected_sha256=row['sha256'],
                provenance=dict(archive=str(archive),archive_sha256=expected_hash,member=row['member']))
            save_canonical(run,target)
            print(json.dumps(dict(topic='retirement',seed=seed,cell=cell,horizon=60,events=len(run['events']))),flush=True)


def cross_archive(topic,seed):
    root=EVIDENCE/'2026-10-25/cross-topic-n500-t60-v1'
    index=json.loads((root/'metadata/archive-index.json').read_bytes())
    record=next(r for r in index if r['relative_path']==f'archives/{topic}-seed-{seed}.tar.gz')
    archive=root/record['relative_path']
    wanted=[dict(v,member=k,database=k.endswith('.sqlite3')) for k,v in record['members'].items()
            if k.endswith('/run.sqlite3') or (k.startswith(f'inputs/inputs/{topic}/seed-{seed}/') and (k.endswith('/binding.json') or k.endswith('/common.json')))]
    with extracted_members(archive,wanted,OUTPUT,expected_archive_sha256=record['sha256']) as files:
        bindings={}
        common_member=f'inputs/inputs/{topic}/seed-{seed}/common.json'
        common=json.loads(files[common_member].read_bytes())
        for row in wanted:
            if row['member'].endswith('/binding.json'):
                value=json.loads(files[row['member']].read_bytes());bindings[value['cell_id']]=value
        for row in wanted:
            if not row['member'].endswith('/run.sqlite3'):continue
            # Read contract only; immutable connection and hashes remain mandatory.
            from sources import original_database
            with original_database(files[row['member']],row['sha256']) as (db,_):
                contract=json.loads(db.execute('SELECT contract_json FROM binding').fetchone()[0])
            cell=contract['cell_id'];target=destination(topic,seed,cell,60)
            if target.exists():load_canonical(target);continue
            run=normalize_database(files[row['member']],topic_key=topic,cohort='cross_topic_t60_2seeds',horizon=60,
                binding=bindings[cell],expected_sha256=row['sha256'],
                provenance=dict(archive=str(archive),archive_sha256=record['sha256'],member=row['member'],
                    common_member=common_member,common_sha256=record['members'][common_member]['sha256'],
                    model_identity=common['payload']['adapter_binding']))
            save_canonical(run,target)
            print(json.dumps(dict(topic=topic,seed=seed,cell=cell,horizon=60,events=len(run['events']))),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort',choices=['core','tail','cross','sample'],required=True)
    parser.add_argument('--seed',type=int,default=20261201)
    parser.add_argument('--topic',choices=['gm-market-support','genai-net-job-loss'])
    args=parser.parse_args()
    if not EVIDENCE.is_dir():raise RuntimeError('V evidence unavailable; no fallback')
    OUTPUT.mkdir(exist_ok=True,parents=True)
    if args.cohort=='core':core_seed(args.seed)
    elif args.cohort=='tail':tail_seed(args.seed)
    elif args.cohort=='cross':
        if not args.topic:parser.error('--topic required for cross')
        cross_archive(args.topic,args.seed)
    else:
        inspection=json.loads((OUTPUT/'source-schema-inspection.json').read_bytes())
        raw=next(r for r in inspection['extracted'] if r['path'].endswith('sqlite3'))
        run=normalize_database(raw['path'],topic_key='retirement',cohort='retirement_t30_10seeds',horizon=30,
            expected_sha256=raw['sha256'],provenance=dict(archive=inspection['archive'],archive_sha256=inspection['archive_actual_sha256'],original_source_path=raw['source_path']))
        save_canonical(run,destination('retirement',20261201,'SIS-A0-B0',30))
        print(json.dumps(run['source'],ensure_ascii=False))


if __name__=='__main__':main()
