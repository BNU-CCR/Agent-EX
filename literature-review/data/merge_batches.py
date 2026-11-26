"""Rebuild auditable CSV views from research batches; never infer unknown dates."""
import collections, csv, json, pathlib, re, shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]
def read(p): return json.loads((ROOT/p).read_text(encoding='utf-8-sig'))
def write_csv(name,rows,fields=None):
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with (ROOT/'data'/name).open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fields,extrasaction='ignore');writer.writeheader()
        for r in rows: writer.writerow({k:(';'.join(map(str,v)) if isinstance(v,list) else '' if v is None else v) for k,v in r.items()})
root=read('batches/crossdisciplinary/records.json'); en=read('batches/english/results.json');cn=read('batches/chinese/records.json');cat=read('batches/chinese/journals_catalog.json')
logs=read('batches/crossdisciplinary/search_log.json')+en['searches']+read('batches/chinese/search_log.json')
followup=ROOT/'batches/ccr_fulltext_followup/attempts.json'
if followup.exists():
    for i,a in enumerate(read('batches/ccr_fulltext_followup/attempts.json'),1):
        logs.append(dict(search_id=f'CCR-FOLLOW-{i:02}',venue_id='CCR',platform='official_metadata_or_fulltext_access',search_date='2026-11-26',coverage_start='2022-01-01',coverage_end='2026-11-26',query_exact='GET '+a['url'],query_fields='source_access_verification',result_count='',retrieved_count='',screened_count='',status='verification' if a.get('status')==200 else 'access_blocked',source_url=a['url'],export_path='batches/ccr_fulltext_followup/attempts.json',notes=a.get('error') or ('PDF obtained' if a.get('is_pdf') else 'Metadata or HTML only; no formal full text obtained')))
for i,r in enumerate(read('batches/crossdisciplinary/publisher_metadata.json'),1):
    logs.append(dict(search_id=f'S-X-META-{i:02}',venue_id='',platform='Crossref_publisher_deposit',search_date='2026-11-26',coverage_start='2022-01-01',coverage_end='2026-11-26',query_exact='GET '+r['source_url'],query_fields='DOI metadata verification',result_count='',retrieved_count=0 if r.get('error') else 1,screened_count=0 if r.get('error') else 1,status='access_blocked' if r.get('error') else 'verification',source_url=r['source_url'],export_path='batches/crossdisciplinary/publisher_metadata.json',notes=r.get('error','created is not publication date')))
records=[]
for batch,items in [('crossdisciplinary',root),('english',en['records']),('chinese',cn)]:
    for raw in items:
        r=dict(raw);rid=r['record_id'];r['source_batch']=f'batches/{batch}/'+('results.json' if batch=='english' else 'records.json')
        r['online_first_date']=r.get('online_first_date',r.get('online_date',''));r['volume_year']=r.get('volume_year',r.get('issue_year',''))
        r['date_basis']=r.get('date_basis',r.get('date_evidence',''));r['related_versions']=r.get('related_versions',r.get('version_relation',r.get('notes','')))
        r['research_object']=r.get('research_object',r.get('object',''));r['reason']=r.get('reason',r.get('include_reason',''))
        r['screening_status']=r.get('screening_status',r.get('inclusion_status','candidate'))
        eligibility=r.get('date_eligibility','date_pending')
        r['date_eligibility']={'eligible':'confirmed','eligible_year_only':'date_pending'}.get(eligibility,eligibility)
        r['fulltext_url']=r.get('fulltext_url',r.get('fulltext_source',''));r['supplement_status']=r.get('supplement_status',r.get('supplement_checked','not_checked'))
        if r['reading_status']=='fulltext_republication_read':
            r['reading_status']='fulltext_partial';r['notes']=r.get('notes','')+' Republication read, original version not checked; normalized to partial.'
        card=r.get('card_path',r.get('reading_card_path',''))
        if batch=='chinese' and (ROOT/f'batches/chinese/{rid}.md').exists():card=f'batches/chinese/{rid}.md'
        if batch=='crossdisciplinary' and (ROOT/f'reading-cards/{rid}.md').exists():card=f'reading-cards/{rid}.md'
        if card and (ROOT/card).exists():
            dest=ROOT/f'reading-cards/{rid}.md'
            if (ROOT/card).resolve()!=dest.resolve():shutil.copyfile(ROOT/card,dest)
            card=f'reading-cards/{rid}.md'
        r['card_path']=card
        if card:
            cardtext=(ROOT/card).read_text(encoding='utf-8-sig')
            question=re.search(r'## 2\..*?\n\n(.*?)(?=\n\n##|\Z)',cardtext,re.S) or re.search(r'^2\.\s+\*\*[^*]+\*\*[:：]?\s*(.+)$',cardtext,re.M)
            mechanism=re.search(r'## 3\..*?\n\n(.*?)(?=\n\n##|\Z)',cardtext,re.S) or re.search(r'^3\.\s+\*\*[^*]+\*\*[:：]?\s*(.+)$',cardtext,re.M)
            r['research_question']=question.group(1).strip() if question else r.get('research_question','待核实')
            if mechanism and r.get('mechanisms','') in ['', '待分主题补充']:r['mechanisms']=mechanism.group(1).strip()
        else:r.setdefault('research_question','待全文核查；拟对话问题：'+r['reason'])
        if rid=='R007':r.update(reading_status='fulltext_checked',evidence_location='PMC主文§1–4；§2.1–2.5，§3.2–3.6，Figs3–5')
        if rid=='R010':r['notes']=r.get('notes','')+' Official PDF/ACL/Crossref raw author Talwalkwar; TACL author page Talwalkar used as normalized name. Published-online 09-04 vs website09-07 retained.'
        if r['reading_status']!='fulltext_checked' and r['screening_status']=='included':r['screening_status']='candidate'
        if r['date_eligibility']=='date_pending' and r['screening_status']=='included':r['screening_status']='candidate'
        if r['reading_status']=='fulltext_checked' and not card:r['screening_status']='candidate';r['notes']=r.get('notes','')+' Fulltext card not yet complete.'
        if not r.get('venue_id'):
            match=next((v for v in en['journals'] if v['title']==r['venue']),None)
            r['venue_id']=match['venue_id'] if match else 'SUP-'+rid
        if not r.get('work_id'):r['work_id']='W-'+rid
        r['search_date']='2026-11-26'
        ids=r.get('search_ids',[])
        if not ids and r.get('search_id'):ids=r['search_id'].split(';')
        if not ids:
            title=r['title'];matches=[l['search_id'] for l in logs if title in l.get('query_exact','')]
            if not matches:matches=[l['search_id'] for l in logs if any(len(s)>=6 and s in title for s in re.findall(r'"([^"]+)"',l.get('query_exact',''))) ]
            if not matches:matches=[l['search_id'] for l in logs if l.get('venue_id')==r['venue_id']]
            if not matches:
                source=r.get('official_url') or r.get('metadata_evidence_url') or r.get('discovery_url','')
                sid='S-BATCH-'+rid
                logs.append(dict(search_id=sid,venue_id=r['venue_id'],platform='batch_source_verification_index',search_date='2026-11-26',coverage_start='2022-01-01',coverage_end='2026-11-26',query_exact='Source verification documented in batch: '+source,query_fields='batch evidence index; not a new search query',result_count='',retrieved_count=1,screened_count=1,status='verification',source_url=source,export_path=r['source_batch'],notes='Source reading already documented by worker; added during consolidation to connect record and source. Not a separately executed database search.'))
                matches=[sid]
            ids=matches
        r['search_id']=';'.join(ids)
        r.setdefault('relation_to_agent_ex',r['reason']);r.setdefault('notes','')
        r['research_object']={'human_social_process':'human_social_process_simulation','人类社会过程的模拟':'human_social_process_simulation','AI_collective_behavior':'ai_collective_behavior','AI群体行为':'ai_collective_behavior','其他':'other'}.get(r['research_object'],r['research_object'])
        purposemap={'方法评估':'method_evaluation','机制检验':'mechanism_test','理论探索':'theory_exploration','其他':'other','mechanism_exploration':'theory_exploration','theory_development':'theory_exploration','tool_development':'system_development'}
        purposes=list(dict.fromkeys(purposemap.get(x.strip(),x.strip()) for x in r['simulation_purpose'].split(';')))
        r['simulation_purpose']=';'.join(purposes);r['primary_purpose']=purposes[0]
        method=r['method_type'].lower()
        r['method_type']={'llm_multiagent':'llm_multiagent_social_simulation','traditional_rule_abm':'rule_based_abm','traditional_rule_abm_pending':'rule_based_abm_pending'}.get(method,method)
        records.append(r)
fields=['record_id','work_id','venue_id','title','authors','language','venue','document_type','doi','official_url','discovery_url','metadata_evidence_url','online_first_date','volume_year','preprint_date','date_basis','date_eligibility','related_versions','search_id','search_date','screening_status','core_level','reason','research_question','research_object','simulation_purpose','primary_purpose','method_type','mechanisms','reading_status','fulltext_url','supplement_status','findings','evidence_location','relation_to_agent_ex','card_path','source_batch','notes']
write_csv('literature_master.csv',records,fields)
journals=[]
for v in en['journals']:
    journals.append(dict(venue_id=v['venue_id'],title=v['title'],issn=v.get('issn',''),eissn=v.get('eissn',''),discipline=v['discipline'],language='en',index_type=v['index_type'],directory_version=v['directory_version'],index_source=v['index_source'],index_verification='pending_MJL',index_historical='',verification_date='2026-11-26',scope_type='communication_draft' if v['discipline']=='communication' else 'problem_led_supplement',coverage_start='2022-01-01',coverage_end='2026-11-26',coverage_status=v['status'],gap=v['gap']))
for v in cat['journals']:
    journals.append(dict(venue_id=v['venue_id'],title=v['title'],issn=v.get('issn',''),eissn=v.get('eissn',''),discipline=v['subject'],language='zh',index_type=v['index_type'],directory_version=v['catalog_version'],index_source=v['source_url'],index_verification=v['verification_status']+';direct_NJU_pending',index_historical='',verification_date='2026-11-26',scope_type='CSSCI_source_subject_catalog',coverage_start='2022-01-01',coverage_end='2026-11-26',coverage_status=v['search_status'],gap='Only public checks; authenticated CNKI title/abstract/keyword export and historical index pending; catalog p'+str(v['catalog_page'])+' row'+str(v['catalog_row'])))
existing={v['venue_id'] for v in journals}
for r in records:
    if r['document_type'] in ['conference_paper','preprint'] or r['venue_id'] in existing:continue
    index='current_index_pending';source=r.get('official_url','');verified='pending_specific_index'
    if r['venue_id']=='V-JASSS':index='SSCI';source='https://www.jasss.org/v02/page_content_includes/_include_about.html';verified='publisher_explicit;MJL_not_independently_verified'
    if r['venue_id']=='V-EPJDS':index='SCIE;SSCI';source='https://link.springer.com/journal/13688';verified='publisher_explicit;MJL_not_independently_verified'
    journals.append(dict(venue_id=r['venue_id'],title=r['venue'],issn='',eissn='2193-1127' if r['venue_id']=='V-EPJDS' else '2041-1723' if r['venue_id']=='V-NCOMMS' else '',discipline='interdisciplinary',language=r['language'],index_type=index,directory_version='problem-led source, current publisher page',index_source=source,index_verification=verified,index_historical='',verification_date='2026-11-26',scope_type='problem_led_supplement',coverage_start='2022-01-01',coverage_end='2026-11-26',coverage_status='source_verification_only',gap='Article/metadata verification only; no whole-journal search'))
    existing.add(r['venue_id'])
for i,v in enumerate(cat.get('extensions',[]),1):
    journals.append(dict(venue_id=f'CNEXT{i:02}',title=v['title'],issn='',eissn='',discipline='新闻学与传播学待目录核对',language='zh',index_type='CSSCI_expanded_pending',directory_version='2025-2026 lead only',index_source='https://cssrac.nju.edu.cn/',index_verification='unverified_directory_lead',index_historical='',verification_date='2026-11-26',scope_type='extension_lead',coverage_start='2022-01-01',coverage_end='2026-11-26',coverage_status='not_searched',gap='Original expanded catalog not obtained; not part of confirmed20 source list'))
write_csv('journals_master.csv',journals)
lf=['search_id','venue_id','platform','search_date','coverage_start','coverage_end','query_exact','query_fields','result_count','retrieved_count','screened_count','status','source_url','export_path','notes']
write_csv('search_log.csv',logs,lf)
core=[]
for v in journals:
    included=[r for r in records if r['venue_id']==v['venue_id'] and r['screening_status']=='included']
    candidates=[r for r in records if r['venue_id']==v['venue_id'] and r['screening_status']=='candidate']
    if not included:continue
    core.append(dict(venue_id=v['venue_id'],title=v['title'],confirmed_included=len(included),direct_comparison_count=sum(r['core_level']=='direct_comparison' for r in included),record_ids=';'.join(r['record_id'] for r in included),candidate_count=len(candidates),candidate_ids=';'.join(r['record_id'] for r in candidates),publication_years=';'.join(sorted({str(r['volume_year']) for r in included})),continuity_evidence='multiple years' if len({str(r['volume_year']) for r in included})>1 else 'one verified year; not sustained-output proof',contribution_types=';'.join(sorted({r['core_level'] for r in included})),value_to_agent_ex=' / '.join(r['reason'] for r in included),coverage_limit=v['gap']))
    core[-1]['publication_years']=';'.join(sorted({r['online_first_date'][:4] for r in included}))
    core[-1]['issue_years']=';'.join(sorted({str(r['volume_year']) for r in included}))
    core[-1]['method_types']=';'.join(sorted({r['method_type'] for r in included}))
    core[-1]['major_topics']=' / '.join(r['research_question'] for r in included)
    core[-1]['tracking_reason']='Prioritize actual relevant papers and methods identified here; count alone does not rank journal importance.'
write_csv('core_source_journals.csv',core)
conference=[]
for r in records:
    if r['document_type']=='conference_paper':conference.append(dict(record_id=r['record_id'],work_id=r['work_id'],venue_id=r['venue_id'],venue=r['venue'],track='Findings of NAACL' if r['record_id']=='R001' else 'main conference',title=r['title'],doi=r['doi'],official_url=r['official_url'],formal_date=r['online_first_date'],screening_status=r['screening_status'],reading_status=r['reading_status'],notes='Not a submission journal; date checked from official proceedings'))
write_csv('conference_sources.csv',conference)
counts=dict(records=len(records),publication_records_formal=sum(r['document_type']!='preprint' for r in records),included_fulltext=sum(r['screening_status']=='included' for r in records),included_work_ids=len({r['work_id'] for r in records if r['screening_status']=='included'}),included_empirical_work_ids=len({r['work_id'] for r in records if r['screening_status']=='included' and r['document_type'] not in ['review','editorial'] and 'review' not in r['method_type'].lower() and 'conceptual' not in r['method_type'].lower()}),status=dict(collections.Counter(r['screening_status'] for r in records)),date_status=dict(collections.Counter(r['date_eligibility'] for r in records)),reading_status=dict(collections.Counter(r['reading_status'] for r in records)),journals=len(journals),log_rows=len(logs),cards=sum(bool(r['card_path']) for r in records),core_source_journals=len(core))
(ROOT/'data/counts.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf8')
def esc(s):return str(s).replace('\\','\\textbackslash{}').replace('&','\\&').replace('%','\\%').replace('_','\\_')
bib=[]
for r in records:
    if r['screening_status']!='included':continue
    typ='inproceedings' if r['document_type']=='conference_paper' else 'article'
    container='booktitle' if typ=='inproceedings' else 'journal'
    author=' and '.join(x.strip() for x in r['authors'].split(';'))
    props=dict(title='{'+esc(r['title'])+'}',author=esc(author),year=r['online_first_date'][:4] or str(r['volume_year']),**{container:esc(r['venue'])},url=r['official_url'],note=f"{r['record_id']}; online-first {r['online_first_date']}; full-text main paper checked 2026-11-26")
    if r['doi']:props['doi']=r['doi']
    bib.append('@'+typ+'{'+r['record_id']+',\n'+',\n'.join('  '+k+' = {'+v+'}' for k,v in props.items())+'\n}')
(ROOT/'exports/references.bib').write_text('\n\n'.join(bib)+'\n',encoding='utf8')
print(json.dumps(counts,ensure_ascii=False,indent=2))
