import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tarfile

import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sources import normalize_database, save_canonical, load_canonical
from extract_originals import extracted_members


def fixture_database(path, temporal=False):
    labels = list('abcdefg')
    binding = dict(node_agent_ids=['x', 'y'], matched_seed=7, cell_id='SIS-A0-B1',
        topic_package={'stance_labels': labels},
        groups={'payload': {'memberships': {'x': 'Blue', 'y': 'Green'}}},
        randomized={'payload': {'edges': [[0, 1]]}}, ws={'payload': {'edges': [[0, 1]]}})
    db = sqlite3.connect(path)
    if temporal:
        db.executescript('CREATE TABLE binding(contract_json); CREATE TABLE attempts(ordinal,prepared_json,status); CREATE TABLE commits(ordinal,payload_json); CREATE TABLE snapshots(ordinal,payload_json);')
        db.execute('INSERT INTO binding VALUES(?)', (json.dumps({'run_id':'r','start_event_ordinal':0,'end_event_ordinal_exclusive':2}),))
        db.execute('INSERT INTO snapshots VALUES(0,?)', (json.dumps({'private':{'x':1,'y':2},'public':{'x':1,'y':2}}),))
        for k, agent, before, after in [(0,'x','a','c'),(1,'y','b','b')]:
            pre={'agent_id':agent,'stance_label':before,'reason':'old'}
            update={'agent_id':agent,'stance_label':after,'reason':'new','published':True}
            db.execute('INSERT INTO attempts VALUES(?,?,?)',(k,json.dumps({'payload':{'pre_state':pre,'publish_flag':True}}),'committed'))
            db.execute('INSERT INTO commits VALUES(?,?)',(k,json.dumps({'result':{'trace':{'payload':{'pre_state':pre,'proposed_private_update':update}},'selection':{'selected':[]}}})))
        db.execute('INSERT INTO snapshots VALUES(2,?)',(json.dumps({'private':{'x':3,'y':2},'public':{'x':3,'y':2}}),))
    else:
        db.executescript('CREATE TABLE binding(manifest_payload_json); CREATE TABLE events(event_ordinal,event_id,status,payload_json); CREATE TABLE private_updates(agent_id,event_ordinal,payload_json); CREATE TABLE event_input_evidence(event_id,payload); CREATE TABLE public_posts(event_ordinal,payload_json); CREATE TABLE private_states(agent_id,payload_json);')
        db.execute('INSERT INTO binding VALUES(?)',(json.dumps({'run_id':'r','matched_seed':7,'model_identity':{'model':'fixture'},'run_spec':{'identity_network_binding':binding}}),))
        for agent,stance in [('x','a'),('y','b')]:
            db.execute('INSERT INTO private_updates VALUES(?,NULL,?)',(agent,json.dumps({'agent_id':agent,'stance_label':stance,'reason':'old'})))
            db.execute('INSERT INTO public_posts VALUES(NULL,?)',(json.dumps({'author_agent_id':agent,'stance_label':stance}),))
        for k,agent,before,after in [(0,'x','a','c'),(1,'y','b','b')]:
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(k,str(k),'succeeded',json.dumps({'agent_id':agent,'publish_flag':True})))
            db.execute('INSERT INTO private_updates VALUES(?,?,?)',(agent,k,json.dumps({'agent_id':agent,'stance_label':after,'published':True,'reason':'new'})))
            db.execute('INSERT INTO public_posts VALUES(?,?)',(k,json.dumps({'author_agent_id':agent,'stance_label':after})))
            selected=[] if k else [{'post_id':'p','source_agent_id':'y','stance_label':'b','source_event_ordinal':None,'display_slot':0,'public_reason':'feed'}]
            db.execute('INSERT INTO event_input_evidence VALUES(?,?)',(str(k),json.dumps({'sis_input':{'pre_state':{'agent_id':agent,'stance_label':before,'reason':'old'}},'causal_snapshot':{'payload':{'selection':{'selected':selected}}}})))
            db.execute('INSERT INTO private_states VALUES(?,?)',(agent,json.dumps({'stance_label':after})))
    db.commit();db.close()
    return binding


def test_normalizes_original_without_mutation(tmp_path,temporal):
    p=tmp_path/'raw.sqlite3';binding=fixture_database(p,temporal)
    before=hashlib.sha256(p.read_bytes()).hexdigest()
    run=normalize_database(p, binding=binding if temporal else None, topic_key='fixture',cohort='fixture',horizon=1)
    assert run['events']['after'].tolist()==[3,2]
    assert run['initial_stances']=={'x':1,'y':2}
    assert run['edges']==[('x','y')]
    assert before==hashlib.sha256(p.read_bytes()).hexdigest()
    assert run['source']['snapshot_match'] is True
    save_canonical(run,tmp_path/'canonical')
    restored=load_canonical(tmp_path/'canonical')
    assert restored['events']['published'].tolist()==[True,True]
    assert restored['meta']['horizon']==1


def test_rejects_broken_state_chain(tmp_path):
    p=tmp_path/'raw.sqlite3';fixture_database(p)
    db=sqlite3.connect(p); db.execute("UPDATE event_input_evidence SET payload=replace(payload,'\"stance_label\": \"a\"','\"stance_label\": \"g\"') WHERE event_id='0'");db.commit();db.close()
    with unittest.TestCase().assertRaisesRegex(ValueError,'pre-state'):
        normalize_database(p,topic_key='fixture',cohort='fixture',horizon=1)


def test_group_display_case_normalization(tmp_path):
    p=tmp_path/'raw.sqlite3';fixture_database(p)
    db=sqlite3.connect(p)
    row=json.loads(db.execute('SELECT manifest_payload_json FROM binding').fetchone()[0])
    row['run_spec']['identity_network_binding']['groups']['payload']['memberships']={'x':'blue','y':'green'}
    db.execute('UPDATE binding SET manifest_payload_json=?',(json.dumps(row),));db.commit();db.close()
    run=normalize_database(p,topic_key='fixture',cohort='fixture',horizon=1)
    assert run['groups']=={'x':'Blue','y':'Green'}


def test_stream_extract_hash_and_cleanup(tmp_path):
    archive=tmp_path/'a.tar.gz';payload=b'original'
    with tarfile.open(archive,'w:gz') as tar:
        info=tarfile.TarInfo('evidence/22');info.size=len(payload);tar.addfile(info,io.BytesIO(payload))
    spec=[{'member':'evidence/22','bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}]
    with extracted_members(archive,spec,tmp_path,headroom=0) as files:
        target=files['evidence/22'];assert target.read_bytes()==payload
    assert not target.exists()
    assert archive.exists()


class OriginalSourceTests(unittest.TestCase):
    def invoke(self,func,*args):
        with tempfile.TemporaryDirectory(prefix='ica-source-fixture-') as directory:
            func(Path(directory),*args)

    def test_core_original(self):self.invoke(test_normalizes_original_without_mutation,False)
    def test_temporal_original(self):self.invoke(test_normalizes_original_without_mutation,True)
    def test_broken_chain(self):self.invoke(test_rejects_broken_state_chain)
    def test_group_case(self):self.invoke(test_group_display_case_normalization)
    def test_bounded_extract(self):self.invoke(test_stream_extract_hash_and_cleanup)


if __name__=='__main__':unittest.main()
