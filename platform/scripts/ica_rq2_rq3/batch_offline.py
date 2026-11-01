"""Sequential bounded extraction/analysis; no network, model or live task access."""
from pathlib import Path
import json
import subprocess
import sys
import time

from extract_originals import core_seed, tail_seed, cross_archive, OUTPUT
from run_analysis import analyze_one, aggregate


def analyze_available():
    canonical=OUTPUT/'canonical'
    for source in sorted(canonical.rglob('initial.json')):
        relative=source.parent.relative_to(canonical)
        target=OUTPUT/'analysis-v1/runs'/relative
        result=analyze_one(source.parent,target,199)
        print(json.dumps({'stage':'analysis','meta':result['meta'],
            'events':result['n_events'],'seconds':result['seconds']}),flush=True)


def main():
    stages=[('core',seed,None) for seed in range(20261201,20261204)]
    stages += [('tail',seed,None) for seed in range(20261201,20261204)]
    stages += [('cross',seed,topic) for topic in ['gm-market-support','genai-net-job-loss']
               for seed in [20261201,20261202]]
    stages += [('core',seed,None) for seed in range(20261204,20261211)]
    log=OUTPUT/'batch-progress.jsonl'
    for kind,seed,topic in stages:
        row={'stage':kind,'seed':seed,'topic':topic,'started_unix':time.time()}
        with log.open('a',encoding='utf-8') as stream:stream.write(json.dumps(row)+'\n')
        print(json.dumps(row),flush=True)
        if kind=='core':core_seed(seed)
        elif kind=='tail':tail_seed(seed)
        else:cross_archive(topic,seed)
        analyze_available()
        row['completed_unix']=time.time()
        with log.open('a',encoding='utf-8') as stream:stream.write(json.dumps(row)+'\n')
    final=aggregate(OUTPUT/'analysis-v1/runs',OUTPUT/'analysis-v1/tables')
    if final['completed_horizon_trajectories']!=102 or final['unique_network_events']!=1890000:
        raise ValueError('Completed cohort coverage differs from 60 T30 +42 T60 /1890000 unique events')
    print(json.dumps({'complete':True,'unique_events':1890000,'horizon_trajectories':102}),flush=True)


if __name__=='__main__':main()
