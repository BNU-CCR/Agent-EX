"""Prepare current-master exports; preserve all round-one artifacts."""
import collections,csv,json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1]
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.reader(f))
tables={p.stem:read(p) for p in [ROOT/'data/literature_master.csv',ROOT/'data/journals_master.csv',ROOT/'data/search_log.csv',ROOT/'data/conference_sources.csv']}
for name in ['method_venue_map','journal_submission_candidates','method_validation_matrix','venue_coverage_audit']:
 p=ROOT/'data'/f'{name}.csv'
 if p.exists():tables[name]=read(p)
heads=tables['literature_master'][0];records=[dict(zip(heads,r)) for r in tables['literature_master'][1:]]
counts=dict(records=len(records),status=dict(collections.Counter(r['screening_status'] for r in records)),method_tiers=dict(collections.Counter(r['method_relevance_tier'] for r in records)),fulltext_methods={t:sum(r['screening_status']=='included' and r['method_relevance_tier']==t for r in records) for t in ['core_method','method_validation','application','direct_comparator','peripheral']})
log_heads=tables['search_log'][0]
log_rows=[dict(zip(log_heads,row)) for row in tables['search_log'][1:]]
coverage_dates=[r['coverage_end'] for r in log_rows if re.fullmatch(r'\d{4}-\d{2}-\d{2}',r.get('coverage_end',''))]
assert coverage_dates,'No dated search coverage evidence'
counts.update(search_coverage_start='2022-01-01',search_coverage_end=max(coverage_dates))
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

# Keep preprints visible in a separate bibliography without mixing formal inclusion.
frontier=[]
for r in records:
 if r['screening_status']!='frontier':continue
 assert r['document_type']=='preprint',r['record_id']
 props={'title':'{'+esc(r['title'])+'}',
        'author':esc(' and '.join(x.strip() for x in r['authors'].split(';'))),
        'url':r['fulltext_url'] or r['official_url'],
        'howpublished':'Author preprint; formal publication not verified',
        'note':esc(r['record_id']+'; frontier; reading='+r['reading_status']+'; date='+r['date_eligibility'])}
 if r['date_eligibility']=='preprint_eligible' and re.match(r'^\d{4}',r['preprint_date']):
  props['year']=r['preprint_date'][:4]
 if r['doi']:props['doi']=r['doi']
 arxiv=re.search(r'arxiv\.org/(?:abs|html|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)',props['url'])
 if arxiv:props.update(archivePrefix='arXiv',eprint=arxiv.group(1))
 frontier.append('@misc{'+r['record_id']+',\n'+',\n'.join('  '+k+' = {'+v+'}' for k,v in props.items())+'\n}')
(ROOT/'exports/references_methods_frontier.bib').write_text('\n\n'.join(frontier)+'\n',encoding='utf8')
