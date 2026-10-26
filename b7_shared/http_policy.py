"""One in-flight request per service, shared by workers and desktop profiles.

The OS releases the file lock if a worker dies. The cooldown remains on disk,
so starting another task cannot accidentally bypass a server's Retry-After.
"""
import hashlib
import json
import math
import os
import random
import re
import tempfile
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
from .lifecycle import SuiteLock


class CooldownPending(RuntimeError):
    """A server cooldown exceeds this request's bounded waiting budget."""


def service_policy(url):
    host=(urlsplit(url).hostname or '').lower()
    if host=='arxiv.org' or host.endswith('.arxiv.org'):return 'arxiv',3.2
    if host=='api.crossref.org':return 'crossref',1.15
    if host=='anystyle.io':return 'anystyle',1.0
    if host=='grobidorg-grobid.hf.space':return 'grobid',1.0
    return host,.8


def retry_seconds(headers,now=None):
    headers={k.lower():str(v) for k,v in headers.items()}
    value=headers.get('retry-after','').strip()
    try:seconds=float(value)
    except ValueError:
        try:seconds=parsedate_to_datetime(value).timestamp()-(time.time() if now is None else now)
        except (TypeError,ValueError,OverflowError):return None
    return max(0,seconds) if math.isfinite(seconds) else None


def state_root():
    if os.environ.get('B7_HTTP_STATE_DIR'):return Path(os.environ['B7_HTTP_STATE_DIR'])
    base=Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir())
    return base/'B7Workbench'/'network-v1'


class ServiceGate:
    def __init__(self,url,root=None,interval=None,notify=None,max_wait=120):
        self.service,default=service_policy(url)
        self.interval=default if interval is None else interval
        self.root=Path(root) if root is not None else state_root()
        self.path=self.root/(hashlib.sha256(self.service.encode()).hexdigest()[:24]+'.lock')
        self.notify=notify or (lambda message:None)
        self.max_wait=max_wait;self.lock=None;self.state={};self.wait_seconds=0

    def _save(self):
        file=self.lock.file
        # SuiteLock opens a+b: truncate the payload first, keeping locked byte 0.
        file.truncate(1);file.seek(1)
        file.write(json.dumps(self.state).encode('utf-8'));file.flush()

    def __enter__(self):
        begin=time.monotonic();announced=False
        try:
            while True:
                try:self.lock=SuiteLock(self.path);self.lock.__enter__();break
                except RuntimeError:
                    if time.monotonic()-begin>=self.max_wait:raise CooldownPending(self.service+'：来源排队超时，稍后可重试')
                    if not announced:self.notify(self.service+'：正在排队，等待前一个请求完成');announced=True
                    time.sleep(.05)
            file=self.lock.file;file.seek(1)
            try:self.state=json.loads(file.read().decode('utf-8'))
            except (ValueError,UnicodeError):self.state={}
            seconds=max(0,self.state.get('next',0)-time.time(),self.state.get('cooldown',0)-time.time())
            if seconds>self.max_wait-(time.monotonic()-begin):
                raise CooldownPending(self.service+'：服务限流，仍需等待 '+str(math.ceil(seconds))+' 秒；本次暂缓，其他来源继续')
            if seconds>.25:self.notify(self.service+'：'+('限流等待 ' if self.state.get('cooldown',0)>time.time() else '请求间隔等待 ')+str(math.ceil(seconds))+' 秒')
            if seconds:time.sleep(seconds)
            self.wait_seconds=round(time.monotonic()-begin,3)
            self.state['next']=time.time()+max(self.interval,self.state.get('interval',0))
            self._save()
            return self
        except BaseException:
            if self.lock and self.lock.file:self.lock.__exit__(None,None,None)
            self.lock=None
            raise

    def feedback(self,status,headers,attempt=1):
        h={k.lower():str(v) for k,v in headers.items()}
        try:
            count=float(h.get('x-rate-limit-limit','0'))
            match=re.fullmatch(r'([\d.]+)s?',h.get('x-rate-limit-interval',''))
            if count>0 and match:
                interval=float(match[1])/count*1.05
                if math.isfinite(interval):self.state['server_interval']=max(self.interval,interval)
        except (ValueError,ZeroDivisionError):pass
        if status in (429,502,503,504):
            seconds=retry_seconds(h)
            if seconds is None:seconds=min(60,2**min(attempt,5))+random.uniform(.1,.5)
            self.state['cooldown']=max(self.state.get('cooldown',0),time.time()+seconds)
            if status==429:
                base=max(self.interval,self.state.get('server_interval',0))
                self.state['interval']=max(base,min(60,self.state.get('interval',base)*1.5))
            self.notify(self.service+'：'+('请求限流' if status==429 else '服务暂不可用')+'，等待 '+str(math.ceil(seconds))+' 秒后重试')
        elif 200<=status<300:
            self.state.pop('cooldown',None)
            self.state['interval']=max(self.interval,self.state.get('server_interval',0))
        self._save()

    def __exit__(self,*args):
        try:
            self.state['next']=time.time()+max(self.interval,self.state.get('interval',0))
            self._save()
        finally:self.lock.__exit__(*args)
