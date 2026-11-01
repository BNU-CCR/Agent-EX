"""Bounded, restartable offline analysis of verified canonical original records.

No model/runtime imports. Source directories are immutable inputs; each complete
analysis receives its own numeric tables and source/code hash receipt. Reusing a
completed analysis is permitted only when all inputs and analysis code match.
"""
from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import json
import os
import time

import metrics_rq2
import metrics_rq3

ROOT = Path('V:/Agent EX/Agent-EX-evidence/2026-11-01/ica-rq2-rq3-v1')


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_table(path, rows):
    """Write plain numeric records, preserving blank NA rather than zero."""
    path = Path(path)
    keys = list(dict.fromkeys(k for row in rows for k in row))
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'wt', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, keys, extrasaction='raise')
        if keys:
            writer.writeheader()
            writer.writerows(rows)


def signature(source, permutations):
    files = [source / name for name in
             ('initial.json', 'events.csv.gz', 'feed.csv.gz', 'source.json', 'snapshots.json')]
    files = [p for p in files if p.exists()]
    modules = [Path(__file__), Path(metrics_rq2.__file__), Path(metrics_rq3.__file__)]
    from sources import __file__ as loader_file
    modules.append(Path(loader_file))
    return {'inputs': {p.name: sha(p) for p in files},
            'code': {p.name: sha(p) for p in modules},
            'permutations': permutations, 'analysis_seed': 20261101}


def analyze_one(source, output, permutations):
    from sources import load_canonical
    expected = signature(source, permutations)
    done = output / 'analysis-verification.json'
    if done.exists():
        receipt = json.loads(done.read_text(encoding='utf-8'))
        if receipt['signature'] != expected:
            raise ValueError(f'Existing analysis differs; retain it and use a new output: {output}')
        if any(sha(output / name) != digest for name, digest in receipt['tables'].items()):
            raise ValueError('Existing analysis table hash differs')
        return receipt
    if output.exists() and any(output.iterdir()):
        raise ValueError(f'Incomplete existing output retained: {output}')
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    run = load_canonical(source)
    tables = metrics_rq2.analyze_run(run)
    tables.update(metrics_rq3.analyze_run(run, permutations=permutations, analysis_seed=20261101))
    hashes = {}
    counts = {}
    for name, rows in tables.items():
        destination = output / (name + '.csv.gz')
        write_table(destination, rows)
        hashes[destination.name] = sha(destination)
        counts[name] = len(rows)
    if expected != signature(source, permutations):
        raise ValueError('Source/code changed during offline analysis')
    receipt = {'meta': run['meta'], 'n_agents': len(run['node_ids']),
               'n_events': len(run['events']), 'n_feed_slots': len(run['feed']),
               'signature': expected, 'tables': hashes, 'row_counts': counts,
               'seconds': round(time.monotonic()-started, 3),
               'original_records_replayed': True, 'model_requests': 0,
               'all_events_successful': True, 'before_after_chain_validated': True,
               'population_flow_conserved': True, 'historical_public_feed_validated': True}
    done.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    return receipt


def aggregate(directory, output):
    """Disk-stream per-run tables; endpoint pairings never pool event units."""
    receipts = sorted(directory.rglob('analysis-verification.json'))
    manifests = [json.loads(p.read_text(encoding='utf-8')) for p in receipts]
    output.mkdir(parents=True, exist_ok=True)
    table_names = sorted({n for row in manifests for n in row['tables']})
    for name in table_names:
        target = output / name
        keys = None
        with gzip.open(target, 'wt', encoding='utf-8', newline='') as writer_stream:
            writer = None
            for receipt_path, manifest in zip(receipts, manifests):
                if name not in manifest['tables']:
                    continue
                source = receipt_path.parent / name
                if sha(source) != manifest['tables'][name]:
                    raise ValueError('Per-run hash mismatch')
                with gzip.open(source, 'rt', encoding='utf-8', newline='') as reader_stream:
                    reader = csv.DictReader(reader_stream)
                    if not reader.fieldnames:
                        continue
                    if keys is None:
                        keys = reader.fieldnames
                        writer = csv.DictWriter(writer_stream, keys)
                        writer.writeheader()
                    if keys != reader.fieldnames:
                        raise ValueError(f'Incompatible table columns: {name}')
                    writer.writerows(reader)
    import pandas as pd
    endpoint = output / 'B1_global_convergence_by_run.csv.gz'
    if endpoint.exists():
        pairs = metrics_rq3.paired_results({'B1_global_convergence_by_run': pd.read_csv(endpoint)})
        for name, rows in pairs.items():
            write_table(output / (name+'.csv.gz'), rows)
    unique = {}
    for manifest in manifests:
        m = manifest['meta']
        key = (m['topic_key'], m['matched_seed'], m['cell_id'])
        unique[key] = max(unique.get(key, 0), manifest['n_events'])
    summary = {'completed_horizon_trajectories': len(manifests),
               'unique_network_events': sum(unique.values()),
               'horizon_panel_events_including_reused_prefixes': sum(m['n_events'] for m in manifests),
               'sources': manifests, 'model_requests': 0,
               'files': {p.name: sha(p) for p in output.glob('*.csv.gz')}}
    (output/'AGGREGATE_VERIFICATION.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--canonical-root', type=Path, default=ROOT/'canonical')
    parser.add_argument('--output', type=Path, default=ROOT/'analysis-v1')
    parser.add_argument('--max-runs', type=int, default=1)
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--aggregate', action='store_true')
    parser.add_argument('--permutations', type=int, default=199)
    args = parser.parse_args()
    if not ROOT.is_dir():
        raise RuntimeError('V controlled root unavailable; no fallback')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sources = sorted(args.canonical_root.rglob('initial.json'))
    selected = sources if args.all else sources[:args.max_runs]
    for path in selected:
        relative = path.parent.relative_to(args.canonical_root)
        receipt = analyze_one(path.parent, args.output/'runs'/relative, args.permutations)
        print(json.dumps({k: receipt[k] for k in ('meta','n_events','n_feed_slots','seconds')}, ensure_ascii=False), flush=True)
    if args.aggregate:
        result = aggregate(args.output/'runs', args.output/'tables')
        print(json.dumps({k: result[k] for k in ('completed_horizon_trajectories','unique_network_events')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
