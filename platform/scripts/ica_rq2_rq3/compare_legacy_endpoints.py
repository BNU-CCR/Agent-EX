"""Cross-check new ORIGINAL replay against previously plotted endpoint flows.

Old derived tables are comparison targets only, not computation inputs. No old
table is changed on mismatch. Matching counts avoids different anonymous-ID salts.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import argparse
import pandas as pd

ROOT=Path('V:/Agent EX/Agent-EX-evidence/2026-11-01/ica-rq2-rq3-v1')
REPO=Path(__file__).resolve().parents[3]


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def check(root=ROOT):
    old30=REPO/'reports/2026-10-24-n500-poster-analysis-v1/process/tables/agents_endpoint.csv'
    old60=REPO/'reports/2026-10-25-t60-process-evidence-v1/core/agent_endpoints.csv'
    cross=Path('V:/Agent EX/Agent-EX-evidence/2026-10-25/cross-topic-n500-t60-v1/public-results-v2/tables/transition_matrices.csv')
    sources={str(p):sha(p) for p in (old30,old60,cross)}
    before30=pd.read_csv(old30);before60=pd.read_csv(old60);beforecross=pd.read_csv(cross)
    new=pd.read_csv(root/'analysis-v1/tables/A1_origin_destination_paths.csv.gz')
    checks=[]
    mismatches=[]
    for (topic,seed,cell,horizon),rows in new.groupby(['topic_key','matched_seed','cell_id','horizon']):
        actual=Counter(zip(rows.stance_r0.astype(int),rows.stance_end.astype(int)))
        if topic=='retirement':
            old=before30 if horizon==30 else before60
            old=old[(old.matched_seed==seed)&(old.cell_id==cell)]
            expected=Counter(zip(old.initial_private.astype(int),old.terminal_private.astype(int))) if horizon==30 else Counter(zip(old.t0.astype(int),old.t60.astype(int)))
        else:
            old=beforecross[(beforecross.topic_key==topic)&(beforecross.matched_seed==seed)&(beforecross.cell_id==cell)&
                            (beforecross.kind=='agent')&(beforecross.start_sweep==0)&(beforecross.end_sweep==horizon)]
            expected=Counter({(int(r.from_stance),int(r.to_stance)):int(r.count) for r in old.itertuples(index=False)})
        passed=all(actual[i,j]==expected[i,j] for i in range(1,8) for j in range(1,8)) and sum(actual.values())==sum(expected.values())==500
        row=dict(topic_key=topic,matched_seed=int(seed),cell_id=cell,horizon=int(horizon),matched=passed)
        checks.append(row)
        if not passed:mismatches.append(row)
        if topic=='retirement' and horizon==60:
            expected30=Counter(zip(old.t0.astype(int),old.t30.astype(int)))
            actual30=Counter(zip(rows.stance_r0.astype(int),rows.stance_r30.astype(int)))
            if actual30!=expected30:mismatches.append({**row,'comparison':'continued_T30_prefix'})
            expected_three=Counter(zip(old.t0.astype(int),old.t30.astype(int),old.t60.astype(int)))
            actual_three=Counter(zip(rows.stance_r0.astype(int),rows.stance_r30.astype(int),rows.stance_end.astype(int)))
            if actual_three!=expected_three:mismatches.append({**row,'comparison':'R0_R30_R60_joint_paths'})
        elif topic!='retirement' and horizon==60:
            for start,end,from_column,to_column in [(0,30,'stance_r0','stance_r30'),(30,60,'stance_r30','stance_end')]:
                window=beforecross[(beforecross.topic_key==topic)&(beforecross.matched_seed==seed)&
                    (beforecross.cell_id==cell)&(beforecross.kind=='agent')&
                    (beforecross.start_sweep==start)&(beforecross.end_sweep==end)]
                wanted=Counter({(int(v.from_stance),int(v.to_stance)):int(v.count) for v in window.itertuples(index=False)})
                found=Counter(zip(rows[from_column].astype(int),rows[to_column].astype(int)))
                if any(found[i,j]!=wanted[i,j] for i in range(1,8) for j in range(1,8)):
                    mismatches.append({**row,'comparison':f'R{start}_R{end}'})
    unchanged=all(sha(Path(path))==digest for path,digest in sources.items())
    report={'source_sha256_before_after':sources,'sources_unchanged':unchanged,
            'checks':checks,'mismatches':mismatches,'n_horizon_trajectories':len(checks),
            'new_tables_derived_from_original_records_not_old_tables':True}
    (root/'legacy-endpoint-comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if mismatches or not unchanged or len(checks)!=102:
        raise ValueError('Legacy endpoint discrepancy or incomplete coverage: retain both; inspect report')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    result=check(parser.parse_args().root)
    print(json.dumps({'checks':result['n_horizon_trajectories'],'mismatches':len(result['mismatches'])}))
