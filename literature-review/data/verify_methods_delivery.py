"""Verify current artifacts against the immutable round-one baseline and change ledger."""
import collections,csv,hashlib,io,json,pathlib,subprocess
R=pathlib.Path(__file__).resolve().parents[1]
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def oldcsv(p):
 raw=subprocess.check_output(['git','show','d88ba3c:literature-review/'+p],cwd=R.parent)
 return list(csv.DictReader(io.StringIO(raw.decode('utf8'))))
m=json.loads((R/'data/round1_preservation_manifest.json').read_text(encoding='utf8'))
rs=read(R/'data/literature_master.csv');by={r['record_id']:r for r in rs};assert len(by)==len(rs)
ledger=json.loads((R/'data/method_change_ledger.json').read_text(encoding='utf8'))
for old in oldcsv('data/literature_master.csv'):
 new=by[old['record_id']]
 for k in m['original_fields']:
  if old[k]==new[k]:continue
  chain=[x for x in ledger if x['record_id']==old['record_id'] and x['field']==k]
  value=old[k]
  for change in chain:assert change['old']==value;value=change['new'];assert (R/change['source']).exists()
  assert value==new[k],(old['record_id'],k,'unlogged change')
for p,h in m['preserved_files'].items():assert hashlib.sha256((R/p).read_bytes()).hexdigest()==h,p
oldlog=oldcsv('data/search_log.csv');log=read(R/'data/search_log.csv');assert log[:231]==oldlog
assert len({x['search_id'] for x in log})==len(log),'duplicate search IDs'
from method_schema import TIERS,MATURITY,EVIDENCE,TAGS
dois=[]
for r in rs:
 assert r['method_relevance_tier'] in TIERS and r['method_maturity'] in MATURITY and r['method_evidence_level'] in EVIDENCE,r['record_id']
 assert set(r['method_contribution_type'].split(';'))<=TAGS,r['record_id']
 if r['method_coding_status']=='fulltext_supported':assert r['reading_status']=='fulltext_checked' and r['card_path'] and (R/r['card_path']).exists(),r['record_id']
 else:assert r['method_maturity']=='unclear' and r['method_evidence_level']=='unclear',r['record_id']
 if r['screening_status']=='included':assert r['date_eligibility']=='confirmed' and r['document_type']!='preprint',r['record_id']
 if r['doi']:dois.append(r['doi'].lower())
assert len(dois)==len(set(dois)),'duplicate DOI'
counts=json.loads((R/'data/methods_counts.json').read_text(encoding='utf8'));assert counts['records']==len(rs)
result=dict(checked='2026-11-26',records=len(rs),original_ids_preserved=len(m['record_ids']),original_files_hashed=len(m['preserved_files']),legacy_changes=len(ledger),search_rows=len(log),original_search_prefix_preserved=231,status=dict(collections.Counter(r['screening_status'] for r in rs)),method_tiers=dict(collections.Counter(r['method_relevance_tier'] for r in rs)),fulltext_cards=sum(bool(r['card_path']) for r in rs),date_pending=sum(r['date_eligibility']=='date_pending' for r in rs),checks='passed',limitations='No experiment rerun; workbook visual verification separate; not database coverage certification')
(R/'reports/methods_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False))
