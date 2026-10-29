"""P0-C pure offline primitives: verified wire, independent M/O, text-blind sampling."""
from collections import Counter, defaultdict
import hashlib
import json


def decode_wire(wire, expected_sha256):
    if hashlib.sha256(wire).hexdigest()!=expected_sha256:
        raise ValueError('wire hash mismatch')
    request=json.loads(wire)
    if [m['role'] for m in request['messages']]!=['system','user']:
        raise ValueError('system/user role order differs')
    return json.loads(request['messages'][1]['content'])


def decode_code(code,p,m):
    if type(code) is not int or not 1<=code<=7 or type(p) is not int or p not in (0,1) or type(m) is not int or m not in (0,1):
        raise ValueError('exact integer code and binary factors required')
    q=8-code if m else code
    return 8-q if p else q


def options(p,m,o):
    if type(o) is not int or o not in (0,1):
        raise ValueError('binary order required')
    values=[]
    for q in range(1,8):
        code=8-q if m else q
        values.append(dict(agreement=q,code=code,semantic=decode_code(code,p,m)))
    return list(reversed(values)) if o else values


def categories(row):
    before,after,feed=row['before'],row['after'],row['feed_length']
    if any(type(v) is not int or not 1<=v<=7 for v in (before,after)) or type(feed) is not int or feed<0:
        raise ValueError('invalid event scores/feed length')
    result=[]
    if before==5 and after==3:result.append('5_to_3')
    if before==3 and after==5:result.append('3_to_5')
    if before==after==3:result.append('stay_3')
    if before==after==5:result.append('stay_5')
    distance=lambda y:min(abs(y-3),abs(y-5))
    if before in (1,2,6,7) and distance(after)<distance(before):result.append('extreme_toward_3_or_5')
    if feed==0 and before!=after:result.append('empty_changed')
    if feed>0 and before==after:result.append('nonempty_unchanged')
    return tuple(result)


def sample_events(rows,quota=48,seed=20261029):
    """Exact full frame, hashed round-robin strata; never reads free text.

    Seven categories overlap. quota is per category, not a population-proportional
    sample. Sparse whole categories smaller than quota are censused. Full frame
    denominators must be used instead of sample frequencies for descriptive rates.
    """
    if type(quota) is not int or quota<1:raise ValueError('positive quota required')
    counts=Counter();reservoir=defaultdict(list);seen=set()
    rank=lambda s:hashlib.sha256((str(seed)+'\0'+s).encode()).hexdigest()
    for row in rows:
        eid=row['event_id']
        if eid in seen:raise ValueError('duplicate event identity')
        seen.add(eid)
        for category in categories(row):
            key=(category,str(row['topic']),str(row['seed']),row['cell'],str(row['window']),
                 str(row['before']),str(row['after']),'empty' if row['feed_length']==0 else row.get('feed_direction','nonempty'))
            counts[key]+=1
            items=reservoir[key]
            candidate=(rank(eid),eid)
            if len(items)<quota:items.append(candidate);items.sort()
            elif candidate<items[-1]:items[-1]=candidate;items.sort()
    selected=set();sample_counts=Counter();memberships=defaultdict(list)
    for category in sorted({k[0] for k in counts}):
        keys=sorted((k for k in counts if k[0]==category),key=lambda k:rank(json.dumps(k)))
        chosen=0
        for depth in range(quota):
            for key in keys:
                if depth>=len(reservoir[key]):continue
                eid=reservoir[key][depth][1]
                selected.add(eid);sample_counts[key]+=1;memberships[eid].append(category);chosen+=1
                if chosen==quota:break
            if chosen==quota:break
    fields=('category','topic','seed','cell','window','before','after','feed_class')
    frame=[dict(zip(fields,key),population=count,sampled=sample_counts[key]) for key,count in sorted(counts.items())]
    return dict(selected_ids=sorted(selected),frame=frame,memberships=dict(memberships),
                all_events=len(seen),sampling_seed=seed,quota_per_category=quota)
