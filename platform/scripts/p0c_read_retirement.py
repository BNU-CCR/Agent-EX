"""Remote read-only numeric stream for seven previously unexported T30 seeds.

Executed with python -B -c from trusted source bytes; writes only stdout.
Never imports a runtime, dispatches HTTP, creates a DB or changes a service.
"""
import hashlib
import json
from pathlib import Path
import sqlite3


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def emit(value):
    print(json.dumps(value,separators=(',',':'),ensure_ascii=True),flush=True)


root=Path('/root/autodl-tmp/agent-ex-core-run-20261022-v1')
for seed in range(20261204,20261211):
    expected=json.loads((root/f'finalized/seed-{seed}/verification.json').read_text())
    run_ids={r['cell_id']:r['run_id'] for r in expected['runs']}
    for a in range(2):
        for b in range(3):
            cell=f'SIS-A{a}-B{b}';path=root/f'research/seed-{seed}/{cell}/run.sqlite3'
            if any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal')):
                raise ValueError('source sidecars present')
            before_hash=digest(path)
            conn=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
            conn.execute('PRAGMA query_only=ON')
            try:
                binding=conn.execute('SELECT run_id FROM binding').fetchone()[0]
                if binding!=run_ids[cell]:raise ValueError('run identity differs from original verification')
                progress=conn.execute('SELECT next_event_ordinal,succeeded_event_count FROM progress').fetchone()
                if progress!=(15000,15000):raise ValueError('run not complete')
                if conn.execute("SELECT COUNT(*) FROM attempts WHERE status!='succeeded'").fetchone()[0]:
                    raise ValueError('non-succeeded original core attempts')
                first=json.loads(conn.execute('SELECT payload FROM event_input_evidence LIMIT 1').fetchone()[0])
                labels=first['sis_input']['topic_package']['stance_labels']
                scores={label:i+1 for i,label in enumerate(labels)}
                initial={}
                for raw, in conn.execute('SELECT payload_json FROM private_updates WHERE event_ordinal IS NULL'):
                    item=json.loads(raw);initial[item['agent_id']]=scores[item['stance_label']]
                if len(initial)!=500:raise ValueError('Round0 roster incomplete')
                emit(dict(kind='run_start',seed=seed,cell=cell,run_id=binding,db_sha256=before_hash,
                          renderer=first['sis_input']['prompt']['evidence']['renderer_version'],
                          source_path=str(path),source_version='retirement-t30-20261022'))
                seen=0
                query='''SELECT e.event_ordinal,e.payload_json,e.payload_hash,
                    u.payload_json,u.payload_hash,i.payload FROM events e
                    JOIN private_updates u ON u.event_ordinal=e.event_ordinal
                    JOIN event_input_evidence i ON i.event_id=e.event_id ORDER BY e.event_ordinal'''
                for ordinal,event_raw,event_hash,update_raw,update_hash,input_raw in conn.execute(query):
                    if ordinal!=seen:raise ValueError('event cursor gap')
                    if hashlib.sha256(event_raw.encode()).hexdigest()!=event_hash or hashlib.sha256(update_raw.encode()).hexdigest()!=update_hash:
                        raise ValueError('saved event/update payload hash differs')
                    event=json.loads(event_raw);update=json.loads(update_raw);saved=json.loads(input_raw)['sis_input']
                    if event['agent_id']!=saved['receiver_agent_id'] or event['event_id']!=saved['event_id']:
                        raise ValueError('event/input receiver identity differs')
                    e=saved['prompt']['evidence'];posts=e['shown_posts']
                    feeds=[scores[p['stance']] for p in posts]
                    previous=scores[saved['pre_state']['stance_label']]
                    after=scores[update['stance_label']]
                    n=len(feeds);direction='empty' if not n else ('lower' if sum(feeds)<previous*n else 'higher' if sum(feeds)>previous*n else 'equal')
                    emit(dict(kind='event',topic='retirement',seed=seed,cell=cell,run_id=binding,ordinal=ordinal,
                        agent_id=event['agent_id'],initial_stance=initial[event['agent_id']],before=previous,after=after,
                        feed_length=n,feed_direction=direction,feed=feeds,
                        published=event['publish_flag'],activation_before=saved['pre_state']['successful_update_count']))
                    seen+=1
                if seen!=15000:raise ValueError('source coverage incomplete')
            finally:conn.close()
            after_hash=digest(path)
            if after_hash!=before_hash:raise ValueError('source DB changed during read-only export')
            emit(dict(kind='run_end',seed=seed,cell=cell,run_id=binding,events=seen,db_sha256=after_hash))
