import io
import ipaddress
import json
import re
import socket
import shutil
import threading
import time
import urllib.error
import urllib.parse as up
import urllib.request as ur
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from .evidence import Page, norm, title_score, readable, save, sha
from b7_shared.http_policy import ServiceGate, CooldownPending

UA='ZZU-Reference-Identity/0.1 (bounded academic metadata verification)'
RATE_LOCK=threading.Lock();LAST={}
FAKE_DNS_NETWORK=None


def public_url(url,resolve=True):
    try:
        p=up.urlsplit(url)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.port not in (None,80,443):return False
        if p.hostname.lower()=='localhost' or p.hostname.endswith(('.local','.internal')):return False
        try:
            if not ipaddress.ip_address(p.hostname).is_global:return False
        except ValueError:
            if resolve:
                addresses=[ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(p.hostname,p.port or 443,type=socket.SOCK_STREAM)]
                if any(not addr.is_global and not (FAKE_DNS_NETWORK is not None and addr in FAKE_DNS_NETWORK) for addr in addresses):return False
        return True
    except (ValueError,OSError):return False


class PublicRedirect(ur.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        before,after=up.urlsplit(req.full_url),up.urlsplit(newurl)
        if req.get_header('Authorization') and (before.scheme,before.netloc)!=(after.scheme,after.netloc):raise ValueError('Authenticated cross-origin redirect rejected')
        if not public_url(newurl):raise ValueError('Nonpublic redirect rejected')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def utc():return datetime.now(timezone.utc).isoformat()


class Tools:
    def __init__(self,store,env,limit=12,replay=None):
        self.store=store;self.output=store.output;self.env=env;self.limit=limit;self.logs=[];self.identifiers=[];self.done=set()
        self.allowed=set();self.input_identifiers=set();self.replay=Path(replay) if replay else None
        self.notify=lambda message:None
        self.discover()
    def discover(self):
        for e in self.store.items:
            if e.get('url'):self.allowed.add(e['url'])
            for u in re.findall(r'https?://[^\s<>"\\]+',e['text']):self.allowed.add(u.rstrip('.,;)\']'))
    def redact(self,text):
        for k,v in self.env.items():
            if ('KEY' in k or 'TOKEN' in k) and v:text=text.replace(v,'[REDACTED]')
        return text
    def request(self,url,purpose,payload=None,secret=None,accept='application/json, application/xml, text/html, */*'):
        if len(self.logs)>=self.limit:raise ValueError('本条补查请求预算已用尽')
        rid=f'R{len(self.logs)+1:03}'
        log={'id':rid,'url':url,'purpose':purpose,'method':'POST' if payload is not None else 'GET','body':payload,'started_utc':utc(),'state':'failed'}
        self.logs.append(log);start=time.monotonic();body=b''
        if self.replay:
            for previous in sorted((self.replay/'requests').glob('R*.json')):
                try:
                    old=json.loads(previous.read_text('utf-8'))
                    if old['url']==url and old['method']==log['method'] and old.get('body')==payload and old['state']=='ok' :
                        if sha(old['raw_path'])!=old['sha256']:raise ValueError('Cached response hash mismatch')
                        body=Path(old['raw_path']).read_bytes();raw=self.output/'requests'/f'{rid}{Path(old["raw_path"]).suffix}';raw.parent.mkdir(parents=True,exist_ok=True);raw.write_bytes(body)
                        log.update(state='ok',http_status=old.get('http_status'),content_type=old.get('content_type'),final_url=old.get('final_url'),raw_path=str(raw.resolve()),sha256=sha(raw),elapsed_seconds=0,finished_utc=utc(),replayed_from=str(previous.resolve()),replayed_log_sha256=sha(previous))
                        save(self.output/'requests'/f'{rid}.json',log);save(self.output/'requests.json',self.logs);return log,body
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    log.setdefault('cache_errors',[]).append({'path':str(previous),'error':self.redact(str(exc))[:300]})
        log['attempts']=[]
        try:
            if not public_url(url):raise ValueError('Target is not a reachable public HTTP(S) URL')
            headers={'User-Agent':UA,'Accept':accept}
            if payload is not None:headers['Content-Type']='application/json'
            if secret:headers['Authorization']='Bearer '+secret
            req=ur.Request(url,data=json.dumps(payload).encode('utf-8') if payload is not None else None,headers=headers)
            for attempt in range(1,5):
                entry={'attempt':attempt,'started_utc':utc()};body=b''
                with ServiceGate(url,notify=self.notify) as gate:
                    try:
                        with ur.build_opener(PublicRedirect()).open(req,timeout=25) as response:
                            body=response.read(12_000_001);status=response.status;rh=dict(response.headers)
                            log.update(final_url=response.url,content_type=response.headers.get('Content-Type',''))
                    except urllib.error.HTTPError as exc:
                        status=exc.code;rh=dict(exc.headers);body=exc.read(200000)
                    gate.feedback(status,rh,attempt)
                    entry['queue_seconds']=gate.wait_seconds
                if len(body)>12_000_000:raise ValueError('Response exceeds 12MB')
                response_headers={k:v for k,v in rh.items() if k.lower() in ('retry-after','x-rate-limit-limit','x-rate-limit-interval','x-rate-limit-type','x-concurrency-limit')}
                raw_attempt=self.output/'requests'/f'{rid}-attempt-{attempt}.raw'
                raw_attempt.parent.mkdir(parents=True,exist_ok=True)
                raw_attempt.write_bytes(body if body.startswith(b'%PDF') else self.redact(body.decode('utf-8',errors='replace')).encode('utf-8'))
                entry.update(http_status=status,response_headers=response_headers,raw_path=str(raw_attempt.resolve()),sha256=sha(raw_attempt),finished_utc=utc())
                log['attempts'].append(entry)
                log.update(http_status=status,response_headers=response_headers,
                    state='ok' if 200<=status<300 else 'rate_limited' if status==429 else 'not_found' if status==404 else 'http_error')
                if log['state']!='ok':log['error']=f'HTTP {status}';log['retry_after']=next((v for k,v in rh.items() if k.lower()=='retry-after'),None)
                else:log.pop('error',None);log.pop('retry_after',None)
                save(self.output/'requests'/f'{rid}.json',log)
                if status not in (429,502,503,504) or attempt==4:break
        except urllib.error.HTTPError as exc:
            body=exc.read(200000);log.update(http_status=exc.code,state='rate_limited' if exc.code==429 else 'not_found' if exc.code==404 else 'http_error',error=f'HTTP {exc.code}',retry_after=exc.headers.get('Retry-After'))
        except CooldownPending as exc:log.update(state='rate_limited',error=self.redact(str(exc))[:700])
        except Exception as exc:log.update(state='transport_error',error=self.redact(str(exc))[:700])
        suffix='.pdf' if body.startswith(b'%PDF') else '.txt'
        raw=self.output/'requests'/f'{rid}{suffix}';raw.parent.mkdir(parents=True,exist_ok=True)
        raw.write_bytes(body if suffix=='.pdf' else self.redact(body.decode('utf-8',errors='replace')).encode('utf-8'))
        log.update(raw_path=str(raw.resolve()),sha256=sha(raw),elapsed_seconds=round(time.monotonic()-start,3),finished_utc=utc())
        save(self.output/'requests'/f'{rid}.json',log);save(self.output/'requests.json',self.logs)
        return log,body
    def add_response(self,log,text,url=None,kind='metadata',data=None):
        return self.store.add('live_'+log['purpose'],kind,text,url or log['url'],data,[log['raw_path'],self.output/'requests'/f'{log["id"]}.json'],log['id'],usable=False if log['state']!='ok' else None)
    def doi(self,doi,input_title,origin='candidate'):
        doi=re.sub(r'^https?://(?:dx\.)?doi.org/','',doi,flags=re.I).strip().rstrip('.')
        key=('doi',doi.lower())
        if key in self.done:return
        self.done.add(key);result={'doi':doi,'origin':origin,'state':'unresolved','evidence_ids':[]}
        for provider,url in [('crossref','https://api.crossref.org/works/'+up.quote(doi,safe='')),('datacite','https://api.datacite.org/dois/'+up.quote(doi,safe=''))]:
            log,body=self.request(url,'doi_'+provider)
            if log['state']!='ok':continue
            try:
                obj=json.loads(body)
                if provider=='crossref':
                    m=obj['message'];record={'title':'; '.join(m.get('title',[])),'authors':[' '.join(filter(None,[a.get('given'),a.get('family')])) or a.get('name','') for a in m.get('author',[])], 'doi':m.get('DOI'),'year':str((m.get('published',m.get('issued',{})).get('date-parts') or [['']])[0][0]),'pages':m.get('page'),'volume':m.get('volume'),'issue':m.get('issue'),'type':m.get('type'),'container':m.get('container-title'),'publisher':m.get('publisher'),'dates':{k:m[k] for k in ['published','published-online','published-print','issued'] if k in m},'url':m.get('URL'),'links':m.get('link')}
                else:
                    m=obj['data']['attributes'];record={'title':'; '.join(t['title'] for t in m.get('titles',[])),'authors':[a.get('name','') for a in m.get('creators',[])],'doi':m.get('doi'),'year':str(m.get('publicationYear','')),'type':m.get('types'),'publisher':m.get('publisher'),'url':m.get('url'),'related':m.get('relatedIdentifiers')}
                e=self.add_response(log,json.dumps(record,ensure_ascii=False,indent=2),record.get('url'),data=record)
                similarity=title_score(input_title,record.get('title'))
                result.update(state='title_match' if similarity>=.88 else 'mismatch' if similarity<.55 else 'uncertain',resolved_title=record.get('title'),title_similarity=round(similarity,4),evidence_ids=[e['id']])
                break
            except (ValueError,KeyError,TypeError,IndexError):continue
        self.identifiers.append(result);self.discover()
    def search(self,query):
        key=self.env.get('DEEPSEEK_API_KEY')
        if not key:raise ValueError('DeepSeek search key not configured')
        query=query[:128];log,body=self.request('https://api.deepseek.com/v1/tools/search','search',{'query':query,'count':5,'need_content':False},key)
        if log['state']=='ok':
            for r in json.loads(body).get('results',[])[:5]:
                self.add_response(log,json.dumps(r,ensure_ascii=False,indent=2),r.get('url'),kind='search',data={'title':r.get('title')})
        self.discover()
    def fetch(self,url):
        self.discover()
        if url not in self.allowed:raise ValueError('Fetch URL not present in observed evidence; search first')
        log,body=self.request(url,'fetch',accept='text/html, application/pdf, application/xml, */*')
        if log['state']=='ok':
            if body.startswith(b'%PDF'):
                import pdfplumber
                with pdfplumber.open(io.BytesIO(body)) as pdf:
                    text='\n\n'.join(f'[Physical page {i+1}]\n'+(p.extract_text() or '') for i,p in enumerate(pdf.pages[:3]))
            else:
                text=body.decode('utf-8',errors='replace');parser=Page();parser.feed(text);text='\n'.join(parser.parts)
                for link in parser.links:self.allowed.add(up.urljoin(log.get('final_url',url),link))
            self.add_response(log,text,url,'document')
        else:self.add_response(log,'访问失败：'+log['state'],url,'document')
        self.discover()
    def typed_lookup(self,action,value):
        observed=' '.join(e['text']+' '+e['url'] for e in self.store.items)
        if value not in observed and value not in self.input_identifiers:raise ValueError('Identifier not found in observed evidence')
        if action=='book_editions':
            if not re.fullmatch(r'OL\d+W',value):raise ValueError('Invalid work ID')
            url=f'https://openlibrary.org/works/{value}/editions.json?limit=20'
        elif action=='pmc_fulltext':
            if not re.fullmatch(r'PMC\d+',value):raise ValueError('Invalid PMC ID')
            url=f'https://www.ebi.ac.uk/europepmc/webservices/rest/{value}/fullTextXML'
        elif action=='arxiv_lookup':
            if not re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?',value):raise ValueError('Invalid arXiv ID')
            url='https://export.arxiv.org/api/query?'+up.urlencode({'id_list':value})
        else:raise ValueError('Unsupported action')
        log,body=self.request(url,action)
        if log['state']!='ok':return
        if action=='book_editions':
            data=json.loads(body);records=[{k:r[k] for k in ['key','title','by_statement','publish_date','publishers','publish_places','edition_name','isbn_10','isbn_13'] if k in r} for r in data.get('entries',[])]
            self.add_response(log,json.dumps({'editions':records,'limited_to':20},ensure_ascii=False,indent=2),url,data={'type':'book_editions'})
        else:
            root=ET.fromstring(body)
            if action=='pmc_fulltext':
                front=root.find('front');text=' '.join((front if front is not None else root).itertext())
                self.add_response(log,text,url,'document')
            else:
                ns={'a':'http://www.w3.org/2005/Atom'}
                for entry in root.findall('a:entry',ns):
                    entry_url=entry.findtext('a:id',default='',namespaces=ns)
                    if not re.match(r'^https?://(?:www\.)?arxiv\.org/abs/(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?$',entry_url):
                        e=self.add_response(log,'arXiv 返回接口错误或非作品记录：'+ET.tostring(entry,encoding='unicode'),url,'document');e.update(usable=False,quality='api_error');continue
                    record={'title':entry.findtext('a:title',default='',namespaces=ns).strip(),'authors':[a.findtext('a:name',default='',namespaces=ns) for a in entry.findall('a:author',ns)],'year':entry.findtext('a:published',default='',namespaces=ns)[:4],'arxiv':value,'url':entry.findtext('a:id',default='',namespaces=ns)}
                    self.add_response(log,json.dumps(record,ensure_ascii=False,indent=2),record['url'],data=record)
        self.discover()
    def arxiv(self,value,input_title,origin='candidate'):
        key=('arxiv_lookup',value)
        if key in self.done:return
        self.done.add(key);before=len(self.store.items)
        self.typed_lookup('arxiv_lookup',value)
        entries=self.store.items[before:]
        result={'identifier_type':'arxiv','arxiv':value,'origin':origin,'state':'unresolved','evidence_ids':[]}
        for e in entries:
            if not e['usable'] or not e.get('data',{}).get('title'):continue
            title=e['data'].get('title','');score=title_score(input_title,title)
            result.update(state='title_match' if score>=.88 else 'mismatch' if score<.55 else 'uncertain',resolved_title=title,title_similarity=round(score,4),evidence_ids=[e['id']]);break
        self.identifiers.append(result)
    def execute(self,action,title):
        kind=action['tool'];arg=action['argument'];key=(kind,arg)
        if key in self.done:return {'state':'already_attempted'}
        if kind not in ('doi_lookup','arxiv_lookup'):self.done.add(key)
        before=len(self.logs)
        try:
            if kind=='search':self.search(arg)
            elif kind=='fetch':self.fetch(arg)
            elif kind=='doi_lookup':
                if arg.lower() not in ' '.join(e['text'].lower() for e in self.store.items):raise ValueError('DOI not observed')
                self.doi(arg,title)
            elif kind=='arxiv_lookup':self.arxiv(arg,title)
            else:self.typed_lookup(kind,arg)
            logs=self.logs[before:]
            return {'state':'completed' if logs and all(x['state']=='ok' for x in logs) else 'completed_with_failures' if logs else 'no_new_request','request_ids':[x['id'] for x in logs]}
        except Exception as exc:return {'state':'failed','error':self.redact(str(exc))[:700],'request_ids':[x['id'] for x in self.logs[before:]]}
