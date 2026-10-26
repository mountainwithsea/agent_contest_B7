import argparse
import io
import json
import mimetypes
import subprocess
import sys
import threading
import zipfile
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit,unquote
from .jobs import JobStore,safe_path
from .lifecycle import OwnedProcess,stamp,FileLock
from .continuation import resume_info,retry_targets
from .jobs import atomic
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
def default_data_root():
    from b7_shared.config import data_dir
    return data_dir('reference')

class App:
    def __init__(self,root,fake_dns=False):
        self.store=JobStore(root);self.fake_dns=fake_dns;self.active=None;self.lock=threading.RLock()
        for job in self.store.list():
            owned=OwnedProcess(job.get('worker_pid',0),job.get('worker_created'))
            if job['state'] in ('running','queued') and owned.poll() is None:
                self.active=(job['id'],owned)
                threading.Thread(target=self.monitor,args=(job['id'],owned),daemon=True).start()
            elif job['state'] in ('running','queued'):self.store.update(job['id'],state='interrupted',error='服务上次停止，可继续处理')
    def launch(self,jid):
        with self.lock:
            if self.active and self.active[1].poll() is None:raise ValueError('已有任务运行，请等待完成或先取消')
            job=self.store.read(jid)
            if job['state']=='completed' and not resume_info(job)['resume_available']:raise ValueError('所有条目已确认，无需继续补查')
            if job['state'] in ('completed','failed','cancelled','interrupted'):
                run_id=uuid4().hex
                atomic(self.store.folder(jid)/'runs'/run_id/'job-before.json',job)
                self.store.update(jid,resume_run=run_id,resume_targets=retry_targets(job))
                self.store.event(jid,'resume','继续处理：复用已有提取与成功解析，只补查未确认或查询受阻的条目')
            self.store.update(jid,state='queued',error=None)
            log=(self.store.folder(jid)/'worker.log').open('ab')
            try:
                proc=subprocess.Popen([sys.executable,'-X','utf8','-m','ref_app.worker',str(self.store.folder(jid).resolve())]+(['--fake-dns'] if self.fake_dns else []),cwd=ROOT,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            finally:log.close()
            self.active=(jid,proc)
            self.store.update(jid,worker_pid=proc.pid,worker_created=stamp(proc.pid))
            threading.Thread(target=self.monitor,args=(jid,proc),daemon=True).start()
    def monitor(self,jid,proc):
        proc.wait()
        with self.lock:
            if self.active!=(jid,proc):return
            job=self.store.read(jid)
            if job['state'] in ('running','queued'):self.store.update(jid,state='failed',error='工作进程异常退出，已保存的步骤可继续')
    def cancel(self,jid):
        with self.lock:
            if not self.active or self.active[0]!=jid or self.active[1].poll() is not None:raise ValueError('该任务当前没有运行')
            self.active[1].terminate();self.active[1].wait(timeout=10)
            self.store.update(jid,state='cancelled',error='用户取消；已发出的API请求可能已经计费')
            self.store.event(jid,'cancelled','用户取消，保留已有结果与证据')

def handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,status,body,ctype='application/json; charset=utf-8',attachment=None):
            if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=False).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            if attachment:self.send_header('Content-Disposition','attachment; filename="'+attachment+'"')
            self.end_headers();self.wfile.write(body)
        def valid_host(self):return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        def do_GET(self):
            if not self.valid_host():return self.respond(403,{'error':'invalid host'})
            try:
                path=unquote(urlsplit(self.path).path);parts=path.strip('/').split('/')
                if path=='/':return self.respond(200,(ROOT/'ref_app/static/index.html').read_bytes(),'text/html; charset=utf-8')
                if path in ('/process.js','/process.css'):
                    return self.respond(200,(ROOT/'ref_app/static'/path[1:]).read_bytes(),'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
                if len(parts)==4 and parts[:2]==['api','jobs'] and parts[3]=='visual':
                    from .visual_process import snapshot
                    job=app.store.read(parts[2])
                    return self.respond(200,snapshot(app.store.folder(parts[2]),job))
                if path=='/api/jobs':return self.respond(200,app.store.list())
                if len(parts)==3 and parts[:2]==['api','jobs']:
                    obj=app.store.read(parts[2]);obj.update(resume_info(obj));obj['events']=app.store.events(parts[2]);obj['files']=[str(p.relative_to(app.store.folder(parts[2]))).replace('\\','/') for p in app.store.folder(parts[2]).rglob('*') if p.is_file() and p.suffix!='.tmp' and not p.name.startswith('.')];return self.respond(200,obj)
                if len(parts)>=3 and parts[0]=='files':
                    p=safe_path(app.store.folder(parts[1]),'/'.join(parts[2:]))
                    if not p.is_file() or p.name.startswith('.'):return self.respond(404,{'error':'file missing'})
                    kind=mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
                    if p.suffix=='.html' and p.name!='index.html':kind='text/plain; charset=utf-8'
                    if p.suffix in ('.json','.jsonl','.txt','.log','.py'):kind='text/plain; charset=utf-8'
                    return self.respond(200,p.read_bytes(),kind)
                if len(parts)==3 and parts[:2]==['api','export']:
                    buf=io.BytesIO();folder=app.store.folder(parts[2]);app.store.read(parts[2])
                    if app.store.read(parts[2])['state'] in ('queued','running'):raise ValueError('请等待任务停止后导出完整快照')
                    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
                        for p in folder.rglob('*'):
                            if p.is_file() and p.suffix!='.tmp' and not p.name.startswith('.'):z.write(p,p.relative_to(folder))
                    return self.respond(200,buf.getvalue(),'application/zip','reference-audit.zip')
                self.respond(404,{'error':'not found'})
            except (ValueError,OSError) as exc:self.respond(400,{'error':str(exc)[:300]})
        def do_POST(self):
            origin=self.headers.get('Origin')
            if not self.valid_host() or self.headers.get('X-Ref-App')!='1' or origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
                return self.respond(403,{'error':'只允许本机应用页面操作'})
            try:
                parts=urlsplit(self.path).path.strip('/').split('/')
                if parts==['api','jobs']:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=20*1024*1024:raise ValueError('文件大小须在1字节至20MB之间')
                    data=self.rfile.read(size)
                    if len(data)!=size:raise ValueError('上传不完整')
                    with app.lock:
                        if app.active and app.active[1].poll() is None:raise ValueError('已有任务运行，请先等待或取消')
                        mode=self.headers.get('X-Run-Mode','balanced')
                        if mode not in ('balanced','legacy','local-parse','local-full','public-parse'):raise ValueError('Unknown run mode')
                        job=app.store.create(unquote(self.headers.get('X-Filename','input.txt')),data)
                        app.store.update(job['id'],parser_backend='public' if mode in ('balanced','public-parse') else 'legacy' if mode=='legacy' else 'local',stop_after='parse' if mode.endswith('-parse') else 'identity',verification_policy='registry-first-v1' if mode=='balanced' else 'legacy',allow_identity_model=self.headers.get('X-Allow-Identity-Model')=='1')
                        app.launch(job['id'])
                    return self.respond(201,job)
                if len(parts)==4 and parts[:2]==['api','jobs']:
                    if parts[3]=='cancel':app.cancel(parts[2])
                    elif parts[3]=='resume':app.launch(parts[2])
                    else:raise ValueError('Unknown action')
                    return self.respond(200,app.store.read(parts[2]))
                self.respond(404,{'error':'not found'})
            except (ValueError,OSError) as exc:self.respond(400,{'error':str(exc)[:300]})
    return Handler

def main():
    import signal
    if hasattr(signal,'SIGBREAK'):signal.signal(signal.SIGBREAK,signal.default_int_handler)
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8766);p.add_argument('--fake-dns',action='store_true');args=p.parse_args()
    data=default_data_root()
    singleton=FileLock(data/'.server.lock');singleton.__enter__()
    app=App(data,args.fake_dns);server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(app));server.daemon_threads=True
    print(f'Reference app: http://127.0.0.1:{args.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        if app.active and app.active[1].poll() is None:app.cancel(app.active[0])
        server.server_close()
        singleton.__exit__()
if __name__=='__main__':main()
