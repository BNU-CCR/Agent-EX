"""Publish hashes and numeric properties of recovered cases, never private text."""
from collections import Counter
import argparse
import base64
import csv
import gzip
import hashlib
import json
from pathlib import Path

KEYWORDS=('保障','劳动','退休','延长','标识','安全','选择','消费者','替代','自动化','创造','新增','岗位','效率','成本')
sha=lambda b:hashlib.sha256(b).hexdigest()


def csv_write(path,rows):
    with path.open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def report(private,index,output):
    expected={r['event_id']:r for r in csv.DictReader(index.open(encoding='utf-8'))}
    evidence_root=private.parent.parent.parent
    profile_paths=[evidence_root/f'2026-10-25/cross-topic-n500-t60-v1/frozen-v1/run/inputs/{topic}/seed-{seed}/common.json'
        for topic in ('gm-market-support','genai-net-job-loss') for seed in (20261201,20261202)]
    cross_profiles={}
    for path in profile_paths:
        seed=int(path.parent.name.split('-')[1]);topic=path.parent.parent.name
        value=json.loads(path.read_text(encoding='utf-8'))
        cross_profiles[topic,seed]=value['payload']['adapter_binding']
    core_profile=evidence_root/'2026-10-22/core-service-v1/amendment.json'
    new_profile=evidence_root/'2026-10-25/cross-context-capacity-8192-v1/start-identity.json'
    old=json.loads(core_profile.read_text(encoding='utf-8'));new=json.loads(new_profile.read_text(encoding='utf-8'))
    if old['new_argv'][old['new_argv'].index('--max-model-len')+1]!='4096' or new['context_limit']!=8192:
        raise ValueError('historical context profile differs')
    profile_paths.extend([core_profile,new_profile])
    rows=[];slots=[];proofs=[];seen=set();casebook=['# C2真实事件个案库（匿名数值与内容hash）\n',
        '选择只使用数值和输入特征，不按理由内容。331个去重案例来自七个重叠类别；不是总体比例样本。完整理由与HTTP正文保存在私有受控归档，不在本册发布。关键词仅为字面出现，不是论据强度或因果解释。\n']
    with gzip.open(private,'rt',encoding='utf-8') as f:
        for line in f:
            record=json.loads(line)
            if record['kind']=='source_proof':
                if record['source_sha256_before']!=record['source_sha256_after'] or not record['read_only']:
                    raise ValueError('source mutation proof')
                proofs.append(record);continue
            s=record['sample'];eid=s['event_id']
            if eid in seen or s!=expected[eid]:raise ValueError('sample identity/exact metadata differs')
            seen.add(eid);saved=record['saved_evidence'];response=saved['response_saved'];tr=response['transport_evidence']
            wire=base64.b64decode(tr['request_body_base64'],validate=True)
            if sha(wire)!=record['actual_wire_sha256'] or sha(wire)!=tr['request_body_sha256']:
                raise ValueError('actual wire differs')
            actual=json.loads(wire);user=json.loads(actual['messages'][1]['content']);e=record['input_evidence']
            if actual['messages']!=e['exact_messages_shown']:raise ValueError('saved/actual messages differ')
            labels=user['allowed_stance_labels'];scores={v:i+1 for i,v in enumerate(labels)}
            if scores[record['pre_state']['stance_label']]!=int(s['before']) or scores[record['post_label']]!=int(s['after']):
                raise ValueError('original label mapping differs')
            if 'update_saved' in saved:post_reason=saved['update_saved']['reason']
            else:post_reason=saved['commit_saved']['result']['trace']['payload']['proposed_private_update']['reason']
            pre_reason=record['pre_state']['reason']
            selected={v['post_id']:v for v in record['selection']['selected']}
            feed_text=[];ages=[];feed_scores=[]
            for slot,(msg,shown) in enumerate(zip(user['social_messages'],e['shown_posts'],strict=True)):
                if any(msg[k]!=shown[k] for k in ('member_id','stance','reason')):
                    raise ValueError('wire displayed feed content/order differs')
                post=selected[shown['post_id']];feed_scores.append(scores[msg['stance']]);feed_text.append(msg['reason'])
                ages.append(post['message_age'])
                group=e['source_groups'][slot] if slot<len(e['source_groups']) else None
                slots.append(dict(event_id=eid,display_slot=slot,source_anon=sha((s['topic']+s['seed']+post['source_agent_id']).encode())[:20],
                    source_semantic=scores[msg['stance']],source_publication_ordinal=post['source_event_ordinal'],
                    message_age=post['message_age'],is_round0=post['is_round0'],source_group_backend=group,
                    model_visible_source_group=msg.get('source_group','not_shown'),
                    model_visible_extra_keys=json.dumps(sorted(set(msg)-{'member_id','stance','reason'})),
                    text_sha256=sha(msg['reason'].encode()),text_characters=len(msg['reason']),
                    lexical_flags=';'.join(k for k in KEYWORDS if k in msg['reason'])))
            if len(feed_scores)!=int(s['feed_length']):raise ValueError('actual feed count differs')
            identity=record['model_identity']
            if s['source_version']=='retirement-tail-20261025':
                identity=saved['contract_saved']['parent']['model_renderer_sampling_identity']['adapter_binding']
            elif s['source_version']=='cross-topic-20261025':
                profile=cross_profiles[s['topic'],int(s['seed'])]
                if profile['record_hash']!=identity['adapter_binding_hash']:
                    raise ValueError('actual adapter identity differs from source profile')
                identity=profile
            row={k:s[k] for k in ('event_id','topic','source_version','seed','cell','ordinal','initial_stance','before','after',
                'feed_length','feed_direction','activation_before','prior_exposure_slots','selected_categories')}
            row.update(agent_anon=sha((s['topic']+s['seed']+s['agent_id']).encode())[:20],
                actual_wire_sha256=sha(wire),before_reason_sha256=sha(pre_reason.encode()),after_reason_sha256=sha(post_reason.encode()),
                actual_memory_entries=len(user['memory']),source_renderer=e['renderer_version'],
                actual_model_name=actual['model'],model_revision=identity['model_revision'],
                historical_context_cap=8192 if s['source_version']=='cross-topic-20261025' else 4096,
                context_scope='historical service profile, not token count serialized in HTTP request',
                source_db_sha256=record['source_db_sha256'],feed_sum=sum(feed_scores),
                feed_age_min=min(ages) if ages else '',feed_age_max=max(ages) if ages else '',
                actual_private_update_count_before=record['pre_state']['successful_update_count'],
                publish_flag=s['published'],new_public_semantic=s['after'] if str(s['published']).lower()=='true' else '',
                lexical_feed_flags=';'.join(k for k in KEYWORDS if any(k in t for t in feed_text)))
            rows.append(row)
            casebook.extend([f"## {eid}\n",
                f"{s['topic']} / seed{s['seed']} / {s['cell']} / ordinal{s['ordinal']}；R0={s['initial_stance']}，事件前后{s['before']}→{s['after']}。类别：{s['selected_categories']}。",
                f"实际feed {len(feed_scores)}条，显示顺序分数{feed_scores}；此前实际曝光槽位{s['prior_exposure_slots']}，此前模型激活{s['activation_before']}（不含Round0），实际输入记忆{len(user['memory'])}条。发布标志{s['published']}。",
                f"feed字面词标记：{row['lexical_feed_flags'] or '未命中预设词表'}；不等同于论据主题的人工编码。actual wire SHA `{sha(wire)}`。\n"])
    if seen!=set(expected) or sum(p['selected_events'] for p in proofs)!=len(rows):
        raise ValueError('recovery coverage incomplete')
    output.mkdir(parents=True,exist_ok=False)
    csv_write(output/'sampled_material_features.csv',sorted(rows,key=lambda r:r['event_id']))
    csv_write(output/'sampled_feed_slots.csv',sorted(slots,key=lambda r:(r['event_id'],r['display_slot'])))
    (output/'event_casebook.md').write_text('\n\n'.join(casebook),encoding='utf-8')
    verified=dict(schema='p0c.sample.recovery.v1',sampled_events=len(rows),source_dbs=len(proofs),
        actual_feed_slots=len(slots),actual_wire_replayed=True,all_sources_unchanged=True,
        private_archive_sha256=sha(private.read_bytes()),sample_index_sha256=sha(index.read_bytes()),
        raw_text_published=False,round0_update_offset=1,source_proofs=proofs)
    verified['historical_profile_files']={str(p):sha(p.read_bytes()) for p in profile_paths}
    (output/'sample_recovery_verification.json').write_text(json.dumps(verified,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({k:verified[k] for k in ('sampled_events','source_dbs','actual_feed_slots','actual_wire_replayed','all_sources_unchanged')},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('private',type=Path);p.add_argument('index',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();report(a.private,a.index,a.output)
