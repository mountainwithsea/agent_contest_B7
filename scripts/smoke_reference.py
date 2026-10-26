"""Optional live two-reference smoke. No personal keys or paid model calls.

Run after setup; public parsing/registry requests are real and may be unavailable.
All task data lives in a temporary directory and is removed on exit.
"""
import argparse
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TEXT='''References
[1] Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N. Gomez, Lukasz Kaiser, and Illia Polosukhin. Attention is all you need. Advances in Neural Information Processing Systems, 2017. arXiv:1706.03762.
[2] Jacob Devlin, Ming-Wei Chang, Kenton Lee, and Kristina Toutanova. BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. Proceedings of NAACL-HLT, 2019. doi:10.18653/v1/N19-1423.
'''


def main():
    args=argparse.ArgumentParser();args.add_argument('--fake-dns',action='store_true');options=args.parse_args()
    with tempfile.TemporaryDirectory(prefix='b7-reference-smoke-') as tmp:
        temp=Path(tmp)
        env={k:v for k,v in os.environ.items() if not k.startswith(('B7_','LLM_','DEEPSEEK_','OPENALEX_','REFERENCE_','ANYSTYLE_','GROBID_'))}
        env.update(PYTHONPATH=os.pathsep.join([str(ROOT),str(ROOT/'reference-checker')]),PYTHONUTF8='1',
                   B7_ENV_FILE=str(temp/'no-env'),REFERENCE_DATA_DIR=str(temp/'data'),
                   DEEPSEEK_API_KEY='unused-no-paid-model-call',ANYSTYLE_FORMAT_MODE='remote')
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        url=f'http://127.0.0.1:{port}';opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(path,data=None,headers=None):
            with opener.open(urllib.request.Request(url+path,data=data,headers=headers or {}),timeout=20) as response:return response.read()
        command=[sys.executable,'-B','-X','utf8','-m','ref_app','--port',str(port)]
        if options.fake_dns:command.append('--fake-dns')
        with (temp/'service.log').open('wb') as log:
            process=subprocess.Popen(command,cwd=ROOT/'reference-checker',env=env,stdout=log,stderr=log)
            try:
                for _ in range(100):
                    try:request('/api/jobs');break
                    except OSError:
                        if process.poll() is not None:raise RuntimeError('Service stopped: '+(temp/'service.log').read_text('utf8'))
                        time.sleep(.1)
                page=request('/').decode('utf8');assert '<html' in page
                job=json.loads(request('/api/jobs',TEXT.encode(),{'Origin':url,'X-Ref-App':'1','X-Filename':'smoke.txt','X-Run-Mode':'balanced'}))
                deadline=time.monotonic()+300
                while True:
                    current=json.loads(request('/api/jobs/'+job['id']))
                    if current['state'] not in ('queued','running'):break
                    if time.monotonic()>deadline:raise TimeoutError('Live smoke timed out')
                    time.sleep(.5)
                assert current['state']=='completed',current.get('error')
                summary=current['summary']
                assert current['reference_count']==2,current
                assert summary['existence'].get('confirmed')==2,summary
                assert not any(summary.get(k,0) for k in ('identity_model_attempts','deepseek_search_calls','parsing_model_attempts','extraction_model_attempts')),summary
                report={'standalone_python_environment':str(Path(sys.executable).resolve().parent.parent.relative_to(ROOT)),
                        'format_mode':'remote','references':2,'summary':summary,'http_ui':True,'task_data_temporary':True}
                print(json.dumps(report,ensure_ascii=False,indent=2))
                return report
            finally:
                if process.poll() is None:process.terminate();process.wait(timeout=10)
                # Stop only a worker created by this smoke task if an assertion
                # interrupted it before normal completion; never touch other jobs.
                sys.path.insert(0,str(ROOT/'reference-checker'))
                from ref_app.lifecycle import OwnedProcess
                for p in (temp/'data').glob('*/job.json'):
                    j=json.loads(p.read_text('utf8'));worker=OwnedProcess(j.get('worker_pid',0),j.get('worker_created'))
                    if worker.poll() is None:worker.terminate()


if __name__=='__main__':main()
