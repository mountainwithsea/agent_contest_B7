"""File-upload application integration for the bounded registry-first policy."""
import concurrent.futures
import html
import json
import os
import time
from datetime import datetime,timezone
from collections import Counter
from uuid import uuid4
import shutil
from pathlib import Path
from urllib.parse import quote
from .jobs import atomic
from .efficient import prepare, verify, decide, review_result, POLICY
from reference_identity.evidence import sha, load


def public_row(r):
    return {k:r[k] for k in ('id','input','dimensions','elapsed_seconds','policy','model_reason')} | {
        'title':r['input']['qwen'].get('title') or '字段解析待复核',
        'candidates':[{'id':e['id'],'kind':e['kind'],'source':e['source'],'url':e['url'],'usable':e['usable'],'data':e['data'],'text':e['text'][:1200]} for e in r['evidence']],
        'query_count':sum(max(1,len(q.get('attempts',[]))) for q in r['initial_requests']+r['requests']), 'model_count':len(r['model_calls']),
        'query_steps':r['timeline'],
        'queries':[{k:q.get(k) for k in ('url','state','purpose','elapsed_seconds','checkpoint_reused','raw_path','sha256','attempts','response_headers')} for q in r['initial_requests']+r['requests']]}


def failed(row,error):
    dims=decide(row['input']['qwen'],[],[{'stage':'parse_or_verify','error':error}])
    dims['execution']['status']='failed';dims['existence']['gaps']=[error]
    return {'id':row['id'],'input':row['input'],'dimensions':dims,'evidence':[],'requests':[],'initial_requests':[],'providers':[],'timeline':[],'model_calls':[],'model_reason':None,'policy':POLICY,'elapsed_seconds':0}

def preserve_result(path,result):
    if path.exists():
        history=path.parent/'history'/(uuid4().hex+'.json');history.parent.mkdir(exist_ok=True)
        shutil.copyfile(path,history)
    atomic(path,result)

def intact(result):
    return all(Path(a['path']).is_file() and sha(a['path'])==a['sha256'] for e in result['evidence'] for a in e['artifacts'])


def run_balanced(folder,job,refs,qualified,values,config,store,emit,change_stage):
    start=time.perf_counter();out=folder/'verification';source=folder/'retrieval';source.mkdir(exist_ok=True);out.mkdir(exist_ok=True)
    store.update(job['id'],identity_dir='verification')
    rows=[];results={};completed=set()
    retry_ids=set(job.get('resume_targets',[]))
    for i,ref in enumerate(refs):
        cid=f'R{i+1:03}';q={'title':'','authors':[],'doi':[],'arxiv':[],'urls':[]}
        from .continuation import checked_json
        previous=checked_json(out/'references'/cid/'result.json')
        reusable=previous and previous.get('input',{}).get('raw_text')==ref['raw_text'] and intact(previous)
        if reusable:results[cid]=previous  # Display old evidence until its replacement is complete.
        if cid not in retry_ids and reusable and previous['dimensions']['existence']['status']=='confirmed':
            results[cid]=previous;rows.append({'id':cid,'input':previous['input'],'providers':[],'requests':[],'fetched_pages':[]})
            completed.add(cid)
            emit(cid+'：复用已确认作品与完整证据');continue
        error=None
        try:q=prepare(qualified[i])
        except Exception as exc:error='字段尚不能可靠用于检索：'+type(exc).__name__+'。请查看双解析器报告。'
        inp={'id':cid,'raw_text':ref['raw_text'],'source_pages':ref.get('pages',[]),'source_ids':ref.get('source_ids',[]),'qwen':q,'parser_model':'dual-tools-with-bounded-fallback','title_variants':q.get('qualification',{}).get('query',{}).get('title_variants',[q.get('title','')]),'book_route':q.get('work_type')=='book'}
        row={'id':cid,'input':inp,'providers':[],'requests':[],'fetched_pages':[]};rows.append(row)
        if error:
            results[cid]=failed(row,error);preserve_result(out/'references'/cid/'result.json',results[cid])
            completed.add(cid)
    atomic(out/'inputs.json',rows)
    def publish():
        ordered=[results[k] for k in sorted(results)]
        atomic(out/'result.json',{'policy':POLICY,'references':ordered})
        store.update(job['id'],results=[public_row(r) for r in ordered])
    def task(row):
        existing=out/'references'/row['id']/'result.json'
        if existing.exists():
            old=load(existing)
            if row['id'] in retry_ids and old.get('dimensions',{}).get('existence',{}).get('status')!='confirmed':
                row['_refresh_checkpoint']=True
            # All evidence artifacts must still match before accepting a checkpoint.
            transient=any(e.get('error') in ('rate_limited','transport_error','http_error') for e in old.get('dimensions',{}).get('execution',{}).get('errors',[]))
            if row['id'] not in retry_ids and not transient and old['input']==row['input'] and all(Path(a['path']).is_file() and sha(a['path'])==a['sha256'] for e in old['evidence'] for a in e['artifacts']):return old
        return verify(row,source,out,values,emit=lambda s:emit(s))
    publish()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(task,r):r for r in rows if r['id'] not in completed}
        for future in concurrent.futures.as_completed(futures):
            row=futures[future]
            try:r=future.result()
            except Exception as exc:
                r=failed(row,'查询步骤执行失败：'+type(exc).__name__);preserve_result(out/'references'/row['id']/'result.json',r)
            results[row['id']]=r;completed.add(row['id']);publish();emit('已完成 '+str(len(completed))+'/'+str(len(rows))+' 条查询与规则核验',done=len(completed),total=len(rows))
    change_stage('identity')
    # Opt-in model review is limited to five ambiguous items, with no search tool.
    eligible=[r for r in rows if results[r['id']]['dimensions']['existence']['status']=='candidate' and any(e['usable'] and e['kind'] in ('metadata','document') for e in results[r['id']]['evidence'])]
    if job.get('allow_identity_model'):
        for row in eligible[:5]:
            emit(row['id']+'：必要歧义复核（本任务最多5条）')
            base=out/'references'/row['id']
            results[row['id']]=review_result(results[row['id']],base/'reviews'/uuid4().hex,config,emit=lambda s:emit(s))
            preserve_result(base/'result.json',results[row['id']]);publish()
    else:emit('模型复核关闭：保留规则无法确认的条目；未调用 DeepSeek 查询或核验')
    change_stage('report');publish()
    ordered=[results[k] for k in sorted(results)]
    summary={'references':len(rows),'existence':dict(Counter(r['dimensions']['existence']['status'] for r in ordered)),
        'query_seconds':round(time.perf_counter()-start,3),'requests':sum(max(1,len(q.get('attempts',[]))) for r in ordered for q in r['requests']+r['initial_requests']),
        'logical_queries':sum(len(r['requests'])+len(r['initial_requests']) for r in ordered),
        'identity_model_attempts':sum(len(r['model_calls']) for r in ordered),'deepseek_search_calls':0,'policy':POLICY,
        'model_review_enabled':bool(job.get('allow_identity_model')),'remaining_ambiguous':sum(r['dimensions']['existence']['status']=='candidate' for r in ordered)}
    current=store.read(job['id'])
    extract_files=sorted(folder.glob('extraction*/result.json'))
    extraction=load(extract_files[-1]) if extract_files else {}
    summary.update(total_seconds=round((datetime.now(timezone.utc)-datetime.fromisoformat(job['created'])).total_seconds(),3),
        extraction_seconds=extraction.get('elapsed_seconds'),extraction_model_attempts=extraction.get('api_attempts',0),
        parsing_seconds=current.get('parse_summary',{}).get('wall_seconds'),parsing_model_attempts=current.get('parse_summary',{}).get('model_calls',0))
    atomic(out/'summary.json',summary);build_report(out,ordered,summary)
    store.update(job['id'],report='verification/index.html',summary=summary)


def build_report(out,rows,summary):
    """Self-contained report with real input, parsed fields, requests and evidence."""
    esc=lambda v:html.escape(str(v if v is not None else ''))
    def local(p):return quote(os.path.relpath(p,out).replace('\\','/'),safe='/.:')
    def request_item(record):
        address = record.get('url')
        target = f'<a href="{esc(address)}">{esc(address)}</a>' if address else '未形成请求地址'
        error = f'<br>{esc(record["error_type"])}' if record.get('error_type') else ''
        raw = f'<br><a href="{local(record["raw_path"])}">保存的原始响应</a>' if record.get('raw_path') else ''
        return (f'<li><b>{esc(record.get("purpose") or record.get("provider") or "查询")} · {esc(record["state"])}</b>'
                f' · {record.get("elapsed_seconds",0)} 秒<br>{target}{error}{raw}</li>')
    cards=[]
    for r in rows:
        q=r['input']['qwen'];dims=r['dimensions'];ex=dims['existence'];cid=r['id']
        labels={'confirmed':'作品已找到','candidate':'候选待核','unknown':'证据不足'}
        fields=''.join(f'<tr><td>{esc(c["field"])}</td><td>{esc({"match":"对应","conflict":"有差异","unknown":"未核实","explained":"差异已说明"}.get(c["status"],c["status"]))}</td><td>{esc(c["explanation"])}</td></tr>' for c in dims['fields']['claims'])
        requests=''.join(request_item(z) for z in r['initial_requests']+r['requests'])
        evidence=''.join(f'<details><summary>{esc(e["id"])} · {esc(e["source"])} · {esc(e.get("data",{}).get("title") or e["kind"])}</summary><p>{"可用证据" if e["usable"] else "不可用于确认"} · {esc(e["kind"])}</p><a href="{esc(e["url"])}">来源地址</a><pre>{esc(e["text"])}</pre>'+''.join(f'<a href="{local(a["path"])}">证据文件 · SHA256 {a["sha256"][:12]}…</a><br>' for a in e['artifacts'])+'</details>' for e in r['evidence'])
        cards.append(f'''<article data-state="{ex['status']}"><details><summary><b>{cid} · {labels[ex['status']]}</b><span>{esc(q.get('title') or '解析待复核')}</span></summary>
<h3>1 原始引用</h3><p>{esc(r['input']['raw_text'])}</p><small>物理页：{esc(r['input'].get('source_pages'))}</small>
<h3>2 交给查询的字段</h3><pre>{esc(json.dumps({k:q.get(k) for k in ('title','authors','year','doi','arxiv','urls','links','author_bridge')},ensure_ascii=False,indent=2))}</pre>
<h3>3 实际查询了什么</h3><p>本条 {r['elapsed_seconds']} 秒 · 查询 {len(r['initial_requests'])+len(r['requests'])} 次 · 核验模型尝试 {len(r['model_calls'])} 次</p><ol>{requests or '<li>未发起查询；请先处理字段解析问题。</li>'}</ol>
<h3>4 候选与保存的证据</h3>{evidence or '<p>没有可用证据；不能据此判为虚构。</p>'}
<h3>5 最终判断</h3><p><b>{labels[ex['status']]}</b> · {esc(ex['reason'])}</p><p>身份依据：{esc(ex['anchors'])}</p><table><tr><th>字段</th><th>结果</th><th>说明</th></tr>{fields}</table>
<p>执行：{esc(dims['execution']['status'])}</p><pre>{esc(json.dumps(dims['execution']['errors'],ensure_ascii=False,indent=2))}</pre><p>{esc(r.get('model_reason') or '本条未调用核验模型。')}</p>
<a href="references/{cid}/result.json">完整结果 JSON</a></details></article>''')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>文件到文献核验 · 完整过程</title><style>body{font:16px/1.85 system-ui,"Microsoft YaHei";color:#203c33;background:#f3f6f2;max-width:1100px;margin:35px auto;padding:0 22px}h1{font-size:30px}article{background:white;border:1px solid #d6e2d8;border-radius:12px;margin:16px 0;padding:20px}summary{cursor:pointer}summary span{display:block;margin-top:8px}h3{margin-top:34px;border-left:4px solid #36745b;padding-left:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7f4;padding:14px;font-size:13px}a{color:#25654e;overflow-wrap:anywhere}td,th{text-align:left;border-bottom:1px solid #ddd;padding:10px;vertical-align:top}table{width:100%;table-layout:fixed}td{overflow-wrap:anywhere}li{margin:16px 0}details details{border-top:1px solid #eee;padding:14px 0}button{padding:10px 14px;margin:5px;background:white;border:1px solid #9ab5a5;border-radius:7px;cursor:pointer}small{color:#62766a}</style><h1>从输入文件到每条文献的核验结果</h1><p>读取与分条 → 双工具解析 → 分层查询 → 身份与字段分别判断 → 保存证据</p><p>“证据不足”不等于虚构；作品找到不等于所有字段正确。未核验正文是否支持论文观点。</p>'''
    input_file=next(out.parent.glob('input.*'),None)
    input_link=f'<a href="{local(input_file)}">原始输入文件</a> · ' if input_file else ''
    extraction=sorted(out.parent.glob('extraction*/index.html'))
    extraction_link=f'<a href="{local(extraction[-1])}">读取与分条结果</a> · ' if extraction else ''
    page+=f'<p><b>共 {summary["references"]} 条</b> · 已找到 {summary["existence"].get("confirmed",0)} · 候选待核 {summary["existence"].get("candidate",0)} · 证据不足 {summary["existence"].get("unknown",0)}</p><p>查询与核验 {summary["query_seconds"]} 秒 · 请求 {summary["requests"]} 次 · 核验模型尝试 {summary["identity_model_attempts"]} 次 · DeepSeek 搜索 0 次</p><p>{input_link}{extraction_link}<a href="../manifest.json">输入与代码版本</a> · <a href="../public-parsing/index.html">双解析器对比</a> · <a href="summary.json">统计</a></p>'
    page+=''.join(f'<button data-filter="{s}">{label}</button>' for s,label in [('all','全部'),('confirmed','作品已找到'),('candidate','候选待核'),('unknown','证据不足')])+''.join(cards)
    page=page.replace('<h1>从输入文件到每条文献的核验结果</h1>',f'<h1>从输入文件到每条文献的核验结果</h1><p>端到端 {summary.get("total_seconds","—")} 秒 · 提取模型 {summary.get("extraction_model_attempts","—")} 次 · 字段解析模型 {summary.get("parsing_model_attempts","—")} 次（与查询核验分开统计）</p>')
    page+='''<script>document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>document.querySelectorAll('article').forEach(a=>a.hidden=b.dataset.filter!=='all'&&a.dataset.state!==b.dataset.filter))</script></html>'''
    (out/'index.html').write_text(page,encoding='utf-8')
