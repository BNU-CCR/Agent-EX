"""Private selected-event recovery. Source is executed remotely, stdout gzip only.

Caller supplies SAMPLES as trusted JSON from the frozen numeric index.
"""
from collections import defaultdict
import base64
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


groups=defaultdict(list)
for sample in SAMPLES:
    seed=int(sample['seed']);cell=sample['cell'];topic=sample['topic'];version=sample['source_version']
    if cell not in {f'SIS-A{a}-B{b}' for a in range(2) for b in range(3)} or not 20261201<=seed<=20261210:
        raise ValueError('invalid selected path identity')
    if topic=='retirement':
        if version=='retirement-t30-20261022':
            path=Path(f'/root/autodl-tmp/agent-ex-core-run-20261022-v1/research/seed-{seed}/{cell}/run.sqlite3')
        elif version=='retirement-tail-20261025' and seed<=20261203:
            path=Path(f'/root/autodl-tmp/agent-ex-temporal-run-20261025-v1/research/seed-{seed}/{cell}/extension.sqlite3')
        else:raise ValueError('retirement version differs')
    elif topic in ('gm-market-support','genai-net-job-loss') and seed<=20261202:
        path=Path(f'/root/autodl-tmp/agent-ex-cross-topic-run-20261025-v1/research/{topic}/seed-{seed}/{cell}/run.sqlite3')
    else:raise ValueError('topic outside authorization')
    groups[path].append(sample)

with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',mtime=0) as output:
    def emit(record):output.write((json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n').encode())
    for number,(path,samples) in enumerate(sorted(groups.items())):
        if any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal')):
            raise ValueError('source DB sidecars present')
        before=digest(path)
        conn=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
        conn.execute('PRAGMA query_only=ON')
        try:
            for sample in samples:
                ordinal=int(sample['ordinal']);core=sample['source_version']=='retirement-t30-20261022'
                if core:
                    binding=conn.execute('SELECT run_id FROM binding').fetchone()[0]
                    ev=conn.execute('SELECT event_id,payload_json,payload_hash FROM events WHERE event_ordinal=?',(ordinal,)).fetchone()
                    if not ev:raise ValueError('selected original event missing')
                    if hashlib.sha256(ev[1].encode()).hexdigest()!=ev[2]:raise ValueError('event hash differs')
                    saved=json.loads(conn.execute('SELECT payload FROM event_input_evidence WHERE event_id=?',(ev[0],)).fetchone()[0])
                    req=conn.execute('SELECT payload FROM adapter_requests WHERE event_id=?',(ev[0],)).fetchall()
                    if len(req)!=1:raise ValueError('expected unique original successful attempt')
                    request=json.loads(req[0][0]);aid=request['attempt_id']
                    response=json.loads(conn.execute('SELECT response_payload FROM invocation_evidence WHERE attempt_id=?',(aid,)).fetchone()[0])['response']
                    update=conn.execute('SELECT payload_json,payload_hash FROM private_updates WHERE event_ordinal=?',(ordinal,)).fetchone()
                    if hashlib.sha256(update[0].encode()).hexdigest()!=update[1]:raise ValueError('update hash differs')
                    private_update=json.loads(update[0]);event_input=saved['sis_input']
                    input_evidence=event_input['prompt']['evidence'];pre=event_input['pre_state']
                    selection=saved['causal_snapshot']['payload']['selection']
                    evidence=dict(input_saved=saved,request_saved=request,response_saved=response,
                        update_saved=private_update,event_saved=json.loads(ev[1]))
                    model_identity=request['model_identity']
                    after_label=private_update['stance_label']
                else:
                    contract=json.loads(conn.execute('SELECT contract_json FROM binding').fetchone()[0])
                    if sample['source_version']=='retirement-tail-20261025':
                        identity=contract['parent'];binding=identity['parent_run_id']
                    else:
                        identity=contract;binding=contract['run_id']
                    if identity['matched_seed']!=int(sample['seed']) or identity['cell_id']!=sample['cell']:
                        raise ValueError('selected contract identity mismatch')
                    row=conn.execute('SELECT prepared_json,response_json,status FROM attempts WHERE ordinal=?',(ordinal,)).fetchone()
                    if not row or row[2]!='committed':raise ValueError('selected tail/cross attempt not committed')
                    prepared=json.loads(row[0]);response=json.loads(row[1])
                    commit=json.loads(conn.execute('SELECT payload_json FROM commits WHERE ordinal=?',(ordinal,)).fetchone()[0])
                    event_input=prepared['payload'];input_evidence=event_input['input_evidence'];pre=event_input['pre_state']
                    selection=commit['result']['selection'];trace=commit['result']['trace']['payload']
                    after_label=trace['proposed_private_update']['stance_label']
                    model_identity=dict(adapter_binding_hash=event_input['request']['adapter_binding_hash'],
                                        scope='exact adapter binding hash retained; model revision not serialized directly here')
                    evidence=dict(contract_saved=contract,prepared_saved=prepared,response_saved=response,commit_saved=commit)
                transport=response['transport_evidence']
                wire=base64.b64decode(transport['request_body_base64'],validate=True)
                if hashlib.sha256(wire).hexdigest()!=transport['request_body_sha256'] or len(wire)!=transport['request_body_bytes']:
                    raise ValueError('actual transport wire hash/length mismatch')
                actual=json.loads(wire);messages=actual['messages']
                if messages!=input_evidence['exact_messages_shown']:
                    raise ValueError('actual wire and prompt input evidence differ')
                user=json.loads(messages[1]['content']);labels=user['allowed_stance_labels'];score={v:i+1 for i,v in enumerate(labels)}
                if score[pre['stance_label']]!=int(sample['before']) or score[after_label]!=int(sample['after']):
                    raise ValueError('numeric index/source pre-post mismatch')
                if len(user['social_messages'])!=int(sample['feed_length']):raise ValueError('actual feed length differs')
                # Stored successful updates include the initialized Round0 update;
                # numeric activation_before counts only completed modeled events.
                if int(pre['successful_update_count'])!=int(sample['activation_before'])+1:
                    raise ValueError('activation history differs after explicit Round0 offset')
                emit(dict(kind='private_event',sample=sample,actual_run_id=binding,actual_wire_sha256=transport['request_body_sha256'],
                    input_evidence=input_evidence,pre_state=pre,post_label=after_label,selection=selection,
                    actual_wire=actual,model_identity=model_identity,source_db=str(path),source_db_sha256=before,
                    saved_evidence=evidence))
        finally:conn.close()
        after=digest(path)
        if before!=after:raise ValueError('source changed during selected-event recovery')
        emit(dict(kind='source_proof',source_db=str(path),source_sha256_before=before,
                  source_sha256_after=after,selected_events=len(samples),read_only=True))
        print(f'verified selected source {number+1}/{len(groups)}',file=sys.stderr,flush=True)
