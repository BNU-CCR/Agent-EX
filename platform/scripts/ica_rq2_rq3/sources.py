"""Offline ORIGINAL SQLite reader. No runtime factories, network, or original writes.

Private reason records remain exclusively in the controlled canonical directory.
All ordinals are original global ordinals, including temporal continuation tails.
"""
from contextlib import contextmanager
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

import pandas as pd

EVENT_COLUMNS = ['ordinal','agent_id','before','after','published','reason_changed']
FEED_COLUMNS = ['ordinal','receiver_agent_id','display_slot','source_agent_id',
                'source_stance','publication_ordinal','post_id']


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


@contextmanager
def original_database(path, expected_sha256=None):
    path=Path(path).resolve(strict=True)
    if any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal')):
        raise ValueError('closed sidecar-free original database required')
    before=sha256(path)
    if expected_sha256 and before!=expected_sha256:
        raise ValueError('original SHA-256 mismatch')
    db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        yield db,before
    finally:
        db.close()
        if sha256(path)!=before:
            raise ValueError('original changed during read')


def _binding_metadata(binding, run_id, topic_key, cohort, horizon):
    nodes=binding['node_agent_ids']
    groups=binding['groups']['payload']['memberships']
    if isinstance(groups,list):
        groups={r['agent_id']:r['group'] for r in groups}
    # Display case only; preserve original membership exactly, reject other names.
    display={'blue':'Blue','green':'Green','Blue':'Blue','Green':'Green'}
    groups={agent:display[value] for agent,value in groups.items()}
    cell=binding['cell_id']
    graph=None if cell.endswith('B0') else binding['randomized' if cell.endswith('B1') else 'ws']['payload']
    edges=[] if graph is None else [(nodes[a],nodes[b]) for a,b in graph['edges']]
    return dict(meta=dict(topic_key=topic_key,matched_seed=binding['matched_seed'],cell_id=cell,
                         run_id=run_id,cohort=cohort,horizon=horizon),
                node_ids=nodes,groups=groups,edges=edges)


def normalize_database(path, *, topic_key, cohort, horizon, binding=None,
                       expected_sha256=None, parent=None, provenance=None):
    """Reconstruct actual events and selected historical posts; fail closed on drift.

    Temporal fresh runs require the archived input binding. Temporal tails require
    both that binding and a canonical parent RunData, never a duplicated prefix.
    """
    events=[];feeds=[];reasons=[];snapshots=[]
    with original_database(path,expected_sha256) as (db,digest):
        columns={r[1] for r in db.execute('PRAGMA table_info(binding)')}
        core='manifest_payload_json' in columns
        manifest=json.loads(db.execute('SELECT '+('manifest_payload_json' if core else 'contract_json')+' FROM binding').fetchone()[0])
        if core:
            binding=manifest['run_spec']['identity_network_binding']
        if binding is None:
            raise ValueError('archived input binding required for temporal database')
        labels=binding['topic_package']['stance_labels']
        if len(labels)!=7 or len(set(labels))!=7:
            raise ValueError('original seven-label topic order required')
        number={label:i+1 for i,label in enumerate(labels)}
        run_id=manifest.get('run_id') or manifest.get('parent',{}).get('parent_run_id')
        run=_binding_metadata(binding,run_id,topic_key,cohort,horizon)
        run['binding']=binding
        if parent is not None:
            if parent['node_ids']!=run['node_ids'] or parent['groups']!=run['groups'] or parent['edges']!=run['edges']:
                raise ValueError('tail-parent roster/group/graph mismatch')
            run['initial_stances']=dict(parent['initial_stances']);run['initial_public']=dict(parent['initial_public'])
            events=parent['events'].to_dict('records');feeds=parent['feed'].to_dict('records')
            reasons=list(parent.get('reasons',[]))
            state=dict(run['initial_stances']);public=dict(run['initial_public'])
            for e in events:
                state[e['agent_id']]=e['after']
                if e['published']:public[e['agent_id']]=e['after']
            snapshots=list(parent.get('snapshots',[]))
        elif core:
            initial=[json.loads(r[0]) for r in db.execute('SELECT payload_json FROM private_updates WHERE event_ordinal IS NULL')]
            run['initial_stances']={u['agent_id']:number[u['stance_label']] for u in initial}
            posts=[json.loads(r[0]) for r in db.execute('SELECT payload_json FROM public_posts WHERE event_ordinal IS NULL')]
            run['initial_public']={p['author_agent_id']:number[p['stance_label']] for p in posts}
            state=dict(run['initial_stances']);public=dict(run['initial_public'])
        else:
            initial_row=db.execute('SELECT payload_json FROM snapshots WHERE ordinal=0').fetchone()
            if initial_row is None:raise ValueError('fresh run missing original R0 snapshot')
            initial=json.loads(initial_row[0]);run['initial_stances']=initial['private'];run['initial_public']=initial['public']
            state=dict(initial['private']);public=dict(initial['public'])
        if set(state)!=set(run['node_ids']) or set(public)!=set(state):
            raise ValueError('incomplete initial roster')
        checkpoints={} if core else {k:json.loads(raw) for k,raw in db.execute('SELECT ordinal,payload_json FROM snapshots ORDER BY ordinal')}

        def check_snapshot(cursor):
            if cursor not in checkpoints:return
            snapshot=checkpoints[cursor]
            if snapshot['private']!=state or snapshot['public']!=public:
                raise ValueError('stored snapshot differs from event reconstruction')
            snapshots.append(snapshot)

        check_snapshot(len(events))
        if core:
            rows=db.execute('SELECT e.event_ordinal,e.status,e.payload_json,i.payload,u.payload_json FROM events e JOIN event_input_evidence i ON i.event_id=e.event_id JOIN private_updates u ON u.event_ordinal=e.event_ordinal ORDER BY e.event_ordinal')
        else:
            rows=db.execute('SELECT c.ordinal,a.status,a.prepared_json,c.payload_json FROM commits c JOIN attempts a ON a.ordinal=c.ordinal ORDER BY c.ordinal')
        start=len(events)
        for row in rows:
            ordinal,status=row[:2]
            if ordinal!=len(events):raise ValueError('successful event ordinal gap/duplicate')
            if core:
                if status!='succeeded':raise ValueError('non-success event in original')
                event,inputs,update=map(json.loads,row[2:])
                pre=inputs['sis_input']['pre_state']; selected=inputs['causal_snapshot']['payload']['selection']['selected']
                prompt=inputs['sis_input'].get('prompt',{})
                published=update['published']
                if published!=event['publish_flag']:raise ValueError('publication flag mismatch')
            else:
                if status!='committed':raise ValueError('uncommitted original attempt')
                prepared,commit=map(json.loads,row[2:]);result=commit['result'];trace=result['trace']['payload']
                prompt={'evidence':prepared['payload'].get('input_evidence',{})}
                if not prompt:prompt=prepared['payload'].get('prompt',{})
                pre=trace['pre_state'];update=trace['proposed_private_update'];selected=result['selection']['selected']
                if update is None:raise ValueError('commit without proposed private update')
                published=update['published']
                if prepared['payload']['pre_state']!=pre or prepared['payload']['publish_flag']!=published:
                    raise ValueError('prepared/committed causal mismatch')
            agent=update['agent_id'];before=number[pre['stance_label']];after=number[update['stance_label']]
            if state[agent]!=before:raise ValueError('pre-state differs from last successful commit')
            before_reason=pre.get('reason');after_reason=update.get('reason')
            events.append(dict(ordinal=ordinal,agent_id=agent,before=before,after=after,published=published,
                               reason_changed=None if before_reason is None or after_reason is None else before_reason!=after_reason))
            reason_feed=[]
            shown=prompt.get('evidence',{}).get('shown_posts',[]) if isinstance(prompt,dict) else []
            shown_by_id={p['post_id']:p for p in shown}
            for post in selected:
                feeds.append(dict(ordinal=ordinal,receiver_agent_id=agent,display_slot=post['display_slot'],
                    source_agent_id=post['source_agent_id'],source_stance=number[post['stance_label']],
                    publication_ordinal=post['source_event_ordinal'],post_id=post['post_id']))
                reason_feed.append(dict(source_agent_id=post['source_agent_id'],post_id=post['post_id'],
                    stance=number[post['stance_label']],text=post.get('public_reason',post.get('reason',shown_by_id.get(post['post_id'],{}).get('reason')))))
            reasons.append(dict(ordinal=ordinal,before_reason=before_reason,after_reason=after_reason,feed=reason_feed))
            state[agent]=after
            if published:public[agent]=after
            check_snapshot(ordinal+1)
        if core:
            stored={a:number[json.loads(raw)['stance_label']] for a,raw in db.execute('SELECT agent_id,payload_json FROM private_states')}
            if state!=stored:raise ValueError('terminal stored private state mismatch')
            stored_public={}
            for (raw,) in db.execute('SELECT payload_json FROM public_posts ORDER BY event_ordinal'):
                post=json.loads(raw);stored_public[post['author_agent_id']]=number[post['stance_label']]
            if public!=stored_public:raise ValueError('terminal stored public state mismatch')
            snapshots.append(dict(next_event_ordinal=len(events),private=state.copy(),public=public.copy()))
        if len(events)!=len(state)*horizon:raise ValueError('event count differs from N*horizon')
        run.update(events=pd.DataFrame(events,columns=EVENT_COLUMNS),feed=pd.DataFrame(feeds,columns=FEED_COLUMNS),
                   snapshots=snapshots,reasons=reasons)
        component=dict(source_path=str(Path(path).resolve()),expected_sha256=expected_sha256,
                       actual_sha256=digest,sha256_unchanged_after_read=True,component_events=len(events)-start,
                       original_model_identity=manifest.get('model_identity') or manifest.get('parent',{}).get('model_renderer_sampling_identity') or (provenance or {}).get('model_identity'),
                       provenance=provenance or {})
        components=[] if parent is None else list(parent['source']['components'])
        run['source']=dict(schema='ica-original-normalized-v1',components=components+[component],
                           snapshot_match=True,successful_events=len(events),actual_selected_feed_slots=len(feeds),
                           stored_snapshot_scope='terminal private/public state only; core has no archived per-round snapshots' if core else 'all stored numeric snapshots private/public checked',
                           stored_snapshot_count=1 if core else len(checkpoints))
        run['source']['group_display_normalization']={'blue':'Blue','green':'Green','Blue':'Blue','Green':'Green'}
    return run


def save_canonical(run,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    initial={k:v for k,v in run.items() if k not in ('events','feed','snapshots','reasons','source')}
    for name,value in [('initial',initial),('source',run['source']),('snapshots',run['snapshots'])]:
        (directory/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    run['events'].to_csv(directory/'events.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    run['feed'].to_csv(directory/'feed.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    with gzip.open(directory/'private-reasons.jsonl.gz','wt',encoding='utf-8') as stream:
        for row in run.get('reasons',[]):stream.write(json.dumps(row,ensure_ascii=False)+'\n')


def load_canonical(directory, *, include_reasons=False):
    directory=Path(directory);run=json.loads((directory/'initial.json').read_bytes())
    run['edges']=[tuple(edge) for edge in run['edges']]
    run['source']=json.loads((directory/'source.json').read_bytes())
    run['snapshots']=json.loads((directory/'snapshots.json').read_bytes())
    run['events']=pd.read_csv(directory/'events.csv.gz')
    run['feed']=pd.read_csv(directory/'feed.csv.gz')
    if include_reasons:
        with gzip.open(directory/'private-reasons.jsonl.gz','rt',encoding='utf-8') as stream:
            run['reasons']=[json.loads(line) for line in stream]
    return run
