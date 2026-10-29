"""Build complete P0-C frame before selecting any case; no free text used."""
import argparse
from collections import Counter,defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
from agent_ex.diagnostics.p0c import sample_events


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def csv_write(path,rows):
    rows=list(rows)
    with path.open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def records(base,extra):
    with gzip.open(base/'normalized_events.csv.gz','rt',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            topic=row['topic_key'];ordinal=int(row['ordinal'])
            yield dict(topic=topic,seed=int(row['matched_seed']),cell=row['cell_id'],run_id=row['run_id'],
                ordinal=ordinal,agent_id=row['agent_id'],initial_stance=int(row['initial_stance']),
                before=int(row['before']),after=int(row['after']),feed_length=int(row['feed_length']),
                feed_direction=row['feed_direction'],published=row['published'],
                source_version=('retirement-tail-20261025' if ordinal>=15000 else 'retirement-t30-20261022') if topic=='retirement' else 'cross-topic-20261025')
    with gzip.open(extra,'rt',encoding='utf-8') as f:
        for line in f:
            row=json.loads(line)
            if row['kind']=='event':
                yield {k:v for k,v in row.items() if k not in ('kind','feed','activation_before')}|dict(source_version='retirement-t30-20261022')


def enriched(base,extra):
    history=defaultdict(lambda:[0,0]);cursors={}
    for row in records(base,extra):
        run=(row['topic'],row['seed'],row['cell']);ordinal=row['ordinal']
        if ordinal!=cursors.get(run,0):raise ValueError('noncontiguous or overlapping parent/tail cursor')
        cursors[run]=ordinal+1
        key=run+(row['agent_id'],);activation,slots=history[key]
        identity=json.dumps(run+(ordinal,),separators=(',',':'))
        row.update(event_id='p0c-event-'+hashlib.sha256(identity.encode()).hexdigest()[:24],
            window=(ordinal//500)//10,activation_before=activation,prior_exposure_slots=slots,
            prior_slots_band='0' if slots==0 else '1-10' if slots<=10 else '11-50' if slots<=50 else '>50')
        history[key]=[activation+1,slots+row['feed_length']]
        yield row
    if len(cursors)!=84 or sum(cursors.values())!=1890000:
        raise ValueError('expected 60 retirement parents + 18 tails and 24 cross runs, deduplicated 84 trajectories')


def run(base,extra,output):
    old_manifest=base/'OUTPUT_MANIFEST.json'
    if digest(old_manifest)!='d5fdff0833a86ac4c16d7647d9f74afde6fd229dec156ae03f9e1975ab5bd86a':
        raise ValueError('P0A output manifest pin differs')
    pins=json.loads(old_manifest.read_text(encoding='utf-8'))
    name='normalized_events.csv.gz'
    if digest(base/name)!=pins[name]['sha256']:raise ValueError('P0A events hash differs')
    starts={};ends={};extra_events=0
    with gzip.open(extra,'rt',encoding='utf-8') as f:
        for line in f:
            r=json.loads(line)
            if r['kind']=='run_start':starts[r['run_id']]=r
            elif r['kind']=='run_end':ends[r['run_id']]=r
            else:extra_events+=1
    if len(starts)!=42 or set(starts)!=set(ends) or extra_events!=630000:
        raise ValueError('seven-seed export incomplete')
    for key in starts:
        if starts[key]['db_sha256']!=ends[key]['db_sha256'] or ends[key]['events']!=15000:
            raise ValueError('source changed or not complete')
    result=sample_events(enriched(base,extra),quota=48,seed=20261029)
    selected=set(result['selected_ids']);index=[];transitions=Counter();sources=Counter()
    for r in enriched(base,extra):
        sources[(r['topic'],r['source_version'])]+=1
        key=tuple(r[k] for k in ('topic','source_version','seed','cell','window','before','after','feed_direction','prior_slots_band'))
        transitions[key]+=1
        if r['event_id'] in selected:
            r['selected_categories']=';'.join(result['memberships'][r['event_id']]);index.append(r)
    output.mkdir(parents=True,exist_ok=False)
    csv_write(output/'event_sampling_frame.csv',result['frame'])
    csv_write(output/'sampled_event_index.csv',sorted(index,key=lambda r:r['event_id']))
    keys=('topic','source_version','seed','cell','window','before','after','feed_direction','prior_slots_band')
    csv_write(output/'stance_transition_by_exposure.csv',
        [dict(zip(keys,k),events=n) for k,n in sorted(transitions.items())])
    exposures=Counter()
    for k,n in transitions.items():
        topic,version,seed,cell,window,before,after,direction,band=k
        for measure,weight in [('all',1),('changed',int(before!=after)),('5_to_3',int(before==5 and after==3)),('3_to_5',int(before==3 and after==5))]:
            exposures[(topic,version,direction,band,measure)]+=n*weight
    csv_write(output/'event_exposure_summary.csv',[dict(zip(('topic','source_version','feed_direction','prior_slots_band','measure'),k),events=n)
        for k,n in sorted(exposures.items())])
    provenance=dict(schema='p0c.c2.sampling.v1',events=result['all_events'],unique_sampled=len(index),
        quota_per_overlapping_category=48,sampling_seed=20261029,
        p0a_manifest_sha256=digest(old_manifest),p0a_events_sha256=digest(base/name),
        seven_seed_stream_sha256=digest(extra),seven_seed_sources=list(starts.values()),
        coverage=[dict(topic=k[0],source_version=k[1],events=n) for k,n in sorted(sources.items())],
        duplicate_parent_tail_events=0,text_used_to_select=False,
        prior_exposure_scope='cumulative actual feed slots before event within original full trajectory; not neighbors or potential posts',
        source_validation='Existing P0A verified numeric package + original core read-only seven-seed SQL with payload hashes/run identity and source SHA before/after; not a new full causal cold replay')
    (output/'source_manifest.json').write_text(json.dumps(provenance,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:provenance[k] for k in ('events','unique_sampled','coverage')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('extra',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.base,a.extra,a.output)
