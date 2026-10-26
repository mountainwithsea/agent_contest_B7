(()=>{
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={title:'题名',authors:'作者',year:'年份',container_title:'出版来源',doi:'DOI',arxiv:'arXiv',pages:'页码',volume:'卷',issue:'期'};
const fieldColors={title:'#4285db',authors:'#9a63cc',year:'#d99a22',container_title:'#379b8b',doi:'#dd6c51',arxiv:'#bc638d',pages:'#7881c4',volume:'#8b8b8b',issue:'#777777'};
const states={confirmed:'作品已找到',candidate:'候选待核',unknown:'证据不足'};
const val=v=>Array.isArray(v)?v.map(x=>typeof x==='object'?x.literal||JSON.stringify(x):x).join('；'):v||'—';
const url=u=>{try{let p=new URL(u);return ['http:','https:'].includes(p.protocol)?p.href:'#'}catch{return '#'}};
let host,data,job,refid='R001',field='title',zoom=100,busy=false,revision='',token=0;
const file=p=>'/files/'+job.id+'/'+p.split('/').map(encodeURIComponent).join('/');
const ref=()=>data?.references.find(r=>r.id===refid)||data?.references[0];
function highlighted(r){let spans=[...(r.spans||[])].sort((a,b)=>a.start-b.start||b.end-a.end),pos=0,out='';for(const s of spans){if(s.start<pos)continue;out+=esc(r.raw_text.slice(pos,s.start))+`<mark data-field="${s.field}" class="text-field ${s.field===field?'focused':''}" style="--field:${fieldColors[s.field]};background:${fieldColors[s.field]}33;border-bottom:2px solid ${fieldColors[s.field]}">${esc(r.raw_text.slice(s.start,s.end))}</mark>`;pos=s.end}return out+esc(r.raw_text.slice(pos))}
function fieldOverlay(p){return data.references.filter(rr=>rr.id===refid).flatMap(rr=>(rr.field_boxes||[]).filter(b=>b.page===p.page).map(b=>{const [x,y,x1,y1]=b.bbox;return `<rect class="pv-fieldbox ${rr.id===refid?'selected':''} ${b.field===field?'focused':''}" data-ref="${rr.id}" data-field="${b.field}" x="${x}" y="${y}" width="${x1-x}" height="${y1-y}" fill="${fieldColors[b.field]}" stroke="${fieldColors[b.field]}"><title>${rr.id} · ${labels[b.field]}：${esc(b.quote)}</title></rect>`})).join('')}
function locate(r){
 const pictures=data.pages.map(p=>{
  let picture='';
  if(p.image){const seen=new Set(),top=p.boxes.length?Math.max(0,Math.min(...p.boxes.map(b=>b.bbox[1]))-22):0,bottom=p.boxes.length?Math.min(1000,Math.max(...p.boxes.map(b=>b.bbox[3]))+15):1000,height=bottom-top;
   picture=`<div class="pv-page-caption">${data.input_type==='pdf'?'原文件第 '+p.page+' 页':'原图'}</div><div class="pv-crop" style="position:relative;overflow:hidden;aspect-ratio:${p.width/(p.height*height/1000)}"><div class="pv-sheet" style="position:absolute;top:${-top/height*100}%;width:100%"><img src="${file(p.image)}" alt="原文第 ${p.page} 页"><svg viewBox="0 0 1000 1000" preserveAspectRatio="none">${p.boxes.map(b=>{const rr=data.references.find(x=>x.id===b.ref_id),[x,y,x1,y1]=b.bbox,first=!seen.has(b.ref_id);seen.add(b.ref_id);return `<rect class="pv-box ${b.ref_id===refid?'active':''}" data-ref="${b.ref_id}" x="${x}" y="${y}" width="${x1-x}" height="${y1-y}" stroke="${rr.color}" fill="${b.ref_id===refid?rr.color:'white'}"><title>${b.ref_id} · ${esc(b.text)}</title></rect>${first?`<g class="pv-label ${b.ref_id===refid?'active':''}" data-ref="${b.ref_id}" tabindex="0" role="button" aria-label="选中文献 ${b.ref_id}" aria-pressed="${b.ref_id===refid}"><rect x="${Math.max(0,x-47)}" y="${y-2}" width="44" height="19" rx="3" fill="${b.ref_id===refid?rr.color:'white'}" stroke="${rr.color}"/><text x="${Math.max(0,x-44)}" y="${y+11}" fill="${b.ref_id===refid?'white':rr.color}">${b.ref_id}</text></g>`:''}`}).join('')}${fieldOverlay(p)}</svg></div></div>`;
  }
  const missing=p.image?data.references.filter(rr=>p.text_blocks.some(b=>b.ref_id===rr.id&&!p.boxes.some(box=>box.source_id===b.id))):data.references.filter(rr=>rr.pages.includes(p.page));
  if(missing.length)picture+=`<small>${p.image?'无可靠坐标，以下显示转写文字':'原文文字'}</small>`+missing.map(rr=>`<button class="pv-textgroup ${rr.id===refid?'active':''}" style="--ref:${rr.color}" data-ref="${rr.id}"><b>${rr.id}</b> ${rr.id===refid?highlighted(rr):esc(rr.raw_text)}</button>`).join('');
  return picture;
 }).join('');
 return `<div class="pv-work unified-work"><section class="pv-original"><div class="pv-pagebar"><div class="document-zoom" role="group" aria-label="原文缩放"><button data-zoom="out" aria-label="缩小原文" title="缩小" ${zoom<=100?'disabled':''}>−</button><button class="zoom-value" data-zoom="reset" aria-label="恢复适合宽度" title="恢复适合宽度">${zoom}%</button><button data-zoom="in" aria-label="放大原文" title="放大" ${zoom>=220?'disabled':''}>＋</button></div></div><div class="pv-paper-scroll"><div style="width:${zoom}%;min-width:100%">${pictures}</div></div></section><section class="pv-right" aria-label="选中文献详情">${referencePanel(r)}</section></div><section class="reference-search">${searchResults(r)}</section>`;
}

function rawLink(q){let relative=q.raw_path?.replaceAll('\\','/').split('/'+job.id+'/')[1];return relative?`<a class="pv-link" target="_blank" href="${file(relative)}">打开保存的原始响应 ↗</a>`:''}
function parserState(p,k){
 const a=p?.tools?.grobid?.[k],b=p?.tools?.anystyle?.[k];
 if(!hasValue(a)&&!hasValue(b))return '双方未提取到';
 if(!hasValue(a))return '仅 AnyStyle 提取到';
 if(!hasValue(b))return '仅 GROBID 提取到';
 const soft=p?.soft_fields?.[k];
 if(soft)return soft.state==='agreement_unverified'?'两工具一致':'工具有分歧';
 const norm=x=>val(x).normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
 return norm(a)===norm(b)?'两工具一致':'工具有分歧';
}
function referencePanel(r){
 const d=r.result?.dimensions,p=r.parsing,tools=p?.tools||{};
 const keys=Object.keys(labels).filter(k=>r.chosen[k]!==null&&r.chosen[k]!==undefined&&r.chosen[k]!==''&&(!Array.isArray(r.chosen[k])||r.chosen[k].length));
 return `<div class="structured-fields">${keys.map(k=>`<button class="formatted-field ${['title','authors','container_title'].includes(k)?'wide':''} ${field===k?'focused':''}" data-field="${k}" aria-pressed="${field===k}" style="--field:${fieldColors[k]}"><span>${labels[k]}：</span><strong>${esc(val(r.chosen[k]))}</strong>${field===k&&!(r.field_boxes||[]).some(b=>b.field===k)?`<small class="field-location-note" title="这是原图标注提示，不是字段正误结论。缺少可靠坐标或内容重复时，不猜测原图位置。">${(r.spans||[]).some(b=>b.field===k)?'文字中已找到，暂不能在原图标注':'暂不能确定原图位置'}</small>`:''}</button>`).join('')||`<p class="pv-note">${p?'解析待复核':'等待字段解析'}</p>`}</div>${p&&['tool_failure','needs_review','needs_llm'].includes(p.status)?'<p class="pv-warning">字段解析尚需处理，已保留原文。</p>':''}
 <details class="pv-more extracted-original auxiliary-section" data-disclosure="original" open><summary><span>提取原文</span><svg class="disclosure-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4"/></svg></summary><p>${esc(r.raw_text)}</p></details><details class="pv-more parsing-record auxiliary-section" data-disclosure="parsing" open><summary><span>文献字段解析</span><svg class="disclosure-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4"/></svg></summary><p>${esc(({ready_offline:'已取得可用检索线索',ready_llm:'题名经模型提取，已取得可用检索线索',needs_llm:'尚无足够检索线索，等待题名处理',needs_review:'题名或编号仍无法确定，需要复核',tool_failure:'解析服务失败，需恢复后重试'})[p?.status]||'等待解析')}</p><div class="pv-tablewrap"><table class="pv-table"><tr><th>字段</th><th>GROBID</th><th>AnyStyle</th><th>解析情况</th></tr>${Object.keys(labels).filter(k=>['title','authors','year','container_title','pages'].includes(k)||hasValue(r.chosen[k])||hasValue(tools.grobid?.[k])||hasValue(tools.anystyle?.[k])).map(k=>`<tr><th>${labels[k]}</th><td>${esc(val(tools.grobid?.[k]))}</td><td>${esc(val(tools.anystyle?.[k]))}</td><td class="parser-state">${esc(parserState(p,k))}</td></tr>`).join('')}</table></div><p class="parsing-scope">工具一致不代表字段已核实；未提取到可能是原文未写或工具漏提取，不自动要求补齐。</p></details>
 `;
}

const fieldNames={...labels,venue:'出版来源',identifiers:'编号'};
const claimStates={match:'一致',conflict:'有差异',unknown:'待核实',explained:'差异已说明'};
function fieldValue(record,key){
 if(!record)return null;
 if(key==='venue')return record.venue||record.container_title;
 if(key==='identifiers')return Object.entries(record.identifiers||{doi:record.doi,arxiv:record.arxiv}).filter(([,v])=>v&&(Array.isArray(v)?v.length:true)).map(([k,v])=>k+': '+val(v)).join('；');
 return record[key]||record.identifiers?.[key];
}
function groupRecords(records){
 const norm=v=>String(v||'').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
 const groups=[];
 for(const e of records){
  const title=norm(e.data.title),year=String(e.data.year||'');
  const doi=String(e.data.identifiers?.doi||'').toLowerCase().replace(/^https?:\/\/(?:dx\.)?doi\.org\//,'');
  let g=groups.find(g=>doi&&g.dois.includes(doi)||title&&g.title===title&&g.year===year&&!(doi&&g.dois.length&&!g.dois.includes(doi)));
  if(!g){g={title,year,dois:[],items:[]};groups.push(g)}
  g.items.push(e);if(doi&&!g.dois.includes(doi))g.dois.push(doi);
 }
 return groups;
}
// Only shorten the saved explanation's repeated value pair; never recompute a verdict.
function claimNote(c){
 if(c.status==='match')return ['authors','identifiers'].includes(c.field)?c.explanation||'':'';
 const text=c.explanation||'';
 const pair=text.match(/^原文：(.+?)；候选：(.+?)。([\s\S]*)$/);
 if(pair){
  const notes=[];
  if(pair[1]==='未明确解析')notes.push('原引用未明确解析');
  if(pair[2]==='未提供')notes.push('查询来源未提供');
  if(pair[3])notes.push(pair[3]);
  return notes.join(' · ');
 }
 if(text==='与所选候选的题名比较；网页可采用已记录的页面标题对应。')return '';
 return text;
}
const sourceName=s=>({crossref:'Crossref',openalex:'OpenAlex',arxiv:'arXiv',europepmc:'Europe PMC',datacite:'DataCite'})[s]||s;
const hasValue=v=>v!==null&&v!==undefined&&v!==''&&(!Array.isArray(v)||v.length>0);
function confirmationBasis(existence){
 const phrases=(existence.anchors||[]).map(a=>{
  if(a.basis==='explicit_identifier_and_title')return '原引用编号与题名共同对应';
  if(['title_and_all_explicit_authors','same_record_title_and_all_explicit_authors'].includes(a.basis)){
   const n=(a.matches||[]).filter(m=>m.matched).length;
   return `题名经规范化后对应，${n?n+' 位明确作者':'原引用明确作者'}均匹配`;
  }
  if(a.basis==='input_url_and_page_title')return '原引用链接与页面标题对应';
  if(a.basis==='reviewed_document_title_and_byline')return '作品页面的题名与署名对应';
  return '';
 }).filter(Boolean);
 return [...new Set(phrases)].join('；')||existence.reason||'未记录具体确认依据';
}
// Compare only records already used to confirm this work. Missing fields are not conflicts.
// This describes saved source wording; it neither re-identifies a work nor changes its verdict.
function sourceDifferences(records){
 const norm=v=>String(v).normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
 return ['title','authors','year','venue','pages','doi'].flatMap(key=>{
  const values=records.map(e=>({e,value:fieldValue(e.data,key)})).filter(x=>hasValue(x.value));
  const groups=new Map();
  for(const x of values){
   const k=key==='authors'&&Array.isArray(x.value)?x.value.map(a=>norm(typeof a==='object'?a.literal:a)).sort().join('|'):norm(val(x.value));
   if(!groups.has(k))groups.set(k,[]);groups.get(k).push(x);
  }
  if(groups.size<2||new Set(values.map(x=>x.e.source)).size<2)return [];
  return [{key,variants:[...groups.values()]}];
 });
}
function executionNote(r){
 const d=r.result.dimensions,errors=d.execution.errors||[];
 if(!errors.length&&d.execution.status==='completed')return '';
 const messages=[...new Set(errors.map(e=>sourceName(e.stage||'查询服务')+'：'+(({rate_limited:'请求限流',http_error:'请求失败',transport_error:'连接失败'})[e.error]||e.error)))];
 return `<p class="query-interruption">${messages.length?'查询受阻 · '+esc(messages.join('；')):'查询尚未全部完成'}。可恢复后补查，当前不能据此判断文献不存在。</p>`;
}
// Absence of confirmation never becomes a positive hallucination verdict.
function hallucinationLabel(existence){return existence.status==='confirmed'?'非幻觉文献':'待判定';}
function fieldConclusion(c,r,observed){
 if(c.status!=='unknown')return claimNote(c);
 if(r.result.dimensions.existence.status!=='confirmed'&&c.field==='title')return '尚未取得足够的作品身份对应证据';
 const input=fieldValue(r.chosen,c.field),haveInput=hasValue(input),haveSource=hasValue(observed);
 if(!haveInput&&!haveSource)return '双方暂无可比较值；不据此判断引用错误';
 if(!haveInput)return '原引用未提取到该字段；可对照原文检查，不代表原文没写';
 if(!haveSource)return '待补证：当前来源未提供该字段，需其他来源';
 return claimNote(c)||'字段尚未核实';
}
function searchResults(r){
 const result=r.result;if(!result)return `<div class="found-heading"><h3>核验结果</h3></div><p class="pv-note">${job.stop_after==='parse'?'本任务仅解析，未进行查询。':['failed','cancelled','interrupted'].includes(job.state)?'本条尚无查询结果；任务已停止。':'正在等待本条查询结果…'}</p>`;
 const d=result.dimensions,cs=result.candidates||[],qs=result.queries||[],claims=d.fields.claims||[];
 const ids=d.existence.evidence_ids||[];
 const primary=cs.find(e=>ids.includes(e.id))||(d.existence.status!=='confirmed'?cs.find(e=>e.usable):null);
 const title=d.existence.status==='confirmed'?(d.existence.matched_title||primary?.data.title):primary?.data.title;
 const ordered=[...cs].sort((a,b)=>Number(ids.includes(b.id))-Number(ids.includes(a.id)));
 const groups=groupRecords(ordered);
 const visibleClaims=claims;
 const differences=sourceDifferences(d.existence.status==='confirmed'?cs.filter(e=>ids.includes(e.id)):[]);
 return `<div class="found-work"><div class="found-heading"><h3>核验结果</h3><span class="result-status ${d.existence.status}" data-hallucination="${d.existence.status==='confirmed'?'no':'undetermined'}" title="仅判断被引用作品是否存在；非幻觉不代表所有引用字段正确。未确认不等于幻觉。">${hallucinationLabel(d.existence)}</span><span class="identity-reason">${esc(d.existence.status==='confirmed'?confirmationBasis(d.existence):d.existence.reason||'尚无确认依据')}</span></div>${d.existence.status!=='confirmed'&&(d.existence.gaps||[]).length?`<p class="identity-gap">${esc([...new Set(d.existence.gaps)].join('；'))}</p>`:''}</div>

 <div class="comparison-scroll"><table class="field-comparison"><thead><tr><th>字段</th><th>原引用</th><th>查询结果</th><th>结论</th></tr></thead><tbody>${visibleClaims.map((c,index)=>{const record=cs.find(e=>c.quotes?.some(q=>q.evidence_id===e.id))||primary;const quotes=(c.quotes||[]).map(q=>q.quote).filter(Boolean);const native=fieldValue(record?.data,c.field);const observed=native!==null&&native!==undefined&&native!==''&&(!Array.isArray(native)||native.length)?native:quotes.join('；');return `<tr class="claim-${esc(c.status)}"><th>${esc(fieldNames[c.field]||c.field)}</th><td>${esc(val(fieldValue(r.chosen,c.field)))}</td><td>${esc(val(observed))}${record?`<small class="query-field-source"><a href="${esc(url(record.url))}" target="_blank" rel="noopener">${esc(sourceName(record.source))} ↗</a></small>`:''}</td><td><span class="claim-state ${esc(c.status)}"><span aria-hidden="true">${({match:'✓',conflict:'≠',unknown:'·',explained:'≈'})[c.status]||'·'}</span> ${esc(claimStates[c.status]||'待核实')}</span>${fieldConclusion(c,r,observed)?`<small class="claim-note">${esc(fieldConclusion(c,r,observed))}</small>`:''}${differences.some(x=>x.key===c.field||(c.field==='identifiers'&&x.key==='doi'))?'<small class="claim-note source-wording-note">确认来源间记载不同；写法或版本差异尚未归因，详见下方来源记录</small>':''}</td></tr>`}).join('')||'<tr><td colspan="4">字段尚未核验</td></tr>'}</tbody></table></div>
 ${executionNote(r)}
 <div class="evidence-groups flat-evidence">${groups.map((g,i)=>`<details class="evidence-group" data-disclosure="group-${i}"><summary>${esc(g.items[0].data.title||g.items[0].url||'来源记录')}<small>${g.items.length} 份记录 · ${esc([...new Set(g.items.map(e=>sourceName(e.source)))].join(' / '))}</small></summary>${g.items.map(e=>`<article class="evidence-record"><div class="record-heading"><b>${esc(sourceName(e.source))}</b><small>${esc(e.id)} · ${ids.includes(e.id)?'用于确认':e.usable?'未用于确认':'不可用于确认'}</small><a href="${esc(url(e.data.record_url||e.url))}" target="_blank" rel="noopener">来源页面 ↗</a></div><dl>${['title','authors','year','venue','identifiers','pages'].map(k=>`<dt>${fieldNames[k]}</dt><dd>${esc(val(fieldValue(e.data,k)))}</dd>`).join('')}</dl><pre class="pv-evidence">${esc(e.text||'未保存正文片段；请查看来源记录。')}</pre></article>`).join('')}</details>`).join('')}</div>`;

}
function fileSummary(){
 const s=data.file_summary;if(!s)return '';
 const completed=job.state==='completed';
 return `<section class="file-summary" aria-label="文件核验汇总"><div class="file-summary-heading"><h3>文件汇总</h3><small>${s.total} 条已提取文献${completed?'':' · 处理中，数量持续更新'}</small></div><div class="file-summary-counts">${[['非幻觉文献',s.non_hallucinated,'confirmed'],['已证实幻觉',s.hallucinated,'hallucinated'],['待判定',s.undetermined,'undetermined'],['尚未核验',s.unverified,'unverified']].map(([label,n,kind])=>`<div class="summary-${kind}"><strong>${n}</strong><span>${label}</span></div>`).join('')}</div><p class="file-summary-diagnostics">字段有差异 <b>${s.field_differences}</b> 条<span>·</span>字段待补证 <b>${s.field_unverified}</b> 条<span>·</span>解析／查询受阻 <b>${s.execution_issues}</b> 条</p>${s.uncertain_groups?`<p class="file-summary-alert">另有 ${s.uncertain_groups} 组原文尚未可靠分组，未计入以上条数；请检查提取记录，本文件尚不能视为检查完整。</p>`:''}<p class="file-summary-note">非幻觉仅表示作品已确认存在，字段仍可能有差异。待判定与程序失败都不算幻觉；当前流程不凭“查不到”自动判为幻觉。问题项数量可重叠。</p></section>`;
}
function draw(){
 if(!host||!data)return;
 const old=host.querySelector('.pv-paper-scroll'),scroll=old?{top:old.scrollTop,left:old.scrollLeft}:null;
 const pane=host.querySelector('.pv-right'),rightScroll=pane?.scrollTop||0;
 const comparisonScroll=host.querySelector('.comparison-scroll')?.scrollLeft||0;
 const sameRef=host.dataset.ref===refid;
 const disclosureState=new Map(sameRef?[...host.querySelectorAll('details')].map(d=>[d.dataset.disclosure||d.querySelector('summary')?.textContent,d.open]):[]);
 const focused=host.contains(document.activeElement)?{ref:document.activeElement.dataset.ref,field:document.activeElement.dataset.field}:null;
 const r=ref();if(!r){host.innerHTML='<div class="pv-loading">'+(['completed','failed','cancelled','interrupted'].includes(job.state)?'尚无可靠提取的文献，请检查运行记录。':'正在读取文件，提取后的文献会显示在这里。')+'</div>'+fileSummary();return}
 refid=r.id;host.dataset.ref=refid;host.dataset.step='unified';host.classList.add('unified');
 host.innerHTML=`${data.warnings?.length?`<details class="pv-warning"><summary>原文显示提示（${data.warnings.length}）</summary>${data.warnings.map(w=>`<p>${esc(w)}</p>`).join('')}</details>`:''}${data.extraction_status==='需要复核'?'<p class="pv-warning">文献提取有待复核内容，请结合原文检查。</p>':''}${locate(r)}${fileSummary()}`;
 const scroller=host.querySelector('.pv-paper-scroll');if(scroll){scroller.scrollTop=scroll.top;scroller.scrollLeft=scroll.left}
 if(sameRef)host.querySelector('.pv-right').scrollTop=rightScroll;
 if(sameRef&&host.querySelector('.comparison-scroll'))host.querySelector('.comparison-scroll').scrollLeft=comparisonScroll;
 host.querySelectorAll('details').forEach(d=>{const key=d.dataset.disclosure||d.querySelector('summary')?.textContent;if(disclosureState.has(key))d.open=disclosureState.get(key)});
 if(focused?.ref)host.querySelector(`.pv-label[data-ref="${focused.ref}"]`)?.focus({preventScroll:true});
 else if(focused?.field)host.querySelector(`.formatted-field[data-field="${focused.field}"]`)?.focus({preventScroll:true});
}
function revealWithin(container,target){
 if(!container||!target)return;
 const c=container.getBoundingClientRect(),t=target.getBoundingClientRect();
 if(t.top<c.top+12||t.bottom>c.bottom-12)container.scrollTop+=t.top-c.top-container.clientHeight*.28;
 if(t.left<c.left+8||t.right>c.right-8)container.scrollLeft+=t.left-c.left-24;
}
function syncField(origin){
 const selected=host.querySelector(`.formatted-field[data-field="${field}"]`);
 if(origin==='original')revealWithin(host.querySelector('.pv-right'),selected);
 if(origin==='fields'){
 const target=host.querySelector(`.pv-fieldbox[data-ref="${refid}"][data-field="${field}"]`)||host.querySelector(`.pv-textgroup.active .text-field[data-field="${field}"]`);
 revealWithin(host.querySelector('.pv-paper-scroll'),target);
 }
}
function choose(id){if(!data.references.some(r=>r.id===id))return;if(refid!==id){field='title';}refid=id;draw()}
function mount(){
 host=document.querySelector('#process-view');
 host.onclick=e=>{const control=e.target.closest('[data-zoom]');if(control){const action=control.dataset.zoom;zoom=action==='reset'?100:Math.min(220,Math.max(100,zoom+(action==='in'?20:-20)));draw();host.querySelector(`[data-zoom="${action}"]`)?.focus({preventScroll:true});return}const b=e.target.closest('.pv-label,.pv-box,.pv-fieldbox,.pv-textgroup,.formatted-field,.text-field');if(!b)return;const origin=b.closest('.pv-original')?'original':'fields';if(b.dataset.ref&&b.dataset.ref!==refid){field='title';}if(b.dataset.field)field=b.dataset.field;if(b.dataset.ref)refid=b.dataset.ref;draw();if(b.dataset.field)syncField(origin)};
 host.onkeydown=e=>{if(e.target.matches('.pv-label')&&['Enter',' '].includes(e.key)){e.preventDefault();choose(e.target.dataset.ref)}};

}
window.ProcessView={async update(j){if(!host)mount();if(job?.id!==j.id){token++;data=null;refid='R001';field='title';zoom=100;revision='';host.innerHTML='<div class="pv-loading">正在加载原文与过程…</div>'}job=j;if(busy||revision===j.id+j.updated)return;busy=true;const myToken=token,id=j.id;try{const response=await fetch('/api/jobs/'+id+'/visual');if(!response.ok)throw Error('可视化数据暂不可用');const d=await response.json();if(token!==myToken||job.id!==id)return;data=d;revision=j.id+j.updated;draw()}catch(e){if(token===myToken)host.innerHTML='<div class="pv-warning">'+esc(e.message)+'；可在下方审计报告查看保存的结果。</div>'}finally{busy=false}}};
})();
