"""Read exact saved P0-B wires. Public output contains no full prompt/reason text."""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
from agent_ex.diagnostics.p0c import decode_wire

LEDGER='8e4c2ea9b084f09f3bf40ca2e17a798a032a2036945ddfd7d5cdcce7e85c1caf'
CASES='78618901ea876decfef00c0a8cf74c7108059fad5b316db18485e3719f9eead9'
NUMERIC='36f3db1a6fcc1b0f5519e0d49baffbe4960f814bc88434ea085147471b731fe3'
sha=lambda b:hashlib.sha256(b).hexdigest()


def write_csv(path,rows):
    with path.open('x',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def audit(evidence,output):
    restored=evidence/'private-evidence/restore-v1'
    ledger=restored/'run/ledger/ledger.sqlite3';cases=restored/'inputs/cases.json'
    if sha(ledger.read_bytes())!=LEDGER or sha(cases.read_bytes())!=CASES:
        raise ValueError('externally pinned input hash differs')
    records=json.loads(cases.read_text(encoding='utf-8'));by_id={c['case_id']:c for c in records}
    if sha((evidence/'public-numeric-v1/manifest.json').read_bytes())!=NUMERIC:
        raise ValueError('numeric manifest differs')
    numeric=list(csv.DictReader((evidence/'public-numeric-v1/cases.csv').open(encoding='utf-8')))
    numeric_pins=json.loads((evidence/'public-numeric-v1/manifest.json').read_text(encoding='utf-8'))
    # Numeric file's external manifest must itself bind the actual CSV.
    cases_entry=numeric_pins['files']['cases.csv']
    if type(cases_entry) is not str or sha((evidence/'public-numeric-v1/cases.csv').read_bytes())!=cases_entry:
        raise ValueError('numeric cases hash differs')
    inventories={};mapping={};propositions={};feeds={};sampling=set();system_hashes=set()
    conn=sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    conn.execute('PRAGMA query_only=ON');conn.row_factory=sqlite3.Row
    wire_count=0
    try:
        for row in conn.execute('SELECT case_id,wire,wire_sha256,state FROM attempts ORDER BY case_id'):
            c=by_id.pop(row['case_id'])
            if row['state']!='committed':raise ValueError('nonterminal source')
            payload=decode_wire(row['wire'],row['wire_sha256']);request=json.loads(row['wire'])
            expected=json.dumps(c['request'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
            if row['wire']!=expected:raise ValueError('saved wire differs from frozen request')
            wire_count+=1
            system_hashes.add(sha(request['messages'][0]['content'].encode()))
            sampling.add(json.dumps({k:v for k,v in request.items() if k not in ('messages','seed')},sort_keys=True))
            if c['kind']!='research':continue
            topic=c['topic'];p=int(c['reverse_proposition']);m=int(c['reverse_mapping'])
            labels=payload['allowed_stance_labels']
            if labels!=c['allowed_labels']:raise ValueError('wire options differ')
            codes=[int(label.split('｜')[0]) for label in labels]
            semantics=[c['original_semantic_by_label'][label] for label in labels]
            mapping[topic,p,m]=dict(topic=topic,p=p,m=m,display_codes=json.dumps(codes),
                semantic_order=json.dumps(semantics),label_list_sha256=sha(json.dumps(labels,ensure_ascii=False).encode()),
                numeric_mapping_changed=m,semantic_label_order_reversed=m,
                parser_rule='q=8-code if m else code; y=8-q if p else q')
            statement=payload['core_statement'];statement_hash=sha(statement.encode())
            propositions[topic,p]=dict(topic=topic,p=p,statement_sha256=statement_hash,characters=len(statement),
                operation='original' if not p else 'operational_opposition_not_proven_logical_complement',
                equality_note='AI negative includes equality; do not equate not-net-loss with net-gain' if topic=='genai-net-job-loss' else 'support/opposition wording, not measurement invariance')
            material=[('statement',statement),('fact_card',payload['fact_card']),
                      ('initial_reason',payload['current_private']['reason'])]
            for kind,text in material:
                key=(topic,kind,sha(text.encode()))
                inventories[key]=dict(topic=topic,kind=kind,anonymous_id='stimulus-'+key[2][:20],
                    text_sha256=key[2],characters=len(text),utf8_bytes=len(text.encode()),
                    pre_semantic=c['original_semantic_score'] if kind=='initial_reason' else '',
                    reason_index=c['reason_index'] if kind=='initial_reason' else '',
                    content_scope='private archive inputs/cases.json; exact saved wire equality verified')
            for slot,message in enumerate(payload['social_messages']):
                text=message['reason'];stance=c['original_semantic_by_label'][message['stance']]
                feeds[topic,p,m,c['feed'],slot]=dict(topic=topic,p=p,m=m,feed=c['feed'],display_slot=slot,
                    anonymous_source=message['member_id'],source_semantic=stance,text_sha256=sha(text.encode()),
                    characters=len(text),utf8_bytes=len(text.encode()),memory_entries=len(payload['memory']),
                    order_scope='actual wire array; no timestamp field; not inferred network chronology')
    finally:conn.close()
    if by_id or wire_count!=1526:raise ValueError('exact saved request cover differs')
    if sha(ledger.read_bytes())!=LEDGER:raise ValueError('source ledger changed')
    summary={}
    for topic in sorted({r['topic'] for r in numeric}):
        rows=[r for r in numeric if r['topic']==topic];none=[r for r in rows if r['feed']=='none']
        draws=defaultdict(list)
        for r in rows:draws[tuple(r[k] for k in ('pre_semantic','reason_index','p','m','feed'))].append(r['output_semantic'])
        summary[topic]=dict(no_feed_count=len(none),initial_retained=sum(r['pre_semantic']==r['output_semantic'] for r in none),
            output3=sum(r['output_semantic']=='3' for r in none),three_draw_groups=len(draws),
            all_three_same=sum(len(set(v))==1 for v in draws.values()))
    output.mkdir(parents=True,exist_ok=False)
    for name,values in [('stimulus_inventory',inventories),('mapping_and_order_audit',mapping),
                        ('proposition_reversal_audit',propositions),('feed_content_audit',feeds)]:
        write_csv(output/(name+'.csv'),list(values.values()))
    result=dict(schema='p0c.c1.wire.audit.v1',actual_wires_verified=wire_count,
        source_ledger_sha256=LEDGER,source_cases_sha256=CASES,numeric_manifest_sha256=NUMERIC,
        model_request_parameters=[json.loads(v) for v in sorted(sampling)],system_prompt_hashes=sorted(system_hashes),
        no_feed=summary,private_text_published=False,
        template_scope='HTTP messages verified; no saved server-side token IDs, cannot prove tokenized template from wire alone')
    (output/'c1_audit_verification.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('evidence',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();audit(args.evidence,args.output)
