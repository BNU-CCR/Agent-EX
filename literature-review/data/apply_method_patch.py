"""Apply a reviewed, fingerprinted research batch without rebuilding historical rows."""
import csv,hashlib,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:
  r=csv.DictReader(f);return r.fieldnames,list(r)
def write(p,h,rows):
 with p.open('w',encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,h);w.writeheader();w.writerows(rows)
def apply(relative):
 folder=(ROOT/relative).resolve();assert folder.is_relative_to(ROOT/'batches'),folder
 source=folder/'results.json';batch=json.loads(source.read_text(encoding='utf-8-sig'))
 p=ROOT/'data/literature_master.csv'
 assert hashlib.sha256(p.read_bytes()).hexdigest()==batch['expected_master_sha256'],'Stale batch: review current master before applying'
 fields,rows=read(p);by={r['record_id']:r for r in rows}
 manifest=json.loads((ROOT/'data/round1_preservation_manifest.json').read_text(encoding='utf8'))
 lp=ROOT/'data/method_change_ledger.json';ledger=json.loads(lp.read_text(encoding='utf8'))
 hp=ROOT/'data/method_coding_history.json';history=json.loads(hp.read_text(encoding='utf8')) if hp.exists() else []
 for patch in batch.get('updates',[]):assert patch['record_id'] in by,patch['record_id']
 for new in batch.get('new_records',[]):
  assert new['record_id'] not in by,new['record_id']
  assert not any(new.get('doi') and x['doi'].lower()==new['doi'].lower() for x in rows),'Duplicate DOI'
  row={k:'' for k in fields};row['record_id']=new['record_id'];rows.append(row);by[new['record_id']]=row
 for patch in batch.get('updates',[])+batch.get('new_records',[]):
  rid=patch['record_id'];target=by[rid]
  assert set(patch)<=set(fields),'Unknown schema field'
  if patch.get('card_path'):assert (ROOT/patch['card_path']).is_file()
  for k,v in patch.items():
   assert isinstance(v,str),(rid,k)
   if target[k]==v:continue
   change=dict(record_id=rid,field=k,old=target[k],new=v,date=batch['date'],batch=batch['batch_id'],reason='Audited new source/reading evidence; no experiment execution',source=source.relative_to(ROOT).as_posix())
   if rid in manifest['record_ids'] and k in manifest['original_fields']:ledger.append(change)
   if k.startswith('method_'):history.append(change)
   target[k]=v
 sh,logs=read(ROOT/'data/search_log.csv');ids={x['search_id'] for x in logs}
 for q in json.loads((folder/'source_operations.json').read_text(encoding='utf8')):
  assert q['search_id'] not in ids,q['search_id']
  row={k:'' for k in sh};row.update(venue_id='methods',coverage_start='2022-01-01',coverage_end=batch['date'],query_fields='public source operation; totals not supplied',export_path=(folder/'source_operations.json').relative_to(ROOT).as_posix())
  row.update({k:str(v) for k,v in q.items() if k in sh});logs.append(row);ids.add(row['search_id'])
 write(p,fields,rows);write(ROOT/'data/search_log.csv',sh,logs)
 lp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf8');hp.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding='utf8')
 print(batch['batch_id'],len(rows),'records;',len(logs),'source/search operations')
if __name__=='__main__':apply(sys.argv[1])
