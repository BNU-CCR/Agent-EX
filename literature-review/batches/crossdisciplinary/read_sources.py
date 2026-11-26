"""Temporary, legal open-source reading cache; no article copies are committed."""
import concurrent.futures, pathlib, tempfile, requests, fitz, json
CACHE=pathlib.Path(tempfile.gettempdir())/'agentex-literature-20261126'; CACHE.mkdir(exist_ok=True)
SOURCES={
 'chuang':'https://aclanthology.org/2024.findings-naacl.211.pdf',
 'steiglechner':'https://cris.leibniz-zmt.de/id/eprint/5307/1/Steiglechner-2023.pdf',
 'ashery':'https://openaccess.city.ac.uk/id/eprint/35211/1/sciadv.adu9368.pdf',
 'tjuatja':'https://aclanthology.org/2024.tacl-1.56.pdf',
 'piao':'https://fi.ee.tsinghua.edu.cn/~gaochen/papers/Nature2026-LLM-Polarization.pdf'}
def get(item):
 key,url=item
 try:
  r=requests.get(url,timeout=45);r.raise_for_status(); doc=fitz.open(stream=r.content,filetype='pdf')
  text='\n'.join(f'\n---PDF page {i+1}---\n'+p.get_text() for i,p in enumerate(doc))
  (CACHE/(key+'.txt')).write_text(text,encoding='utf8'); return dict(key=key,url=url,pages=len(doc),cache=str(CACHE/(key+'.txt')),status='retrieved')
 except Exception as e:return dict(key=key,url=url,status='access_blocked',error=str(e))
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:data=list(pool.map(get,SOURCES.items()))
 pathlib.Path(__file__).with_name('fulltext_access.json').write_text(json.dumps(data,indent=2),encoding='utf8')
 print(json.dumps(data,indent=2))
