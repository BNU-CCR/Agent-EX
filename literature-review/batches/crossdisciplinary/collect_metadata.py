"""Retrieve publisher-deposited dates; preserve provenance, do not infer online-first dates."""
import concurrent.futures, json, pathlib, requests
ROOT = pathlib.Path(__file__).parent
DOIS = ['10.18653/v1/2024.findings-naacl.211','10.1140/epjds/s13688-025-00579-1','10.18564/jasss.5726','10.1038/s41467-026-77340-3','10.1016/j.ipm.2026.104689','10.18564/jasss.4725','10.1098/rsif.2023.0372','10.1002/sdr.1761','10.1126/sciadv.adu9368','10.1162/tacl_a_00685','10.1103/j1zg-ddqv','10.1016/j.ipm.2026.104636']
def fetch(doi):
    url='https://api.crossref.org/works/'+doi
    try:
        response=requests.get(url,timeout=35); response.raise_for_status(); m=response.json()['message']
        return dict(doi=doi,source_url=url,retrieved_date='2026-11-26',title=m.get('title'),authors=m.get('author'),venue=m.get('container-title'),type=m.get('type'),dates={k:m[k] for k in ['published-online','published-print','published','issued','created'] if k in m},volume=m.get('volume'),issue=m.get('issue'),page=m.get('page'),article_number=m.get('article-number'),publisher_url=m.get('resource'),links=m.get('link'))
    except Exception as e: return dict(doi=doi,source_url=url,error=str(e))
if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: data=list(pool.map(fetch,DOIS))
    (ROOT/'publisher_metadata.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in data: print(json.dumps({k:r.get(k) for k in ['doi','title','venue','dates','error']},ensure_ascii=False))
