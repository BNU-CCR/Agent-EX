"""Deterministic numeric sampling; selected private sidecars only; no semantic coding.

Public indices use an explicit metadata/numeric whitelist. Raw text is rendered
only below CONTROLLED_ROOT. Sidecar adapter: mapping[(run_id, ordinal)] -> dict
or callable(run_id, ordinal) -> dict. Dict fields: before_reason, after_reason,
feed=[{text: exact original message, ...}]. Absent text stays explicitly missing.
"""
from collections import Counter
import hashlib
import heapq
import json
from pathlib import Path

import pandas as pd

CONTROLLED_ROOT = Path('V:/Agent EX/Agent-EX-evidence/2026-11-01/ica-rq2-rq3-v1')
CATEGORIES = (
    ('C1', 'New-argument adoption'),
    ('C2', 'Directionally selective adoption'),
    ('C3', 'Movement toward locally dominant stance'),
    ('C4', 'Stance adjustment with largely retained reasons'),
    ('C5', 'Retention of original stance'),
    ('C6', 'Mixed or indeterminate response'),
)
SAFE_FIELDS = ('topic_key', 'matched_seed', 'cell_id', 'run_id', 'cohort', 'horizon',
               'identity_a', 'network_b', 'n_agents', 'ordinal', 'round', 'agent_id',
               'prior_stance', 'after_stance', 'public_before', 'public_after',
               'published', 'reason_changed', 'feed_length', 'exposure_class',
               'feed_mean', 'feed_variance', 'distance_numerator', 'distance_denominator',
               'same_group_count', 'other_group_count', 'mean_post_age',
               'repeat_post_slots', 'prior_source_exposures') + tuple(
                   f'feed_stance_{s}_count' for s in range(1, 8))
DIMENSIONS = ('topic_key', 'matched_seed', 'identity_a', 'network_b',
              'update_status', 'dominance_relation', 'reason_change_status')


def _scalar(value):
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, 'item') else value


def _digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def select_candidates(events: pd.DataFrame, n=150, selection_seed='ica2027-rq2-v1'):
    """Select up to n actual distinct events, balancing numeric strata.

    Each full-stratum queue is ordered by SHA256(seed, run_id, ordinal). Greedy
    round-robin chooses the queue whose seven marginal strata have lowest
    cumulative representation; hash breaks ties. This is purposive coverage,
    NOT a probability sample and not a mechanism prevalence estimate.
    """
    required = {'topic_key', 'matched_seed', 'run_id', 'ordinal', 'identity_a',
                'network_b', 'prior_stance', 'after_stance', 'feed_length'}
    if missing := required-set(events.columns):
        raise ValueError(f'missing numeric event columns: {sorted(missing)}')
    if n < 1 or int(n) != n:
        raise ValueError('n must be positive integer')
    if events.duplicated(['run_id', 'ordinal']).any():
        raise ValueError('duplicate run_id/ordinal: canonicalize overlapping horizons first')
    safe = events[[c for c in SAFE_FIELDS if c in events.columns]]
    queues = {}
    pool_limit = int(n)
    columns = list(safe.columns)
    for values in safe.itertuples(index=False, name=None):
        raw = dict(zip(columns, values))
        row = {k: _scalar(v) for k, v in raw.items()}
        before, after = int(row['prior_stance']), int(row['after_stance'])
        counts = [int(row.get(f'feed_stance_{s}_count') or 0) for s in range(1, 8)]
        length = int(row['feed_length'])
        if length and sum(counts) != length:
            raise ValueError('seven actual feed counts must sum to feed_length')
        maximum = max(counts)
        modes = [s for s, count in enumerate(counts, 1) if count == maximum]
        # Unique modal stance, strictly over half the actual slots.
        dominant = modes[0] if length and len(modes) == 1 and 2*maximum > length else None
        if dominant is None:
            relation = 'no_feed' if not length else 'no_strict_dominance'
        else:
            delta = abs(after-dominant)-abs(before-dominant)
            relation = 'toward_dominant' if delta < 0 else ('away_from_dominant' if delta > 0 else 'unchanged_distance')
        reason = row.get('reason_changed')
        row.update(update_status='changed' if before != after else 'retained',
                   dominant_feed_stance=dominant, dominance_relation=relation,
                   reason_change_status='missing' if reason is None else ('changed' if reason else 'unchanged'),
                   selection_seed=selection_seed, selection_method='deterministic_marginal_strata_coverage',
                   coder_assessment='pending_human_review')
        identity = json.dumps([selection_seed, row['run_id'], row['ordinal']], ensure_ascii=False)
        rank = _digest(identity)
        row['case_id'] = 'CASE-' + rank[:16]
        stratum = tuple(str(row[d]) for d in DIMENSIONS)
        queue = queues.setdefault(stratum, [])
        entry = (-int(rank, 16), rank, row)
        if len(queue) < pool_limit:
            heapq.heappush(queue, entry)
        elif entry[0] > queue[0][0]:
            heapq.heapreplace(queue, entry)
        # Once n distinct strata exist, at most one case per stratum is needed.
        # This caps retained numeric candidates without materializing all rows.
        if pool_limit > 1 and len(queues) >= n:
            pool_limit = 1
            for key, bucket in queues.items():
                queues[key] = [max(bucket, key=lambda x: x[0])]
    queues = {key: sorted(((rank, row) for _, rank, row in queue), reverse=True,
                          key=lambda x: x[0]) for key, queue in queues.items()}
    counters = [Counter() for _ in DIMENSIONS]
    chosen = []
    while queues and len(chosen) < n:
        key = min(queues, key=lambda k: (sum(counters[i][v] for i, v in enumerate(k)),
                                        max(counters[i][v] for i, v in enumerate(k)),
                                        queues[k][-1][0]))
        _, row = queues[key].pop()
        row['selection_order'] = len(chosen)+1
        chosen.append(row)
        for i, value in enumerate(key):
            counters[i][value] += 1
        if not queues[key]:
            del queues[key]
    reason_index = [{k: r[k] for k in ('case_id', 'run_id', 'ordinal', 'topic_key',
                                      'matched_seed', 'identity_a', 'network_b',
                                      'reason_change_status', 'selection_order')}
                    for r in chosen]
    matrix = [dict(case_id=r['case_id'], run_id=r['run_id'], ordinal=r['ordinal'],
                   category_id=category_id, category_name=name,
                   coder_assessment='pending_human_review',
                   evidence_status='not_yet_human_read',
                   required_evidence='exact before/after reasons and actually read feed; see coding framework',
                   counterexplanations='argument content; starting stance; distance; exposure selection; time/history; scale boundaries',
                   mechanism_claim='none_before_human_review')
              for r in chosen for category_id, name in CATEGORIES]
    return dict(A2_reason_case_index=reason_index, A3_candidate_cases=chosen,
                A3_mechanism_evidence_matrix=matrix)


def _render_exact(value):
    if value is None or value is pd.NA:
        return 'MISSING_NOT_RECOVERED\n'
    if not isinstance(value, str):
        raise ValueError('private text sidecar fields must be strings or None')
    # A fence longer than every backtick run preserves exact contents safely.
    import re
    fence = '`' * max(3, 1+max((len(x) for x in re.findall(r'`+', value)), default=0))
    return f'{fence}text\n{value}\n{fence}\n'


def write_private_casebook(candidates, sidecars, output_root):
    """Render selected exact text only under the controlled V task directory.

    Caller must keep this file out of public review packets. Adapter exceptions
    propagate; missing dictionary keys become explicitly missing sidecars.
    """
    destination = Path(output_root).resolve()
    controlled = CONTROLLED_ROOT.resolve()
    if destination != controlled and controlled not in destination.parents:
        raise ValueError('private casebook destination must be under controlled V task root')
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / 'A3_text_evidence_casebook.md'
    with path.open('w', encoding='utf-8', newline='\n') as handle:
        handle.write('# Controlled private text evidence casebook\n\n'
                     'EXCLUDE FROM PUBLIC REVIEW PACKET. Purposive numeric coverage; '
                     'all semantic codes pending human review. No automated mechanism claims.\n\n')
        for row in candidates:
            run_id, ordinal = row['run_id'], int(row['ordinal'])
            sidecar = (sidecars(run_id, ordinal) if callable(sidecars)
                       else sidecars.get((run_id, ordinal), {})) or {}
            handle.write(f"## {row['case_id']}\n\n")
            handle.write('Numeric provenance: ' + json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n\n')
            handle.write('### Exact update-before reason\n\n' + _render_exact(sidecar.get('before_reason')) + '\n')
            handle.write('### Exact update-after reason\n\n' + _render_exact(sidecar.get('after_reason')) + '\n')
            handle.write('### Actually read feed texts\n\n')
            feed = sidecar.get('feed')
            if not feed:
                if row.get('feed_length') is not None and int(row['feed_length'])==0:
                    handle.write('NO_SELECTED_FEED (actual saved feed_length=0; not missing text).\n\n')
                else:
                    handle.write('MISSING_NOT_RECOVERED (saved numeric record requires feed text).\n\n')
            else:
                for slot, message in enumerate(feed):
                    handle.write(f'#### Supplied actual feed item {slot}\n\n')
                    handle.write(_render_exact(message.get('text')) + '\n')
            handle.write('### Human assessment\n\nC1–C6: PENDING. Record direct quotations, '
                         'counterevidence, alternative explanations, coder ID, and adjudication.\n\n')
    return path
