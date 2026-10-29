"""Seal P0-C public summaries and private reproducibility evidence separately."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile
import zlib

WORK=Path(__file__).resolve().parents[2]
ROOT=Path('V:/Agent EX/Agent-EX-evidence/2026-10-29/p0c-directionality-v1')
REPORT=WORK/'reports/2026-10-29-p0c-directionality'


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def pack(directory,path):
    entries={p.relative_to(directory).as_posix():dict(bytes=p.stat().st_size,sha256=digest(p))
        for p in sorted(directory.rglob('*')) if p.is_file()}
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in entries:z.write(directory/name,name)
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None or set(z.namelist())!=set(entries):raise ValueError('archive exact cover/CRC')
        for name,entry in entries.items():
            data=z.read(name)
            if hashlib.sha256(data).hexdigest()!=entry['sha256'] or len(data)!=entry['bytes']:raise ValueError('archive member differs')
    receipt=dict(bytes=path.stat().st_size,sha256=digest(path),members=entries)
    path.with_suffix(path.suffix+'.receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return receipt


for name in ('event_sampling_frame.csv','sampled_event_index.csv','stance_transition_by_exposure.csv','event_exposure_summary.csv','source_manifest.json'):
    if (ROOT/'c2'/name).read_bytes()!=(ROOT/'c2-root-recomputed'/name).read_bytes():
        raise ValueError('full-frame deterministic recomputation differs: '+name)
files={p.name:dict(bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(REPORT.iterdir()) if p.is_file()}
manifest=REPORT/'FILE_MANIFEST.json'
if manifest.exists():raise ValueError('do not overwrite an existing public manifest')
manifest.write_text(json.dumps(dict(schema='p0c.public.v1',files=files,model_calls=0),indent=2,sort_keys=True)+'\n',encoding='utf-8')
pin=digest(manifest)
(REPORT/'FILE_MANIFEST.sha256').write_text(pin+'  FILE_MANIFEST.json\n',encoding='utf-8')
public=ROOT/'public-results-v1';shutil.copytree(REPORT,public)
pub=pack(public,ROOT/'p0c-public-results-v1.zip')
private=ROOT/'private-evidence-v1';private.mkdir(exist_ok=False)
for name in ('private-sampled-events-final-v1.jsonl.gz','retirement-seven-t30-v2.jsonl.gz'):
    shutil.copy2(ROOT/name,private/name)
shutil.copy2(ROOT.parent.parent/'2026-10-27/p0-directionality-v4/normalized_events.csv.gz',private/'normalized_events.csv.gz')
scripts=private/'code';scripts.mkdir()
for name in ('audit_p0c_stimuli.py','p0c_read_retirement.py','sample_p0c_events.py','p0c_recover_sample.py','report_p0c_cases.py','seal_p0c_delivery.py'):
    shutil.copy2(WORK/'platform/scripts'/name,scripts/name)
shutil.copy2(WORK/'platform/src/agent_ex/diagnostics/p0c.py',scripts/'p0c.py')
for name in ('test_p0c.py','test_p0c_public_verifier.py'):
    shutil.copy2(WORK/'platform/tests'/name,scripts/name)
shutil.copy2(WORK/'docs/superpowers/plans/2026-10-29-p0c-directionality.md',private/'execution-plan.md')
shutil.copy2(Path('C:/Users/Bai Yuexi/.codex/attachments/4b985185-fd07-49e5-baaa-ff3f91a43d07/已粘贴的文本.txt'),private/'human-authorization.txt')
proof=json.loads((REPORT/'sample_recovery_verification.json').read_text(encoding='utf-8'))
profiles=private/'historical-profiles';profiles.mkdir()
for number,(name,pinned) in enumerate(proof['historical_profile_files'].items()):
    p=Path(name)
    if digest(p)!=pinned:raise ValueError('historical source profile changed')
    shutil.copy2(p,profiles/f'{number}-{p.name}')
(private/'source-profile-locations.json').write_text(json.dumps(proof['historical_profile_files'],indent=2)+'\n',encoding='utf-8')
pri=pack(private,ROOT/'p0c-private-evidence-v1.zip')
restore=ROOT/'private-restored-v1';restore.mkdir(exist_ok=False)
with zipfile.ZipFile(ROOT/'p0c-private-evidence-v1.zip') as z:
    for name in z.namelist():
        target=restore/name
        if not target.resolve().is_relative_to(restore.resolve()):raise ValueError('unsafe member')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
for name,entry in pri['members'].items():
    if digest(restore/name)!=entry['sha256']:raise ValueError('restored member differs')
result=dict(schema='p0c.local.delivery.v1',passed=True,public_manifest_sha256=pin,
    public_zip_sha256=pub['sha256'],public_members=len(pub['members']),
    private_zip_sha256=pri['sha256'],private_members=len(pri['members']),
    private_restoration_verified=True,full_sampling_recomputed_byte_exact=True,model_calls=0)
(ROOT/'local-delivery-verification.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps(result))
