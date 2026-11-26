"""Check delivered research tables, joins, dates, BibTeX and XLSX export consistency."""
import collections, csv, hashlib, json, pathlib, re, subprocess, zipfile, xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
def rows(name):return list(csv.DictReader((ROOT/'data'/name).open(encoding='utf8',newline='')))
records=rows('literature_master.csv');journals=rows('journals_master.csv');logs=rows('search_log.csv');core=rows('core_source_journals.csv');candidates=rows('submission_candidates.csv');conferences=rows('conference_sources.csv')
issues=[]
def check(ok,msg):
    if not ok:issues.append(msg)
for name,items,key in [('records',records,'record_id'),('journals',journals,'venue_id'),('logs',logs,'search_id')]:check(len(items)==len({x[key] for x in items}),name+' identifiers not unique')
valid_logs={r['search_id'] for r in logs};valid_venues={r['venue_id'] for r in journals}|{r['venue_id'] for r in conferences}|{'V-ARXIV'}
doi_groups=collections.defaultdict(list)
for r in records:
    rid=r['record_id'];check(r['venue_id'] in valid_venues,f'{rid} venue missing');check(bool(r['reason']),f'{rid} reason missing');check(bool(r['search_id']),f'{rid} search provenance missing')
    check(all(s in valid_logs for s in r['search_id'].split(';')),f'{rid} search id missing')
    if r['doi']:doi_groups[r['doi'].lower().removeprefix('https://doi.org/')].append(rid)
    if r['screening_status']=='included':
        check(r['date_eligibility']=='confirmed',f'{rid} date gate');check(r['reading_status']=='fulltext_checked',f'{rid} text gate');check(bool(r['online_first_date']) and '2022'<=r['online_first_date'][:4]<='2026',f'{rid} time window')
        check(bool(r['card_path']) and (ROOT/r['card_path']).is_file(),f'{rid} reading card missing');check(bool(r['official_url']),f'{rid} official source missing')
    if r['card_path']:check((ROOT/r['card_path']).is_file(),f'{rid} broken card')
for doi,ids in doi_groups.items():check(len(ids)==1,f'duplicate DOI {doi}: {ids}')
lookup={r['record_id']:r for r in records};jlookup={r['venue_id']:r for r in journals}
for r in core:
    ids=r['record_ids'].split(';');check(all(x in lookup and lookup[x]['screening_status']=='included' for x in ids),'invalid core join '+r['venue_id']);check(int(r['confirmed_included'])==len(ids),'core count '+r['venue_id'])
    check(all(lookup[x]['document_type']!='conference_paper' for x in ids),'conference in journal source')
for r in candidates:check(r['venue_id'] in jlookup,'candidate venue missing');check(all(x in lookup for x in r['nearby_record_ids'].split(';')),'candidate article missing')
bib=(ROOT/'exports/references.bib').read_text(encoding='utf8');bibids=re.findall(r'@\w+\{([^,]+),',bib);included={r['record_id'] for r in records if r['screening_status']=='included'};check(set(bibids)==included and len(bibids)==len(included),'BibTeX IDs differ from included')
ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
expected={'文献主表':len(records)+1,'检索期刊':len(journals)+1,'核心来源':len(core)+1,'投稿候选':len(candidates)+1,'检索日志':len(logs)+1,'会议来源':len(conferences)+1}
book=ROOT/'exports/literature_and_journals.xlsx'
with zipfile.ZipFile(book) as z:
    check(z.testzip() is None,'XLSX ZIP CRC failure')
    sheetinfo=ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet',ns);check(len(sheetinfo)==7,'XLSX sheet count')
    for i,s in enumerate(sheetinfo,1):
        xml=ET.fromstring(z.read(f'xl/worksheets/sheet{i}.xml'));sheetrows=xml.findall('s:sheetData/s:row',ns)
        if s.attrib['name'] in expected:check(len(sheetrows)==expected[s.attrib['name']],f"XLSX row count {s.attrib['name']}: {len(sheetrows)}")
        check(not [c for c in xml.findall('.//s:c',ns) if c.get('t')=='e'],f"XLSX error cell in {s.attrib['name']}")
        if i==1:
            cache={c.get('r'):c.findtext('s:v',default='',namespaces=ns) for c in xml.findall('.//s:c',ns)}
            for cell,value in {'B7':15,'B8':38,'B9':2,'B10':2,'B11':13}.items():check(cache.get(cell)==str(value),'summary formula cache '+cell)
    masterxml=ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
    shared=[]
    if 'xl/sharedStrings.xml' in z.namelist():shared=[''.join(si.itertext()) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',ns)]
    cells=masterxml.findall('s:sheetData/s:row',ns)[1:];xlsxids=[]
    for row in cells:
        cell=row.find('s:c',ns);value=cell.findtext('s:v',default='',namespaces=ns)
        if cell.get('t')=='s':value=shared[int(value)]
        elif cell.get('t')=='inlineStr':value=''.join(cell.find('s:is',ns).itertext())
        xlsxids.append(value)
    check(xlsxids==[r['record_id'] for r in records],'XLSX record ordering/IDs differ')
changed=subprocess.check_output(['git','diff','--name-only','dd4190c2ac380997149c29b5bcede104b6f95b83'],cwd=ROOT.parent,text=True).splitlines()
check(all(p.startswith('literature-review/') for p in changed),'changed path outside literature-review')
for area in ['reports','reading-cards','journal-profiles','protocol']:
    for p in (ROOT/area).glob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8-sig')):
            if re.match(r'^(?:https?:|#)',target):continue
            path=target.split('#')[0]
            if path:check((p.parent/path).exists(),f'broken local link {p.name}: {target}')
report=dict(date='2026-11-26',checks='IDs, DOI dedup, source/date/fulltext gates, card links, journal/conference separation, joins, BibTeX, XLSX CRC/rows/IDs/formula cache, local Markdown links, change scope',status='pass' if not issues else 'fail',issues=issues,records=len(records),included=len(included),cards=len(list((ROOT/'reading-cards').glob('*.md'))),core_source_journals=len(core),submission_candidates=len(candidates),log_rows=len(logs),xlsx_sha256=hashlib.sha256(book.read_bytes()).hexdigest(),csv_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data').glob('*.csv')})
(ROOT/'reports/delivery_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(bool(issues))
