"""Record bounded primary-source venue checks without rebuilding prior rows."""
import collections,csv,hashlib,json,pathlib
R=pathlib.Path(__file__).resolve().parents[3]; B=pathlib.Path(__file__).resolve().parent
S=pathlib.Path('C:/Users/Bai Yuexi/AppData/Local/Temp/agentex-literature-export')
date='2026-11-27'
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:q=csv.DictReader(f);return q.fieldnames,list(q)
def write(p,h,rows):
 with p.open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,h);w.writeheader();w.writerows(rows)
queries=[
 'site.sciencedirect.com/science/article "Information Sciences" "large language" "social simulation"',
 'site.sciencedirect.com/science/article "Expert Systems with Applications" "large language" "agent-based"',
 'site.sciencedirect.com/journal/information-sciences/about/aims-and-scope',
 'site.sciencedirect.com/journal/expert-systems-with-applications/about/aims-and-scope',
 '"Information Sciences" "LLM" "simulation" "social" 2025 2026',
 '"Information Sciences" "large language models" "opinion dynamics"',
 '"Expert Systems with Applications" "generative" "social simulation"',
 '"Information Sciences" "large language model" "agent-based"',
 '"An LLM-enhanced agent-based simulation tool for information propagation"',
 '"Information Sciences" "large language model" "consensus" 2026',
 '"Information Sciences" "social simulation" 2024 2025 2026',
 'site.sciencedirect.com/science/article "Information Sciences" "large language models" "group decision"',
 'site.sciencedirect.com/science/article "Information Sciences" "agent-based" "2024"',
 '"10.1016/j.eswa.2026.132901" "Available online"',
 'site.sciencedirect.com/science/article "Information Sciences" "LLM" "simulation"']
ops=[]
def op(platform,q,u,status,notes):ops.append(dict(search_id=f'BJ-{len(ops)+1:02}',platform=platform,search_date=date,query_exact=q,source_url=u,status=status,notes=notes))
for q in queries:op('public_web_search',q,'','query_run_bounded_not_database_inventory','publisherindexedabstracts/metadata;noresulttotalretained;irrelevantandlookalikedomainsnotused')
ins='https://shop.elsevier.com/journals/information-sciences/0020-0255';eswa='https://shop.elsevier.com/journals/expert-systems-with-applications/0957-4174'
events=[
 ('scopeINS','https://www.sciencedirect.com/journal/information-sciences/about/aims-and-scope','403'),
 ('scopeESWA','https://www.sciencedirect.com/journal/expert-systems-with-applications/about/aims-and-scope','403'),
 ('shopINS',ins,'official_HTML_read'),
 ('ESWA_article','https://www.sciencedirect.com/science/article/pii/S0957417426018130','403'),
 ('shopESWA',eswa,'official_HTML_read'),
 ('ESWA_abs','https://www.sciencedirect.com/science/article/abs/pii/S0957417426018130','403'),
 ('shopINS_description_find',ins,'official_description_read'),
 ('shopESWA_description_find',eswa,'official_description_read'),
 ('crossref_ESWA','https://api.crossref.org/works/10.1016/j.eswa.2026.132901','HTTP200'),
 ('crossref_IPM','https://api.crossref.org/works/10.1016/j.ipm.2026.105184','HTTP200'),
 ('INS_guide','https://www.sciencedirect.com/journal/information-sciences/publish/guide-for-authors','403'),
 ('ESWA_guide','https://www.sciencedirect.com/journal/expert-systems-with-applications/publish/guide-for-authors','403'),
 ('INS_article','https://www.sciencedirect.com/science/article/abs/pii/S0020025525002178','403'),
 ('IPM_article','https://www.sciencedirect.com/science/article/abs/pii/S0306457326005741','403'),
 ('shopINS_static',ins,'HTTP200'),('shopESWA_static',eswa,'HTTP200'),
 ('crossref_INS','https://api.crossref.org/works/10.1016/j.ins.2025.122085','HTTP200')]
for q,u,status in events:op('public_primary_source',q,u,status,'failedopeningnotfullread;shopnotcompleteauthorguide;crossrefcreatednotpublishedonline')
op('local_audit','deduplicate_R005_and_reconcile_coverage','data/literature_master.csv','checked','RoleSimLLMexistingR005;noduplicate;41requestedentries')
assert len(ops)==33
dump(B/'source_operations.json',ops)
h,_=read(R/'data/literature_master.csv');new=[];metas=[]
for rid,num,title,authors,venue,vid,year,tier,obj,purpose,tags in [
 ('M046','132901','Large language model-driven group consensus decision-making model: The case of local debt risk','Min Liu;Luxiang Zhang','Expert Systems with Applications','V-ESWA','2026','application','other','system_development','interaction_protocol;application'),
 ('M047','105184','From rules to reasoning: A systematic review of agent-based and LLM-empowered simulation of public collaboration','Yulong Jie;Shuigen Hu;Jun Su;Jue Wang','Information Processing & Management','V-IPM','2027','core_method','other','method_evaluation','simulation_paradigm;theory_to_model_translation;validation_and_external_validity')]:
  m=json.loads((S/f'BJ_{num}.json').read_text(encoding='utf8'))['message'];doi=m['DOI'];url='https://www.sciencedirect.com/science/article/abs/pii/'+('S0957417426018130' if rid=='M046' else 'S0306457326005741')
  n={k:'' for k in h};n.update(record_id=rid,work_id='W'+rid,venue_id=vid,title=title,authors=authors,language='en',venue=venue,document_type='journal_article',doi=doi,official_url=url,discovery_url=url,metadata_evidence_url='https://api.crossref.org/works/'+doi,volume_year=year,date_basis='Crossrefpublishedprint/volumeonly;published-onlineabsent;creatednotfirstonline',date_eligibility='date_pending',related_versions='publisherindexedabstract_only;formal_fulltextnotacquired',search_id='BJ-01;BJ-02;BJ-24;BJ-25',search_date=date,screening_status='candidate',core_level='method_validity' if rid=='M047' else 'peripheral',reason='PublisherindexedabstractandCrossrefidentity;formalfirstonlineandfulltextpending',research_question='CompareABMandLLMpubliccollaborationsimulation' if rid=='M047' else 'LLMassistedconsensusanddecisionoptimisationinlocaldebtrisk',research_object=obj,simulation_purpose=purpose,primary_purpose=purpose,method_type='cross_paradigm_review' if rid=='M047' else 'LLM_KG_dynamictrust_consensus_decisionsystem',mechanisms='abstractonly_details_pending',reading_status='abstract_read',supplement_status='not_checked',findings='Abstractclaims1064studies_2x4andtemporalcontrols;denominators/datepending' if rid=='M047' else 'AbstractclaimsLLMtrustnetwork_KG_negotiation;human/syntheticrolesandvalidationpending',evidence_location='publisher_search_index_abstract;Crossrefmetadata;directarticle403',relation_to_agent_ex='Potentialcrossparadigmmethodreview;notimportedcorpusorvalidationrate' if rid=='M047' else 'Adjacentnormativeconsensusoptimisation_notautomaticallydescriptivesocialsimulation',source_batch='BJ',notes='Published-print2027-02;created2026-09-18notfirstonline;do_notexcludeorfabricate2026publication' if rid=='M047' else 'Volume329/2026-11;created2026-05-22notfirstonline;abstractsignificanceclaimnotverified',method_relevance_tier=tier,method_contribution_type=tags,method_maturity='unclear',disciplinary_home='information_science;simulation_methodology' if rid=='M047' else 'intelligent_systems;decision_support',method_transferability='pending_fulltext',method_evidence_level='unclear',method_relevance_rationale='跨范式综述摘要直接涉及方法比较，待核全文/语料分母。' if rid=='M047' else '邻接智能决策应用；不将共识优化自动等同人类过程仿真。',method_coding_status='abstract_provisional',method_pending_fields='formal_firstonline;fulltext;method_maturity;method_evidence_level;method_transferability;validation_denominators',method_evidence_location='publisherindexedAbstract;Crossrefidentity',method_coding_source='reports/information_systems_method_venues.md',method_last_checked=date)
  new.append(n);metas.append({k:m.get(k) for k in ['DOI','title','container-title','published-online','published-print','created','volume','issue','article-number']})
dump(B/'results.json',dict(batch_id='BJ-information-systems-venue-scope-and-bounded-precedents',date=date,expected_master_sha256=hashlib.sha256((R/'data/literature_master.csv').read_bytes()).hexdigest(),updates=[],new_records=new))
primary=json.loads((S/'BJ_primary.json').read_text(encoding='utf8'))
dump(R/'data/information_systems_audit_BJ.json',dict(checked_date=date,query_count=15,source_operations=33,primary_static_sources=primary,crossref_selected_metadata=metas,reused_record='R005',not_master_adjacent_INS='10.1016/j.ins.2025.122085',identity_correction='LAIDSim title is IJCAI2024Demo DOI10.24963/ijcai.2024/1007, not Information Sciences',limitations='Indexedabstractsnotfulltexts;shopscopenotcompleteguides;creatednotfirstonline;nofullinventoryorMJL/APCcertification'))
vh,vs=read(R/'data/method_venue_map.csv');ch,cs=read(R/'data/journal_submission_candidates.csv')
for vid,title,url,record in [('INS','Information Sciences',ins,''),('ESWA','Expert Systems with Applications',eswa,'M046')]:
 v={k:'' for k in vh};v.update(venue_id=vid,venue=title,disciplinary_home='information_science;intelligent_systems;decision_support',scope_url=url,author_guidelines_url='https://www.sciencedirect.com/journal/'+('information-sciences' if vid=='INS' else 'expert-systems-with-applications')+'/publish/guide-for-authors',record_ids=record,precedents_2022_onward='Peng2025historicaldata_dynamicnetworkconsensus_DOI10.1016/j.ins.2025.122085_nonLLM_adjacent' if vid=='INS' else 'M0462026LLM_KG_consensus_abstractonly',method_publication_type='algorithmic_intelligentsystems_and_decisionmethods',continuity_evidence='scope_and_bounded_adjacent_sample_notcontinuousLLMsocialsimulationinventory',current_paper_judgment='weakfit_withouttechnicalmethodcontribution',future_method_paper_judgment='conditional_requires_generalisablemethodandcomparisons',current_paper_gap='Opiniontrajectoryalone_notclearintelligentsystemadvance',future_method_paper_gap='Needmatchedcomparisons_errororvaliditybenefit_notrenaming',article_types_and_length='originalresearch;details/lengthpending_guide403',code_data_requirements='pending_guide403',oa_fees='not_verified_noquote',index_status='MJL_independent_check_pending',venue_type='journal',verified_date=date,verification_status='officialshop_scope200;dedicatedscope/guide403;boundedpublisherindexedabstract',evidence_note='INSnotScienceChinaINSorUSCISI;noLLMformalmethodfulltextverified' if vid=='INS' else 'Normativeconsensusoptimisation_notautomaticallydescriptivesocialsimulation',required_writing_changes='Technicalmethodquestion/contribution/unitsandcomparisonclear',required_existing_analyses='Assessclaimandbenchmarkalignment;notprojectrunaudit',required_new_experiments='Conditionalmatchedmethodvalidation;notexecuted',recommendation_grade='scope_and_adjacent_precedent_only_not_ranked' if vid=='INS' else 'conditional_adjacent_method_candidate',pending_items='firstonline/fulltext;fullinventory;guide;fees;MJL',requirements_authority='officialpublisher_shop_scope;fitisinference',master_venue_ids='' if vid=='INS' else 'V-ESWA',venue_id_namespace='methods_map')
 assert vid not in {x['venue_id'] for x in vs};vs.append(v)
 if vid=='ESWA':cs.append(v.copy())
write(R/'data/method_venue_map.csv',vh,vs);write(R/'data/journal_submission_candidates.csv',ch,cs)
ah,ar=read(R/'data/venue_coverage_audit.csv')
for x in ar:
 if x['requested_venue'] in ['Information Sciences','Expert Systems with Applications','Information Processing & Management']:
  name=x['requested_venue'];x.update(map_venue_id={'Information Sciences':'INS','Expert Systems with Applications':'ESWA','Information Processing & Management':''}[name],audit_status='partial_scope_and_adjacent_sample_directLLM_fulltext_pending' if name=='Information Sciences' else 'partial_scope_and_LLMdecision_abstract_fulltext_pending' if name=='Expert Systems with Applications' else 'partial_sample_metadata_scope_guide_pending',sample_record_ids={'Information Sciences':'','Expert Systems with Applications':'M046','Information Processing & Management':'R005;M047'}[name],scope_check='officialshop_checked_dedicatedpage403' if name!='Information Processing & Management' else 'pending_nextBK',coverage_boundary='15boundedpublicqueries_notwholevenueinventory;abstractsnotfulltext;firstonlinepending',next_action='fulltext/firstonline_andguide_inventory' if name!='Information Processing & Management' else 'BKofficialscope/date_andlegalfulltext',checked_date=date,evidence_urls='reports/information_systems_method_venues.md',source_operation_ids='BJ-01..BJ-33')
write(R/'data/venue_coverage_audit.csv',ah,ar)
summary=dict(checked_date=date,total_taskbook_rows=len(ar),not_yet_reconciled=[x['requested_venue'] for x in ar if x['audit_status'].startswith('not_yet_reconciled')],partial=[dict(venue=x['requested_venue'],status=x['audit_status'],boundary=x['coverage_boundary']) for x in ar if x['audit_status'].startswith('partial')],boundary='Allstatusesincludingcuratedsamplesarenotfullinventorycertification')
dump(R/'data/coverage_status_summary_BJ.json',summary)
print('BJ prepared: 2abstractcandidates, 2venueentries,1conditionaljournal; coverage2notreconciled/10partial')
