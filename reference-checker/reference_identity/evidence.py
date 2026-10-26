import hashlib
import html
import json
import re
import unicodedata
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path


def norm(value):
    s=unicodedata.normalize('NFKD',str(value or '')).casefold()
    return ''.join(c for c in s if c.isalnum())


def title_score(a,b):
    variants=[str(a or ''),re.sub(r'(?<=\w)-\s+(?=\w)','',str(a or ''))]
    return max(SequenceMatcher(None,norm(x),norm(b)).ratio() for x in variants) if a and b else 0


def author_coverage(cited,found):
    def tokens(s):
        if ',' in s:
            parts=s.split(',',1);s=parts[1]+' '+parts[0]
        return [norm(x) for x in s.split() if norm(x)]
    def match(a,b):
        if norm(a)==norm(b):return True
        aa,bb=tokens(a),tokens(b)
        if len(aa)<2 or len(bb)<2:return False
        if aa[-1]!=bb[-1]:return False
        return aa[0]==bb[0] or (min(len(aa[0]),len(bb[0]))==1 and aa[0][0]==bb[0][0])
    matches=[{'input':a,'matched':next((b for b in found if match(a,b)),None)} for a in cited]
    return {'coverage':sum(bool(x['matched']) for x in matches)/len(cited) if cited else None,'matches':matches,'returned_author_count':len(found)}


def classify_content(text):
    head=text[:10000]
    if re.search(r'client challenge|making sure you.{0,15}not a bot|正在确认你是不是机器人|anubis_challenge|checking your browser|verify you are human|just a moment\.\.\.',head,re.I):return 'challenge'
    if len(text.strip())<60:return 'thin'
    return 'usable'


class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[];self.links=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style','noscript'):self.hidden+=1
        if tag=='a' and a.get('href'):self.links.append(a['href'])
        if tag=='meta' and a.get('content') and (a.get('name','').startswith(('citation_','dc.')) or a.get('property','').startswith('og:')):self.parts.append((a.get('name') or a.get('property'))+': '+a['content'])
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript') and self.hidden:self.hidden-=1
    def handle_data(self,data):
        if not self.hidden and data.strip():self.parts.append(data.strip())


def readable(text):
    text=html.unescape(text)
    return re.sub(r'\\([#.*_\[\]():/,!&?~|+\-])',r'\1',text)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text('utf-8'))
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')


class EvidenceStore:
    def __init__(self,output):
        self.output=Path(output);self.items=[];self.sources={}
    def add(self,source,kind,text,url='',data=None,paths=(),request_id=None,usable=None):
        text=readable(text)
        quality=classify_content(text) if kind in ('document','search') else 'usable'
        item={'id':f'E{len(self.items)+1:03}','source':source,'kind':kind,'url':url or '', 'text':text[:24000],
              'text_truncated':len(text)>24000,'data':data or {},'quality':quality,'usable':quality=='usable' if usable is None else usable,
              'request_id':request_id,'artifacts':[]}
        for path in paths:
            path=Path(path).resolve()
            if path.is_file():
                entry={'path':str(path),'sha256':sha(path)};item['artifacts'].append(entry);self.sources[str(path)]=entry
        self.items.append(item);return item
    def persist(self):save(self.output/'evidence.json',self.items)
    def pack(self):
        return [{k:v for k,v in e.items() if k not in ('artifacts',)} for e in self.items]


def enrich_record(candidate,raw):
    """Copy descriptive fields from the originating raw registry item, never an audit."""
    r=dict(candidate);p=candidate['source'];target=norm((r.get('identifiers') or {}).get('doi'))
    try:
        value=json.loads(raw)
        if p=='crossref':
            msg=value['message'];items=msg.get('items',[msg])
            obj=next((x for x in items if target and norm(x.get('DOI'))==target),None)
            if obj:
                r.update(pages=obj.get('page'),volume=obj.get('volume'),issue=obj.get('issue'),publisher=obj.get('publisher'),publication_dates={k:obj[k] for k in ['published','published-print','published-online','issued'] if k in obj},ISBN=obj.get('ISBN'),editors=obj.get('editor'),links=obj.get('link'))
        elif p=='openlibrary':
            obj=next((x for x in value.get('docs',[]) if norm(x.get('title'))==norm(r.get('title'))),None)
            if obj:r.update(catalog_fields=obj)
    except (ValueError,KeyError,TypeError):pass
    return {k:v for k,v in r.items() if k not in ('title_exact','title_contains','title_similarity','first_author_literal_found','year_agreement','provider_score')}


def seed_evidence(row,source,store,include_input_identifiers=False):
    source=Path(source);q=row['input']['qwen'];options=[]
    for p in row['providers']:
        cs=sorted(p.get('candidates',[]),key=lambda x:title_score(q.get('title'),x.get('title')),reverse=True)
        def explicit(c):
            ids=c.get('identifiers',{})
            def clean(v,k):
                v=re.sub(r'^https?://(?:dx\.)?doi.org/|^https?://arxiv.org/abs/','',str(v or '').lower()).rstrip('.')
                return re.sub(r'v\d+$','',v) if k=='arxiv' else v
            return include_input_identifiers and any(clean(a,k)==clean(ids.get(k),k) for k in ('doi','arxiv') for a in q.get(k,[]) if ids.get(k))
        # All five returned registry candidates get an author check; an earlier
        # same-title commentary/edition must not hide the correct third record.
        options.extend(c for c in cs[:(3 if p['provider']=='deepseek' else 5)] if title_score(q.get('title'),c.get('title'))>=.60 or explicit(c))
    options.sort(key=lambda x:(x.get('evidence_kind')=='metadata',title_score(q.get('title'),x.get('title'))),reverse=True)
    seen=set()
    for c in options[:30]:
        key=(c['source'],norm(c['title']),c.get('url'))
        if key in seen:continue
        seen.add(key);rid=c.get('request_id');log=source/c['audit_path'] if c.get('audit_path') else source/'requests'/f'{rid}.json'
        if not log.exists():continue
        request=load(log)
        if request.get('audit_path'):
            immutable=(source/request['audit_path']).resolve()
            if not immutable.is_relative_to(source.resolve()) or not immutable.is_file():continue
            log=immutable;request=load(log)
        raw=source/(request.get('raw_response') or '__missing__')
        if not raw.is_file() or request.get('state')!='ok':continue
        data=enrich_record(c,raw.read_text('utf-8'))
        # Whole normalized record is a derived view; originating payload remains linked.
        kind='search' if c.get('evidence_kind')=='search_result' else 'metadata'
        store.add(c['source'],kind,json.dumps(data,ensure_ascii=False,indent=2),c.get('url'),data,[log,raw],rid)
    for p in row.get('fetched_pages',[]):
        raw=source/(p.get('raw_response') or '__missing__');rid=p.get('request_id');log=source/'requests'/f'{rid}.json'
        if not raw.is_file():continue
        extracted=source/(p.get('extracted_text') or '__missing__')
        paths=[raw,log]
        if extracted.is_file():text=extracted.read_text('utf-8');paths.append(extracted)
        else:
            try:
                v=load(raw);text=v.get('content','') if isinstance(v,dict) else ''
            except (ValueError,UnicodeError):text=''
        if not text:continue
        e=store.add('saved_page','document',text,p.get('url'),{},paths,rid)
        if p.get('state')!='ok':e.update(usable=False,quality='failed')
    return store
