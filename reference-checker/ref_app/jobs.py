import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from .lifecycle import FileLock

LOCK=threading.RLock()
REPLACE_TIMEOUT=2.0
EXTENSIONS={'.txt','.pdf','.docx','.png','.jpg','.jpeg'}
def utc():return datetime.now(timezone.utc).isoformat()
def safe_path(root,relative):
    root=Path(root).resolve();p=(root/relative).resolve()
    if not p.is_relative_to(root):raise ValueError('Path outside job')
    return p
def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Keep temporary names short: appending to a content-addressed destination
    # can exceed Windows MAX_PATH even when the destination itself is valid.
    tmp=path.with_name('.write-'+uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
        deadline=time.monotonic()+REPLACE_TIMEOUT;delay=.01
        while True:
            try:
                os.replace(tmp,path)
                break
            except PermissionError:
                # Windows readers/scanners may briefly deny rename/delete.
                # Keep the old JSON intact; never fall back to truncating it.
                remaining=deadline-time.monotonic()
                if remaining<=0:raise
                time.sleep(min(delay,remaining));delay=min(delay*2,.1)
    finally:
        try:tmp.unlink(missing_ok=True)
        except OSError:pass
class JobStore:
    def __init__(self,root):self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
    def folder(self,jid):
        if not re.fullmatch(r'[a-f0-9]{32}',jid):raise ValueError('Invalid job id')
        return self.root/jid
    def _read(self,jid):return json.loads((self.folder(jid)/'job.json').read_text('utf-8'))
    def read(self,jid):
        with LOCK,FileLock(self.folder(jid)/'.state.lock',wait=5):
            return self._read(jid)
    def update(self,jid,**values):
        with LOCK,FileLock(self.folder(jid)/'.state.lock',wait=5):
            obj=self._read(jid);obj.update(values,updated=utc());atomic(self.folder(jid)/'job.json',obj);return obj
    def create(self,name,data):
        ext=Path(name).suffix.lower()
        if ext not in EXTENSIONS or not data or len(data)>20*1024*1024:raise ValueError('请选择不超过20MB的PDF、DOCX、TXT或图片')
        jid=uuid4().hex;folder=self.folder(jid);folder.mkdir()
        (folder/('input'+ext)).write_bytes(data)
        obj={'id':jid,'name':Path(name.replace('\\','/')).name,'input':'input'+ext,'input_sha256':hashlib.sha256(data).hexdigest(),'state':'queued','created':utc(),'updated':utc(),'completed_stages':[],'current':None}
        atomic(folder/'job.json',obj);return obj
    def event(self,jid,stage,message,**detail):
        with LOCK:
            ev={'time':utc(),'stage':stage,'message':message,**detail}
            previous=self.read(jid).get('current') or {}
            if previous.get('stage')==stage:
                for key in ('done','total'):
                    if key not in ev and key in previous:ev[key]=previous[key]
            with (self.folder(jid)/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(ev,ensure_ascii=False)+'\n')
            self.update(jid,current=ev)
    def events(self,jid):
        path=self.folder(jid)/'events.jsonl';out=[]
        if path.exists():
            for line in path.read_text('utf-8').splitlines():
                try:out.append(json.loads(line))
                except ValueError:pass
        return out
    def list(self):
        rows=[]
        for p in self.root.glob('*/job.json'):
            try:rows.append(self.read(p.parent.name))
            except (ValueError,OSError):pass
        return sorted(rows,key=lambda x:x['created'],reverse=True)
