"""Single reference application launcher; Ctrl+C stops its owned service."""
import argparse
import json
import os
import socket
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from b7_shared.config import ROOT, child_environment, load_values


def local_json(url,body=None,headers=None):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data=json.dumps(body).encode() if body is not None else None
    with opener.open(urllib.request.Request(url,data=data,headers=headers or {}),timeout=10) as response:
        return json.loads(response.read())


def stop_service(process,url):
    if process.poll() is not None:return
    try:
        for task in local_json(url+'/api/jobs'):
            if task.get('state') in ('running','queued'):
                local_json(url+'/api/jobs/'+task['id']+'/cancel',{},
                           {'Origin':url,'X-Ref-App':'1','Content-Type':'application/json'})
    except (OSError,ValueError):pass
    process.terminate()
    try:process.wait(timeout=8)
    except subprocess.TimeoutExpired:process.kill();process.wait()


def wait_for_exit(process):
    # Bounded waits let Python dispatch console signals while Windows is
    # waiting for a native child handle. An indefinite wait can defer them.
    while True:
        try:return process.wait(timeout=.25)
        except subprocess.TimeoutExpired:pass


def main():
    if hasattr(signal,'SIGBREAK'):signal.signal(signal.SIGBREAK,signal.default_int_handler)
    parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');parser.add_argument('--fake-dns',action='store_true');args=parser.parse_args()
    values=load_values();preferred=int(values.get('REFERENCE_PORT','8876'))
    with socket.socket() as probe:
        try:probe.bind(('127.0.0.1',preferred))
        except OSError:probe.bind(('127.0.0.1',0))
        port=probe.getsockname()[1]
    env=child_environment();command=[sys.executable,'-B','-X','utf8','-m','ref_app','--port',str(port)]
    if args.fake_dns or values.get('REFERENCE_FAKE_DNS')=='1':command.append('--fake-dns')
    process=subprocess.Popen(command,cwd=ROOT/'reference-checker',env=env,creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
    url=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('Reference service stopped during startup')
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url+'/api/jobs',timeout=.5):break
            except OSError:time.sleep(.1)
        else:raise TimeoutError('Reference service startup timed out')
        print('Reference checker: '+url,flush=True)
        if not args.no_browser:webbrowser.open(url)
        return wait_for_exit(process)
    except KeyboardInterrupt:return 0
    finally:
        stop_service(process,url)


if __name__=='__main__':raise SystemExit(main())
