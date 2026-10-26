"""Readable presentation of saved parsing evidence; never changes decisions."""
import html
import json
from .jobs import atomic

FIELDS={'authors':'作者','year':'年份','container_title':'出版物','volume':'卷','issue':'期','pages':'页码'}
LABELS={'ready_offline':'规则通过，可进入检索','ready_llm':'模型补充，可进入检索','needs_review':'待复核','needs_llm':'待模型处理','tool_failure':'服务失败，未完成'}

def render(folder,rows,summary):
    e=lambda v:html.escape(str(v if v is not None else '未提取'))
    counts=summary['counts'];metrics=[]
    for tool in ('grobid','anystyle'):
        records=[json.loads(p.read_text('utf-8')) for p in (folder/'network'/tool).glob('*.json')]
        metrics.append({'tool':tool,'requests':len(records),'failed':sum(not r['ok'] for r in records),'request_seconds':round(sum(r['seconds'] for r in records),3)})
    summary['public_request_metrics']=metrics
    calls=[json.loads(p.read_text('utf-8')) for p in (folder/'model').rglob('*.json') if 'elapsed_seconds' in json.loads(p.read_text('utf-8'))]
    summary['model_calls']=len(calls)
    summary['model_request_seconds']=round(sum(c['elapsed_seconds'] for c in calls),3)
    local=[json.loads(p.read_text('utf-8')) for p in (folder/'local-format').glob('*.json')]
    summary['local_format']={'batches':len(local),'failed':sum(not r['ok'] for r in local),'seconds':round(sum(r['elapsed_seconds'] for r in local),3)}
    atomic(folder/'summary.json',summary)
    cards=[]
    for q in rows:
        atomic(folder/'qualified'/f"{q['id']}.json",q)
        columns=[]
        for tool,rec in q['native_parsers'].items():
            f=(rec or {}).get('fields',{});items=[]
            for key,label in [('title','题名'),*FIELDS.items(),('doi','DOI'),('arxiv','arXiv')]:
                v=f.get(key)
                if key=='authors':v='；'.join(a['literal'] for a in v or [])
                elif isinstance(v,list):v='；'.join(v)
                items.append('<dt>'+label+'</dt><dd>'+e(v or '未提取')+'</dd>')
            columns.append('<section><h3>'+tool+'</h3><dl>'+''.join(items)+'</dl>'+('<a href="'+e(rec['evidence'])+'">原始响应与批次记录</a>' if rec else '<p>服务未完成</p>')+'</section>')
        cards.append('<article id="'+e(q['id'])+'"><h2>'+e(q['id'])+' <small>'+e(LABELS[q['status']])+'</small></h2><p class="muted">物理页码 '+e(', '.join(map(str,q['source']['pages'] or [])))+'</p><h3>① 原文</h3><blockquote>'+e(q['raw_text'])+'</blockquote><h3>② 两个工具分别读出了什么</h3><div class="grid">'+''.join(columns)+'</div><h3>③ 我们交给下一步的线索</h3><p><b>题名：</b>'+e(' / '.join(q['query']['titles']) or '未确定')+'</p><p><b>编号：</b>'+e('；'.join(k.upper()+': '+', '.join(v) for k,v in q['query']['identifiers'].items() if v) or '无可靠编号')+'</p><p class="muted">仍需结合检索结果比较的字段：'+e('、'.join(FIELDS[k] for k in q['pending_fields']) or '未发现工具分歧，但尚未核验真实性')+'</p><a href="qualified/'+e(q['id'])+'.json">原文字符区间、规则理由及模型记录位置</a></article>')
    table=''.join('<tr><td>'+e(m['tool'])+'</td><td>'+str(m['requests'])+'</td><td>'+str(m['failed'])+'</td><td>'+str(m['request_seconds'])+' 秒</td></tr>' for m in metrics)
    table+='<tr><td>DeepSeek 题名兜底</td><td>'+str(len(calls))+'</td><td>'+str(sum(not c.get('valid',False) for c in calls))+'</td><td>'+str(summary['model_request_seconds'])+' 秒</td></tr>'
    if local:table+='<tr><td>本地 AnyStyle 转换（无网络）</td><td>'+str(len(local))+' 批</td><td>'+str(summary['local_format']['failed'])+'</td><td>'+str(summary['local_format']['seconds'])+' 秒</td></tr>'
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>双工具解析报告</title><style>
body{font:16px/1.8 system-ui,"Microsoft Yahei";background:#f4f6f1;color:#234338;max-width:1180px;margin:35px auto;padding:20px}h1{font-size:30px}h2{font-size:24px}h3{font-size:17px;margin-top:26px}small,.muted{font-size:14px;color:#657b70}article,.overview{background:white;padding:30px;border-radius:16px;margin:28px 0}blockquote{margin:15px 0;padding:20px;background:#f3f6f1;white-space:pre-wrap;overflow-wrap:anywhere}.grid{display:grid;grid-template-columns:1fr 1fr;gap:28px}.grid section{min-width:0;border-top:3px solid #80a18d}dl{display:grid;grid-template-columns:65px 1fr;gap:9px}dt{color:#657b70}dd{margin:0;overflow-wrap:anywhere}a{color:#24634f}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}.numbers{font-size:22px}nav{display:flex;gap:10px;flex-wrap:wrap}@media(max-width:750px){.grid{display:block}article,.overview{padding:18px}body{padding:12px}}
</style><h1>参考文献字段解析</h1>'''
    page+='<p>原文 → GROBID 与 AnyStyle → 本地规则整合 → 必要时 DeepSeek。没有启动查询或身份核验。</p><section class="overview"><p class="numbers">共 '+str(len(rows))+' 条 · 规则通过 '+str(counts['ready_offline'])+' · 模型补充 '+str(counts['ready_llm'])+' · 待复核 '+str(counts['needs_review']+counts['needs_llm'])+' · 服务失败 '+str(counts['tool_failure'])+'</p><p><b>字段解析阶段实际耗时：'+f"{summary['wall_seconds']:.2f}"+' 秒。</b>不包含此前的文件读取、区域定位和分组。</p><table><tr><th>服务</th><th>请求次数</th><th>失败次数</th><th>请求累计时间</th></tr>'+table+'</table><p class="muted">两服务并行，请求时间不能相加当作总等待时间。AnyStyle 包含会话初始化、解析和 CSL 转换。规则通过表示有可检索线索，不代表字段全对或作品真实。</p><a href="summary.json">耗时明细</a> · <a href="result.json">完整解析结果</a> · <a href="../extraction-provenance.json">文献列表来源</a></section><nav>'+''.join('<a href="#'+e(q['id'])+'">'+e(q['id'])+'</a>' for q in rows)+'</nav>'+''.join(cards)+'</html>'
    if (folder/'acceptance.json').exists():
        audit=json.loads((folder/'acceptance.json').read_text('utf-8'))
        note='<p>与旧解析结果对照：'+str(audit['same_title_count'])+' 条题名在忽略大小写、标点和空白后相同；核对了 '+str(audit['source_spans_checked'])+' 个原文证据区间。旧解析阶段 '+f"{audit['old_parse_stage_seconds']:.2f}"+' 秒。该对照不是独立准确率评测。<a href="acceptance.json">查看验收记录</a></p>'
        page=page.replace('</section><nav>',note+'</section><nav>',1)
    (folder/'index.html').write_text(page,'utf-8')
    return summary
