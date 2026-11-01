"""Reproduce ICA figures from seed-level offline tables, never event pseudo-CIs."""
from pathlib import Path
import argparse
import os

ROOT = Path('V:/Agent EX/Agent-EX-evidence/2026-11-01/ica-rq2-rq3-v1')
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'matplotlib-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd
import numpy as np

TOPICS = [('retirement', 'Retirement policy'), ('gm-market-support', 'GM market sales'),
          ('genai-net-job-loss', 'AI-related job loss')]
COLORS = {'B0':'#173B63', 'B1':'#12A5BD', 'B2':'#E8893B'}


def read(folder, name):
    frame = pd.read_csv(folder/(name+'.csv.gz'))
    if 'network_b' not in frame and 'network_condition' in frame:
        frame['network_b'] = frame['network_condition']
    if 'identity_a' not in frame and 'identity_condition' in frame:
        frame['identity_a'] = frame['identity_condition']
    return frame


def long_panel(frame):
    """The completed T60 panel only; retirement T30 n10 remains separate."""
    return frame[frame.horizon == 60].copy()


def get_topic(frame, key):
    if key == 'retirement':
        return frame[~frame.topic_key.isin(['gm-market-support','genai-net-job-loss'])]
    return frame[frame.topic_key == key]


def style(ax):
    ax.spines[['top','right']].set_visible(False)
    ax.spines[['left','bottom']].set_color('#B3C0CD')
    ax.tick_params(colors='#30465D', labelsize=8)
    ax.grid(axis='y', color='#E9EFF3', linewidth=.6)
    ax.set_axisbelow(True)


def save(fig, output, name, caption):
    output.mkdir(parents=True, exist_ok=True)
    for suffix in ['svg','pdf','png']:
        fig.savefig(output/(name+'.'+suffix), dpi=600 if suffix=='png' else 180,
                    facecolor='white', bbox_inches='tight')
    (output/(name+'_caption.md')).write_text(caption+'\n', encoding='utf-8')
    plt.close(fig)


def seed_points(ax, frame, xfield, yfield, levels, *, colors=COLORS):
    """Average the two identity conditions within each matched seed first."""
    group = frame.groupby(['matched_seed', xfield], as_index=False)[yfield].mean()
    for seed, rows in group.groupby('matched_seed'):
        rows = rows.set_index(xfield).reindex(levels)
        ax.plot(range(len(levels)), rows[yfield], color='#A5B3C0', alpha=.65, lw=.8, zorder=1)
    for x, level in enumerate(levels):
        vals = group.loc[group[xfield]==level, yfield].dropna().values
        offsets = np.linspace(-.07,.07,len(vals)) if len(vals)>1 else np.zeros(len(vals))
        ax.scatter(x+offsets, vals, s=23, color=colors[level], edgecolor='white', linewidth=.6, zorder=3)
        if len(vals):
            ax.plot([x-.14,x+.14], [vals.mean()]*2, color=colors[level], lw=2.8, zorder=4)
    ax.set_xticks(range(len(levels)), levels)
    style(ax)


def figure5(tables, out):
    endpoints = long_panel(read(tables,'B1_global_convergence_by_run'))
    excess = long_panel(read(tables,'B2_local_excess_homophily'))
    excess = excess[(excess['round']==excess.horizon)&(excess.permutation_mode=='unrestricted')&(excess.edge_scope=='all')]
    identity = long_panel(read(tables,'B3_identity_effects_by_seed'))
    effects = long_panel(read(tables,'B1_paired_network_effects'))
    fig, axes = plt.subplots(3,4,figsize=(13.2,8.4),layout='constrained')
    for r,(key,title) in enumerate(TOPICS):
        a,raw,b,c = axes[r]
        seed_points(a,get_topic(endpoints,key),'network_b','variance',['B0','B1','B2'])
        a.margins(y=.20)
        a.set_ylabel(title+'\nPrivate variance', fontsize=9)
        relative=get_topic(effects,key).groupby(['matched_seed','network_condition'])['network_effect_variance_pct_of_b0'].mean().groupby('network_condition').mean()
        a.text(.03,.97,' / '.join(f'{net}: {relative[net]:+.1f}%' for net in ['B1','B2']),
               transform=a.transAxes,va='top',fontsize=7,bbox={'facecolor':'white','alpha':.85,'edgecolor':'none','pad':2})
        raw_topic=get_topic(excess,key)
        seed_points(raw,raw_topic,'network_b','actual_same_stance_fraction',['B1','B2'])
        expected=raw_topic.groupby(['matched_seed','network_b'])['expected_same_stance_fraction'].mean()
        for x,network in enumerate(['B1','B2']):
            values=expected.xs(network,level='network_b').values
            raw.scatter(np.repeat(x+.10,len(values)),values,marker='x',s=20,color='#576E82',linewidth=.9,zorder=5)
        raw.set_ylim(0,1)
        raw.set_ylabel('Same-stance edge fraction',fontsize=9)
        if r==0:
            raw.legend(handles=[Line2D([],[],ls='',marker='o',color='#12A5BD',label='Observed'),
                                Line2D([],[],ls='',marker='x',color='#576E82',label='Expected')],
                       frameon=False,fontsize=7,loc='upper left')
        seed_points(b,get_topic(excess,key),'network_b','excess_same_stance_fraction',['B1','B2'])
        b.axhline(0,color='#53677B',lw=.8,ls='--')
        b.set_ylabel('Excess same-stance edges',fontsize=9)
        seed_points(c,get_topic(identity,key),'network_condition','variance_a1_minus_a0',['B0','B1','B2'])
        c.axhline(0,color='#53677B',lw=.8,ls='--')
        c.set_ylabel('Variance: A1 minus A0',fontsize=9)
    for ax,title in zip(axes[0],['A  Global convergence','B  Local alignment: raw','Local alignment: excess','C  Group-cue effects']):
        ax.set_title(title,loc='left',weight='bold',fontsize=11,pad=13)
    save(fig,out,'Figure5_Communication_Structure',
         'Figure 5. Communication structure shapes global convergence and local opinion alignment. '
         'Completed N=500, T60 Qwen trajectories: retirement 3 matched seeds; GM sales and AI job loss 2 each. '
         'A: population variance, annotated with the equal-seed mean percentage contrast against each matched B0; '
         'B-left: observed same-stance edge fractions (circles) and exact fixed-count expectations (crosses); '
         'B-right: observed same-stance edge fraction minus exact expectation under fixed graph and global seven-bin counts '
         '(unrestricted node permutation). All seed points are displayed, averaging A0/A1 within seed in A/B; '
         'C: paired A1-A0 differences within each seed/network. Short thick lines are seed means, not confidence intervals. '
         'Within-Blue/Green permutation baselines and raw edge fractions are supplied separately. '
         'B0 has no social edges. Network assignment jointly changes realized exposure; these contrasts do not isolate topology at equal dose. '
         'Original joint Stage-A/B manipulation admission did not pass; C does not identify an identity/trust mechanism.')


def figure_a1(tables,out):
    flow=long_panel(read(tables,'A1_net_stance_flows'))
    fig,axes=plt.subplots(2,3,figsize=(11.4,6),layout='constrained',sharex=True,sharey='row')
    for col,(key,title) in enumerate(TOPICS):
        topic=get_topic(flow,key)
        for b,ls in [('B1','-'),('B2','--')]:
            for stance,color in [(3,'#173B63'),(5,'#E8893B')]:
                rows=topic[(topic.network_b==b)&(topic.stance==stance)]
                initial_rows=rows.sort_values('round').drop_duplicates(['matched_seed','cell_id']).copy()
                initial_rows['round']=0
                initial_rows['population_share']=initial_rows.round0_count/initial_rows.n_agents
                initial_rows['cumulative_net_flow']=0
                rows=pd.concat([initial_rows,rows],ignore_index=True)
                seed=rows.groupby(['matched_seed','round'],as_index=False)[['population_share','cumulative_net_flow']].mean()
                for metric,ax in [('population_share',axes[0,col]),('cumulative_net_flow',axes[1,col])]:
                    for _,s in seed.groupby('matched_seed'):
                        ax.plot(s['round'],s[metric],color=color,ls=ls,lw=.5,alpha=.18)
                    m=seed.groupby('round')[metric].mean()
                    ax.plot(m.index,m,color=color,ls=ls,lw=1.8)
        axes[0,col].set_title(title,loc='left',weight='bold',fontsize=10)
        axes[0,col].set_ylim(0,1)
        axes[1,col].set_xlabel('Interaction round')
        for ax in axes[:,col]:
            style(ax)
            ax.set_xlim(0,60)
    axes[0,0].set_ylabel('Population share')
    axes[1,0].set_ylabel('Cumulative net inflow (agents)')
    axes[0,0].legend(handles=[Line2D([],[],color='#173B63',label='Stance 3'),Line2D([],[],color='#E8893B',label='Stance 5'),
        Line2D([],[],color='#667788',label='B1'),Line2D([],[],color='#667788',ls='--',label='B2')],frameon=False,fontsize=8)
    save(fig,out,'FigureA1_Asymmetric_Flows',
        'Figure A1. Asymmetric opinion flows and the emergence of dominant positions. '
        'Upper panels: private stance-3/stance-5 shares; lower panels: cumulative incoming minus outgoing successful updates, '
        'which equals current population minus round-0 population, not a count of unique movers. '
        'Solid B1; dashed B2; blue stance3; orange stance5. Thin lines are matched seeds after averaging identity conditions; '
        'thick lines are equally weighted seed means. N500/T60, retirement3/GM2/AI2 matched seeds. '
        'All seven-bin round transitions, direct events, multistep paths and endpoint contributors are separate evidence tables.')


def figure6(tables,out):
    rows=long_panel(read(tables,'A2_directional_update_rates'))
    fig,axes=plt.subplots(1,3,figsize=(11.4,3.5),layout='constrained',sharey=True)
    maxima=[]
    for ax,(key,title) in zip(axes,TOPICS):
        topic=get_topic(rows,key)
        for offset,(start,target,color,label) in zip([-.12,.12],[(5,3,'#173B63','5 to 3 | pure 3'),(3,5,'#E8893B','3 to 5 | pure 5')]):
            s=topic[(topic.prior_stance==start)&(topic.target_stance==target)&(topic.feed_condition=='all_slots_exact_target_and_nonempty')]
            s=s.groupby(['matched_seed','network_b'],as_index=False).agg(exact_rate=('exact_rate','mean'))
            for x,b in enumerate(['B1','B2']):
                values=s.loc[s.network_b==b,'exact_rate'].dropna().values
                maxima.extend(values)
                ax.scatter(np.repeat(x+offset,len(values)),values,color=color,s=28,edgecolor='white',linewidth=.6,label=label if x==0 else None)
                if len(values):ax.plot([x+offset-.065,x+offset+.065],[values.mean()]*2,color=color,lw=2.5)
        ax.set_xticks([0,1],['B1','B2']);style(ax)
        ax.set_title(title,loc='left',weight='bold',fontsize=10)
    axes[0].set_ylabel('Exact directional update probability')
    ymax=min(1,max(.05,np.ceil(max(maxima,default=0)*1.18/.05)*.05))
    axes[0].set_ylim(0,ymax)
    axes[0].legend(frameon=False,fontsize=8,loc='upper right')
    save(fig,out,'Figure6_Realized_Exposure_Updating',
        'Figure 6. Directional updating conditional on realized pure public-message exposure. '
        'Each probability counts events with pre-state i and nonempty feed entirely stance j; numerator is exact i-to-j updates. '
        'Toward-target (including partial) updates are separately reported and are not substituted for exact changes. '
        'Points: each matched seed, equal mean across A0/A1 rates; thick marks: equal seed mean. '
        'Missing opportunities are NA, never zero. All per-condition numerators and denominators accompany this figure. '
        'Realized exposure is endogenous, so conditional contrasts do not identify a content or conformity causal mechanism. '
        'Completed T60 Qwen panel: retirement3/GM2/AI2 seeds.')


def figure_s1(tables,out):
    rows=long_panel(read(tables,'B4_private_public_distributions'))
    layers=[('private_state','Private opinion'),('public_flow','New public expression'),('public_stock','Latest public stock'),('realized_exposure','Realized exposure')]
    fig,axes=plt.subplots(3,4,figsize=(12,7.8),layout='constrained',sharex=True,sharey=True)
    for r,(key,title) in enumerate(TOPICS):
        topic=get_topic(rows,key)
        for col,(layer,heading) in enumerate(layers):
            ax=axes[r,col]
            for b,ls in [('B1','-'),('B2','--')]:
                for stance,color in [(3,'#173B63'),(5,'#E8893B')]:
                    data=topic[(topic.layer==layer)&(topic.network_b==b)]
                    seed=data.groupby(['matched_seed','round'])[f'share_{stance}'].mean()
                    mean=seed.groupby('round').mean()
                    ax.plot(mean.index,mean,color=color,ls=ls,lw=1.6)
            style(ax);ax.set_ylim(0,1);ax.set_xlim(0,60)
            if r==0:ax.set_title(heading,loc='left',weight='bold',fontsize=9)
            if col==0:ax.set_ylabel(title+'\nStance share',fontsize=9)
            if r==2:ax.set_xlabel('Round')
    axes[0,0].legend(handles=[Line2D([],[],color='#173B63',label='Stance 3'),Line2D([],[],color='#E8893B',label='Stance 5'),
        Line2D([],[],color='#667788',label='B1'),Line2D([],[],color='#667788',ls='--',label='B2')],fontsize=7,frameon=False)
    save(fig,out,'FigureS1_Private_to_Visible',
        'Figure S1. From private opinions to visible public expressions. '
        'Each panel displays stance-3/stance-5 shares in one layer, equally averaging identity conditions and matched seeds. '
        'Private and public-stock denominators are500 agents; public stock means exactly the latest public post per agent, '
        'not the cumulative archive. Public flow denominators are newly published posts in that round; exposure denominators are '
        'actually selected message slots. Empty layers are NA. Solid B1/dashed B2; retirement3/GM2/AI2 seeds at T60. '
        'Seven-bin distributions, all individual seed trajectories, ordinal Wasserstein/TV gaps, message ages and repeated exposure are supplied separately.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tables',type=Path,default=ROOT/'analysis-v1/tables')
    parser.add_argument('--output',type=Path,default=ROOT/'figures-v1')
    args=parser.parse_args()
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none','pdf.fonttype':42,'axes.labelcolor':'#173B63','text.color':'#173B63'})
    for plot in [figure_a1,figure6,figure5,figure_s1]:
        plot(args.tables,args.output)
        print(plot.__name__+' rendered',flush=True)


if __name__=='__main__':main()
