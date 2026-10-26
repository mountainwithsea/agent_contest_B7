"""Bounded registry-first verification. Search snippets never prove identity."""
import json
import re
import time
from uuid import uuid4
import shutil
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from reference_identity.evidence import EvidenceStore, seed_evidence, norm, title_score, load
from reference_identity.assessment import match_authors
from reference_identity.tools import Tools
from .jobs import atomic

POLICY = 'registry-first-v1'


def source_urls(raw):
    """Join only URL-continuation punctuation, keeping the exact original span."""
    out=[]
    for match in re.finditer(r'https?://\s*[^\s<>()]+',raw):
        value=re.sub(r'\s+','',match.group());end=match.end()
        while True:
            tail=re.match(r'\s+([^\s<>()]+)',raw[end:])
            if not tail:break
            token=tail[1]
            host_only='/' not in value.split('://',1)[1]
            continuation=value.endswith('/') or (host_only and value.endswith('.') and re.match(r'[a-zA-Z]{2,12}/',token))
            if not continuation or not re.fullmatch(r'[A-Za-z0-9_~.%/?=&+#:@!$*,;\-]+',token):break
            value+=token;end+=tail.end()
        value=value.rstrip('.,;')
        if urlsplit(value).hostname and '.' in urlsplit(value).hostname:
            out.append({'url':value,'start':match.start(),'end':end,'quote':raw[match.start():end],'method':'url_continuation_punctuation'})
    return out


def title_key(s):
    return norm(re.sub(r'(?<=\w)-\s+(?=\w)', '', s or ''))


def identifier(s, kind):
    s = str(s or '').lower().strip().rstrip('.')
    s = re.sub(r'^https?://(?:dx\.)?doi.org/', '', s)
    s = re.sub(r'^https?://arxiv.org/abs/', '', s)
    return re.sub(r'v\d+$', '', s) if kind == 'arxiv' else s


def decide(q, evidence, errors=()):
    """Exact normalized title + complete authors OR explicit ID + title.

    ID/title anchors locate a work even when a cited author is wrong. Differences
    remain field conflicts. No fuzzy-title threshold alone can confirm a work.
    """
    anchors=[]; candidates=[]; identifier_issues=[]
    cited=[a['literal'] for a in q.get('authors',[])]
    for e in evidence:
        if not e.get('usable'):continue
        d=e.get('data',{});title=d.get('title','')
        if title_score(q.get('title'),title)>=.65:candidates.append(e)
        if e['kind']!='metadata':continue
        ids=d.get('identifiers',{})
        same_id=any(identifier(a,k)==identifier(b,k) for k in ('doi','arxiv') for a in q.get(k,[]) for b in [ids.get(k) or d.get(k)] if b)
        exact=bool(title_key(q.get('title')) and title_key(q.get('title'))==title_key(title))
        if same_id and not exact:
            identifier_issues.append({'evidence_id':e['id'],'status':'conflict' if title_score(q.get('title'),title)<.55 else 'unknown','explanation':'原文编号已解析，但登记题名不同；不能直接确认对应作品。','returned_title':title})
        if not exact:continue
        kind=str(d.get('type','')).lower()
        if any(t in kind for t in ('dataset','audiovisual','conference talk')) and q.get('work_type') not in ('dataset','software'):
            continue
        matches=match_authors(cited,d.get('authors',[]))
        if same_id or cited and all(m['matched'] for m in matches):
            anchors.append((e,'explicit_identifier_and_title' if same_id else 'title_and_all_explicit_authors',matches))
    # Only document HEAD titles at an input URL count; body mentions are not enough.
    for e in evidence:
        d=e.get('data',{})
        if e.get('usable') and e['kind']=='document' and d.get('input_url_title_anchor'):
            anchors.append((e,'input_url_and_page_title',[]))
    best=anchors[0][0] if anchors else max(candidates,key=lambda e:title_score(q.get('title'),e.get('data',{}).get('title')),default=None)
    claims=[]
    def claim(field,state,explanation,value=None):
        quotes=[]
        if best and value:
            text=str(value)
            if text in best['text']:quotes=[{'evidence_id':best['id'],'quote':text[:650]}]
        claims.append({'field':field,'status':state,'explanation':explanation,'quotes':quotes})
    if best:
        d=best.get('data',{})
        claim('title','match' if title_key(q.get('title'))==title_key(d.get('title')) else 'unknown','与所选候选的题名比较；网页可采用已记录的页面标题对应。',d.get('title'))
        found=d.get('authors',[]); matches=match_authors(cited,found)
        missing=[m['input'] for m in matches if not m['matched']]
        state='unknown' if not cited or not found else 'conflict' if missing else 'match'
        claim('authors',state,'原文作者与候选名单不对应：'+ '、'.join(missing)+'。差异可能来自引用、来源或版本，未自动归因。' if state=='conflict' else '原文明确作者均能对应。' if state=='match' else '作者缺失、解析有歧义或页面没有署名；尚未核实。',next(iter(found),None))
        for field,key in [('year','year'),('venue','container_title'),('pages','pages')]:
            wanted=q.get(key); got=d.get('venue') or d.get('container') if field=='venue' else d.get(key)
            if isinstance(got,list):got='; '.join(got)
            state='unknown' if not wanted or not got else 'match' if norm(wanted)==norm(got) else 'conflict'
            claim(field,state,f'原文：{wanted or "未明确解析"}；候选：{got or "未提供"}。'+('来源差异，未推断原因。' if state=='conflict' else ''),got)
    else:claim('title','unknown','本次尚未取得足以对应作品的记录。')
    claim('identifiers','conflict' if any(x['status']=='conflict' for x in identifier_issues) else 'unknown' if identifier_issues else 'match' if any(a[1]=='explicit_identifier_and_title' for a in anchors) else 'unknown','编号与题名共同对应。' if any(a[1]=='explicit_identifier_and_title' for a in anchors) else '编号未核清或原文未提供；不能凭候选编号反推原文正确。')
    status='confirmed' if anchors else 'candidate' if candidates or any(e['kind']=='search' and e.get('usable') for e in evidence) else 'unknown'
    reason={'confirmed':'取得同一作品的身份依据；作者、年份等字段另行比较。','candidate':'找到相关候选，但当前证据未满足确认条件。','unknown':'本次未取得足够证据；不代表文献不存在。'}[status]
    gaps=[] if anchors else ['缺少可对应原引用的编号与题名、题名与作者，或原始网页标题证据。']
    return {'existence':{'status':status,'reason':reason,'matched_title':best.get('data',{}).get('title','') if best else '', 'evidence_ids':[a[0]['id'] for a in anchors],'anchors':[{'evidence_id':e['id'],'basis':basis,'matches':m} for e,basis,m in anchors],'gaps':gaps},
            'fields':{'status':'issues' if any(c['status']!='match' for c in claims) else 'assessed','reviewed':True,'method':'deterministic','claims':claims,'identifier_issues':identifier_issues,'unresolved':['部分字段未核实；已找到作品不等于引用全部正确。'] if any(c['status']=='unknown' for c in claims) else []},
            'execution':{'status':'partial' if errors else 'completed','errors':list(errors)}}


def prepare(qualified):
    """Restore authors only when a parser covers the entire raw author prefix."""
    from .local_parsers import downstream
    from .qualification import span
    q=downstream(qualified)
    raw=qualified['raw_text'].lower()
    if re.search(r'\bdataset card\b',raw):q['work_type']='dataset'
    elif re.search(r'\bgithub repository\b',raw):q['work_type']='software'
    elif re.search(r'\bofficial documentation\b|\bproject week page\b',raw):q['work_type']='webpage'
    q['url_evidence']=source_urls(qualified['raw_text'])
    q['urls']=[]
    for link in q['url_evidence']:
        before=qualified['raw_text'][max(0,link['start']-100):link['start']]
        related=bool(re.search(r'\b(?:data|code|dataset|implementation|source code|full version|extended version)\s*(?:(?:can\s+be\s+found|is\s+available|are\s+available|available|at)\s*)?(?:at\s*)?[:：]?\s*$',before,re.I))
        # Respect the existing parser's explicit resource roles as well.
        related=related or any(x.get('source',{}).get('start')==link['start'] and x.get('role') in ('related_data','related_code','alternate_version') for x in q.get('links',[]))
        link['role']='related_resource' if related else 'unknown'
        if not related:q['urls'].append(link['url'])
    return q


def stages(q):
    # Crossref's response is assessed before any secondary source is contacted.
    if q.get('arxiv'):return [['crossref'],['arxiv'],['datacite','europepmc'],['openalex']]
    if q.get('doi'):return [['crossref'],['datacite','europepmc'],['arxiv'],['openalex']]
    if q.get('work_type')=='book':return [['crossref'],['openlibrary'],['googlebooks'],['openalex']]
    if q.get('work_type') in ('webpage','software','dataset') and q.get('urls'):return [['crossref'],['datacite'],['openalex']]
    return [['crossref'],['europepmc','datacite'],['arxiv'],['openalex']]


def mark_document(e,q,logs):
    """Exact canonical URL and page head title; never use a body substring."""
    from html.parser import HTMLParser
    def canonical(u):
        p=urlsplit(u);return (p.hostname,(p.path or '/').rstrip('/'),p.query)
    if e['kind']!='document' or not e.get('usable') or not any(canonical(e['url'])==canonical(u) for u in q.get('urls',[])):return
    log=next((r for r in logs if r['id']==e.get('request_id')),None)
    if not log or canonical(log.get('final_url',log['url']))!=canonical(e['url']):return
    class Head(HTMLParser):
        def __init__(self):super().__init__();self.inside=False;self.titles=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='title':self.inside=True
            if tag=='meta' and (a.get('property')=='og:title' or a.get('name')=='citation_title'):self.titles.append(a.get('content',''))
        def handle_endtag(self,tag):
            if tag=='title':self.inside=False
        def handle_data(self,data):
            if self.inside:self.titles.append(data)
    try:
        head=Head();head.feed(Path(log['raw_path']).read_text('utf-8'))
    except (OSError,UnicodeError):return
    title=q.get('title','');variants=[title]
    # Descriptive documentation prefixes are citation wrappers, not page titles.
    if re.match(r'^.{1,50}\bdocumentation\s*:',title,re.I):variants.append(title.split(':',1)[1].strip())
    for actual in head.titles:
        options=[actual]+re.split(r'\s+[|·–—-]\s+',actual)
        if any(len(title_key(v))>=8 and title_key(v)==title_key(t) for v in variants for t in options):
            e['data'].update(title=actual,input_url_title_anchor=True,authors=[]);return


def verify(row,source,out,values,config=None,allow_model=False,emit=lambda s:None):
    from .retrieval import retrieve_row
    started=time.perf_counter();base_folder=Path(out)/'references'/row['id'];base_folder.mkdir(parents=True,exist_ok=True)
    folder=base_folder
    if (base_folder/'result.json').exists():
        run_id=uuid4().hex
        history=base_folder/'history'/f'{run_id}.json';history.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(base_folder/'result.json',history)
        folder=base_folder/'attempts'/run_id;folder.mkdir(parents=True)
    q=row['input']['qwen'];store=EvidenceStore(folder);tools=Tools(store,values,limit=3);calls=[];timeline=[]
    tools.notify=lambda message:emit(row['id']+'：'+message)
    all_providers=[];all_requests=[];page_items=[]
    for round_no,selected in enumerate(stages(q),1):
        if selected:
            emit(row['id']+'：第 '+str(round_no)+' 层查询 '+', '.join(selected))
            retrieve_row(row,source,values,workers=3,emit=emit,selected=selected)
            all_providers.extend(row['providers']);all_requests.extend(row['requests'])
        row['providers']=all_providers;row['requests']=all_requests
        store.items=[];seed_evidence(row,source,store,include_input_identifiers=True)
        # Reassign page IDs after metadata to maintain unique quote references.
        for page in page_items:
            copied=dict(page);copied['id']=f'E{len(store.items)+1:03}';store.items.append(copied)
        dims=decide(q,store.items)
        timeline.append({'round':round_no,'sources':selected,'status':dims['existence']['status']})
        if dims['existence']['status']=='confirmed':break
        if round_no==1 and q.get('urls'):
            # Even an explicit URL can be slow or return a large PDF. First
            # allow sufficient Crossref metadata to end the work without it.
            for url in q['urls'][:2]:
                tools.allowed.add(url);emit(row['id']+'：读取原文链接 '+url)
                try:tools.fetch(url)
                except Exception as exc:timeline.append({'stage':'fetch','sources':['input_url'],'error':type(exc).__name__})
            page_items=[e for e in store.items if e['kind']=='document']
            for e in page_items:mark_document(e,q,tools.logs)
            dims=decide(q,store.items)
            timeline.append({'round':round_no,'sources':['input_url'],'status':dims['existence']['status']})
            if dims['existence']['status']=='confirmed':break
    errors=[{'stage':r.get('purpose','query'),'error':r.get('parse_error') or r['state'],'url':r.get('url','')} for r in all_requests+tools.logs if r['state']!='ok' or r.get('parse_error')]
    dims=decide(q,store.items,errors)
    result={'id':row['id'],'input':row['input'],'dimensions':dims,'evidence':store.items,'requests':tools.logs,'initial_requests':all_requests,'providers':all_providers,'timeline':timeline,'model_calls':calls,'model_reason':None,'policy':POLICY,'elapsed_seconds':round(time.perf_counter()-started,3)}
    store.persist();atomic(folder/'input.json',row['input']);atomic(folder/'timeline.json',timeline);atomic(folder/'result.json',result)
    if folder!=base_folder:atomic(base_folder/'result.json',result)
    if allow_model and config:return review_result(result,folder,config,emit)
    return result


def review_result(result,folder,config,emit=lambda s:None):
    """Review saved evidence once; never reissue requests or overwrite raw responses."""
    dims=result['dimensions'];evidence=result['evidence'];q=result['input']['qwen'];errors=list(dims['execution']['errors'])
    if dims['existence']['status']=='candidate' and any(e['usable'] and e['kind'] in ('metadata','document') for e in evidence):
        from reference_identity.client import Client
        from reference_identity.engine import JUDGE_PROMPT, validate_verdict
        from reference_identity.assessment import assess
        result['model_reason']='分层查询后仍有候选歧义，进行一次有逐字引证校验的复核；不调用搜索服务。'
        emit(result['id']+'：'+result['model_reason']);client=Client(config,folder/'model')
        atomic(folder/'before-model.json',result)
        started=time.perf_counter()
        try:
            pack=[{k:v for k,v in e.items() if k not in ('artifacts',)} for e in evidence]
            verdict=client.ask('bounded_review',JUDGE_PROMPT+json.dumps({'input':result['input'],'evidence':pack},ensure_ascii=False),lambda v:validate_verdict(v,evidence),max_tokens=3500)
            # Carry identifier conflicts into the strict model guard.
            identifiers=[{'state':'mismatch','origin':'input','evidence_ids':[i['evidence_id']]} for i in dims['fields']['identifier_issues'] if i['status']=='conflict']
            checked=assess(q,evidence,identifiers,verdict,errors,reviewed=True)
            if checked['existence']['status']=='confirmed':dims=checked
            else:dims['fields']['model_review']=verdict
        except Exception as exc:
            errors.append({'stage':'bounded_review','error':type(exc).__name__});dims['execution']={'status':'partial','errors':errors}
        result['model_calls']=client.calls;result['dimensions']=dims
        result['elapsed_seconds']=round(result['elapsed_seconds']+time.perf_counter()-started,3)
        atomic(folder/'result.json',result)
    return result
