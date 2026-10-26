"""Bounded independent-source retrieval; never equate failed requests with absence."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import time
import hashlib
from . import providers
from .jobs import atomic
from reference_identity import tools as network
from reference_identity.evidence import EvidenceStore, sha


def collect(selected, fetch, workers=3, on_done=lambda provider:None):
    if len(set(selected))!=len(selected):raise ValueError('Duplicate provider')
    completed={}
    with ThreadPoolExecutor(max_workers=max(1,min(workers, len(selected) or 1))) as pool:
        futures={pool.submit(fetch,p):p for p in selected}
        for future in as_completed(futures):
            provider=futures[future]
            try:completed[provider]=future.result()
            except Exception as exc:
                # Exception text can contain credentials; persist only the type.
                error={'state':'processing_error','error_type':type(exc).__name__,'provider':provider}
                completed[provider]=({**error,'candidates':[]},dict(error))
            on_done(provider)
    return ([completed[p][0] for p in selected],[completed[p][1] for p in selected])


def valid_checkpoint(source, record, url, payload):
    try:
        raw=(source/record['raw_response']).resolve()
        return (record.get('state') in ('ok','not_found') and record['url']==url and record.get('body')==payload
                and raw.is_relative_to(source.resolve()) and sha(raw)==record['sha256'])
    except (KeyError,TypeError,OSError,ValueError):return False


def retrieve_row(row, source, values, workers=3, emit=lambda message:None, selected=None):
    source=Path(source);providers.HERE=source;providers.ENV=values
    if selected is None:
        selected=['crossref','datacite','arxiv','europepmc','openalex','deepseek']
        if row['input']['book_route']:selected+=['openlibrary','googlebooks']
    started=time.perf_counter()
    def fetch(provider):
        rid=row['id']+'--'+provider;path=source/'request-index'/f'{rid}.json'
        url,payload,_headers=providers.endpoint(provider,row['input'])
        legacy=source/'requests'/f'{rid}.json'
        try:record=json.loads((path if path.exists() else legacy).read_text('utf-8'))
        except (OSError,ValueError):record=None
        reused=bool(not row.get('_refresh_checkpoint') and record and valid_checkpoint(source,record,url,payload))
        if not reused:
            attempt_root=source/'transport'/rid
            attempt=attempt_root/f'attempt-{len(list(attempt_root.glob("attempt-*")))+1}'
            tool=network.Tools(EvidenceStore(attempt),values,limit=1)
            tool.notify=lambda message:emit(row['id']+'：'+message)
            secret=values.get('DEEPSEEK_API_KEY') if provider=='deepseek' else values.get('OPENALEX_API_KEY') if provider=='openalex' else None
            record,_body=tool.request(url,provider,payload,secret)
            record={**record,'request_id':rid,'raw_response':str(Path(record['raw_path']).relative_to(source))}
        record.pop('parse_error',None)
        try:candidates=providers.extract(provider,record)
        except Exception as exc:
            candidates=[];record['parse_error']=type(exc).__name__
        record.pop('audit_path',None)
        digest=hashlib.sha256(json.dumps(record,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()
        audit=Path('records')/rid/(digest+'.json')
        record['audit_path']=audit.as_posix()
        for candidate in candidates:candidate['audit_path']=record['audit_path']
        if not (source/audit).exists():atomic(source/audit,record)
        atomic(path,record)
        state='parse_error' if record.get('parse_error') else record['state']
        return {'provider':provider,'state':state,'candidates':candidates,'checkpoint_reused':reused},record
    results,records=collect(selected,fetch,workers,lambda p:emit('来源完成：'+row['id']+' · '+p))
    row['providers']=results;row['requests']=records
    row['retrieval_schedule']={'version':1,'workers':workers,'sources':selected,'early_stop':False,
        'elapsed_seconds':round(time.perf_counter()-started,4),'all_sources_completed':len(results)==len(selected)}
    atomic(source/'schedules'/f'{row["id"]}.json',row)
    return row
