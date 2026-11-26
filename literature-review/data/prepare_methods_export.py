"""Prepare current-master exports; preserve all round-one artifacts."""
import collections,csv,json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1]
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.reader(f))
tables={p.stem:read(p) for p in [ROOT/'data/literature_master.csv',ROOT/'data/journals_master.csv',ROOT/'data/search_log.csv',ROOT/'data/conference_sources.csv']}
for name in ['method_venue_map','journal_submission_candidates']:
 p=ROOT/'data'/f'{name}.csv'
 if p.exists():tables[name]=read(p)
heads=tables['literature_master'][0];records=[dict(zip(heads,r)) for r in tables['literature_master'][1:]]
counts=dict(records=len(records),status=dict(collections.Counter(r['screening_status'] for r in records)),method_tiers=dict(collections.Counter(r['method_relevance_tier'] for r in records)),fulltext_methods={t:sum(r['screening_status']=='included' and r['method_relevance_tier']==t for r in records) for t in ['core_method','method_validation','application','direct_comparator','peripheral']})
tables['counts']=counts
(ROOT/'exports/methods_workbook_input.json').write_text(json.dumps(tables,ensure_ascii=False),encoding='utf8')
(ROOT/'data/methods_counts.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf8')
def esc(s):return str(s).replace('&','\\&').replace('%','\\%').replace('_','\\_')
out=[]
for r in records:
 if r['screening_status']!='included':continue
 typ='inproceedings' if r['document_type']=='conference_paper' else 'article'
 props={'title':'{'+esc(r['title'])+'}','author':esc(' and '.join(x.strip() for x in r['authors'].split(';'))),'year':r['online_first_date'][:4] or r['volume_year'],'booktitle' if typ=='inproceedings' else 'journal':esc(r['venue']),'url':r['official_url'],'note':r['record_id']+'; methods-first review; '+r['method_relevance_tier']}
 if r['doi']:props['doi']=r['doi']
 out.append('@'+typ+'{'+r['record_id']+',\n'+',\n'.join('  '+k+' = {'+v+'}' for k,v in props.items())+'\n}')
(ROOT/'exports/references_methods.bib').write_text('\n\n'.join(out)+'\n',encoding='utf8');print(json.dumps(counts,ensure_ascii=False))
