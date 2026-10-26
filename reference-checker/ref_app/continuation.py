"""Resume work on saved input; preserve prior runs and their evidence."""
import json
from pathlib import Path
from .jobs import atomic
from reference_identity.evidence import sha


def retry_targets(job):
    out=[]
    for row in job.get('results',[]):
        d=row.get('dimensions',{})
        # Auxiliary outages do not invalidate an already evidenced identity.
        # Field differences and historical errors remain visible in that result.
        if d.get('existence',{}).get('status')!='confirmed':
            out.append(row['id'])
    return out


def resume_info(job):
    targets=retry_targets(job)
    parsing=job.get('parse_summary',{}).get('counts',{})
    parse_pending=sum(parsing.get(k,0) for k in ('needs_llm','needs_review','tool_failure'))
    available=job.get('state') in ('failed','cancelled','interrupted') or (job.get('state')=='completed' and (bool(targets) or parse_pending>0))
    return {'resume_available':available,'resume_count':len(targets) or parse_pending}


def checked_json(path,job_folder=None):
    path=Path(path)
    try:
        if job_folder:
            inventory=Path(job_folder)/'inventory.json'
            if inventory.exists():
                hashes=json.loads(inventory.read_text('utf-8'))
                expected=hashes.get(str(path.relative_to(job_folder)))
                if expected and sha(path)!=expected:return None
        return json.loads(path.read_text('utf-8'))
    except (OSError,ValueError,TypeError):return None


def record_manifest(folder,manifest,run_id=None):
    """An explicit continuation may use new code; old manifest/code stay intact."""
    folder=Path(folder);old=checked_json(folder/'manifest.json')
    if old and old.get('input_sha256')!=manifest['input_sha256']:
        raise ValueError('上传文件哈希不一致，不能继续')
    if run_id:
        relative=Path('runs')/run_id
        atomic(folder/relative/'manifest.json',{**manifest,'parent_manifest_sha256':sha(folder/'manifest.json') if old else None,
            'continuation':True,'reuse_policy':'Reuse verified saved extraction/parser batches and confirmed rows; retry unresolved or failed rows.'})
        return relative/'code',str(relative/'manifest.json').replace('\\','/')
    if old and old!=manifest:raise ValueError('输入、模型或代码已改变，请使用继续按钮保留证据后补查')
    atomic(folder/'manifest.json',manifest)
    return Path('code'),'manifest.json'
