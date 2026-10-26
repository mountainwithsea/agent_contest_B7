import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from b7_shared.http_policy import ServiceGate
from reference_identity.evidence import EvidenceStore,sha
from reference_identity.tools import Tools


class RecoveryTests(unittest.TestCase):
    def test_refresh_keeps_old_evidence_request_record_immutable(self):
        from ref_app.retrieval import retrieve_row
        from reference_identity.evidence import seed_evidence
        calls=[]
        def request(tool,url,purpose,payload=None,secret=None):
            calls.append(1);raw=tool.output/'raw.json';raw.parent.mkdir(parents=True,exist_ok=True)
            raw.write_text(json.dumps({'message':{'items':[{'title':['Example title'],'DOI':'10.1234/example','author':[]}]},'generation':len(calls)}))
            return {'url':url,'body':payload,'state':'ok','raw_path':str(raw),'sha256':sha(raw),'generation':len(calls)},b''
        row={'id':'R001','input':{'book_route':False,'title_variants':['Example title'],'qwen':{'title':'Example title','authors':[],'doi':[],'arxiv':[]}}}
        with tempfile.TemporaryDirectory() as d,patch('reference_identity.tools.Tools.request',request):
            root=Path(d);source=root/'source';store=EvidenceStore(root/'evidence')
            retrieve_row(row,source,{},selected=['crossref']);seed_evidence(row,source,store)
            old_artifacts=[dict(a) for e in store.items for a in e['artifacts']]
            self.assertTrue(old_artifacts)
            row['_refresh_checkpoint']=True;retrieve_row(row,source,{},selected=['crossref'])
            self.assertTrue(all(sha(a['path'])==a['sha256'] for a in old_artifacts))

    def test_legacy_request_index_is_unchanged_after_upgrade_refresh(self):
        from ref_app.retrieval import retrieve_row
        with tempfile.TemporaryDirectory() as d:
            source=Path(d);legacy=source/'requests/R001--crossref.json';legacy.parent.mkdir()
            legacy.write_text(json.dumps({'url':'https://api.crossref.org/works','state':'rate_limited'}))
            before=sha(legacy)
            def request(tool,url,purpose,payload=None,secret=None):
                raw=tool.output/'raw.json';raw.parent.mkdir(parents=True,exist_ok=True);raw.write_text('{"message":{"items":[]}}')
                return {'url':url,'body':payload,'state':'ok','raw_path':str(raw),'sha256':sha(raw)},b''
            row={'id':'R001','_refresh_checkpoint':True,'input':{'book_route':False,'title_variants':['Example title'],'qwen':{'title':'Example title','authors':[],'doi':[],'arxiv':[]}}}
            with patch('reference_identity.tools.Tools.request',request):retrieve_row(row,source,{},selected=['crossref'])
            self.assertEqual(sha(legacy),before)
            self.assertTrue((source/row['requests'][0]['audit_path']).is_file())
    def test_public_parser_retries_429_and_keeps_failure_records(self):
        import io,urllib.error
        from ref_app.public_parsers import PublicTransport
        hits=[]
        def send(*args):
            hits.append(1)
            if len(hits)<3:raise urllib.error.HTTPError('https://anystyle.io/parse',429,'rate limited',{'Retry-After':'0'},io.BytesIO(b'limited'))
            return '[]',200
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);gate=lambda url,**kw:ServiceGate(url,root=root/'rates',interval=0,**kw)
            with patch('ref_app.public_parsers.ServiceGate',gate):
                raw,status=PublicTransport(root,send=send).call('anystyle','https://anystyle.io/parse')
            self.assertEqual((raw,status),('[]',200))
            records=[json.loads(p.read_text('utf-8')) for p in root.glob('network/anystyle/*.json')]
            self.assertEqual(sorted(r['http_status'] for r in records),[200,429,429])
            self.assertEqual(sum(r.get('raw_response')=='limited' for r in records),2)

    def test_401_is_not_retried(self):
        import io,urllib.error
        from ref_app.public_parsers import PublicTransport
        hits=[]
        def send(*args):
            hits.append(1);raise urllib.error.HTTPError('https://anystyle.io/parse',401,'unauthorized',{},io.BytesIO(b'invalid'))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);gate=lambda url,**kw:ServiceGate(url,root=root/'rates',interval=0,**kw)
            with patch('ref_app.public_parsers.ServiceGate',gate),self.assertRaises(urllib.error.HTTPError):
                PublicTransport(root,send=send).call('anystyle','https://anystyle.io/parse')
            self.assertEqual(len(hits),1)

    def test_429_recovers_and_keeps_each_raw_response(self):
        hits=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(1);status=429 if len(hits)<3 else 200
                self.send_response(status);self.send_header('Retry-After','0');self.end_headers()
                self.wfile.write(json.dumps({'attempt':len(hits)}).encode())
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);events=[];tool=Tools(EvidenceStore(root/'evidence'),{},limit=1);tool.notify=events.append
                gate=lambda url,**kw:ServiceGate(url,root=root/'rates',interval=0,**kw)
                with patch('reference_identity.tools.public_url',return_value=True),patch('reference_identity.tools.ServiceGate',gate,create=True):
                    rec,body=tool.request(f'http://127.0.0.1:{server.server_port}/x','crossref')
                self.assertEqual(rec['state'],'ok')
                self.assertEqual([a['http_status'] for a in rec['attempts']],[429,429,200])
                self.assertEqual(json.loads(body)['attempt'],3)
                self.assertEqual(len(tool.logs),1)  # retries do not consume new logical query slots
                for i,a in enumerate(rec['attempts'],1):
                    self.assertEqual(sha(a['raw_path']),a['sha256'])
                    self.assertEqual(json.loads(Path(a['raw_path']).read_text())['attempt'],i)
                self.assertTrue(any('限流' in m for m in events))
        finally:server.shutdown();server.server_close();thread.join()

    def test_rate_limited_checkpoint_is_not_reused(self):
        from ref_app.retrieval import valid_checkpoint
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'raw.txt').write_text('429')
            rec={'url':'https://api.crossref.org/works','body':None,'state':'rate_limited','raw_response':'raw.txt','sha256':sha(root/'raw.txt')}
            self.assertFalse(valid_checkpoint(root,rec,rec['url'],None))


if __name__=='__main__':unittest.main()
