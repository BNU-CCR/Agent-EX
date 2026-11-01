"""Package verified offline ICA evidence; no network/model/source mutation.

Run only after aggregate verification, result briefs, and figures are complete.
Private text belongs exclusively to full package A, never the Review Packet.
"""
from collections import defaultdict
import argparse
import csv
import gzip
import hashlib
import heapq
import json
from pathlib import Path
import zipfile


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_declared_inputs(paths_to_sha256):
    for path,digest in paths_to_sha256.items():
        if sha256(path)!=digest:
            raise ValueError(f'declared input SHA-256 differs: {Path(path).name}')


def validate_aggregate(summary):
    """Fail closed unless the complete approved four horizon panels are present."""
    if summary.get('completed_horizon_trajectories') != 102 or summary.get('unique_network_events') != 1890000:
        raise ValueError('requires 102 horizon trajectories and 1890000 unique network events')
    if summary.get('model_requests') != 0:
        raise ValueError('offline analysis must record zero model requests')
    expected = set()
    for topic, horizon, seeds in [('retirement',30,range(20261201,20261211)),
                                 ('retirement',60,range(20261201,20261204)),
                                 ('gm-market-support',60,range(20261201,20261203)),
                                 ('genai-net-job-loss',60,range(20261201,20261203))]:
        for seed in seeds:
            for a in range(2):
                for b in range(3):
                    expected.add((topic,seed,f'SIS-A{a}-B{b}',horizon))
    observed = []
    for receipt in summary.get('sources', []):
        meta = receipt['meta']
        observed.append((meta['topic_key'],int(meta['matched_seed']),meta['cell_id'],int(meta['horizon'])))
        if receipt.get('n_agents') != 500 or receipt.get('n_events') != 500*int(meta['horizon']):
            raise ValueError('population/event count differs from frozen completed panel')
        for field in ('original_records_replayed','all_events_successful','before_after_chain_validated',
                      'population_flow_conserved','historical_public_feed_validated'):
            if receipt.get(field) is not True:
                raise ValueError(f'analysis verification absent: {field}')
    if len(observed) != 102 or set(observed) != expected:
        raise ValueError('exact topic/seed/cell/horizon panel coverage is incomplete')
    return True


def review_allowed(path):
    name = Path(path).name.lower()
    return not (name in ('initial.json','a3_text_evidence_casebook.md') or
                'reason' in name and name != 'a2_reason_case_index.csv' or
                'sqlite' in name or 'binding' in name or
                name.startswith(('a2_event_exposure_numeric','events.csv','feed.csv','snapshots.')))


def write_verified_zip(destination, files, memory_files=None):
    """Write/CRC-test/hash every member; restore one small CSV and rehash inputs."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    memory_files = memory_files or {}
    if set(files) & set(memory_files) or 'SHA256SUMS' in files or 'SHA256SUMS' in memory_files:
        raise ValueError('duplicate/reserved archive name')
    for name in list(files)+list(memory_files):
        if Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name:
            raise ValueError('unsafe archive member name')
    source_hashes = {name:sha256(path) for name,path in files.items()}
    expected = {**source_hashes, **{name:hashlib.sha256(data).hexdigest() for name,data in memory_files.items()}}
    sums = ''.join(f'{digest}  {name}\n' for name,digest in sorted(expected.items())).encode()
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for name,path in sorted(files.items()):
            archive.write(path,name)
        for name,data in sorted(memory_files.items()):
            archive.writestr(name,data)
        archive.writestr('SHA256SUMS', sums)
    restored = False
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC mismatch')
        if set(archive.namelist()) != set(expected)|{'SHA256SUMS'}:
            raise ValueError('ZIP coverage mismatch')
        if archive.read('SHA256SUMS') != sums:
            raise ValueError('ZIP SHA256SUMS differs')
        for name,digest in expected.items():
            with archive.open(name) as stream:
                actual = hashlib.file_digest(stream,'sha256').hexdigest()
            if actual != digest:
                raise ValueError(f'ZIP member SHA mismatch: {name}')
        small = next((name for name in sorted(expected)
                      if name.endswith(('.csv','.csv.gz')) and archive.getinfo(name).file_size < 8*1024**2),None)
        if small:
            restore = destination.parent/'verification-restores'/(destination.stem+'__'+Path(small).name)
            restore.parent.mkdir(parents=True, exist_ok=True)
            restore.write_bytes(archive.read(small))
            if sha256(restore) != expected[small]:
                raise ValueError('restored small CSV differs')
            restored = True
    for name,path in files.items():
        if sha256(path) != source_hashes[name]:
            raise ValueError(f'packaged source changed: {name}')
    receipt = dict(zip_path=str(destination),zip_sha256=sha256(destination),
                   members_verified=len(expected)+1,crc_ok=True,
                   small_csv_restored_exactly=restored,source_hashes_unchanged_after=True,
                   member_sha256=expected,
                   checksum_scope='all members except SHA256SUMS itself; whole ZIP SHA recorded externally')
    destination.with_suffix('.verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt


def selected_sidecars(candidates, run_directories):
    """Stream JSONL, retain only selected exact event texts, never whole sidecars."""
    wanted = defaultdict(set)
    for row in candidates:
        wanted[row['run_id']].add(int(row['ordinal']))
    output = {}
    for run_id, ordinals in wanted.items():
        directory = run_directories.get(run_id)
        if directory is None:
            continue
        path = Path(directory)/'private-reasons.jsonl.gz'
        if not path.exists():
            continue
        before = sha256(path)
        with gzip.open(path,'rt',encoding='utf-8') as stream:
            remaining = set(ordinals)
            for line in stream:
                row = json.loads(line)
                ordinal = int(row['ordinal'])
                if ordinal in remaining:
                    output[run_id,ordinal] = row
                    remaining.remove(ordinal)
                if not remaining:
                    break
        if sha256(path) != before:
            raise ValueError('private sidecar changed during selected-text read')
    return output


def _candidate_pool(path, longest, n=150):
    """Bounded top-hash queue per numeric stratum, same ordering as casebook."""
    import pandas as pd
    import casebook
    queues = {}
    limit = n
    seed = 'ica2027-rq2-v1'
    for chunk in pd.read_csv(path, chunksize=30000, usecols=lambda c:c in casebook.SAFE_FIELDS):
        for raw in chunk.itertuples(index=False, name=None):
            row = {k:casebook._scalar(v) for k,v in zip(chunk.columns,raw)}
            key = row['topic_key'],int(row['matched_seed']),row['cell_id']
            if int(row['horizon']) != longest[key]:
                continue
            before,after = int(row['prior_stance']),int(row['after_stance'])
            counts = [int(row.get(f'feed_stance_{s}_count') or 0) for s in range(1,8)]
            length = int(row['feed_length'])
            top = max(counts)
            modes = [i+1 for i,c in enumerate(counts) if c == top]
            dominant = modes[0] if length and len(modes)==1 and 2*top>length else None
            if dominant is None:
                relation = 'no_feed' if not length else 'no_strict_dominance'
            else:
                delta = abs(after-dominant)-abs(before-dominant)
                relation = 'toward_dominant' if delta<0 else ('away_from_dominant' if delta>0 else 'unchanged_distance')
            reason = row.get('reason_changed')
            strata = tuple(map(str,(row['topic_key'],row['matched_seed'],row['identity_a'],row['network_b'],
                                   'changed' if before!=after else 'retained',relation,
                                   'missing' if reason is None else ('changed' if reason else 'unchanged'))))
            rank = casebook._digest(json.dumps([seed,row['run_id'],row['ordinal']],ensure_ascii=False))
            entry = (-int(rank,16),rank,row)
            bucket = queues.setdefault(strata,[])
            if len(bucket)<limit:
                heapq.heappush(bucket,entry)
            elif entry[0]>bucket[0][0]:
                heapq.heapreplace(bucket,entry)
            if limit>1 and len(queues)>=n:
                limit=1
                for k,q in queues.items():
                    queues[k]=[max(q,key=lambda x:x[0])]
    return pd.DataFrame([row for bucket in queues.values() for _,_,row in bucket])


def _csv_bytes(rows):
    import io
    stream=io.StringIO(newline='')
    fields=list(dict.fromkeys(k for row in rows for k in row))
    writer=csv.DictWriter(stream,fields)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def build_packages(root, repo):
    """Complete-cohort only; caller runs after findings and plots are finalized."""
    root,repo=Path(root).resolve(),Path(repo).resolve()
    if root.drive.upper()!='V:':
        raise ValueError('outputs require controlled V drive; no fallback')
    tables=root/'analysis-v1/tables'
    verification=tables/'AGGREGATE_VERIFICATION.json'
    summary=json.loads(verification.read_text(encoding='utf-8'))
    validate_aggregate(summary)
    verification_hash=sha256(verification)
    for name,digest in summary['files'].items():
        if sha256(tables/name)!=digest:
            raise ValueError(f'aggregate file hash differs: {name}')
    briefs={letter:root/'evidence-packages'/letter for letter in ('A','B')}
    for folder in briefs.values():
        if not (folder/'CORE_FINDINGS.md').exists():
            raise ValueError('required CORE_FINDINGS.md not ready')
    figures=sorted((root/'figures-v1').rglob('*'))
    if not any(p.suffix=='.svg' for p in figures):
        raise ValueError('figures-v1 not ready')
    methods=repo/'reports/2026-11-01-ica-rq2-rq3-work/METHODS.md'
    framework=repo/'reports/2026-11-01-ica-rq2-micro-macro-v1/A3_micro_response_coding_framework.md'
    if not methods.is_file() or not framework.is_file():
        raise ValueError('methods/coding framework not ready')
    longest={}
    for receipt in summary['sources']:
        m=receipt['meta']; key=m['topic_key'],int(m['matched_seed']),m['cell_id']
        longest[key]=max(longest.get(key,0),int(m['horizon']))
    directories={}
    manifest=[]
    canonical_inputs={}
    for receipt_path in sorted((root/'analysis-v1/runs').rglob('analysis-verification.json')):
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        m=receipt['meta']; key=m['topic_key'],int(m['matched_seed']),m['cell_id']
        directory=root/'canonical'/receipt_path.parent.relative_to(root/'analysis-v1/runs')
        canonical_inputs.update({directory/name:digest for name,digest in receipt['signature']['inputs'].items()})
        if int(m['horizon'])==longest[key]:
            directories[m['run_id']]=directory
        source=json.loads((directory/'source.json').read_text(encoding='utf-8'))
        # Explicit source schema excludes arbitrary private binding/reason payloads.
        manifest.append(dict(meta=m,canonical_directory=str(directory),
                             canonical_sha256=receipt['signature']['inputs'],
                             components=[{k:c.get(k) for k in ('source_path','expected_sha256','actual_sha256',
                                 'sha256_unchanged_after_read','component_events','original_model_identity','provenance')}
                                         for c in source['components']],
                             analysis_code_sha256=receipt['signature']['code'],
                             source_hash_scope='original components checked before/after upstream extraction; archive provenance retained'))
    if len(manifest)!=102:
        raise ValueError('canonical manifest count differs from verified aggregate')
    verify_declared_inputs(canonical_inputs)
    import casebook
    pool=_candidate_pool(tables/'A2_event_exposure_numeric.csv.gz',longest)
    cases=casebook.select_candidates(pool,n=150)
    if len(cases['A3_candidate_cases'])!=150:
        raise ValueError('150 genuine distinct review candidates unavailable')
    casepath=casebook.write_private_casebook(cases['A3_candidate_cases'],
        selected_sidecars(cases['A3_candidate_cases'],directories),root/'evidence-packages/A/private')
    case_files={f'tables/{name}.csv':_csv_bytes(rows) for name,rows in cases.items()}
    all_tables=sorted(tables.glob('*.csv.gz'))
    dictionary=['# Data dictionary','',
        'All numeric CSVs preserve topic, matched seed, condition, run and horizon. Blank cells are missing/undefined, never zero.',
        'Matched seed/run is the independent replicate. T30 and T60 panels reuse prefixes and are not independent samples.',
        'A round is N successful weighted activations, not one activation per agent. Population remains N=500.',
        'A2 exact rates use event opportunities with nonempty pure-target feed; toward-target is a different numerator. No per-slot duplicated outcome denominators.',
        'Response-cell denominators repeat over observed outcome rows of a conditioning cell; never sum repeated denominators.',
        'Private state, latest public stock, new public flow and actually read historical posts are distinct. Public stance is not sender private stance.',
        'A3 selection is purposive numeric coverage; all semantic judgments pending human review. Raw text is excluded from Review Packet.',
        'B0 adjacency statistics and zero-opportunity rates may be undefined. Group labels remain backend memberships when A0 hides them.',
        'Stage-A/B joint manipulation did not pass; source associations do not establish trust/identity mechanisms.',
        'P0 is separate fixed-step diagnostic context, not an extra network replicate.','']
    for path in all_tables:
        with gzip.open(path,'rt',encoding='utf-8',newline='') as stream:
            fields=next(csv.reader(stream),[])
        dictionary.extend([f'## {path.name}','',', '.join(f'`{x}`' for x in fields),''])
    for name,rows in cases.items():
        dictionary.extend([f'## {name}.csv','',', '.join(f'`{x}`' for x in rows[0]),''])
    common_memory={'DATA_DICTIONARY.md':'\n'.join(dictionary).encode(),
                   'SOURCE_MANIFEST.json':json.dumps(manifest,ensure_ascii=False,indent=2).encode()}
    codefiles={f'scripts/{p.name}':p for p in sorted((repo/'platform/scripts/ica_rq2_rq3').glob('*.py'))}
    common_memory['CODE_MANIFEST.json']=json.dumps({name:sha256(path) for name,path in codefiles.items()},indent=2).encode()
    common_files={**codefiles,'METHODS.md':methods,'AGGREGATE_VERIFICATION.json':verification}
    notes=repo/'reports/2026-11-01-ica-rq2-rq3-work'
    for name in ('REPRODUCE.md','GAPS_AND_INTERPRETATION.md'):
        common_files[name]=notes/name
    for name in ('independent-verification.json','legacy-endpoint-comparison.json','runtime-and-figure-verification.json','casebook-text-availability.json'):
        if not (root/name).is_file():
            raise ValueError('Final delivery evidence not ready: '+name)
        common_files['verification/'+name]=root/name
    for path in (root/'p0-context').rglob('*'):
        if path.is_file() and path.suffix in ('.csv','.gz','.json','.md') and review_allowed(path):
            common_files['p0-context/'+str(path.relative_to(root/'p0-context')).replace('\\','/')]=path
    package_files={}
    for letter in ('A','B'):
        files=dict(common_files)
        files.update({f'tables/{p.name}':p for p in all_tables if p.name.startswith(letter)})
        files.update({f'findings/{p.name}':p for p in briefs[letter].glob('*.md')})
        for path in figures:
            if path.is_file():
                name=path.name.lower()
                appropriate=('a1' in name or 'figure6' in name) if letter=='A' else ('figure5' in name or 's1' in name)
                if appropriate:
                    files['figures/'+str(path.relative_to(root/'figures-v1')).replace('\\','/')]=path
        package_files[letter]=files
    package_files['A'].update({'A3_micro_response_coding_framework.md':framework,
                               'private/A3_text_evidence_casebook.md':casepath})
    review=dict(common_files)
    for letter in ('A','B'):
        for name,path in package_files[letter].items():
            if review_allowed(path) and not name.startswith('private/'):
                target=f'findings/{letter}/{path.name}' if name.startswith('findings/') else name
                review[target]=path
    # Full event/path/person tables are unnecessary in the compact review packet.
    review={name:p for name,p in review.items() if review_allowed(p) and not p.name.startswith(
        ('A1_origin_destination_paths','A1_dominant_stance_formation','A2_exposure_history_summary'))}
    for path in figures:
        if path.is_file():
            review['figures/'+str(path.relative_to(root/'figures-v1')).replace('\\','/')]=path
    memories={'A':{**common_memory,**case_files},'B':dict(common_memory),
              'Review':{**common_memory,**case_files}}
    names={'A':'ICA2027_RQ2_MicroMacro_Evidence_v1.zip',
           'B':'ICA2027_RQ3_StructureIdentity_Evidence_v1.zip',
           'Review':'ICA2027_RQ2_RQ3_Review_Packet_v1.zip'}
    receipts=[]
    for key,files in [('A',package_files['A']),('B',package_files['B']),('Review',review)]:
        receipts.append(write_verified_zip(root/'packages'/names[key],files,memories[key]))
    if sha256(verification)!=verification_hash:
        raise ValueError('aggregate verification changed during packaging')
    verify_declared_inputs(canonical_inputs)
    (root/'packages/PACKAGE_VERIFICATION.json').write_text(json.dumps(receipts,indent=2),encoding='utf-8')
    return receipts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--repo',type=Path,required=True)
    args=parser.parse_args()
    result=build_packages(args.root,args.repo)
    print(json.dumps([{k:r[k] for k in ('zip_path','zip_sha256','members_verified','crc_ok')}
                      for r in result],indent=2))


if __name__=='__main__':
    main()
