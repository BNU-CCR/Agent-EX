import hashlib
import json
import pytest


def module():
    from agent_ex.diagnostics import p0c
    return p0c


def test_wire_is_verified_before_material_is_consumed():
    wire=json.dumps({'messages':[{'role':'system','content':'schema'},
        {'role':'user','content':json.dumps({'core_statement':'fixture'})}]}).encode()
    pin=hashlib.sha256(wire).hexdigest()
    assert module().decode_wire(wire,pin)['core_statement']=='fixture'
    with pytest.raises(ValueError,match='hash'):
        module().decode_wire(wire,'0'*64)


def test_mapping_and_order_are_independent_and_invertible():
    m=module()
    for p in (0,1):
        for mapping in (0,1):
            for order in (0,1):
                options=m.options(p,mapping,order)
                assert sorted(x['semantic'] for x in options)==list(range(1,8))
                assert sorted(x['code'] for x in options)==list(range(1,8))
                for x in options:
                    assert m.decode_code(x['code'],p,mapping)==x['semantic']
                if order:
                    assert options==list(reversed(m.options(p,mapping,0)))
                # O changes only order; M changes pairs, not semantic label order.
                if mapping:
                    assert [x['agreement'] for x in options]==[x['agreement'] for x in m.options(p,0,order)]


@pytest.mark.parametrize('value',[True,0,8,1.0])
def test_invalid_code_fails_closed(value):
    with pytest.raises(ValueError):module().decode_code(value,0,0)


def test_event_categories_use_pre_not_round_zero():
    m=module()
    row=dict(before=5,after=3,initial_stance=1,feed_length=0)
    assert m.categories(row)==('5_to_3','empty_changed')
    assert m.categories(dict(before=3,after=3,initial_stance=5,feed_length=2))==('stay_3','nonempty_unchanged')
    assert 'extreme_toward_3_or_5' in m.categories(dict(before=1,after=2,initial_stance=7,feed_length=1))


def test_sampling_is_order_and_text_independent_and_preserves_rare():
    m=module()
    rows=[dict(event_id=str(i),topic='a',seed=1,cell='b',window=0,
        before=5,after=3,initial_stance=1,feed_length=i%2,reason='sensitive '+str(i)) for i in range(8)]
    a=m.sample_events(rows,quota=3,seed=20261029)
    b=m.sample_events([dict(r,reason='different') for r in reversed(rows)],quota=3,seed=20261029)
    assert a['selected_ids']==b['selected_ids']
    assert 'reason' not in json.dumps(a)
    rare=m.sample_events(rows[:2],quota=3,seed=20261029)
    assert rare['selected_ids']==['0','1']
    assert sum(x['population'] for x in a['frame'] if x['category']=='5_to_3')==8


def test_duplicate_event_identity_rejected():
    row=dict(event_id='same',topic='a',seed=1,cell='b',window=0,before=5,after=3,initial_stance=5,feed_length=0)
    with pytest.raises(ValueError,match='duplicate'):module().sample_events([row,row])
