import html
import json
import os
from collections import Counter
from pathlib import Path
from urllib.parse import quote
from .evidence import load,save

LABELS={'confirmed':'已确认作品','probable':'较强线索，待核','uncertain':'证据不足，待核','conflict':'引用身份冲突','not_found':'本轮未找到'}
FIELDS={'title':'题名','authors':'作者','year':'年份','identifiers':'DOI／编号','venue':'出版来源','pages':'页码','edition':'图书版本','other':'其他'}
STATES={'match':'对应','explained':'有差异，可解释','conflict':'存在冲突','unknown':'尚未核清'}
KINDS={'metadata':'书目记录','document':'页面／文档正文','search':'搜索线索'}


def build_report(output):
    output=Path(output);data=load(output/'result.json');rows=data['references'];counts=Counter(r['verdict']['status'] for r in rows)
    esc=lambda x:html.escape(str(x or ''))
    def link(path,label):
        target=quote(os.path.relpath(path,output).replace('\\','/'),safe='/.:')
        return f'<a href="{esc(target)}">{esc(label)}</a>'
    cards=[]
    for row in rows:
        cid=row['id'];v=row['verdict'];folder=output/'references'/cid;lookup={e['id']:e for e in row['evidence']}
        dims=row.get('dimensions',{})
        dimension_panel=''
        if dims:
            ex,fi,run=dims['existence'],dims['fields'],dims['execution']
            execution_labels={'completed':'完成','partial':'部分失败／含重试','failed':'执行失败'}
            field_labels={'issues':'有差异或待核字段','assessed':'已完成字段比较','unavailable':'字段解释未生成'}
            errors=''.join('<li>'+esc(x['stage'])+'：'+esc(x['error'])+('（已自动恢复）' if x.get('recovered') else '')+'</li>' for x in run['errors'])
            dimension_panel=f'<div class="pair"><section><h3>① 作品身份</h3><b>{esc({"confirmed":"已确认对应作品","candidate":"已有候选，仍需身份核实","unknown":"证据不足"}[ex["status"]])}</b><p>{esc(ex["reason"])}</p><p>身份依据：{esc(", ".join(ex["evidence_ids"])) or "暂缺"}</p></section><section><h3>② 字段与版本</h3><b>{field_labels[fi["status"]]}</b><p>字段说明：{"已复核" if fi["reviewed"] else "未完成模型复核，以下可能仅为初稿"}。此状态不等于作品不存在。</p><h3>③ 程序执行</h3><b>{execution_labels[run["status"]]}</b><ul>{errors or "<li>无模型阶段失败</li>"}</ul></section></div>'
        fields=[]
        for c in v['claims']:
            fragments=''.join(f'<blockquote><small>{esc(q["evidence_id"])} · {esc(lookup[q["evidence_id"]]["source"])}</small><br>{esc(q["quote"])}</blockquote>' for q in c['quotes'])
            fields.append(f'<div class="field"><b>{FIELDS[c["field"]]} <span class="pill">{STATES[c["status"]]}</span></b><p>{esc(c["explanation"])}</p>{fragments}</div>')
        ids=[]
        for item in row['identifier_checks']:
            state={'title_match':'登记题名相符；作者等仍需比较','mismatch':'指向其他题名','uncertain':'题名关系待核','unresolved':'登记信息未取得'}.get(item['state'],item['state'])
            ids.append(f'<li><code>{esc(item.get("doi") or item.get("arxiv"))}</code>（来自{"原引用" if item["origin"]=="input" else "候选记录"}）<br><b>{esc(state)}</b> · {esc(item.get("resolved_title"))} · {esc(", ".join(item["evidence_ids"]))}</li>')
        actions=[]
        for stage in row['timeline']:
            if stage.get('assessment'):actions.append(f'<div class="action"><b>第 {stage.get("round")} 轮{"缺口补查" if stage.get("phase")=="recovery" else "规划"}：工具决定怎么查</b><p>{esc(stage["assessment"])}</p></div>')
            for action in stage.get('executions',[]):
                a=action['action'];actions.append(f'<div class="action"><b>{esc(a["tool"])}</b><p>{esc(a["reason"])}</p><code>{esc(a["argument"])}</code><p>执行状态：{esc(action["state"])} · {esc(", ".join(action.get("request_ids",[])))} {esc(action.get("error"))}</p></div>')
            if stage.get('state')=='failed':actions.append(f'<p>规划／执行失败：{esc(stage.get("reason"))}</p>')
        requests=[]
        for r in row['requests']:
            requests.append(f'<tr><td>{r["id"]}</td><td>{esc(r["purpose"])}</td><td>{esc(r["state"])} / HTTP {esc(r.get("http_status"))}</td><td>{link(folder/"requests"/(r["id"]+".json"),"请求日志")} · {link(r['raw_path'],'原始响应') if r.get('raw_path') else '无响应文件'}<br><a href="{esc(r["url"])}">查询地址 ↗</a></td></tr>')
        evidence=[]
        for e in row['evidence']:
            files=' · '.join(link(a['path'],Path(a['path']).name) for a in e['artifacts'])
            excerpt=esc(e['text'][:9000]);extra='<p>展示截断；完整内容见证据 JSON 和原始响应。</p>' if len(e['text'])>9000 else ''
            evidence.append(f'<details class="ev" id="{cid}-{e["id"]}"><summary>{e["id"]} · {KINDS[e["kind"]]} · {esc(e["source"])} · {"可用" if e["usable"] else "排除："+esc(e["quality"])}</summary><p><a href="{esc(e["url"])}">来源页面 ↗</a></p><pre>{excerpt}</pre>{extra}<p class="files">{files}</p></details>')
        unresolved=''.join(f'<li>{esc(s)}</li>' for s in v['unresolved']+v.get('guard_notes',[]))
        usage=sum((c.get('usage') or {}).get('total_tokens',0) for c in row['model_calls'])
        cards.append(f'''<details class="ref" data-status="{v['status']}" data-search="{esc(cid+' '+row['input']['qwen'].get('title',''))}"><summary><b>{cid}</b><span>{esc(row['input']['qwen'].get('title'))}</span><em>{LABELS[v['status']]}</em></summary>
<div class="inside">{dimension_panel}<p class="muted">下方为模型字段解释；作品身份以独立检查栏为准。</p><p class="reason">{esc(v['reason'])}</p><div class="pair"><section><h3>原引用</h3><p>{esc(row['input']['raw_text'])}</p></section><section><h3>工具识别到的作品</h3><p>{esc(v['matched_title']) or '尚未确认'}</p><p>核心证据：{esc(', '.join(v['evidence_ids'])) or '无'}</p><p class="muted">已确认作品不代表所有字段正确。下面分别显示字段判断。</p></section></div>
{('<div class="notice"><b>仍未解决／程序保护检查</b><ul>'+unresolved+'</ul></div>') if unresolved else ''}
<h3>逐个字段：为什么这样判断</h3>{''.join(fields) or '<p>模型输出没有通过校验，请查看日志；此处未人工补写。</p>'}
<details class="section"><summary>工具自动查了什么？（{len(row['requests'])} 次请求）</summary><p>先读取已有自动检索材料，再按通用规则核对候选 DOI，随后执行模型提出的补查。</p><ul>{''.join(ids) or '<li>没有待核的候选 DOI。</li>'}</ul>{''.join(actions)}<div class="tablewrap"><table><tr><th>编号</th><th>用途</th><th>响应状态</th><th>可回查证据</th></tr>{''.join(requests)}</table></div></details>
<details class="section"><summary>全部证据（{len(row['evidence'])} 条，含被排除内容）</summary>{''.join(evidence)}</details>
<p class="muted">本条耗时 {row['elapsed_seconds']} 秒 · 模型步骤 {len(row['model_calls'])} 次（含重试及缓存） · 返回统计 token {usage:,} · {link(folder/'result.json','逐条完整结果')} · {link(folder/'timeline.json','规划与执行记录')} · {link(folder/'model','模型输入输出目录')}</p></div></details>''')
    total_requests=sum(len(r['requests']) for r in rows);reused_requests=sum(bool(q.get('replayed_from')) for r in rows for q in r['requests']);calls=sum(len(r['model_calls']) for r in rows)
    reused_calls=sum(bool(c.get('replayed_from')) for r in rows for c in r['model_calls'])
    tokens=sum((c.get('usage') or {}).get('total_tokens',0) for r in rows for c in r['model_calls'])
    summary={'references':len(rows),'expected':len(data['manifest']['input_ids']),'status_counts':dict(counts),'new_http_requests':total_requests-reused_requests,'reused_http_responses':reused_requests,'logical_followup_requests':total_requests,'model_calls':calls,'new_model_requests':calls-reused_calls,'reused_model_responses':reused_calls,'reported_total_tokens':tokens,'runner_failures':len(data['manifest']['input_ids'])-len(rows),'unresolved_references':[r['id'] for r in rows if r['verdict']['unresolved'] or r['verdict']['status']!='confirmed']}
    save(output/'summary.json',summary)
    options='<option value="">全部结果</option>'+''.join(f'<option value="{s}">{label}（{counts[s]}）</option>' for s,label in LABELS.items())
    page=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>自动作品身份核验 · __COUNT__ 条引用</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f7f5;color:#233d35;font:17px/1.8 system-ui,"Microsoft Yahei",sans-serif}main{max-width:1180px;margin:auto;padding:40px 26px 90px}h1{font-size:34px;line-height:1.4}h2{margin-top:44px}h3{font-size:18px;margin-top:28px}a{color:#176d55;overflow-wrap:anywhere}.muted{font-size:14px;color:#647b6e}.stats{display:flex;gap:16px;flex-wrap:wrap;margin:28px 0}.stat{flex:1;min-width:180px;background:white;border:1px solid #d6e3db;border-radius:12px;padding:20px}.stat b{display:block;font-size:34px}.notice{background:#fff4dc;border-left:4px solid #b88820;padding:20px 24px;margin:24px 0}.flow{background:#e3eee7;border-radius:12px;padding:24px;line-height:2.3}.controls{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}input,select,button{font:inherit;border:1px solid #a8c4b6;border-radius:8px;padding:10px 14px;background:white;max-width:100%}input{flex:1;min-width:180px}button{cursor:pointer}.ref{margin:16px 0;border:1px solid #d6e3db;background:white;border-radius:12px}.ref>summary{display:flex;gap:16px;padding:22px;cursor:pointer;list-style:none}.ref>summary:before{content:'＋';color:#6d8a7c}.ref[open]>summary:before{content:'−'}.ref>summary span{flex:1;line-height:1.6}.ref em{font-size:14px;font-style:normal;color:#327259}.ref[data-status="uncertain"] em,.ref[data-status="probable"] em{color:#9b701b}.ref[data-status="conflict"] em{color:#a03636}.inside{padding:0 26px 26px;border-top:1px solid #e5ece7}.reason{font-size:20px;margin:26px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:22px}.pair section{padding:20px;background:#f3f7f4;border-radius:10px;overflow-wrap:anywhere}.pair h3{margin:0}.field{border-top:1px solid #e4ebe6;padding:22px 0}.pill{font-size:13px;font-weight:normal;background:#ecf2ee;padding:4px 10px;border-radius:20px;margin-left:8px}blockquote{margin:14px 0;padding:12px 20px;background:#f7f8f5;border-left:3px solid #a7c0b1;overflow-wrap:anywhere;font-size:15px}blockquote small{color:#6b7b70}.section{border-top:1px solid #dae5dd;padding:20px 0}.section>summary{cursor:pointer;font-weight:600}.action{padding:18px;background:#f5f7f4;margin:18px 0;border-radius:8px}code{overflow-wrap:anywhere;font-size:14px}.tablewrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:13px;text-align:left;vertical-align:top;border-bottom:1px solid #dce5df;min-width:90px}.ev{border-bottom:1px solid #dce5df;padding:14px 0;font-size:14px}.ev summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7f4;padding:16px;font:13px/1.7 monospace}.files{font-size:13px}li{margin:12px 0;overflow-wrap:anywhere}[hidden]{display:none!important}@media(max-width:700px){main{padding:25px 15px 60px}h1{font-size:27px}.pair{grid-template-columns:1fr}.ref>summary{flex-wrap:wrap;padding:16px;gap:9px}.ref>summary span{flex-basis:80%}.ref em{margin-left:27px}.inside{padding:0 16px 18px}.reason{font-size:18px}.stats{gap:10px}.stat{min-width:140px;padding:14px}.notice{padding:16px}}</style>
<main><p class="muted">自主运行 · 已有候选 → 作品身份核验 · 全过程留证</p><h1>工具自己查、自己比较，结果是什么？</h1><p>本次选择 __COUNT__ 条引用。__INPUT_DESCRIPTION__程序核对候选标识符，让文本模型规划补查并解释证据，再对输出引文做校验。本轮没有读入上一轮人工辅助审计的结论，也没有手工修改任何单条判断。</p>
<div class="stats"><div class="stat"><b>__COUNT__</b>完成 / 预期 __EXPECTED__ 条</div><div class="stat"><b>__CONFIRMED__</b>已确认作品身份</div><div class="stat"><b>__REST__</b>身份仍需核实或有冲突</div></div>
<div class="notice"><b>如何理解“已确认作品”？</b><p>它表示工具根据当前证据认为找到了对应作品。页码、版本、作者数量等字段仍可能待核，请展开查看。这是模型辅助的自动判断，尚无独立真值评测，不能把确认比例当准确率。</p></div>
<div class="flow">① 读入原引用、候选及保存的页面 → ② 排除验证页、核对候选 DOI<br>③ 文本模型发现疑点并提出补查 → ④ 程序实际查询并保存原始响应<br>⑤ 文本模型引用证据给出判断，并复核一次 → ⑥ 程序独立检查身份条件，有缺口则返回补查；身份、字段、执行状态分开</div>
<p class="muted">文本模型：__MODEL__ · 图像模型调用：0 次。补查请求 __REQUESTS__ 次（其中复用先前自动请求 __REUSED__ 次） · 模型步骤 __CALLS__ 次（含重试，其中缓存 __CACHED_CALLS__ 次） · API 返回的 token 合计 __TOKENS__。最多两轮初始规划及两轮身份缺口补查，每轮两项任务，每条最多 12 个请求；达到上限仍有问题会保留待核。</p>
<h2>从一条引用开始看</h2><p>点击题名，先看中文结论，再看字段及原文证据。需要了解程序怎么得出结论时，展开“工具自动查了什么”。“搜索线索”与“书目记录／正文”明确区分。</p><div class="controls"><select id="status" aria-label="筛选结果">__OPTIONS__</select><input id="search" aria-label="搜索编号或题名" placeholder="输入编号或题名"><button id="collapse">收起全部</button></div><p id="count" class="muted"></p>__CARDS__
<p class="muted">可复查：<a href="manifest.json">运行输入、代码哈希与限制</a> · <a href="result.json">全部结果 JSON</a> · <a href="summary.json">统计</a>。旧输入保持不变；新请求、模型提示与回答都在 references 目录中。</p></main>
<script>const rows=[...document.querySelectorAll('.ref')];function filter(){const s=document.querySelector('#status').value,q=document.querySelector('#search').value.toLowerCase();let n=0;for(const r of rows){r.hidden=(s&&r.dataset.status!==s)||!r.dataset.search.toLowerCase().includes(q);if(!r.hidden)n++;}document.querySelector('#count').textContent='当前显示 '+n+' 条';}document.querySelector('#status').onchange=filter;document.querySelector('#search').oninput=filter;document.querySelector('#collapse').onclick=()=>rows.forEach(r=>r.open=false);filter();</script></html>'''
    replace={'__INPUT_DESCRIPTION__':esc(data['manifest'].get('input_description','输入来自此前 Qwen 解析和自动检索。')),'__COUNT__':len(rows),'__EXPECTED__':summary['expected'],'__CONFIRMED__':counts['confirmed'],'__REST__':len(rows)-counts['confirmed'],'__REQUESTS__':total_requests,'__REUSED__':reused_requests,'__MODEL__':esc(data['manifest']['model']),'__CALLS__':calls,'__CACHED_CALLS__':reused_calls,'__TOKENS__':f'{tokens:,}','__OPTIONS__':options,'__CARDS__':'\n'.join(cards)}
    for k,v in replace.items():page=page.replace(k,str(v))
    (output/'index.html').write_text(page,'utf-8')
