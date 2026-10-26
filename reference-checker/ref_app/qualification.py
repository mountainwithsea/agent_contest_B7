"""Evidence-grounded query hints, not canonical bibliography or identity proof."""
import copy
import re
import unicodedata
from .bibliographic_normalization import clean_title

VERSION='qualified-v2-source-names'

def folded(text):
    chars=[];positions=[]
    for i,c in enumerate(text):
        for k in unicodedata.normalize('NFKC',c).casefold():
            if k.isalnum():chars.append(k);positions.append(i)
    return ''.join(chars),positions

def span(raw,value,identifier=False):
    if not value:return None
    if identifier:
        # Identifiers may span PDF whitespace; punctuation remains significant.
        m=re.search(r'\s*'.join(re.escape(c) for c in value),raw,re.I)
        if not m:return None
        start,end=m.span()
    else:
        n,pos=folded(raw);v,_=folded(value);start=n.find(v) if v else -1
        if start<0:return None
        end=pos[start+len(v)-1]+1;start=pos[start]
    return {'start':start,'end':end,'quote':raw[start:end]}

def key(x):return folded(x)[0]

def related(raw,start):
    prefix=raw[max(0,start-160):start]
    return bool(re.search(r'\b(?:data|dataset|code|source code|full version|extended version)\s+(?:(?:can be found|is available|available)\s*)?(?:at\s*)?[:：]?\s*(?:https?://doi\.org/)?$',prefix,re.I))

def identifiers(raw,parsers):
    candidates=[];rejected=[]
    for p in parsers:
        for value in p.get('doi',[]):candidates.append((value,'parser'))
    for m in re.finditer(r'\b10\.\d{4,9}/[^\s<>]+',raw):candidates.append((m.group(),'raw'))
    accepted=[]
    for original,method in candidates:
        value=re.split(r'(?i)PMCID\s*:|PMID\s*:',original)[0].rstrip('.,;')
        while value.endswith(')') and value.count(')')>value.count('('):value=value[:-1]
        ev=span(raw,value,True)
        reason=None
        if not re.fullmatch(r'10\.\d{4,9}/\S+',value):reason='invalid_identifier_shape'
        elif not ev:reason='not_supported_by_source'
        elif related(raw,ev['start']):reason='associated_resource'
        elif re.match(r'[./_-]?\s+[A-Za-z0-9]',raw[ev['end']:]) and not re.match(r'[.,;]?\s+(?:PMID|PMCID|PubMed|https?\b)',raw[ev['end']:],re.I):reason='possible_identifier_continuation'
        if reason:rejected.append({'value':original,'reason':reason});continue
        accepted.append({'kind':'doi','value':value.lower(),'source':ev,'method':method,'original':original,
                         'transforms':['cut_identifier_label'] if original.rstrip('.,;')!=value else []})
    # Do not query an observed prefix when a longer source-supported value exists.
    accepted=[x for x in accepted if not any(y['value']!=x['value'] and y['value'].startswith(x['value']) for y in accepted)]
    extra=[('pmid',r'\bPMID\s*:\s*(\d+)'),('arxiv',r'(?:arxiv\s*:\s*|arxiv\.org/(?:abs|pdf)/|\babs/)(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+/\d{7}(?:v\d+)?)')]
    for kind,pattern in extra:
        for m in re.finditer(pattern,raw,re.I):
            ev={'start':m.start(1),'end':m.end(1),'quote':m.group(1)}
            if not related(raw,m.start()):accepted.append({'kind':kind,'value':m.group(1),'source':ev,'method':'raw'})
    unique={}
    for item in accepted:unique.setdefault((item['kind'],item['value']),item)
    return list(unique.values()),rejected

def title_candidate(raw,title,parsers):
    ev=span(raw,title)
    if not ev:return None,'题名不能对应原文'
    label=re.match(r'^\s*\[([^\]]+)\]',raw)
    if label and key(title)==key(label[1]):return None,'引用编号被识别为题名'
    if len(key(title))<2 or not any(c.isalpha() for c in title):return None,'缺少题名文字'
    if re.search(r'https?://|\b(?:available from|data can be found|accessed|cited)\b',title,re.I):return None,'题名疑似混入附注或链接'
    for p in parsers:
        if any(key(a.get('literal',''))==key(title) for a in p.get('authors',[])):
            return None,'题名与另一解析器的作者项相同'
    return ev,None

def variants(titles):
    out=[]
    for value in titles:
        for form in (value,re.sub(r'(?<=\w)-\s+(?=\w)','',value),re.sub(r'(?<=\w)-\s+(?=\w)','-',value)):
            if form not in out:out.append(form)
    return out

def qualify(row):
    raw=row['raw_text'];ps={t:((row.get('tools',{}).get(t) or {}).get('fields') or {}) for t in ('grobid','anystyle')}
    parsers=list(ps.values());titles=[];rejected=[]
    for tool,p in ps.items():
        title=p.get('title')
        if not title:continue
        title,transforms=clean_title(raw,title,span)
        ev,error=title_candidate(raw,title,parsers)
        if error:rejected.append({'tool':tool,'field':'title','value':title,'reason':error});continue
        existing=next((x for x in titles if key(x['value'])==key(title)),None)
        if existing:
            existing['tools'].append(tool);existing['transforms'].extend(transforms)
        else:titles.append({'value':title,'tools':[tool],'source':ev,'transforms':transforms})
    # A competing shorter title must not lose a real parenthetical subtitle.
    # Resolve only when another parser reaches the observed document-type
    # boundary; without that structural boundary the disagreement stays open.
    short=[]
    for item in titles:
        for longer in titles:
            if item is longer or not longer['transforms']:continue
            if re.fullmatch(re.escape(item['value'])+r'\s*\([^()]+\)',longer['value'],re.I):
                short.append(item)
                rejected.append({'tool':','.join(item['tools']),'field':'title','value':item['value'],
                                 'reason':'另一解析器保留了类型标记之前的完整括号内容；保留完整题名'})
                break
    titles=[t for t in titles if t not in short]
    ids,badids=identifiers(raw,parsers)
    reasons=[]
    if not ids and len(titles)!=1:reasons.append('没有单一可用题名或编号' if not titles else '两个题名候选存在实质分歧')
    if len(titles)>1:reasons.append('保留不同题名，不自动拼接')
    pending=[];fields={}
    for field in ('authors','year','container_title','volume','issue','pages'):
        vals={t:p.get(field) for t,p in ps.items()}
        def canonical(v):
            if field=='authors':return [sorted(re.findall(r'[^\W_]+',a.get('literal','').casefold())) for a in (v or [])]
            return key(str(v or ''))
        agreement=canonical(vals['grobid'])==canonical(vals['anystyle']) and bool(vals['grobid'])
        fields[field]={'candidates':vals,'state':'agreement_unverified' if agreement else 'pending','usage':'soft_comparison_only'}
        if not agreement:pending.append(field)
    return {'id':row['id'],'raw_text':raw,'source':{k:row.get(k) for k in ('file_id','file_name','index','pages','source_ids')},
            'parser_version':VERSION,'status':'ready_offline' if ids or len(titles)==1 else 'needs_llm',
            'query':{'titles':[t['value'] for t in titles],'title_variants':variants([t['value'] for t in titles]),'identifiers':{k:[x['value'] for x in ids if x['kind']==k] for k in ('doi','pmid','arxiv')},'hard_filters':{}},
            'title_evidence':titles,'identifier_evidence':ids,'rejected':rejected+badids,'soft_fields':fields,
            'pending_fields':pending,'reasons':reasons,'identity_verified':False,
            'source_evidence':{t:(row.get('tools',{}).get(t) or {}).get('evidence') for t in ps}}

def resolve_model(draft,value):
    q=copy.deepcopy(draft);title=value.get('title')
    if title is not None and not isinstance(title,str):raise ValueError('title must be string or null')
    q['model_output']=value
    if title:
        title,transforms=clean_title(q['raw_text'],title,span)
        ev,error=title_candidate(q['raw_text'],title,[])
        if error:raise ValueError(error)
        q['query']['titles']=[title]
        q['query']['title_variants']=variants([title])
        q['title_evidence']=[{'value':title,'source':ev,'tools':['llm'],'transforms':transforms}]
        q['status']='ready_llm'
    else:q['status']='needs_review'
    return q
