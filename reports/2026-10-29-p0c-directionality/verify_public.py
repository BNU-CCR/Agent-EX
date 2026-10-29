"""Standalone public numerical reconciliation. No imports from production code.

This verifies public table algebra and receipt integrity, not private text truth.
"""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path


def categories(before,after,direction):
    values=[]
    if before==5 and after==3:values.append('5_to_3')
    if before==3 and after==5:values.append('3_to_5')
    if before==after==3:values.append('stay_3')
    if before==after==5:values.append('stay_5')
    if before in (1,2,6,7) and min(abs(after-3),abs(after-5))<min(abs(before-3),abs(before-5)):
        values.append('extreme_toward_3_or_5')
    if direction=='empty' and before!=after:values.append('empty_changed')
    if direction!='empty' and before==after:values.append('nonempty_unchanged')
    return values


def aggregate_transitions(rows):
    total=0;counts=Counter();opportunities=defaultdict(Counter)
    for r in rows:
        before=int(r['before']);after=int(r['after']);n=int(r['events']);direction=r['feed_direction']
        if not 1<=before<=7 or not 1<=after<=7 or n<1:raise ValueError('invalid transition')
        total+=n;out=opportunities[r['topic']+'|'+r['source_version']]
        out['all']+=n
        for cat in categories(before,after,direction):counts[cat]+=n
        if before in (3,5):out['before'+str(before)]+=n
        if (before,after)==(5,3):out['5_to_3']+=n
        if (before,after)==(3,5):out['3_to_5']+=n
        if before==5 and direction=='lower':
            out['5_lower_opportunities']+=n;out['5_lower_to3']+=n*(after==3)
        if before==3 and direction=='higher':
            out['3_higher_opportunities']+=n;out['3_higher_to5']+=n*(after==5)
    return dict(events=total,categories=dict(counts),opportunities={k:dict(v) for k,v in opportunities.items()})


def read_csv(root,name):
    with (root/name).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))


def verify(root,pin):
    path=root/'FILE_MANIFEST.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=pin:raise ValueError('external manifest pin differs')
    files=json.loads(path.read_text(encoding='utf-8'))['files']
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual!=set(files)|{'FILE_MANIFEST.json','FILE_MANIFEST.sha256'}:raise ValueError('exact public file cover differs')
    for name,entry in files.items():
        data=(root/name).read_bytes()
        if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise ValueError('member differs: '+name)
    transitions=read_csv(root,'stance_transition_by_exposure.csv');result=aggregate_transitions(transitions)
    source=json.loads((root/'source_manifest.json').read_text(encoding='utf-8'))
    if result['events']!=source['events'] or result['events']!=1890000:raise ValueError('population cover differs')
    frame=read_csv(root,'event_sampling_frame.csv');population=Counter();sampled=Counter()
    frame_keys={}
    fields=('category','topic','seed','cell','window','before','after','feed_class')
    for r in frame:
        key=tuple(r[k] for k in fields)
        if key in frame_keys:raise ValueError('duplicate sampling stratum')
        frame_keys[key]=r;population[r['category']]+=int(r['population']);sampled[r['category']]+=int(r['sampled'])
    if dict(population)!=result['categories'] or any(v!=48 for v in sampled.values()):
        raise ValueError('frame category denominators/quota differ')
    index=read_csv(root,'sampled_event_index.csv');byid={r['event_id']:r for r in index}
    if len(byid)!=len(index) or len(index)!=source['unique_sampled']:raise ValueError('sample cover differs')
    observed=Counter()
    for r in index:
        valid=categories(int(r['before']),int(r['after']),r['feed_direction'])
        for cat in r['selected_categories'].split(';'):
            if cat not in valid:raise ValueError('selected event category differs')
            key=(cat,r['topic'],r['seed'],r['cell'],r['window'],r['before'],r['after'],r['feed_direction'])
            observed[key]+=1
    if any(observed[k]!=int(r['sampled']) for k,r in frame_keys.items()) or set(observed)-set(frame_keys):
        raise ValueError('sample per-stratum reconciliation differs')
    features=read_csv(root,'sampled_material_features.csv');feature_byid={r['event_id']:r for r in features}
    if set(feature_byid)!=set(byid) or len(features)!=len(byid):raise ValueError('recovered case cover differs')
    feed=defaultdict(list)
    for r in read_csv(root,'sampled_feed_slots.csv'):feed[r['event_id']].append(r)
    for eid,r in byid.items():
        f=feature_byid[eid];ss=sorted(feed[eid],key=lambda x:int(x['display_slot']))
        if [int(s['display_slot']) for s in ss]!=list(range(int(r['feed_length']))):raise ValueError('actual slot cover differs')
        for key in ('topic','source_version','seed','cell','ordinal','initial_stance','before','after'):
            if r[key]!=f[key]:raise ValueError('material/index identity differs')
        score_sum=sum(int(s['source_semantic']) for s in ss)
        if score_sum!=int(f['feed_sum']):raise ValueError('actual feed sum differs')
        before=int(r['before']);n=len(ss)
        direction='empty' if not n else 'lower' if score_sum<n*before else 'higher' if score_sum>n*before else 'equal'
        if direction!=r['feed_direction']:raise ValueError('actual feed direction differs')
        if int(f['actual_private_update_count_before'])!=int(r['activation_before'])+1:
            raise ValueError('Round0 activation offset differs')
    proof=json.loads((root/'sample_recovery_verification.json').read_text(encoding='utf-8'))
    if proof['sampled_events']!=len(index) or proof['actual_feed_slots']!=sum(map(len,feed.values())):
        raise ValueError('recovery proof counts differ')
    if any(p['source_sha256_before']!=p['source_sha256_after'] for p in proof['source_proofs']):
        raise ValueError('source changed')
    result.update(verified=True,sampled_events=len(index),actual_feed_slots=proof['actual_feed_slots'],
        scope='public table algebra and exact file hash cover; full source/sampling replay requires separately archived numeric sources')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--manifest-sha256',required=True)
    a=p.parse_args();print(json.dumps(verify(a.directory,a.manifest_sha256),sort_keys=True))
