"""Copy only approved small public ICA outputs into the research checkout.

Full ZIPs, canonical initialization, reasons, SQLite and event/person records stay
on controlled V. This script does not stage, commit, push or alter old outputs.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile

ROOT=Path('V:/Agent EX/Agent-EX-evidence/2026-11-01/ica-rq2-rq3-v1')


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[3])
    args=parser.parse_args();root=args.root;repo=args.repo
    receipts=json.loads((root/'packages/PACKAGE_VERIFICATION.json').read_bytes())
    for receipt in receipts:
        if sha(Path(receipt['zip_path']))!=receipt['zip_sha256']:raise ValueError('ZIP differs from verification')
    table_lists={
        'A':['A1_round_transition_matrices','A1_net_stance_flows','A1_cumulative_flow',
             'A1_dominant_stance_round_shares','A2_directional_update_rates','A2_seed_level_contrasts'],
        'B':['B1_global_convergence_by_run','B1_paired_network_effects','B1_topology_contrasts',
             'B1_time_trajectories','B2_edge_opinion_similarity','B2_local_excess_homophily',
             'B3_identity_effects_by_seed','B3_identity_network_interactions',
             'B4_private_public_distributions','B4_visibility_gap_by_round','B4_public_stock_age']}
    folders={'A':repo/'reports/2026-11-01-ica-rq2-micro-macro-v1',
             'B':repo/'reports/2026-11-01-ica-rq3-communication-structure-v1'}
    copied=[]
    def copy(source,destination):
        if source.stat().st_size>4*1024**2:raise ValueError('Not an appropriate small Git result')
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
        if sha(source)!=sha(destination):raise ValueError('Copy mismatch')
        copied.append({'path':str(destination.relative_to(repo)).replace('\\','/'),
                       'sha256':sha(destination),'bytes':destination.stat().st_size,'controlled_source':str(source)})
    for letter,folder in folders.items():
        folder.mkdir(parents=True,exist_ok=True)
        for source in (root/'evidence-packages'/letter).glob('*.md'):copy(source,folder/source.name)
        for name in table_lists[letter]:
            source=root/'analysis-v1/tables'/(name+'.csv.gz');copy(source,folder/'tables'/source.name)
        for source in (root/'figures-v1').glob('*'):
            wanted=('FigureA1' in source.name or 'Figure6' in source.name) if letter=='A' else ('Figure5' in source.name or 'FigureS1' in source.name)
            if wanted and source.suffix in ['.svg','.pdf','.md']:copy(source,folder/'figures'/source.name)
        receipt=receipts[0 if letter=='A' else 1]
        with zipfile.ZipFile(receipt['zip_path']) as archive:
            for name in ['DATA_DICTIONARY.md','SOURCE_MANIFEST.json']:
                data=archive.read(name)
                if len(data)>4*1024**2:raise ValueError('Metadata unexpectedly large')
                (folder/name).write_bytes(data)
        for name in ['independent-verification.json','legacy-endpoint-comparison.json','runtime-and-figure-verification.json']:
            copy(root/name,folder/'verification'/name)
    work=repo/'reports/2026-11-01-ica-rq2-rq3-work'
    copy(root/'p0-context/p0_context.csv',work/'p0_context.csv')
    copy(root/'p0-context/verification.json',work/'p0_context_verification.json')
    safe_receipts=[{k:r[k] for k in ['zip_path','zip_sha256','members_verified','crc_ok','small_csv_restored_exactly','source_hashes_unchanged_after']} for r in receipts]
    (work/'DELIVERY_MANIFEST.json').write_text(json.dumps({'unique_network_events':1890000,
        'horizon_trajectories':102,'original_p0_research_cases':1512,'network_model_requests_added':0,
        'packages':safe_receipts,'small_public_copies':copied,
        'private_data_in_Git':False,'Gemma_repair':'paused by user; not resumed'},indent=2),encoding='utf-8')
    (work/'README.md').write_text('# ICA2027 RQ2/RQ3 evidence delivery\n\n'
        'See the sibling RQ2 micro-macro and RQ3 communication-structure report folders for findings, selected seed-level numerical results and vector/PDF figures. '
        'The full controlled packages and exact hashes are listed in DELIVERY_MANIFEST.json. '
        'For webpage-GPT review use ICA2027_RQ2_RQ3_Review_Packet_v1.zip, not the full RQ2 package containing selected private reasons.\n\n'
        'Coverage:102 horizon trajectories,1,890,000 unique network events, plus1512 separate original P0 cases. '
        'Independent arithmetic:583,494 checks passed; previous endpoint/triple-flow comparisons matched. '
        'No new model requests or historical data edits. Gemma remains paused. '
        'Read METHODS.md, REPRODUCE.md and GAPS_AND_INTERPRETATION.md before interpreting mechanisms.\n',encoding='utf-8')
    print(json.dumps({'public_files_copied':len(copied),'bytes_copied':sum(r['bytes'] for r in copied),'delivery_manifest':str(work/'DELIVERY_MANIFEST.json')}))


if __name__=='__main__':main()
