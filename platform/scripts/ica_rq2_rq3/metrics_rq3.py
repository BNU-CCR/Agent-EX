"""Offline descriptive RQ3 metrics; no model calls, I/O, fitting or inference.

``analyze_run`` consumes a single fully reconstructed successful-event run.
Tables are lists of plain records; ``paired_results`` consumes their concatenation
(or DataFrames). R0 is initial state, round r ends after r*N serial events.
The original attention-weighted actor schedule samples with replacement: a
round is N updates, not one activation of each agent. Unselected agents retain
their previous private/public states; repeated actors follow the serial chain.
Variance is population variance (ddof=0); speeds are signed change per round.
Local edge statistics use private boundary states; realized exposure ALWAYS uses
the actual historical public post supplied in the feed, never sender private state.

199 permutations and seed 20261101 are post-hoc analytic parameters, not new
experimental conditions. Null quantiles describe fixed-network permutation
spread, NOT seed-level confidence intervals or formal permutation p-values.
No degree-stratified robustness is performed. Small seed cohorts remain distinct.
Public stock is exactly the latest public post per agent, including round-0 posts;
flow contains only newly published posts, exposure only actually selected slots.
Age >=1,5,10 are post-hoc report bins, not frozen experimental parameters.
"""
from collections import defaultdict
import hashlib
import re

import numpy as np
import pandas as pd


RUN_TABLES = (
    "B1_global_convergence_by_run", "B1_time_trajectories",
    "B2_edge_opinion_similarity", "B2_permutation_baselines",
    "B2_local_excess_homophily", "B2_realized_exposure_homophily",
    "B3_source_conditional_updating", "B4_private_public_distributions",
    "B4_public_stock_age", "B4_realized_exposure_distributions",
    "B4_visibility_gap_by_round",
)


def _ratio(a, b):
    return float(a / b) if b else None


def distribution(values):
    """Seven-bin counts/shares, moments undefined for an empty layer."""
    x = np.asarray(values, dtype=int)
    counts = np.bincount(x, minlength=8)[1:8] if x.size else np.zeros(7, dtype=int)
    out = {"n": len(x), "mean": float(x.mean()) if len(x) else None,
           "variance": float(x.var()) if len(x) else None}
    out.update({f"count_{k}": int(counts[k-1]) for k in range(1, 8)})
    out.update({f"share_{k}": _ratio(counts[k-1], len(x)) for k in range(1, 8)})
    return out


def edge_statistics(stances, edges):
    """Undirected Pearson: both orientations have equal endpoint weight."""
    if not len(edges):
        return dict(n_edges=0, same_stance_fraction=None, mean_abs_distance=None,
                    assortativity=None)
    x, y = np.asarray(stances, float)[np.asarray(edges, int)].T
    endpoint_mean = (x.mean() + y.mean()) / 2
    denominator = (np.mean(x*x) + np.mean(y*y)) / 2 - endpoint_mean**2
    return dict(n_edges=len(edges), same_stance_fraction=float(np.mean(x == y)),
                mean_abs_distance=float(np.abs(x-y).mean()),
                assortativity=float((np.mean(x*y)-endpoint_mean**2)/denominator)
                if denominator > 1e-14 else None)


def permuted_stances(stances, groups, mode, rng, permutations):
    """Yield one bounded vector, retaining all seven counts (and group margins)."""
    if mode not in ("unrestricted", "within_group"):
        raise ValueError("Unknown permutation mode")
    indices = [np.flatnonzero(groups == g) for g in np.unique(groups)]
    for _ in range(permutations):
        if mode == "unrestricted":
            yield rng.permutation(stances)
        else:
            p = np.array(stances, copy=True)
            for idx in indices:
                p[idx] = rng.permutation(stances[idx])
            yield p


def _rng(meta, round_number, mode, analysis_seed):
    identity = "|".join(str(meta.get(k, "")) for k in
                        ("topic_key", "matched_seed", "cell_id", "run_id", "cohort", "horizon"))
    digest = hashlib.sha256(f"{identity}|{round_number}|{mode}".encode()).digest()
    words = np.frombuffer(digest, dtype="<u4").tolist()
    return np.random.default_rng(np.random.SeedSequence([analysis_seed, *words]))


def _expected_same(x, groups, edges, mode):
    if not len(edges):
        return None
    if mode == "unrestricted":
        counts = np.bincount(x, minlength=8)[1:8]
        return _ratio(np.sum(counts*(counts-1)), len(x)*(len(x)-1))
    total = 0.
    for ga in np.unique(groups):
        xa = x[groups == ga]
        ca = np.bincount(xa, minlength=8)[1:8]
        for gb in np.unique(groups):
            mask = (groups[edges[:, 0]] == ga) & (groups[edges[:, 1]] == gb)
            n_edges = int(mask.sum())
            if not n_edges:
                continue
            if ga == gb:
                prob = _ratio(np.sum(ca*(ca-1)), len(xa)*(len(xa)-1))
            else:
                xb = x[groups == gb]
                cb = np.bincount(xb, minlength=8)[1:8]
                prob = float(np.sum(ca*cb)/(len(xa)*len(xb)))
            total += n_edges*prob
    return total/len(edges)


def _edge_tables(meta, round_number, x, groups, edges, permutations, analysis_seed):
    """One round at a time: at most permutations*N + permutations*E arrays."""
    same_group = groups[edges[:, 0]] == groups[edges[:, 1]] if len(edges) else np.array([], bool)
    scopes = {"all": edges, "same_group": edges[same_group], "different_group": edges[~same_group]}
    observed, baselines, excess = [], [], []
    for scope, ee in scopes.items():
        observed.append({**meta, "round": round_number, "edge_scope": scope,
                         **edge_statistics(x, ee)})
    for mode in ("unrestricted", "within_group"):
        rng = _rng(meta, round_number, mode, analysis_seed)
        draws = np.asarray(list(permuted_stances(x, groups, mode, rng, permutations)))
        for scope, ee in scopes.items():
            expected = _expected_same(x, groups, ee, mode)
            samples = {}
            if len(ee) and permutations:
                u, v = draws[:, ee[:, 0]], draws[:, ee[:, 1]]
                samples["same_stance_fraction"] = (u == v).mean(axis=1)
                samples["mean_abs_distance"] = np.abs(u-v).mean(axis=1)
                endpoint_mean = (u.mean(axis=1)+v.mean(axis=1))/2
                denom = ((u*u).mean(axis=1)+(v*v).mean(axis=1))/2-endpoint_mean**2
                assort = np.full(permutations, np.nan)
                np.divide((u*v).mean(axis=1)-endpoint_mean**2, denom,
                          out=assort, where=denom > 1e-14)
                samples["assortativity"] = assort
            base = dict(**meta, round=round_number, edge_scope=scope,
                        permutation_mode=mode, permutations=permutations,
                        analysis_seed=analysis_seed,
                        expected_same_stance_fraction=expected,
                        null_description="fixed_graph_fixed_margins_descriptive_no_pvalue")
            for metric in ("same_stance_fraction", "mean_abs_distance", "assortativity"):
                a = samples.get(metric, np.array([]))
                a = a[np.isfinite(a)]
                for suffix, value in (("mean", np.mean(a) if len(a) else None),
                                      ("sd", np.std(a) if len(a) else None),
                                      ("q025", np.quantile(a, .025) if len(a) else None),
                                      ("q975", np.quantile(a, .975) if len(a) else None)):
                    base[f"null_{metric}_{suffix}"] = float(value) if value is not None else None
            baselines.append(base)
            actual = edge_statistics(x, ee)["same_stance_fraction"]
            excess.append({**meta, "round": round_number, "edge_scope": scope,
                           "permutation_mode": mode, "actual_same_stance_fraction": actual,
                           "expected_same_stance_fraction": expected,
                           "excess_same_stance_fraction": actual-expected if expected is not None else None})
    return observed, baselines, excess


def _age_stats(ages):
    a = np.asarray(ages, float)
    return {"mean_age_rounds": float(a.mean()) if len(a) else None,
            **{f"fraction_age_ge_{k}": float(np.mean(a >= k)) if len(a) else None
               for k in (1, 5, 10)}}


def _condition(cell_id):
    match = re.search(r"A([01])[^A-Za-z0-9]*B([012])", str(cell_id))
    if not match:
        raise ValueError(f"Unrecognized cell_id {cell_id!r}; expected A0B0..A1B2")
    return "A"+match[1], "B"+match[2]


def analyze_run(run, *, permutations=199, analysis_seed=20261101):
    """Replay one run; fail closed on broken event/state or public-post identity.

    Required meta: topic_key, matched_seed, cell_id, run_id, cohort, horizon.
    ``events``: ordinal, agent_id, before, after, published; optional reason_changed.
    ``feed``: ordinal, receiver_agent_id, display_slot, source_agent_id,
    source_stance, publication_ordinal (null for R0), optional post_id.
    No raw reason text is consumed or returned. All caller meta is retained.
    """
    if permutations < 0 or int(permutations) != permutations:
        raise ValueError("permutations must be a nonnegative integer")
    meta = dict(run["meta"])
    for key in ("topic_key", "matched_seed", "cell_id", "run_id", "cohort", "horizon"):
        if key not in meta:
            raise ValueError(f"Missing metadata {key}")
    meta["identity_condition"], meta["network_condition"] = _condition(meta["cell_id"])
    nodes = list(map(str, run["node_ids"]))
    n, horizon = len(nodes), int(meta["horizon"])
    if n < 2 or len(set(nodes)) != n or horizon < 1:
        raise ValueError("Invalid nodes/horizon")
    idx = {a: i for i, a in enumerate(nodes)}
    groups = np.array([run["groups"][a] for a in nodes])
    if not set(groups).issubset({"Blue", "Green"}):
        raise ValueError("Unknown group")
    original_x = np.array([run["initial_stances"][a] for a in nodes])
    original_public = np.array([run["initial_public"][a] for a in nodes])
    x = original_x.astype(int)
    public = original_public.astype(int)
    if (not np.array_equal(x, original_x) or not np.array_equal(public, original_public)
            or np.any((x < 1) | (x > 7)) or np.any((public < 1) | (public > 7))):
        raise ValueError("Stances must be integers 1..7")
    raw_edges = [(idx[str(a)], idx[str(b)]) for a, b in run["edges"]]
    if any(a == b for a, b in raw_edges) or len({tuple(sorted(e)) for e in raw_edges}) != len(raw_edges):
        raise ValueError("Edges must be a simple undirected graph")
    edges = np.array(raw_edges, dtype=int).reshape(-1, 2)
    if meta["network_condition"] == "B0" and len(edges):
        raise ValueError("B0 must not have social edges")
    ev = run["events"].sort_values("ordinal")
    if len(ev) != n*horizon or not np.array_equal(ev["ordinal"].to_numpy(), np.arange(n*horizon)):
        raise ValueError("Expected complete contiguous successful-event ordinals")
    feed = run["feed"]
    by_event = {}
    if len(feed):
        required = ("ordinal", "receiver_agent_id", "display_slot", "source_agent_id", "source_stance", "publication_ordinal")
        if any(c not in feed for c in required):
            raise ValueError("Missing actual-feed fields")
        if feed.duplicated(["ordinal", "display_slot"]).any():
            raise ValueError("Duplicate display slot")
        if not feed["ordinal"].isin(ev["ordinal"]).all():
            raise ValueError("Feed ordinal outside successful events")
        # One namedtuple type per run, not one dynamically created class per event.
        for f in feed.sort_values(["ordinal", "display_slot"]).itertuples(index=False):
            by_event.setdefault(int(f.ordinal), []).append(f)
    tables = {name: [] for name in RUN_TABLES}
    initial = distribution(x)
    previous = initial
    public_round = np.zeros(n, dtype=int)
    archive = {(a, None): int(public[i]) for i, a in enumerate(nodes)}
    seen_by_receiver = set()
    post_receivers = defaultdict(set)
    seen_sources = set()
    totals = defaultdict(int)

    def boundary(r, flow, exposure, ages, feed_stats, replaced, stock_before):
        nonlocal previous
        for counter in ("repeated_post_within_receiver_slots", "repeated_post_across_receivers_slots",
                        "old_post_repeated_within_receiver_slots", "old_post_repeated_across_receivers_slots",
                        "repeated_source_within_receiver_slots"):
            feed_stats.setdefault(counter, 0)
            feed_stats[counter.removesuffix("_slots")+"_fraction"] = _ratio(feed_stats[counter], len(exposure))
        d = distribution(x)
        change = d["variance"]-initial["variance"]
        trajectory = {**meta, "round": r, **d,
                      "variance_change_from_r0": change,
                      "variance_fraction_of_r0": _ratio(d["variance"], initial["variance"]),
                      "variance_normalized_change_from_r0": _ratio(change, initial["variance"]),
                      "variance_delta_per_round": d["variance"]-previous["variance"] if r else None,
                      "variance_average_change_per_round_since_r0": change/r if r else None}
        for k in range(1, 8):
            trajectory[f"share_{k}_delta_per_round"] = d[f"share_{k}"]-previous[f"share_{k}"] if r else None
            trajectory[f"share_{k}_change_from_r0"] = d[f"share_{k}"]-initial[f"share_{k}"]
        tables["B1_time_trajectories"].append(trajectory)
        previous = d
        observed, null, excess = _edge_tables(meta, r, x, groups, edges, permutations, analysis_seed)
        tables["B2_edge_opinion_similarity"].extend(observed)
        tables["B2_permutation_baselines"].extend(null)
        tables["B2_local_excess_homophily"].extend(excess)
        for layer, values in (("private_state", x), ("public_flow", flow),
                              ("public_stock", public), ("realized_exposure", exposure)):
            tables["B4_private_public_distributions"].append({**meta, "round": r,
                                                             "layer": layer, **distribution(values)})
        tables["B4_public_stock_age"].append({**meta, "round": r, "n": n,
                                              **_age_stats(r-public_round)})
        tables["B4_realized_exposure_distributions"].append({**meta, "round": r,
            **distribution(exposure), **_age_stats(ages),
            **{k: v for k, v in feed_stats.items() if k.startswith("repeated_") or k.startswith("old_")},
            "post_identity_basis": "post_id_when_available_else_source_and_publication_ordinal"})
        p = np.array([d[f"share_{k}"] for k in range(1, 8)])
        qd = distribution(public)
        q = np.array([qd[f"share_{k}"] for k in range(1, 8)])
        qprev = np.array([stock_before[f"share_{k}"] for k in range(1, 8)])
        tables["B4_visibility_gap_by_round"].append({**meta, "round": r,
            "mean_agent_private_public_abs_gap": float(np.abs(x-public).mean()),
            "private_stock_tv": float(.5*np.abs(p-q).sum()),
            "private_stock_wasserstein": float(np.abs(np.cumsum(p-q)[:-1]).sum()),
            "stock_before_after_round_tv": float(.5*np.abs(q-qprev).sum()),
            "n_stock_agents_replaced_this_round": len(replaced),
            "n_new_public_posts": len(flow),
            "interpretation": "descriptive_visibility_not_identified_mechanism"})
        counts = np.bincount(np.asarray(exposure, int), minlength=8)[1:8] if exposure else np.zeros(7)
        probs = counts/counts.sum() if counts.sum() else np.array([])
        probs = probs[probs > 0]
        f = {**meta, "round": r, "n_slots": len(exposure),
             "mean_feed_stance": float(np.mean(exposure)) if exposure else None,
             "same_stance_fraction": _ratio(feed_stats["same_stance_slots"], len(exposure)),
             "mean_abs_distance": _ratio(feed_stats["distance_sum"], len(exposure)),
             "pooled_slot_stance_entropy_nats": float(-np.sum(probs*np.log(probs))) if len(probs) else None,
             "mean_event_feed_entropy_nats": _ratio(feed_stats["event_entropy_sum"], feed_stats["n_events_with_feed"]),
             "same_group_fraction": _ratio(feed_stats["same_group_slots"], len(exposure)),
             "blue_source_fraction": _ratio(feed_stats["blue_source_slots"], len(exposure)),
             "green_source_fraction": _ratio(feed_stats["green_source_slots"], len(exposure)),
             **dict(feed_stats), **_age_stats(ages),
             "post_identity_basis": "post_id_when_available_else_source_and_publication_ordinal"}
        tables["B2_realized_exposure_homophily"].append(f)
        return trajectory, excess

    empty_stats = lambda: defaultdict(float)
    endpoint, last_excess = boundary(0, [], [], [], empty_stats(), set(), distribution(public))
    conditional = defaultdict(lambda: defaultdict(int))
    event_rows = list(ev.itertuples(index=False))
    for r in range(1, horizon+1):
        block = event_rows[(r-1)*n:r*n]
        if any(str(e.agent_id) not in idx for e in block):
            raise ValueError("Successful event actor is outside the fixed population")
        flow, exposure, ages = [], [], []
        stats = empty_stats()
        replaced = set()
        stock_before = distribution(public)
        for e in block:
            ordinal, agent = int(e.ordinal), str(e.agent_id)
            i, before, after = idx[agent], int(e.before), int(e.after)
            if x[i] != before or not 1 <= after <= 7 or e.before != before or e.after != after:
                raise ValueError("Broken successful-event state replay")
            if not isinstance(e.published, (bool, np.bool_)):
                raise ValueError("published must be a real boolean")
            messages = by_event.get(ordinal, [])
            ss, same_group_count = [], 0
            for f in messages:
                source = str(f.source_agent_id)
                if str(f.receiver_agent_id) != agent or source not in idx or source == agent:
                    raise ValueError("Invalid actual-feed receiver/source")
                po = None if pd.isna(f.publication_ordinal) else int(f.publication_ordinal)
                if po is not None and (po >= ordinal or po < 0 or po != f.publication_ordinal):
                    raise ValueError("Feed references future or invalid public post")
                stance = int(f.source_stance)
                if stance != f.source_stance or archive.get((source, po)) != stance:
                    raise ValueError("Feed post does not match an observed original publication")
                raw_post_id = getattr(f, "post_id", None)
                post_key = (source, "post_id", str(raw_post_id)) if raw_post_id is not None and not pd.isna(raw_post_id) else (source, "ordinal", po)
                receiver_key = (agent, post_key)
                age = r-(po//n+1 if po is not None else 0)
                repeated_self = receiver_key in seen_by_receiver
                repeated_other = bool(post_receivers[post_key]-{agent})
                stats["repeated_post_within_receiver_slots"] += int(repeated_self)
                stats["repeated_post_across_receivers_slots"] += int(repeated_other)
                stats["old_post_repeated_within_receiver_slots"] += int(repeated_self and age >= 1)
                stats["old_post_repeated_across_receivers_slots"] += int(repeated_other and age >= 1)
                stats["repeated_source_within_receiver_slots"] += int((agent, source) in seen_sources)
                seen_by_receiver.add(receiver_key)
                post_receivers[post_key].add(agent)
                seen_sources.add((agent, source))
                sg = groups[idx[source]] == groups[i]
                same_group_count += int(sg)
                stats["same_group_slots"] += int(sg)
                stats["blue_source_slots"] += int(groups[idx[source]] == "Blue")
                stats["green_source_slots"] += int(groups[idx[source]] == "Green")
                stats["same_stance_slots"] += int(stance == before)
                stats["distance_sum"] += abs(stance-before)
                ss.append(stance)
                exposure.append(stance)
                ages.append(age)
            mean_feed = float(np.mean(ss)) if ss else None
            distance = abs(mean_feed-before) if ss else None
            if ss:
                c = np.bincount(ss, minlength=8)[1:8]
                p = c[c > 0]/len(ss)
                stats["event_entropy_sum"] += float(-np.sum(p*np.log(p)))
                stats["n_events_with_feed"] += 1
            mix = ("no_feed" if not ss else "same_group_only" if same_group_count == len(ss)
                   else "other_group_only" if same_group_count == 0 else "mixed_groups")
            key = (r, before, len(ss), same_group_count, len(ss)-same_group_count, mix,
                   any(s == before for s in ss), any((s-4)*(before-4) < 0 for s in ss),
                   any(s != before for s in ss), mean_feed, distance)
            c = conditional[key]
            c["n_events"] += 1
            c["n_changed"] += int(before != after)
            c["n_move_toward_feed"] += int(bool(ss) and abs(after-mean_feed) < abs(before-mean_feed))
            c["n_upward"] += int(after > before)
            c["n_downward"] += int(after < before)
            reason_changed = getattr(e, "reason_changed", None)
            if reason_changed is not None and not pd.isna(reason_changed):
                if not isinstance(reason_changed, (bool, np.bool_)):
                    raise ValueError("reason_changed must be boolean or missing")
                c["n_reason_change_known"] += 1
                c["n_reason_changed"] += int(reason_changed)
                totals["n_reason_change_known"] += 1
                totals["n_reason_changed"] += int(reason_changed)
            totals["n_events"] += 1
            totals["n_changed"] += int(before != after)
            totals["n_low_to_high"] += int(before <= 3 and after >= 5)
            totals["n_high_to_low"] += int(before >= 5 and after <= 3)
            totals["n_upward"] += int(after > before)
            totals["n_downward"] += int(after < before)
            x[i] = after
            if e.published:
                public[i], public_round[i] = after, r
                archive[(agent, ordinal)] = after
                flow.append(after)
                replaced.add(agent)
        endpoint, last_excess = boundary(r, flow, exposure, ages, stats, replaced, stock_before)
    names = ("round", "current_stance", "n_feed", "n_same_group_feed", "n_other_group_feed",
             "source_group_mix", "has_same_stance_source", "has_opposite_side_source",
             "has_different_stance_source", "feed_mean_stance", "abs_feed_mean_distance")
    for key, counts in sorted(conditional.items(), key=lambda kv: str(kv[0])):
        tables["B3_source_conditional_updating"].append({**meta, **dict(zip(names, key)), **counts,
            "change_rate": _ratio(counts["n_changed"], counts["n_events"]),
            "n_reason_change_known": counts["n_reason_change_known"],
            "n_reason_changed": counts["n_reason_changed"] if counts["n_reason_change_known"] else None,
            "reason_change_rate": _ratio(counts["n_reason_changed"], counts["n_reason_change_known"]),
            "move_toward_feed_rate": _ratio(counts["n_move_toward_feed"], counts["n_events"])
            if key[2] else None,
            "interpretation": "event_level_conditional_association_not_source_label_causality"})
    final = {**endpoint, **dict(totals), "change_event_rate": _ratio(totals["n_changed"], totals["n_events"])}
    final.update(n_reason_change_known=totals["n_reason_change_known"],
                 n_reason_changed=totals["n_reason_changed"] if totals["n_reason_change_known"] else None,
                 reason_change_rate=_ratio(totals["n_reason_changed"], totals["n_reason_change_known"]))
    for direction in ("low_to_high", "high_to_low", "upward", "downward"):
        final[f"{direction}_event_rate"] = _ratio(totals[f"n_{direction}"], totals["n_events"])
    for mode in ("unrestricted", "within_group"):
        final[f"excess_same_stance_{mode}"] = next(v["excess_same_stance_fraction"] for v in last_excess
            if v["edge_scope"] == "all" and v["permutation_mode"] == mode)
    tables["B1_global_convergence_by_run"].append(final)
    return tables


def _records(table):
    return table.to_dict("records") if isinstance(table, pd.DataFrame) else list(table)


def _difference(a, b):
    return float(a-b) if a is not None and b is not None and pd.notna(a) and pd.notna(b) else None


def paired_results(tables):
    """Within-seed endpoint contrasts, never pooling agents or mixing cohorts.

    Missing partners produce no invented pair. Duplicate cells within a
    topic/seed/cohort/horizon fail closed. B0 local edge measures remain NA;
    their DID is undefined, not zero. B2-vs-B1 identity contrast is separate.
    """
    names = ("B1_paired_network_effects", "B1_topology_contrasts",
             "B3_identity_effects_by_seed", "B3_identity_network_interactions")
    out = {k: [] for k in names}
    endpoints = _records(tables.get("B1_global_convergence_by_run", []))
    blocks = defaultdict(dict)
    for row in endpoints:
        key = tuple(row[k] for k in ("topic_key", "matched_seed", "cohort", "horizon"))
        a, b = _condition(row["cell_id"])
        if (a, b) in blocks[key]:
            raise ValueError("Duplicate endpoint in matched seed/cohort/horizon")
        blocks[key][a, b] = row
    identity_metrics = ["variance", "mean", *[f"share_{k}" for k in range(1, 8)],
                        "change_event_rate", "n_low_to_high", "n_high_to_low",
                        "low_to_high_event_rate", "high_to_low_event_rate",
                        "upward_event_rate", "downward_event_rate",
                        "excess_same_stance_unrestricted", "excess_same_stance_within_group"]
    for key, cells in blocks.items():
        meta = dict(zip(("topic_key", "matched_seed", "cohort", "horizon"), key))
        meta["round"] = key[-1]
        for a in ("A0", "A1"):
            b0 = cells.get((a, "B0"))
            if b0 is None:
                continue
            for b in ("B1", "B2"):
                target = cells.get((a, b))
                if target is None:
                    continue
                delta = target["variance"]-b0["variance"]
                out["B1_paired_network_effects"].append({**meta, "identity_condition": a,
                    "network_condition": b, "run_id": target["run_id"], "b0_run_id": b0["run_id"],
                    "variance_network": target["variance"], "variance_b0": b0["variance"],
                    "network_effect_variance": delta,
                    "network_effect_variance_pct_of_b0": _ratio(100*delta, b0["variance"]),
                    "normalized_r0_change_difference": _difference(target["variance_normalized_change_from_r0"], b0["variance_normalized_change_from_r0"])})
            b1, b2 = cells.get((a, "B1")), cells.get((a, "B2"))
            if b1 is not None and b2 is not None:
                delta = b2["variance"]-b1["variance"]
                out["B1_topology_contrasts"].append({**meta, "identity_condition": a,
                    "b0_run_id": b0["run_id"], "b1_run_id": b1["run_id"], "b2_run_id": b2["run_id"],
                    "variance_b0": b0["variance"], "variance_b1": b1["variance"], "variance_b2": b2["variance"],
                    "topology_effect_b2_minus_b1": delta,
                    "topology_effect_pct_of_b0": _ratio(100*delta, b0["variance"]),
                    "normalized_r0_change_difference": _difference(b2["variance_normalized_change_from_r0"], b1["variance_normalized_change_from_r0"])})
        identities = {}
        for b in ("B0", "B1", "B2"):
            a0, a1 = cells.get(("A0", b)), cells.get(("A1", b))
            if a0 is None or a1 is None:
                continue
            differences = {metric: _difference(a1.get(metric), a0.get(metric)) for metric in identity_metrics}
            identities[b] = differences
            out["B3_identity_effects_by_seed"].append({**meta, "network_condition": b,
                "a0_run_id": a0["run_id"], "a1_run_id": a1["run_id"],
                **{metric+"_a1_minus_a0": value for metric, value in differences.items()},
                **{metric+"_a0": a0.get(metric) for metric in identity_metrics},
                **{metric+"_a1": a1.get(metric) for metric in identity_metrics},
                "interpretation": "conditional_joint_identity_manipulation_not_identified_label_mechanism"})
        if "B0" in identities:
            for b in ("B1", "B2"):
                if b not in identities:
                    continue
                out["B3_identity_network_interactions"].append({**meta, "network_condition": b,
                    "contrast_type": "identity_network_did_vs_b0",
                    **{metric+"_did": _difference(identities[b][metric], identities["B0"][metric])
                       for metric in identity_metrics},
                    "edge_did_status": "undefined_B0_has_no_social_edges"})
        if "B1" in identities and "B2" in identities:
            out["B3_identity_network_interactions"].append({**meta,
                "network_condition": "B2_minus_B1", "contrast_type": "paired_identity_b2_minus_b1",
                **{metric+"_did": _difference(identities["B2"][metric], identities["B1"][metric])
                   for metric in identity_metrics},
                "edge_did_status": "defined_network_pair_alternative_not_B0_DID"})
    return out
