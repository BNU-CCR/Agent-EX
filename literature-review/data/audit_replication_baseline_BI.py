"""Recalculate provided CSV summaries; never import or execute author model code.

Usage: python audit_replication_baseline_BI.py <download_scratch_directory>
Requires files identified in replication_artifact_audit_BI.json. Output is audit
evidence for the supplied snapshot, not a simulation rerun or execution provenance.
"""
import collections,csv,hashlib,io,json,math,pathlib,statistics,sys
R=pathlib.Path(__file__).resolve().parents[1]
S=pathlib.Path(sys.argv[1])
files=json.loads((S/'BI_files.json').read_text(encoding='utf8'))
for x in files:
 b=(S/('BI_'+x['path'].replace('/','__'))).read_bytes()
 assert hashlib.sha256(b).hexdigest()==x['sha256']
 assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==x['git_blob']
summary=list(csv.DictReader((S/'BI_results__slumulation__summaries__final_step.csv').open()))
# Table 1 visually checked in BH: NetLogo mean, SD, Mesa mean, SD, decimals.
paper={
 'slumpoppercent':([19.9,2.8,19.0,3.2],1),
 'centralslumpoppercent':([16.4,4.1,16.7,3.9],1),
 'peripheryslumpoppercent':([21.0,3.1,19.8,4.1],1),
 'slumareapercent':([10.6,1.4,10.1,1.7],1),
 'centralslumareapercent':([8.3,1.9,8.4,1.7],1),
 'peripheryslumareapercent':([11.3,1.6,10.7,2.2],1),
 'slum-density':([2.32,.10,2.31,.10],2),
 'central-slum-density':([2.67,.37,2.71,.35],2),
 'periphery-slum-density':([2.24,.08,2.20,.08],2),
 'num-slums':([130.5,15.3,125.7,19.3],1),
 'central-num-slums':([23.9,5.6,24.1,4.9],1),
 'peripheral-num-slums':([106.6,13.7,101.5,19.7],1)}
out={};tablechecks=[]
for platform in ['netlogo','mesa']:
 raw=(S/f'BI_results__slumulation__{platform}__baseline.csv').read_text()
 lines=raw.splitlines();start=next(i for i,l in enumerate(lines) if l.startswith('[run number],') or l.startswith('"[run number]",'))
 rows=list(csv.DictReader(io.StringIO('\n'.join(lines[start:]))))
 by=collections.defaultdict(list)
 for row in rows:by[row['[run number]']].append(int(row['[step]']))
 assert len(by)==30 and all(sorted(v)==list(range(51)) for v in by.values())
 final=[r for r in rows if r['[step]']=='50'];matches=[]
 for x in summary:
  if x['experiment']!='Typical Run':continue
  metric=x['metric'];vals=[float(r[metric]) for r in final]
  mu=statistics.mean(vals);sd=statistics.stdev(vals)
  assert int(x[platform+'_n'])==int(x[platform+'_finite_n'])==30
  assert int(x[platform+'_nonfinite_n'])==0
  for a,b in [(mu,float(x[platform+'_mean'])),(sd,float(x[platform+'_stdev']))]:assert math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)
  factor=100 if metric=='slumpoppercent' else 1
  expected,decimals=paper[metric];offset=0 if platform=='netlogo' else 2
  for j,value in enumerate([mu,sd]):
   rounded=round(value*factor,decimals);assert rounded==expected[offset+j],(metric,platform,rounded)
   tablechecks.append(dict(platform=platform,metric=metric,statistic=['mean','sample_sd'][j],unit_multiplier=factor,rounded=rounded,paper_value=expected[offset+j],matches=True))
  matches.append(dict(metric=metric,n=30,mean=mu,sample_sd=sd,mean_standard_error=sd/math.sqrt(30),unit_multiplier_for_paper=factor))
 out[platform]=dict(rows=len(rows),runs=len(by),steps_per_run=51,matched_metrics=matches)
seeds=json.loads((S/'BI_results__slumulation__mesa__baseline_seeds.json').read_text())
assert len(seeds['entries'])==len({e['seed'] for e in seeds['entries']})==30
assert sorted(e['run_number'] for e in seeds['entries'])==list(range(1,31))
result=dict(checked_date='2026-11-27',commit='1e9be1490bcbd5fa23632aeff9cbf872bd18957f',files=files,summary_rows=len(summary),summary_experiment_rows=dict(collections.Counter(x['experiment'] for x in summary)),baseline=out,table1_numeric_checks=tablechecks,matched_paper_numeric_values=len(tablechecks),mesa_seed_entries=30,mesa_unique_seeds=30,netlogo_seed_provenance='baseline_setup.xml setup only; baseline raw no retained random seed; not demonstrated replay',limitations='Only supplied baseline CSV arithmetic and Table1 NetLogo/Mesa columns; no author code executed; old Paper column/statistical definition not verified; table2/3 raw runs and bootstrap not checked; not proven paper-generating commit')
(R/'data/replication_artifact_audit_BI.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print('12 hashed files; 24 baseline metric distributions; 48 Table1 values matched; no simulation rerun')
