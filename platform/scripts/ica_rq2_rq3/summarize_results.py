"""Generate data-first English RQ2/RQ3 briefs from complete offline tables.

Descriptive units are matched seeds. Within each network, A0/A1 receive equal
weight within seed, then available matched seeds receive equal weight. Rates
are averaged as rates, not reconstructed by pooling their event denominators.
No causal identity mediation, coded sycophancy, p-values or confidence intervals.
Production output is gated on all102 horizon trajectories /1,890,000 unique
events; reused retirement T30 prefixes never become extra replications.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path("V:/Agent EX/Agent-EX-evidence/2026-11-01/ica-rq2-rq3-v1")
TOPIC_LABELS = {"retirement":"Retirement", "gm-market-support":"GM market sales",
                "genai-net-job-loss":"AI job loss"}
REQUIRED_TABLES = (
    "B1_global_convergence_by_run", "B1_paired_network_effects", "B1_topology_contrasts",
    "A1_net_stance_flows", "A1_round_transition_matrices", "A2_directional_update_rates",
    "B2_edge_opinion_similarity", "B2_local_excess_homophily", "B2_realized_exposure_homophily",
    "B3_identity_effects_by_seed", "B3_identity_network_interactions",
    "B4_private_public_distributions", "B4_public_stock_age", "B4_visibility_gap_by_round")


def _clean(value):
    if isinstance(value, dict):return {str(k):_clean(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):return [_clean(v) for v in value]
    if isinstance(value, np.generic):value=value.item()
    if isinstance(value,float) and not np.isfinite(value):return None
    return value


def seed_summary(frame, metric):
    """Equal condition weights within seed, then equal available seed weights."""
    if frame.empty or metric not in frame:
        return dict(mean=None,minimum=None,maximum=None,n_seeds=0,n_seeds_missing=0,seed_values=[])
    grouped = frame.groupby("matched_seed",sort=True)[metric]
    means, counts = grouped.mean(), grouped.count()
    valid = means.dropna()
    return _clean(dict(mean=float(valid.mean()) if len(valid) else None,
        minimum=float(valid.min()) if len(valid) else None,
        maximum=float(valid.max()) if len(valid) else None,
        n_seeds=len(valid),n_seeds_missing=int(means.isna().sum()),
        seed_values=[dict(matched_seed=k,value=v,n_defined_condition_rows=int(counts.loc[k]))
                     for k,v in means.items()]))


def validate_coverage(endpoints,verification,*,unit_test_mode=False):
    if unit_test_mode:
        return dict(unit_fixture_only=True,endpoint_rows=len(endpoints))
    if (verification.get("completed_horizon_trajectories") != 102
            or verification.get("unique_network_events") != 1890000 or len(endpoints) != 102):
        raise ValueError("Final findings require all102 horizons and1,890,000 unique events; partial data refused")
    keys=["topic_key","matched_seed","cell_id","horizon"]
    if endpoints.duplicated(keys).any() or not (endpoints["n"]==500).all():
        raise ValueError("Unique complete N500 endpoint cells required")
    expected={("retirement",30):10,("retirement",60):3,
              ("gm-market-support",60):2,("genai-net-job-loss",60):2}
    actual={(str(t),int(h)):int(g.matched_seed.nunique()) for (t,h),g in endpoints.groupby(["topic_key","horizon"])}
    if actual != expected:
        raise ValueError("Exact separate issue/horizon seed cohorts required")
    for (topic,horizon),group in endpoints.groupby(["topic_key","horizon"]):
        if group.cohort.nunique()!=1 or len(group)!=6*expected[(topic,int(horizon))]:
            raise ValueError("Complete six-cell seed blocks required")
        for seed, block in group.groupby("matched_seed"):
            expected_cells={f"SIS-A{a}-B{b}" for a in (0,1) for b in (0,1,2)}
            if set(block.cell_id)!=expected_cells:
                raise ValueError("Unmatched six-cell seed block")
    if not (endpoints["n_events"]==endpoints["horizon"]*500).all():
        raise ValueError("Endpoint event coverage differs from N500*horizon")
    unique_events=int(endpoints.groupby(["topic_key","matched_seed","cell_id"])["n_events"].max().sum())
    if unique_events != 1890000:
        raise ValueError("Prefix-deduplicated actual event coverage differs")
    return dict(unit_fixture_only=False,endpoint_rows=102,unique_network_events=unique_events,
                horizon_events_including_reused_prefixes=int(endpoints.n_events.sum()),
                independent_panels=expected.__len__())


def _normalized(frame):
    frame=frame.copy()
    for old,new in (("network_condition","network_b"),("identity_condition","identity_a")):
        if old in frame and new not in frame:frame[new]=frame[old]
    return frame


def _panel(frame,topic,horizon,cohort):
    return frame[(frame.topic_key==topic)&(frame.horizon==horizon)&(frame.cohort==cohort)]


def _endpoint(frame):
    return frame[frame["round"]==frame["horizon"]] if "round" in frame else frame


def _by_network(frame,metrics):
    return {str(net):{metric:seed_summary(g,metric) for metric in metrics}
            for net,g in frame.groupby("network_b",sort=True)} if "network_b" in frame else {}


def build_summary(tables,verification,*,unit_test_mode=False):
    """Numerical source for briefs; all raw seed values remain in each summary."""
    data={k:_normalized(v) for k,v in tables.items()}
    ends=data["B1_global_convergence_by_run"]
    coverage=validate_coverage(ends,verification,unit_test_mode=unit_test_mode)
    missing=set(REQUIRED_TABLES)-set(data)
    if missing:raise ValueError("Missing result tables: "+", ".join(sorted(missing)))
    result=dict(schema="ica2027.rq2-rq3.numeric-summary.v1",coverage=coverage,
        estimand="equal A0/A1 within matched seed within network, then equal matched seeds; no event pooling",
        uncertainty="observed matched-seed minimum/maximum, not confidence intervals",
        identity_status="Original Stage-A/B joint manipulation admission did not pass; no identified identity mechanism",
        semantic_coding_status="No human semantic mechanism coding completed; sycophancy not identified",
        p0_context=dict(no_feed_held=dict(retirement=[150,168],gm_market_support=[153,168],ai_job_loss=[161,168]),
                        source_labels_visible=False,
                        interpretation="fixed one-step originalP0 context only; not networkreplication or pure3/pure5 exposure"),panels=[])
    for (topic,horizon,cohort), e in ends.groupby(["topic_key","horizon","cohort"],sort=True):
        p=dict(topic_key=topic,horizon=int(horizon),cohort=cohort,n_seeds=int(e.matched_seed.nunique()),
               label=f"{TOPIC_LABELS.get(topic,topic)} T{int(horizon)} (n={e.matched_seed.nunique()} seeds)")
        subset=lambda name:_panel(data[name],topic,horizon,cohort)
        p["b1_endpoint"]=_by_network(e,["variance","mean","share_3","share_5","variance_normalized_change_from_r0","change_event_rate"])
        p["b1_network_effect"]=_by_network(subset("B1_paired_network_effects"),["network_effect_variance","network_effect_variance_pct_of_b0"])
        p["b1_topology_b2_minus_b1"]=seed_summary(subset("B1_topology_contrasts"),"topology_effect_b2_minus_b1")
        flows=_endpoint(subset("A1_net_stance_flows"))
        p["a1_dominant"]={str(s):_by_network(flows[flows.stance==s],["population_share","cumulative_net_flow"])
                          for s in (3,5)}
        transitions=subset("A1_round_transition_matrices")
        direct=[]
        for (seed,cell,net),g in transitions.groupby(["matched_seed","cell_id","network_b"]):
            direct.append(dict(matched_seed=seed,cell_id=cell,network_b=net,
                direct_5_to_3=int(g.loc[(g.from_stance==5)&(g.to_stance==3),"count"].sum()),
                direct_3_to_5=int(g.loc[(g.from_stance==3)&(g.to_stance==5),"count"].sum()),
                low_to_high=int(g.loc[(g.from_stance<=3)&(g.to_stance>=5),"count"].sum()),
                high_to_low=int(g.loc[(g.from_stance>=5)&(g.to_stance<=3),"count"].sum())))
        p["a1_direct_events"]=_by_network(pd.DataFrame(direct),["direct_5_to_3","direct_3_to_5","low_to_high","high_to_low"])
        directions=subset("A2_directional_update_rates")
        pure=directions[((directions.prior_stance==5)&(directions.target_stance==3))|
                        ((directions.prior_stance==3)&(directions.target_stance==5))].copy()
        pure["direction"]=np.where(pure.prior_stance==5,"5_to_3_pure3","3_to_5_pure5")
        p["a2_directional"]={name:_by_network(g,["exact_rate","toward_rate","n_opportunities","n_exact_i_to_j","n_toward_target"])
                             for name,g in pure.groupby("direction")}
        p["a2_directional_actual_cells"]=_clean(pure[["matched_seed","cell_id","network_b","identity_a","direction",
             "n_opportunities","n_exact_i_to_j","n_toward_target","exact_rate","toward_rate"]].to_dict("records"))
        pairkeys=["matched_seed","cell_id","network_b","identity_a"]
        down=pure[pure.direction=="5_to_3_pure3"]
        up=pure[pure.direction=="3_to_5_pure5"]
        paired=down.merge(up,on=pairkeys,suffixes=("_down","_up"),validate="one_to_one")
        for metric in ("exact_rate","toward_rate"):
            paired[metric+"_down_minus_up"]=paired[metric+"_down"]-paired[metric+"_up"]
        p["a2_asymmetry"]=_by_network(paired,["exact_rate_down_minus_up","toward_rate_down_minus_up"])
        edges=_endpoint(subset("B2_edge_opinion_similarity"))
        edges=edges[edges.edge_scope=="all"]
        p["b2_actual"]=_by_network(edges,["same_stance_fraction","mean_abs_distance","assortativity"])
        local=_endpoint(subset("B2_local_excess_homophily"))
        local=local[local.edge_scope=="all"]
        p["b2_excess"]={mode:_by_network(g,["actual_same_stance_fraction","expected_same_stance_fraction","excess_same_stance_fraction"])
                        for mode,g in local.groupby("permutation_mode")}
        p["b2_excess_topology"]={}
        for mode,g in local.groupby("permutation_mode"):
            z=g[g.network_b.isin(["B1","B2"])].groupby(["matched_seed","network_b"])["excess_same_stance_fraction"].mean().unstack()
            if {"B1","B2"}.issubset(z):
                z["difference"]=z.B2-z.B1
                p["b2_excess_topology"][mode]=seed_summary(z.reset_index(),"difference")
        exposure=_endpoint(subset("B2_realized_exposure_homophily"))
        p["b2_realized_exposure"]=_by_network(exposure,["same_stance_fraction","mean_abs_distance","mean_age_rounds",
                      "same_group_fraction","pooled_slot_stance_entropy_nats","repeated_post_within_receiver_fraction"])
        identities=subset("B3_identity_effects_by_seed")
        p["b3_identity_effects"]=_by_network(identities,["variance_a1_minus_a0","mean_a1_minus_a0","share_3_a1_minus_a0",
            "share_5_a1_minus_a0","change_event_rate_a1_minus_a0","excess_same_stance_unrestricted_a1_minus_a0"])
        interactions=subset("B3_identity_network_interactions")
        p["b3_interactions"]={name:_by_network(g,["variance_did","share_3_did","share_5_did","excess_same_stance_unrestricted_did"])
                              for name,g in interactions.groupby("contrast_type")}
        gap=_endpoint(subset("B4_visibility_gap_by_round"))
        p["b4_gap"]=_by_network(gap,["mean_agent_private_public_abs_gap","private_stock_tv","private_stock_wasserstein",
                                "stock_before_after_round_tv","n_stock_agents_replaced_this_round","n_new_public_posts"])
        p["b4_stock_age"]=_by_network(_endpoint(subset("B4_public_stock_age")),
                                     ["mean_age_rounds","fraction_age_ge_1","fraction_age_ge_5","fraction_age_ge_10"])
        layers=_endpoint(subset("B4_private_public_distributions"))
        p["b4_distributions"]={layer:_by_network(g,["n","mean","variance","share_3","share_5"])
                               for layer,g in layers.groupby("layer")}
        result["panels"].append(p)
    return _clean(result)


def _stat(s,*,percent=False,percentage_points=False):
    if not s or s.get("mean") is None:return "NA (no defined opportunities)"
    scale=100 if percent or percentage_points else 1
    fmt=lambda x:f"{x*scale:.2f}"+("pp" if percentage_points else "%" if percent else "")
    return f"{fmt(s['mean'])} [{fmt(s['minimum'])}, {fmt(s['maximum'])}]; n={s['n_seeds']}"


def _mean(p,section,network,metric):
    return p.get(section,{}).get(network,{}).get(metric,{})


def _value(s,digits=3):
    return "NA" if not s or s.get("mean") is None else f"{s['mean']:.{digits}f}"


def _ordering(s):
    if not s or s.get("mean") is None:return "undefined"
    return "higher" if s["mean"]>1e-12 else "lower" if s["mean"] < -1e-12 else "equal"


def _table(headers,rows):
    def cell(value):return str(value).replace('|','\\|').replace('\n',' ')
    return "| "+" | ".join(map(cell,headers))+" |\n| "+" | ".join(["---"]*len(headers))+" |\n"+"\n".join("| "+" | ".join(map(cell,r))+" |" for r in rows)+"\n"


METHODS = ("Each network summary first gives A0 and A1 equal weight within a matched seed, then gives matched seeds equal weight. "
    "Paired identity effects are A1−A0 within seed/network. Brackets show the observed seed range, not confidence intervals. "
    "Undefined rates are retained as NA; valid-seed counts can therefore differ. Retirement T30 (10 seeds) and T60 (3 continuing seeds) "
    "are separate panels; each other T60 issue has 2 seeds. T60 prefixes are not additional replications. "
    "A round contains 500 weighted-with-replacement activations, not one activation of every agent. All private distributions contain 500 agents.")


def _rq2a(summary):
    rows=[]
    phrases=[]
    for p in summary["panels"]:
        for net in ("B0","B1","B2"):
            d=p["a1_direct_events"].get(net,{})
            s3=_mean(p,"b1_endpoint",net,"share_3")
            s5=_mean(p,"b1_endpoint",net,"share_5")
            net3=p["a1_dominant"].get("3",{}).get(net,{}).get("cumulative_net_flow")
            net5=p["a1_dominant"].get("5",{}).get(net,{}).get("cumulative_net_flow")
            rows.append([p["label"],net,_stat(s3,percent=True),_stat(s5,percent=True),_stat(net3),_stat(net5),
                         _stat(d.get("direct_5_to_3")),_stat(d.get("direct_3_to_5"))])
        net="B2"
        phrases.append(f"{p['label']}: B2 endpoint shares were {_value(_mean(p,'b1_endpoint',net,'share_3'))} at stance 3 and {_value(_mean(p,'b1_endpoint',net,'share_5'))} at stance 5")
    central="Opinion redistribution is issue- and network-specific: the observed dominance of stance 3 or 5 is generated by unequal net event flows, rather than interchangeable movement toward a single universal consensus."
    if all((_mean(p,'b1_endpoint',net,'share_3').get('mean') or 0) >
           (_mean(p,'b1_endpoint',net,'share_5').get('mean') or 0)
           for p in summary['panels'] for net in ('B1','B2')):
        central="Networked interaction redistributes opinions toward stance 3, but its endpoint dominance is sharply issue-dependent rather than a universal consensus outcome."
    results=("Serial event accounting links individual updates to population reorganization without treating repeated updates as new agents. "
        +"; ".join(phrases)+". "
        "The accompanying cell-level table reports direct 5→3 and 3→5 event counts separately from endpoint shares. "
        "These counts need not equal changes in group size because agents can leave, re-enter, or move through other stances. "
        "For every run and round, stance-specific cumulative inflow minus outflow equals its population change from round zero. "
        "Thus the dynamic concentration is supported by an exact accounting relationship, while its magnitude and direction remain specific to the issue, topology, and matched seed.")
    discussion=("The flow decomposition treats collective agreement as a redistribution process rather than merely a smaller variance. "
        "A growing stance can attract agents from several origins while simultaneously losing some earlier occupants, so endpoint similarity alone obscures the underlying turnover. "
        "The contrast between direct updates and net accumulation is particularly important under attention-weighted repeated activation. "
        "These findings are compatible with recursive social influence because updated public posts may re-enter later feeds, but conservation itself does not identify amplification or persuasion. "
        "Issue semantics, initial-position dependence, unequal activation opportunity, and publication selectivity remain competing contributors to the observed macroscopic trajectory.")
    return dict(central=central,results=results,discussion=discussion,
        table=_table(["Panel","Network","Endpoint share 3","Endpoint share 5","Net count3 change","Net count5 change","Direct 5→3 events","Direct 3→5 events"],rows),
        figures="FigureA1_Asymmetric_Flows; Figure6_Realized_Exposure_Updating",
        competing="Issue-specific response tendencies; initial-position dependence; repeated activation; selective publication; indirect paths through stance4; recursive re-exposure.")


def _rq2b(summary):
    rows=[]
    phrases=[]
    for p in summary["panels"]:
        for net in ("B1","B2"):
            down=p["a2_directional"].get("5_to_3_pure3",{}).get(net,{})
            up=p["a2_directional"].get("3_to_5_pure5",{}).get(net,{})
            diff=_mean(p,"a2_asymmetry",net,"exact_rate_down_minus_up")
            rows.append([p["label"],net,_stat(down.get("exact_rate"),percent=True),
                         _stat(up.get("exact_rate"),percent=True),_stat(down.get("toward_rate"),percent=True),
                         _stat(up.get("toward_rate"),percent=True),_stat(diff,percentage_points=True)])
        diff=_mean(p,"a2_asymmetry","B2","exact_rate_down_minus_up")
        phrases.append(f"{p['label']}: the B2 exact-update contrast was {_value(diff)}")
    central="Directional response to realized public-message exposure varies by issue and network; exact target adoption and partial movement toward that target are distinct observed outcomes."
    if all((_mean(p,'a2_asymmetry',net,'exact_rate_down_minus_up').get('mean') or 0)>0
           for p in summary['panels'] for net in ('B1','B2')):
        central="With realized pure opposite-stance feeds, exact 5-to-3 adoption is more frequent than mirrored 3-to-5 adoption across the issue-network means, although the asymmetry varies markedly by issue."
    results=("We compared events starting at stance 5 with nonempty pure-3 feeds against events starting at stance 3 with nonempty pure-5 feeds. "
        +"; ".join(phrases)+". "
        "Contrasts are downward minus upward probabilities, expressed on the probability scale here and in percentage points in the table. "
        "Exact target adoption is reported separately from any strict reduction in distance to that target. "
        "Each condition retains its original numerator and opportunity denominator in the seed-level data; rates are not pooled across unequal exposure counts. "
        "Feeds consist of the public posts actually selected for each event, including legitimate older posts, rather than the current private states of all neighbors. "
        "The comparison therefore describes directional responsiveness within evolving exposure environments, not a fixed-message causal effect.")
    discussion=("Unequal update probabilities can accumulate into substantial redistribution even when an individual response is uncommon. "
        "The pure-feed comparison holds the observed target stance fixed within each directional opportunity, but it does not equalize the endogenous histories producing those opportunities. "
        "Original P0 no-feed retention was 150/168, 153/168, and 161/168 for retirement, GM sales, and AI job loss, respectively; these are fixed one-step cases, not network replications. "
        "Selective agreement and conformity remain possible explanations, but numerical movement toward a local opinion is not sufficient evidence of sycophancy. "
        "No completed human semantic coding or experimentally identified sycophancy claim is made here.")
    return dict(central=central,results=results,discussion=discussion,
        table=_table(["Panel","Network","5→3 exact | pure3","3→5 exact | pure5","Toward3 | pure3","Toward5 | pure5","Exact down−up (pp)"],rows),
        figures="Figure6_Realized_Exposure_Updating",
        competing="Starting-position and opportunity selection; unequal prior exposure; repeated sources or older posts; argument content; selective agreement; conformity. Semantic mechanism categories are not coded outcomes.")


def _rq3(summary):
    rows=[]
    phrases=[]
    for p in summary["panels"]:
        topology=p["b1_topology_b2_minus_b1"]
        local=p["b2_excess_topology"].get("unrestricted",{})
        rows.append([p["label"],_stat(topology),_stat(local),
            _stat(_mean(p,"b3_identity_effects","B1","variance_a1_minus_a0")),
            _stat(_mean(p,"b3_identity_effects","B2","variance_a1_minus_a0")),
            _stat(_mean(p,"b4_gap","B2","private_stock_tv"))])
        phrases.append(f"{p['label']}: B2 variance was {_ordering(topology)} (Δ={_value(topology)}), and excess alignment was {_ordering(local)} (Δ={_value(local)})")
    central="The direction and magnitude of topology effects on global variance and distribution-adjusted local alignment must be distinguished, while group-cue contrasts and public visibility show additional conditional heterogeneity."
    if all((p['b1_topology_b2_minus_b1'].get('mean') or 0)>0 and
           (p['b2_excess_topology'].get('unrestricted',{}).get('mean') or 0)>0
           for p in summary['panels']):
        central="Across the issue-horizon means, stronger global convergence in B1 coexists with stronger distribution-adjusted local alignment in B2: collective concentration and local clustering are distinct outcomes."
    results=("Matched-seed comparisons separate global concentration from fixed-network local alignment. "
        +"; ".join(phrases)+". "
        "Positive variance contrasts indicate weaker contraction in B2, whereas positive local contrasts indicate stronger excess same-stance alignment in B2. "
        "Negative contrasts imply the opposite ordering and are retained rather than interpreted through an assumed small-world advantage. "
        "Identity effects are the observed A1−A0 differences within issue, seed, and network; their raw ranges document heterogeneity without assigning causal mediation. "
        "Private opinions, newly published posts, the latest one public post per agent, and actually read slots are summarized separately. "
        "Thus endpoint agreement, adjacent-node similarity, and the public information encountered by receivers are related but nonidentical empirical objects.")
    discussion=("Communication structure can influence the organization of agreement through both who is connected and which public posts are encountered. "
        "The fixed-count permutation baseline isolates excess adjacent similarity from the mechanical effect of a dominant population stance; it is a descriptive network reference, not a seed-level significance test. "
        "Public visibility also depends on publication and retention: the latest-post stock contains one post per agent, whereas feed slots can repeat older material. "
        "Identity contrasts remain conditional associations because the original joint Stage-A/B manipulation admission did not pass. "
        "Topology, evolving selection into exposure, content differences, and differential expression remain competing explanations that require separate controls.")
    return dict(central=central,results=results,discussion=discussion,
        table=_table(["Panel","Variance B2−B1","Excess alignment B2−B1","Variance A1−A0, B1","Variance A1−A0, B2","Private/stock TV, B2"],rows),
        figures="Figure5_Communication_Structure; FigureS1_Private_to_Visible",
        competing="Global stance concentration; clustering and topology; endogenous exposure histories; publication/retention; joint identity-prompt differences. B0 edge metrics and edgeDID are undefined, not zero.")


def question_markdown(title,content):
    return (f"## {title}\n\n{content['central']}\n\n### Magnitudes\n\n{content['table']}\n"
            f"Figures: {content['figures']}.\n\n### Results\n\n{content['results']}\n\n"
            f"### Discussion\n\n{content['discussion']}\n\nCompeting mechanisms: {content['competing']}\n")


def write_reports(summary,package_a,package_b,summary_output):
    if summary["coverage"].get("unit_fixture_only"):
        raise ValueError("UNIT fixtures cannot be delivered as research findings")
    a,b=Path(package_a),Path(package_b)
    for p in (a,b):p.mkdir(parents=True,exist_ok=True)
    qa,qb,qc=_rq2a(summary),_rq2b(summary),_rq3(summary)
    header="# ICA2027: empirical findings from completed Qwen trajectories\n\n"+METHODS+"\n\n"
    parta=question_markdown("RQ2-A: How do asymmetric updates accumulate into redistribution?",qa)
    partb=question_markdown("RQ2-B: What do realized exposure and directional response show?",qb)
    partc=question_markdown("RQ3: How do topology, cues, and visibility organize opinions?",qc)
    outputs={a/"CORE_FINDINGS.md":header+parta+"\n"+partb,
             b/"CORE_FINDINGS.md":header+partc+"\n"+_detail_b1(summary)+"\n"+_detail_b4(summary),
             a/"A1_FINDINGS.md":header+parta,
             a/"A2_FINDINGS.md":header+partb,
             b/"B2_FINDINGS.md":header+partc+"\n"+_detail_b2(summary),
             b/"B3_FINDINGS.md":header+partc+"\n"+_detail_b3(summary),
             b/"B4_FINDINGS.md":header+_detail_b4(summary)}
    for path,text in outputs.items():path.write_text(text,encoding="utf-8")
    destination=Path(summary_output)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return [str(p) for p in outputs]+[str(destination)]


def _detail_b1(summary):
    rows=[]
    for p in summary["panels"]:
        for net in ("B0","B1","B2"):
            d=p["b1_endpoint"].get(net,{})
            effect=p["b1_network_effect"].get(net,{})
            rows.append([p["label"],net,_stat(d.get("variance")),_stat(d.get("mean")),
                         _stat(d.get("variance_normalized_change_from_r0"),percent=True),
                         _stat(effect.get("network_effect_variance")),
                         _stat(effect.get("network_effect_variance_pct_of_b0"))])
    return ("## Global convergence relative to matched no-feed baseline\n\n"+
        _table(["Panel","Network","Endpoint population variance","Private mean","Variance change/R0","Variance B−B0","Variance (B−B0)/B0 (%)"],rows)+
        "\nNegative B−B0 denotes additional contraction relative to its same-identity, same-seed B0. "
        "Positive B2−B1 denotes larger endpoint variance in B2; this is weaker, not stronger, global contraction. "
        "R0-normalized change uses each run's own initial variance. Percent-of-B0 effects are undefined when B0 variance is zero.\n")


def _detail_b2(summary):
    rows=[]
    for p in summary["panels"]:
        for net in ("B1","B2"):
            actual=p["b2_actual"].get(net,{})
            rows.append([p["label"],net,_stat(actual.get("same_stance_fraction")),
                _stat(actual.get("mean_abs_distance")),_stat(actual.get("assortativity")),
                _stat(p["b2_excess"].get("unrestricted",{}).get(net,{}).get("excess_same_stance_fraction")),
                _stat(p["b2_excess"].get("within_group",{}).get(net,{}).get("excess_same_stance_fraction"))])
    return ("## Local and distribution-adjusted alignment\n\n"+
        _table(["Panel","Network","Same stance edges","Edge distance","Undirected assortativity","Unrestricted excess","Within-group excess"],rows)+
        "\nThe point baseline uses the exact fixed-count expectation. The 199 deterministic permutations describe null spread, not formal p-values or seed confidence intervals. "
        "The within-group null preserves Blue/Green stance margins. Degree-stratified robustness was not performed. "
        "Actual exposure similarity uses selected public-message slots and the receiver's pre-update private stance, not all neighbors.\n")


def _detail_b3(summary):
    rows=[]
    for p in summary["panels"]:
        for net in ("B0","B1","B2"):
            d=p["b3_identity_effects"].get(net,{})
            rows.append([p["label"],net,*[_stat(d.get(k)) for k in
                ("variance_a1_minus_a0","mean_a1_minus_a0","share_3_a1_minus_a0","share_5_a1_minus_a0",
                 "change_event_rate_a1_minus_a0","excess_same_stance_unrestricted_a1_minus_a0")]])
    return ("## Identity-cue conditional differences\n\n"+
        _table(["Panel","Network","Variance A1−A0","Mean A1−A0","Share3 A1−A0","Share5 A1−A0","Change rate A1−A0","Excess alignment A1−A0"],rows)+
        "\nSigns and seed ranges, rather than a universal cue effect, are the result. "
        "B0-based edge DID is undefined because B0 has no social edges; the separate B2−B1 paired identity contrast is a valid alternative, not a zero-filled B0 DID. "
        "The original Stage-A/B joint admission did not pass, and this report does not revise that verdict. "
        "Same-group/other-group source-conditioned updating is event-level association within an endogenous feed, not the fixed-message source-label control experiment.\n")


def _detail_b4(summary):
    rows=[]
    layerrows=[]
    for p in summary["panels"]:
        for net in ("B0","B1","B2"):
            gap=p["b4_gap"].get(net,{})
            age=p["b4_stock_age"].get(net,{})
            rows.append([p["label"],net,_stat(gap.get("mean_agent_private_public_abs_gap")),
                _stat(gap.get("private_stock_tv")),_stat(gap.get("private_stock_wasserstein")),
                _stat(age.get("mean_age_rounds")),_stat(age.get("fraction_age_ge_5"),percent=True),
                _stat(gap.get("stock_before_after_round_tv"))])
            for layer in ("private_state","public_flow","public_stock","realized_exposure"):
                d=p["b4_distributions"].get(layer,{}).get(net,{})
                layerrows.append([p["label"],net,layer,_stat(d.get("n")),_stat(d.get("mean")),
                                  _stat(d.get("variance")),_stat(d.get("share_3"),percent=True),_stat(d.get("share_5"),percent=True)])
    return ("## From private opinions to visible public expressions\n\n"
        "Canonical public stock retains only the latest public post per agent (500 posts), including unreplaced round-zero posts. "
        "New expression is the current round's publication flow; realized exposure is the multiset of selected feed slots. "
        "Neither is replaced by the cumulative archive of every historical post.\n\n"+
        _table(["Panel","Network","Agent absolute gap","Private/stock TV","Ordinal Wasserstein","Stock mean age","Stock age≥5","Last-round stock TV change"],rows)+
        "\n"+_table(["Panel","Network","Layer","Count","Mean","Population variance","Share3","Share5"],layerrows)+
        "\nAge is measured in 500-event rounds. Age≥1/5/10 are post-hoc reporting bins. "
        "Empty expression/reading layers have count0 and undefined moments, not zero-valued opinions. "
        "Stock change is a before/after distributional description, not a causal effect of a message. "
        "Repeated posts within a receiver and re-use across receivers are distinguished in the source tables. "
        "FigureS1_Private_to_Visible displays the separate trajectories; Figure5_Communication_Structure links visibility to the structural comparisons.\n")


def read_tables(folder):
    folder=Path(folder)
    proof=json.loads((folder/"AGGREGATE_VERIFICATION.json").read_text(encoding="utf-8"))
    if proof.get("completed_horizon_trajectories")!=102 or proof.get("unique_network_events")!=1890000:
        raise ValueError("Complete aggregate receipt required before reading final report tables")
    tables={}
    for name in REQUIRED_TABLES:
        path=folder/(name+".csv.gz")
        expected=proof.get("files",{}).get(path.name)
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if not expected or expected!=actual:raise ValueError("Missing or changed aggregate table hash: "+name)
        tables[name]=pd.read_csv(path)
    return tables,proof


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables",type=Path,default=ROOT/"analysis-v1/tables")
    parser.add_argument("--package-a",type=Path,default=ROOT/"evidence-packages/A")
    parser.add_argument("--package-b",type=Path,default=ROOT/"evidence-packages/B")
    parser.add_argument("--summary-output",type=Path,default=ROOT/"numeric_summary.json")
    args=parser.parse_args(argv)
    for dest in (args.package_a,args.package_b,args.summary_output):
        if ROOT.resolve() not in dest.resolve().parents:raise ValueError("Controlled output root required")
    tables,proof=read_tables(args.tables)
    summary=build_summary(tables,proof)
    paths=write_reports(summary,args.package_a,args.package_b,args.summary_output)
    print(json.dumps(dict(reports=paths,coverage=summary["coverage"])))


if __name__=="__main__":main()
