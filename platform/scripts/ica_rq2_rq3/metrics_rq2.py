"""Offline, descriptive RQ2 A1/A2 metrics; no model calls or file writes.

Every output carries the supplied run metadata plus identity_a (A0/A1),
network_b (B0/B1/B2), and n_agents. Rows are seed/run units, never pooled
inferential estimates. Exposure classes are post-hoc operational descriptions,
not causal mechanisms or evidence of identity/trust mediation. Directional
opportunities count EVENTS, never feed slots. Population variance uses ddof=0.

Input ordinals must be global, contiguous, successful events. Round r comprises
ordinals [(r-1)*N, r*N). A publication at ordinal k has round k//N+1;
initial publications have round 0. Public state changes only when published.
Weighted attention may activate one agent repeatedly in a round; a round is N
events, not an exhaustive permutation of the population.
"""
from collections import Counter, defaultdict
import re

import numpy as np
import pandas as pd


def _integer(value, label):
    if isinstance(value, (bool, np.bool_)) or pd.isna(value):
        raise ValueError(f'{label}: expected integer, got {value!r}')
    result = int(value)
    if result != value:
        raise ValueError(f'{label}: nonintegral value {value!r}')
    return result


def _stance(value):
    value = _integer(value, 'stance')
    if not 1 <= value <= 7:
        raise ValueError(f'stance outside 1..7: {value}')
    return value


def _rate(numerator, denominator):
    return numerator / denominator if denominator else None


def _exposure_class(before, values):
    if not values:
        return 'no_feed'
    if before == 4:
        return 'neutral_start'
    if len(set(values)) == 1:
        return f'pure_{values[0]}'
    same = sum((v - 4) * (before - 4) > 0 for v in values)
    opposite = sum((v - 4) * (before - 4) < 0 for v in values)
    if 3 * same >= 2 * len(values):
        return 'same_side_majority_2of3'
    if 3 * opposite >= 2 * len(values):
        return 'opposite_side_majority_2of3'
    return 'mixed'


def analyze_run(run: dict) -> dict[str, list[dict]]:
    """Validate one actual trajectory and return tidy A1/A2 tables.

    Validation fails closed for broken state chains, incomplete event-count
    rounds, impossible/future publications, and invalid feed alignment. Source
    extraction/provenance belongs to the caller. No reason text is consumed.
    """
    nodes = list(run['node_ids'])
    n = len(nodes)
    if not n or len(set(nodes)) != n:
        raise ValueError('node_ids must be nonempty and unique')
    node_set = set(nodes)
    meta = dict(run['meta'])
    horizon = _integer(meta['horizon'], 'horizon')
    if horizon < 1:
        raise ValueError('horizon must be positive')
    match = re.fullmatch(r'SIS-(A[01])-(B[012])', meta['cell_id'])
    if not match:
        raise ValueError('expected cell_id SIS-A[01]-B[012]')
    meta.update(identity_a=match[1], network_b=match[2], n_agents=n)
    groups = run['groups']
    if set(groups) != node_set or any(groups[a] not in ('Blue', 'Green') for a in nodes):
        raise ValueError('groups must assign Blue/Green to every node')
    initial = {a: _stance(run['initial_stances'][a]) for a in nodes}
    public = {a: _stance(run['initial_public'][a]) for a in nodes}
    state = initial.copy()
    events = run['events'].sort_values('ordinal', kind='stable')
    if len(events) != n * horizon:
        raise ValueError('event count must equal N*horizon')
    raw_events = events.to_dict('records')
    if [_integer(e['ordinal'], 'ordinal') for e in raw_events] != list(range(n * horizon)):
        raise ValueError('events must contain each global ordinal exactly once')
    feed_by_event = defaultdict(list)
    for f in run['feed'].to_dict('records'):
        ordinal = _integer(f['ordinal'], 'feed ordinal')
        if not 0 <= ordinal < len(raw_events):
            raise ValueError('feed ordinal not in trajectory')
        feed_by_event[ordinal].append(f)
    tables = {name: [] for name in (
        'A1_round_transition_matrices', 'A1_net_stance_flows', 'A1_cumulative_flow',
        'A1_origin_destination_paths', 'A1_dominant_stance_formation',
        'A1_dominant_stance_round_shares', 'A2_event_exposure_numeric',
        'A2_exposure_response_cells', 'A2_directional_update_rates',
        'A2_seed_level_contrasts', 'A2_exposure_history_summary')}

    def emit(table, **row):
        tables[table].append({**meta, **row})

    histories = {a: [] for a in nodes}
    source_history = {a: Counter() for a in nodes}
    post_history = {a: Counter() for a in nodes}
    directional_history = {a: Counter() for a in nodes}
    published_records = {}
    initial_public = public.copy()
    round_states = [state.copy()]
    transitions = np.zeros((7, 7), dtype=np.int64)
    cumulative_inflow = Counter()
    cumulative_outflow = Counter()
    round_actors = set()
    activation_counts = Counter()
    opportunity = Counter()
    exact = Counter()
    toward = Counter()
    response_counts = Counter()
    response_denoms = Counter()
    for e in raw_events:
        ordinal = int(e['ordinal'])
        round_no = ordinal // n + 1
        actor = e['agent_id']
        if actor not in node_set:
            raise ValueError('unknown actor')
        round_actors.add(actor)
        before, after = _stance(e['before']), _stance(e['after'])
        if state[actor] != before:
            raise ValueError(f'private state chain mismatch at ordinal {ordinal}')
        published = e['published']
        if not isinstance(published, (bool, np.bool_)):
            raise ValueError('published must be boolean')
        feed = sorted(feed_by_event[ordinal], key=lambda x: x['display_slot'])
        slots = [_integer(f['display_slot'], 'display_slot') for f in feed]
        if len(set(slots)) != len(slots) or any(s < 0 for s in slots):
            raise ValueError('duplicate/negative display slots')
        values, sources, keys, ages, key_types = [], [], [], [], []
        for f in feed:
            source = f['source_agent_id']
            if f['receiver_agent_id'] != actor or source not in node_set or source == actor:
                raise ValueError('invalid receiver/source alignment')
            stance = _stance(f['source_stance'])
            pub = f['publication_ordinal']
            if pd.isna(pub):
                pub = None
                expected_source, expected_stance = source, initial_public[source]
                publication_round = 0
            else:
                pub = _integer(pub, 'publication ordinal')
                if not 0 <= pub < ordinal or pub not in published_records:
                    raise ValueError('publication must refer to an earlier published event')
                expected_source, expected_stance = published_records[pub]
                publication_round = pub // n + 1
            if (source, stance) != (expected_source, expected_stance):
                raise ValueError('feed source/stance differs from actual referenced publication')
            post_id = f.get('post_id')
            explicit_id = not pd.isna(post_id)
            key = ('post_id', str(post_id)) if explicit_id else ('source_publication', source, pub)
            values.append(stance)
            sources.append(source)
            keys.append(key)
            key_types.append('post_id' if explicit_id else 'source_publication_compound')
            ages.append(round_no - publication_round)
        length = len(values)
        counts = Counter(values)
        below = sum(v < before for v in values)
        above = sum(v > before for v in values)
        equal = length - below - above
        source_counts = Counter(sources)
        prior_sources = source_history[actor]
        prior_total = sum(prior_sources.values())
        repeated = sum(prior_sources[s] > 0 for s in sources)
        repeat_posts = sum(post_history[actor][k] > 0 for k in keys)
        distance_num = sum(values) - before * length
        row = dict(ordinal=ordinal, round=round_no, agent_id=actor,
                   prior_activation_count=activation_counts[actor],
                   activation_count=activation_counts[actor]+1,
                   receiver_group=groups[actor], prior_stance=before, after_stance=after,
                   public_before=public[actor], published=bool(published),
                   public_after=after if published else public[actor],
                   reason_changed=None if pd.isna(e.get('reason_changed')) else bool(e['reason_changed']),
                   feed_length=length, exposure_class=_exposure_class(before, values),
                   feed_mean=_rate(sum(values), length),
                   feed_variance=float(np.var(values)) if length else None,
                   distance_numerator=distance_num, distance_denominator=length,
                   signed_distance=_rate(distance_num, length),
                   below_count=below, above_count=above, equal_count=equal,
                   below_share=_rate(below, length), above_share=_rate(above, length),
                   equal_share=_rate(equal, length),
                   same_group_count=sum(groups[s] == groups[actor] for s in sources),
                   other_group_count=sum(groups[s] != groups[actor] for s in sources),
                   same_group_share=_rate(sum(groups[s] == groups[actor] for s in sources), length),
                   other_group_share=_rate(sum(groups[s] != groups[actor] for s in sources), length),
                   unique_sources=len(source_counts), duplicate_source_slots=length-len(source_counts),
                   source_hhi=sum((c / length)**2 for c in source_counts.values()) if length else None,
                   mean_post_age=_rate(sum(ages), length), max_post_age=max(ages) if ages else None,
                   round0_post_slots=sum(age == round_no for age in ages),
                   repeat_post_slots=repeat_posts, repeated_source_slots=repeated,
                   post_key_method='none' if not key_types else '+'.join(sorted(set(key_types))),
                   prior_source_exposures=prior_total, prior_unique_sources=len(prior_sources),
                   prior_source_hhi=sum((c/prior_total)**2 for c in prior_sources.values()) if prior_total else None,
                   prior_below_slots=directional_history[actor]['below'],
                   prior_above_slots=directional_history[actor]['above'],
                   prior_equal_slots=directional_history[actor]['equal'],
                   changed=after != before, update_delta=after-before,
                   moved_toward_feed_mean=(abs(after*length-sum(values)) < abs(before*length-sum(values))) if length else None,
                   **{f'feed_stance_{s}_count': counts[s] for s in range(1, 8)})
        emit('A2_event_exposure_numeric', **row)
        # Histories are updated only AFTER the event's prior-history snapshot.
        prior_sources.update(sources)
        post_history[actor].update(keys)
        directional_history[actor].update(below=below, above=above, equal=equal)
        if length and len(counts) == 1:
            target = values[0]
            if target != before:
                pair = (before, target)
                opportunity[pair] += 1
                exact[pair] += after == target
                toward[pair] += abs(after-target) < abs(before-target)
        response_key = (round_no, before, row['exposure_class'], distance_num, length)
        response_denoms[response_key] += 1
        response_counts[response_key + (after,)] += 1
        transitions[before-1, after-1] += 1
        histories[actor].append((ordinal, before, after))
        activation_counts[actor] += 1
        state[actor] = after
        if published:
            public[actor] = after
            published_records[ordinal] = actor, after
        if (ordinal + 1) % n == 0:
            if int(transitions.sum()) != n or len(state) != n:
                raise ValueError('round event/population conservation failure')
            prev_counts = Counter(round_states[-1].values())
            next_counts = Counter(state.values())
            baseline = Counter(initial.values())
            for i in range(1, 8):
                for j in range(1, 8):
                    emit('A1_round_transition_matrices', round=round_no, from_stance=i,
                         to_stance=j, count=int(transitions[i-1, j-1]), n_events=n,
                         n_unique_agents=len(round_actors))
                inflow = int(transitions[:, i-1].sum()-transitions[i-1, i-1])
                outflow = int(transitions[i-1].sum()-transitions[i-1, i-1])
                net = inflow-outflow
                cumulative_inflow[i] += inflow
                cumulative_outflow[i] += outflow
                if net != next_counts[i]-prev_counts[i]:
                    raise ValueError('stance count/flow conservation failure')
                if cumulative_inflow[i]-cumulative_outflow[i] != next_counts[i]-baseline[i]:
                    raise ValueError('cumulative flow conservation failure')
                flow = dict(round=round_no, stance=i, inflow=inflow, outflow=outflow,
                            net_flow=net, cumulative_net_flow=next_counts[i]-baseline[i],
                            population_count=next_counts[i], population_share=next_counts[i]/n,
                            previous_count=prev_counts[i], round0_count=baseline[i])
                emit('A1_net_stance_flows', **flow)
                emit('A1_cumulative_flow', round=round_no, stance=i,
                     cumulative_inflow=cumulative_inflow[i], cumulative_outflow=cumulative_outflow[i],
                     cumulative_net_flow=flow['cumulative_net_flow'],
                     population_count=next_counts[i], round0_count=baseline[i],
                     focus_pair=i in (3, 5))
            round_states.append(state.copy())
            transitions.fill(0)
            round_actors.clear()
    for key, count in sorted(response_counts.items()):
        r, before, cls, distance, length, after = key
        denominator = response_denoms[key[:-1]]
        emit('A2_exposure_response_cells', round=r, prior_stance=before,
             exposure_class=cls, distance_numerator=distance, distance_denominator=length,
             feed_length=length, after_stance=after, numerator=count,
             denominator=denominator, probability=count/denominator)
    for i in range(1, 8):
        for j in range(1, 8):
            if i == j:
                continue
            pair = i, j
            denom = opportunity[pair]
            emit('A2_directional_update_rates', prior_stance=i, target_stance=j,
                 feed_condition='all_slots_exact_target_and_nonempty',
                 n_opportunities=denom, n_exact_i_to_j=exact[pair], n_toward_target=toward[pair],
                 exact_rate=_rate(exact[pair], denom), toward_rate=_rate(toward[pair], denom))
            mirror = 8-i, 8-j
            if pair > mirror:
                continue
            left, right = _rate(exact[pair], denom), _rate(exact[mirror], opportunity[mirror])
            emit('A2_seed_level_contrasts', prior_stance=i, target_stance=j,
                 mirror_prior_stance=mirror[0], mirror_target_stance=mirror[1],
                 n_opportunities=denom, mirror_n_opportunities=opportunity[mirror],
                 exact_rate=left, mirror_exact_rate=right,
                 exact_rate_difference=None if left is None or right is None else left-right,
                 toward_rate=_rate(toward[pair], denom),
                 mirror_toward_rate=_rate(toward[mirror], opportunity[mirror]),
                 figure6_pair=pair == (3, 5))
    for actor in nodes:
        history = histories[actor]
        direct35 = sum(b == 3 and a == 5 for _, b, a in history)
        direct53 = sum(b == 5 and a == 3 for _, b, a in history)
        via = Counter()
        anchor = initial[actor] if initial[actor] in (3, 5) else None
        saw4 = False
        for _, _, after in history:
            if after in (3, 5):
                if anchor is not None and after != anchor and saw4:
                    via[anchor, after] += 1
                anchor, saw4 = after, False
            elif anchor is not None and after == 4:
                saw4 = True
        emit('A1_origin_destination_paths', agent_id=actor, group=groups[actor],
             stance_r0=initial[actor], stance_r30=round_states[30][actor] if horizon >= 30 else None,
             stance_end=state[actor], direct_3_to_5_count=direct35, direct_5_to_3_count=direct53,
             via4_3_to_5_count=via[3, 5], via4_5_to_3_count=via[5, 3],
             lower_to_upper_event_count=sum(b <= 3 and a >= 5 for _, b, a in history),
             upper_to_lower_event_count=sum(b >= 5 and a <= 3 for _, b, a in history),
             first_visit_3_ordinal=next((o for o, _, a in history if a == 3), None) if initial[actor] != 3 else -1,
             first_visit_5_ordinal=next((o for o, _, a in history if a == 5), None) if initial[actor] != 5 else -1)
        for target in (3, 5):
            baseline = initial[actor] == target
            entries = [o for o, b, a in history if a == target and b != target]
            first = -1 if baseline else (entries[0] if entries else None)
            leaves = sum(b == target and a != target for _, b, a in history)
            emit('A1_dominant_stance_formation', agent_id=actor, target_stance=target,
                 origin_stance=initial[actor], baseline_occupant=baseline,
                 first_entry_ordinal=first, first_entry_round=0 if first == -1 else (first//n+1 if first is not None else None),
                 retained_continuously=first is not None and not any(o > first and b == target and a != target for o, b, a in history),
                 leave_count=leaves, reentry_count=max(0, len(entries)-(0 if baseline else 1)),
                 endpoint_occupant=state[actor] == target,
                 endpoint_contribution_count=int(state[actor] == target))
    for r, snapshot in enumerate(round_states):
        for target in (3, 5):
            for origin in range(1, 8):
                count = sum(initial[a] == origin and snapshot[a] == target for a in nodes)
                emit('A1_dominant_stance_round_shares', round=r, target_stance=target,
                     origin_stance=origin, contribution_count=count, contribution_share=count/n,
                     target_count=sum(v == target for v in snapshot.values()),
                     target_share=sum(v == target for v in snapshot.values())/n)
    # Compact descriptive conditioning; bins refer to history before this event.
    summary = defaultdict(lambda: [0, 0, 0])
    for row in tables['A2_event_exposure_numeric']:
        total = row['prior_source_exposures']
        history_bin = '0' if total == 0 else ('1-6' if total <= 6 else ('7-30' if total <= 30 else '31+'))
        key = (row['round'], row['prior_stance'], history_bin,
               row['prior_below_slots'], row['prior_above_slots'],
               row['repeated_source_slots'], row['distance_numerator'], row['feed_length'])
        entry = summary[key]
        entry[0] += 1
        entry[1] += row['changed']
        entry[2] += bool(row['moved_toward_feed_mean'])
    for key, (denom, changed, moved) in summary.items():
        r, before, histbin, below, above, repeated, distance, length = key
        emit('A2_exposure_history_summary', round=r, prior_stance=before,
             prior_exposure_bin=histbin, prior_below_slots=below, prior_above_slots=above,
             repeated_source_slots=repeated, distance_numerator=distance, feed_length=length,
             n_events=denom, n_changed=changed, change_rate=changed/denom,
             n_moved_toward_feed_mean=moved, toward_mean_rate=moved/denom if length else None,
             interpretation='posthoc_descriptive_not_causal')
    return tables
