"""Public parsing only. Cookies/CSRF stay in memory; every response is audited."""
import http.cookiejar
import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
import uuid
from datetime import datetime,timezone
from .jobs import atomic
from b7_shared.http_policy import ServiceGate

GROBID='https://grobidorg-grobid.hf.space'
ANYSTYLE='https://anystyle.io'

class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        p=urllib.parse.urlsplit(newurl)
        if p.scheme!='https' or p.netloc.lower() not in ('grobidorg-grobid.hf.space','anystyle.io'):
            raise ValueError('Unexpected public parser redirect')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def send(opener,url,body,headers):
    with opener.open(urllib.request.Request(url,data=body,headers=headers),timeout=120) as r:
        return r.read().decode('utf-8'),r.status

class PublicTransport:
    def __init__(self,folder,send=send,format_mode='remote',converter=None,notify=None):
        self.folder=folder;self.send=send;self.token=None;self.version=None
        self.notify=notify or (lambda message:None)
        if format_mode not in ('local','remote'):raise ValueError('Unknown AnyStyle format mode')
        self.format_mode=format_mode;self.converter=converter
        self.openers={t:urllib.request.build_opener(RestrictedRedirect(),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())) for t in ('grobid','anystyle')}

    def call(self,tool,url,body=None,headers=None,audit_body=None,bootstrap=False):
        for attempt in range(1,5):
            start=time.perf_counter()
            rec={'tool':tool,'url':url,'method':'POST' if body else 'GET','request':audit_body,
                 'utc':datetime.now(timezone.utc).isoformat(),'attempt':attempt,'ok':False}
            retry=False;transport_retry=False
            try:
                with ServiceGate(url,notify=self.notify) as gate:
                    try:
                        raw,status=self.send(self.openers[tool],url,body,headers or {})
                    except urllib.error.HTTPError as exc:
                        gate.feedback(exc.code,dict(exc.headers),attempt)
                        raise
                    gate.feedback(status,{})
                    rec['queue_seconds']=gate.wait_seconds
                rec.update(http_status=status,ok=True)
                # The homepage carries the transient CSRF token, not bibliographic evidence.
                rec['raw_response']='[session bootstrap HTML omitted]' if bootstrap else raw
                return raw,status
            except Exception as exc:
                rec['error']=type(exc).__name__+': '+str(exc)[:500]
                if isinstance(exc,urllib.error.HTTPError):
                    rec['http_status']=exc.code
                    rec['retry_after']=exc.headers.get('Retry-After')
                    rec['raw_response']=exc.read().decode('utf-8',errors='replace') if not bootstrap else '[bootstrap error body omitted]'
                    retry=exc.code in (429,502,503,504)
                elif isinstance(exc,(urllib.error.URLError,TimeoutError)):retry=True;transport_retry=True
                if not retry or attempt==4:raise
            finally:
                rec['seconds']=time.perf_counter()-start
                # Avoid persisting CSRF echoed by an error page as well.
                if self.token:
                    rec=json.loads(json.dumps(rec).replace(self.token,'[REDACTED]'))
                atomic(self.folder/'network'/tool/(uuid.uuid4().hex+'.json'),rec)
            if transport_retry:time.sleep(2)

    def __call__(self,url,body,headers):
        if url==GROBID+'/api/processCitationList':
            if self.version is None:
                raw,_=self.call('grobid',GROBID+'/api/version');self.version=raw
                atomic(self.folder/'grobid-version.json',{'response':raw})
            params=urllib.parse.parse_qs(body.decode())
            return self.call('grobid',url,body,headers,params)
        if url!=ANYSTYLE+'/parse':raise ValueError('Unknown public parser endpoint')
        if self.token is None:
            page,_=self.call('anystyle',ANYSTYLE+'/',bootstrap=True)
            match=re.search(r'<meta name="csrf-token" content="([^"]+)"',page)
            if not match:raise ValueError('AnyStyle session token not found')
            self.token=match[1]
        payload=json.loads(body)
        h={'Content-Type':'application/json','X-CSRF-Token':self.token,'Accept':'application/json','Origin':ANYSTYLE,'Referer':ANYSTYLE+'/'}
        raw,_=self.call('anystyle',ANYSTYLE+'/parse?format=json',body,h,payload)
        segments=json.loads(raw)
        if self.format_mode=='local':
            record={'segments':segments,'ok':False}
            begin=time.perf_counter()
            try:
                from .anystyle_formatter import convert
                converted=(self.converter or convert)(segments)
                if len(converted['csl'])!=len(payload['input']):raise ValueError('Local CSL row alignment')
                record.update(ok=True,result=converted)
                return json.dumps({'input':payload['input'],'parsed_segments':segments,'csl':converted['csl'],
                    'version':'public parser; local AnyStyle 1.5.0 formatter','format_mode':'local','adapter_envelope':True}),200
            except Exception as exc:
                record['error']=type(exc).__name__+': '+str(exc)[:1500]
                record['fallback']='remote format; original labels unchanged'
            finally:
                record['elapsed_seconds']=time.perf_counter()-begin
                atomic(self.folder/'local-format'/(uuid.uuid4().hex+'.json'),record)
        dataset=[{'tokens':[{'label':tag,'value':val} for tag,val in item]} for item in segments]
        export={'dataset':json.dumps(dataset),'format':'csl','authenticity_token':self.token}
        native,status=self.call('anystyle',ANYSTYLE+'/format',urllib.parse.urlencode(export).encode(),
            {'Content-Type':'application/x-www-form-urlencoded','Origin':ANYSTYLE,'Referer':ANYSTYLE+'/'},
            {'dataset':dataset,'format':'csl'})
        # Adapter envelope only; exact native responses are in network/.
        return json.dumps({'input':payload['input'],'parsed_segments':segments,'csl':json.loads(native),
                           'version':'public website; backend version not exposed','adapter_envelope':True}),status
