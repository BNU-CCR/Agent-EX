"""Independent stdlib arithmetic audit; deliberately imports no metric module.

Recomputes each horizon separately while counting overlapping T30/T60 prefixes
only once in the coverage gate. Existing permutations are not rerun or changed.
"""
import argparse
from collections import Counter,defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def csv_rows(path):
    with gzip.open(path,'rt',encoding='utf-8',newline='') as stream:return list(csv.DictReader(stream))


def integer(value):
    if value is None or value=='':return None
    x=float(value)
    if not x.is_integer():raise ValueError('nonintegral numeric value')
    return int(x)


def truth(value):
    if value in (True,'True','true','1',1):return True
    if value in (False,'False','false','0',0):return False
    raise ValueError('invalid boolean')


def close(actual,expected,label):
    if expected is None:
        if actual not in (None,'') and not (isinstance(actual,float) and math.isnan(actual)):
            raise ValueError(label+': expected missing')
    elif actual in (None,'') or not math.isclose(float(actual),expected,rel_tol=1e-9,abs_tol=1e-10):
        raise ValueError(label+': numeric mismatch')


def recompute(run):
    nodes=run['node_ids'];n=len(nodes);horizon=int(run['meta']['horizon'])
    if not n or len(set(nodes))!=n:raise ValueError('invalid node roster')
    state=dict(run['initial_stances']);public=dict(run['initial_public'])
    baseline=Counter(state.values());transitions=Counter();directional=defaultdict(lambda:dict(n_opportunities=0,n_exact_i_to_j=0,n_toward_target=0))
    posts={(a,None):v for a,v in public.items()};post_ids={};by_event=defaultdict(list)
    for feed in run['feed']:by_event[integer(feed['ordinal'])].append(feed)
    snapshots={int(s['next_event_ordinal']):s for s in run.get('snapshots',[]) if 'next_event_ordinal' in s}
    # Legacy fixture/archived snapshots can omit their cursor only at endpoint.
    if run.get('snapshots') and 'next_event_ordinal' not in run['snapshots'][-1]:
        snapshots[n*horizon]=run['snapshots'][-1]
    boundaries={};edge_results={}
    def observe(cursor):
        if cursor in snapshots:
            stored=snapshots[cursor]
            if stored['private']!=state or stored['public']!=public:raise ValueError('original snapshot mismatch')
        if cursor%n:return
        r=cursor//n;counts={k:sum(v==k for v in state.values()) for k in range(1,8)}
        if sum(counts.values())!=n:raise ValueError('seven-bin population mismatch')
        mean=sum(k*v for k,v in counts.items())/n
        variance=sum(v*(k-mean)**2 for k,v in counts.items())/n
        boundaries[r]=dict(counts=counts,mean=mean,variance=variance,
            cumulative={k:counts[k]-baseline[k] for k in range(1,8)})
        for scope in ('all','same_group','different_group'):
            edges=[(a,b) for a,b in run['edges'] if scope=='all' or (run['groups'][a]==run['groups'][b])==(scope=='same_group')]
            if not edges:
                edge_results[r,scope]=dict(n_edges=0,same_stance_fraction=None,mean_abs_distance=None,assortativity=None,expected_same_stance_fraction=None);continue
            pairs=[(state[a],state[b]) for a,b in edges];m=len(pairs)
            endpoints=[v for pair in pairs for v in pair];em=sum(endpoints)/(2*m)
            denominator=sum((v-em)**2 for v in endpoints)/(2*m)
            correlation=(sum((x-em)*(y-em) for x,y in pairs)/m)/denominator if denominator>1e-14 else None
            edge_results[r,scope]=dict(n_edges=m,same_stance_fraction=sum(x==y for x,y in pairs)/m,
                mean_abs_distance=sum(abs(x-y) for x,y in pairs)/m,assortativity=correlation,
                expected_same_stance_fraction=sum(v*(v-1) for v in counts.values())/(n*(n-1)) if n>1 else None)
    observe(0)
    if len(run['events'])!=n*horizon:raise ValueError('event count differs from N*horizon')
    for ordinal,event in enumerate(run['events']):
        if integer(event['ordinal'])!=ordinal:raise ValueError('global event ordinal gap')
        a=event['agent_id'];before=integer(event['before']);after=integer(event['after'])
        if a not in state or state[a]!=before or after not in range(1,8):raise ValueError('serial private chain mismatch')
        rows=by_event.get(ordinal,[]);stances=[];slots=set()
        for feed in rows:
            source=feed['source_agent_id'];publication=integer(feed['publication_ordinal']);stance=integer(feed['source_stance'])
            if feed['receiver_agent_id']!=a or source==a or source not in state:raise ValueError('feed source/receiver mismatch')
            if publication is not None and publication>=ordinal:raise ValueError('future publication')
            key=(source,publication)
            if key not in posts or posts[key]!=stance:raise ValueError('immutable historical publication mismatch')
            post=feed['post_id']
            if post in post_ids and post_ids[post]!=(key,stance):raise ValueError('post identity changed')
            post_ids[post]=(key,stance)
            slot=integer(feed['display_slot'])
            if slot in slots:raise ValueError('duplicate feed slot')
            slots.add(slot);stances.append(stance)
        if stances and len(set(stances))==1 and before!=stances[0]:
            target=stances[0];cell=directional[before,target];cell['n_opportunities']+=1
            cell['n_exact_i_to_j']+=int(after==target)
            cell['n_toward_target']+=int(abs(after-target)<abs(before-target))
        r=ordinal//n+1;transitions[r,before,after]+=1;state[a]=after
        if truth(event['published']):public[a]=after;posts[a,ordinal]=after
        observe(ordinal+1)
    if set(by_event)-set(range(n*horizon)):raise ValueError('feed outside trajectory')
    return dict(rounds=boundaries,transitions=transitions,directional=dict(directional),edges=edge_results,
                events=len(run['events']),feed_slots=len(run['feed']),snapshots_checked=len(snapshots))


def verify_run(canonical,analysis):
    canonical=Path(canonical);analysis=Path(analysis)
    run=json.loads((canonical/'initial.json').read_bytes())
    run['events']=csv_rows(canonical/'events.csv.gz');run['feed']=csv_rows(canonical/'feed.csv.gz')
    run['snapshots']=json.loads((canonical/'snapshots.json').read_bytes())
    result=recompute(run);n=len(run['node_ids']);h=int(run['meta']['horizon'])
    checks=0
    def compare(actual,expected,label):
        nonlocal checks
        close(actual,expected,label);checks+=1
    table=lambda name:csv_rows(analysis/(name+'.csv.gz'))
    rows=table('A1_round_transition_matrices')
    if len(rows)!=h*49:raise ValueError('transition table row coverage')
    seen=set()
    for row in rows:
        key=tuple(integer(row[k]) for k in ('round','from_stance','to_stance'))
        if key in seen:raise ValueError('duplicate transition metric')
        seen.add(key);compare(row['count'],result['transitions'][key],'7x7 transition')
    if seen!={(r,i,j) for r in range(1,h+1) for i in range(1,8) for j in range(1,8)}:
        raise ValueError('transition metric keys incomplete')
    for name in ('A1_net_stance_flows','A1_cumulative_flow'):
        rows=table(name)
        if len(rows)!=7*h:raise ValueError('flow table row coverage')
        if {(integer(row['round']),integer(row['stance'])) for row in rows}!={(r,k) for r in range(1,h+1) for k in range(1,8)}:
            raise ValueError('flow metric keys incomplete')
        for row in rows:
            r,k=integer(row['round']),integer(row['stance']);boundary=result['rounds'][r]
            compare(row['cumulative_net_flow'],boundary['cumulative'][k],'cumulative population flow')
            compare(row['population_count'],boundary['counts'][k],'population count')
            if name=='A1_net_stance_flows':
                inflow=sum(result['transitions'][r,j,k] for j in range(1,8) if j!=k)
                outflow=sum(result['transitions'][r,k,j] for j in range(1,8) if j!=k)
                for field,value in [('inflow',inflow),('outflow',outflow),('net_flow',inflow-outflow)]:compare(row[field],value,field)
    for name in ('B1_time_trajectories','B1_global_convergence_by_run'):
        rows=table(name)
        if len(rows)!=(h+1 if name=='B1_time_trajectories' else 1):raise ValueError('global trajectory row coverage')
        for row in rows:
            r=integer(row['round']) if 'round' in row else h;boundary=result['rounds'][r]
            for field in ('mean','variance'):compare(row[field],boundary[field],field)
            for k in range(1,8):
                if f'count_{k}' in row:compare(row[f'count_{k}'],boundary['counts'][k],'endpoint bin')
                if f'share_{k}' in row:compare(row[f'share_{k}'],boundary['counts'][k]/n,'endpoint share')
    directional=table('A2_directional_update_rates')
    if len(directional)!=42:raise ValueError('directional table row coverage')
    if {(integer(row['prior_stance']),integer(row['target_stance'])) for row in directional}!={(i,j) for i in range(1,8) for j in range(1,8) if i!=j}:
        raise ValueError('directional metric keys incomplete')
    for row in directional:
        key=integer(row['prior_stance']),integer(row['target_stance'])
        expected=result['directional'].get(key,dict(n_opportunities=0,n_exact_i_to_j=0,n_toward_target=0))
        for field,value in expected.items():compare(row[field],value,field)
        denominator=expected['n_opportunities']
        compare(row['exact_rate'],expected['n_exact_i_to_j']/denominator if denominator else None,'directional exact rate')
        compare(row['toward_rate'],expected['n_toward_target']/denominator if denominator else None,'directional toward rate')
    edges=table('B2_edge_opinion_similarity')
    if len(edges)!=3*(h+1):raise ValueError('edge metric row coverage')
    for row in edges:
        expected=result['edges'][integer(row['round']),row['edge_scope']]
        for field in ('n_edges','same_stance_fraction','mean_abs_distance','assortativity'):compare(row[field],expected[field],field)
    for row in table('B2_permutation_baselines'):
        if row['permutation_mode']!='unrestricted':continue
        expected=result['edges'][integer(row['round']),row['edge_scope']]['expected_same_stance_fraction']
        compare(row['expected_same_stance_fraction'],expected,'analytical unrestricted baseline')
    receipt=json.loads((analysis/'analysis-verification.json').read_bytes())
    for filename,digest in receipt['tables'].items():
        if sha(analysis/filename)!=digest:raise ValueError('analysis table SHA mismatch')
    for filename,digest in receipt['signature']['inputs'].items():
        if sha(canonical/filename)!=digest:raise ValueError('canonical input SHA mismatch')
    return dict(meta=run['meta'],n_agents=n,n_events=result['events'],n_feed_slots=result['feed_slots'],
                snapshots_checked=result['snapshots_checked'],numeric_comparisons=checks,passed=True,
                canonical=str(canonical),analysis=str(analysis))


def verify_all(root):
    root=Path(root);completed=[]
    for path in sorted((root/'canonical').rglob('initial.json')):
        relative=path.parent.relative_to(root/'canonical')
        completed.append(verify_run(path.parent,root/'analysis-v1/runs'/relative))
    coverage=Counter((r['meta']['topic_key'],int(r['meta']['horizon'])) for r in completed)
    expected={('retirement',30):60,('retirement',60):18,('gm-market-support',60):12,('genai-net-job-loss',60):12}
    if dict(coverage)!=expected:raise ValueError('incomplete 60 T30 + 42 T60 horizon coverage')
    keys=[(r['meta']['topic_key'],int(r['meta']['matched_seed']),r['meta']['cell_id'],int(r['meta']['horizon'])) for r in completed]
    expected_keys=set()
    for topic,seeds,horizon in [('retirement',range(20261201,20261211),30),('retirement',range(20261201,20261204),60),
        ('gm-market-support',range(20261201,20261203),60),('genai-net-job-loss',range(20261201,20261203),60)]:
        expected_keys.update((topic,seed,f'SIS-A{a}-B{b}',horizon) for seed in seeds for a in range(2) for b in range(3))
    if len(set(keys))!=len(keys) or set(keys)!=expected_keys:raise ValueError('matched seed/cell/horizon identity coverage mismatch')
    unique={}
    for r in completed:
        m=r['meta'];key=(m['topic_key'],m['matched_seed'],m['cell_id'])
        unique[key]=max(unique.get(key,0),r['n_events'])
    if sum(unique.values())!=1890000:raise ValueError('unique original-event coverage mismatch')
    return dict(schema='ica-independent-arithmetic-verification-v1',passed=True,horizon_trajectories=len(completed),
        unique_original_events=sum(unique.values()),horizon_events_including_reused_prefixes=sum(r['n_events'] for r in completed),
        numeric_comparisons=sum(r['numeric_comparisons'] for r in completed),model_requests=0,
        independence='stdlib implementation; no metrics imports; no new permutations',runs=completed,
        code_sha256=sha(__file__))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.resolve().parent!=args.root.resolve():raise ValueError('verification output must be directly inside controlled root')
    result=verify_all(args.root)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='runs'},ensure_ascii=False))


if __name__=='__main__':main()
