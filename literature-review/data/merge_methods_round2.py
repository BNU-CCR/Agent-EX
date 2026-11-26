"""Merge audited method batches; preserve IDs and log every changed original field."""
import csv,json,pathlib,shutil,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:
  d=csv.DictReader(f);return d.fieldnames,list(d)
def write(p,h,rs):
 with p.open('w',encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,h);w.writeheader();w.writerows(rs)
def val(v):return '; '.join(v) if isinstance(v,list) else str(v) if not isinstance(v,str) else v
def run(stage):
 h,rows=read(ROOT/'data/literature_master.csv');by={r['record_id']:r for r in rows}
 manifest=json.loads((ROOT/'data/round1_preservation_manifest.json').read_text(encoding='utf8'))
 lp=ROOT/'data/method_change_ledger.json';ledger=json.loads(lp.read_text(encoding='utf8')) if lp.exists() else []
 batches=['b_mass','b_paradigm','b_odd','b_validation'] if stage=='B' else ['c_crossdisciplinary']
 mapping={'TMP-P01':'M005','TMP-P02':'M004','TMP-ODD01':'M010','TMP-ODD02':'M011','TMP-ODD03':'M012'}
 oldcards={'M003':'M003_card.md','M010':'TMP-ODD01_card.md','M011':'TMP-ODD02_card.md'}
 for name in batches:
  rel='batches/method_round2/'+name;d=json.loads((ROOT/rel/'results.json').read_text(encoding='utf-8-sig'))
  for item in d['records']:
   r=dict(item);r.update(r.pop('methods',{}));rid=mapping.get(r['record_id'],r['record_id']);r['record_id']=rid
   if name=='b_odd':
    r.update(online_first_date=r['date'],volume_year=(r.get('issue_date') or r['date'])[:4],date_basis='; '.join(r['date_evidence']),related_versions=r['version'],language='en',document_type='journal_article',screening_status='included' if r['reading_status']=='fulltext_read' else 'candidate',reading_status='fulltext_checked' if r['reading_status']=='fulltext_read' else 'abstract_checked',date_eligibility='confirmed',search_date='2026-11-26',search_id='S-M2-ODD-'+rid,source_batch=rel+'/results.json',supplement_status='not_checked',reason=r['include_reason'],research_object='research_methodology')
    if rid=='M003':r.update(date_eligibility='date_pending',screening_status='candidate',notes=val(r.get('notes',[]))+'; precise first-online date pending; July2026 issue is not first-online proof')
    if rid=='M012':r.update(date_eligibility='date_pending',notes=val(r.get('notes',[]))+'; institutional online date not publisher-confirmed; preserve issue2027 separately')
    if rid in oldcards:r['card_path']=rel+'/'+oldcards[rid]
   if r.get('suggested_screening_status'):r['screening_status']=r['suggested_screening_status']
   if rid not in by:
    assert not any(r.get('doi') and x['doi'].lower()==r['doi'].lower() for x in rows),rid+' duplicate DOI'
    target={k:'' for k in h};target.update(record_id=rid,work_id='W'+rid,venue_id=r.get('venue_id','V-'+r['venue'].upper().replace(' ','-')));rows.append(target);by[rid]=target
   target=by[rid]
   cp=r.get('card_path','')
   if cp:
    source=ROOT/cp;assert source.exists(),cp
    dest=ROOT/'reading-cards'/f'{rid}.md';assert not dest.exists() or rid not in manifest['record_ids'] or not target.get('card_path'),rid+' preserve existing card'
    shutil.copyfile(source,dest);r['card_path']='reading-cards/'+rid+'.md'
   for k,v in r.items():
    if k not in h:continue
    v=val(v)
    if rid in manifest['record_ids'] and k in manifest['original_fields'] and target[k]!=v:
     ledger.append(dict(record_id=rid,field=k,old=target[k],new=v,date='2026-11-26',batch=stage,reason='New fulltext/version evidence; original batch and Git baseline retained',source=rel+'/results.json'))
    target[k]=v
   if rid in mapping.values():target['work_id']='W'+rid
   if rid=='M005':target['date_eligibility']='preprint_eligible'
  searches=d.get('searches',d.get('search_log',[]))
  sh,srows=read(ROOT/'data/search_log.csv');existing={x['search_id'] for x in srows}
  for q in searches:
   q=dict(q);sid=q.get('search_id') or 'S-M2-'+q.get('query_id','')
   if sid in existing:continue
   row={k:'' for k in sh};row.update(search_id=sid,venue_id=q.get('venue_id','crossdisciplinary'),platform=q.get('platform',q.get('tool','public_web_search')),search_date='2026-11-26',coverage_start='2022-01-01',coverage_end='2026-11-26',query_exact=q.get('query_exact',q.get('exact_query',q.get('query',''))),query_fields=q.get('query_fields','public discovery or exact source; not licensed database coverage'),status=q.get('status','public_supplement_only'),source_url=q.get('source_url',q.get('selected','')),export_path=rel+'/results.json',notes=q.get('notes',q.get('result',q.get('source_scope','Total count not supplied; selected results only'))))
   for k in ['result_count','retrieved_count','screened_count']:
    if k in q:row[k]=q[k]
   srows.append(row);existing.add(sid)
  write(ROOT/'data/search_log.csv',sh,srows)
 write(ROOT/'data/literature_master.csv',h,rows);lp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf8')
 print(stage,len(rows),'records;',len(ledger),'legacy field changes logged')
if __name__=='__main__':run(sys.argv[1])
