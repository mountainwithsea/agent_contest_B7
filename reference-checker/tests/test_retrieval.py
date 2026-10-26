import tempfile
import threading
import time
import unittest
from pathlib import Path
from ref_app.retrieval import collect


class RetrievalTests(unittest.TestCase):
    def test_bounded_parallel_order_and_failure_isolation(self):
        lock=threading.Lock();active=0;peak=0
        def fetch(provider):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            time.sleep(.02 if provider!='a' else .06)
            with lock:active-=1
            if provider=='b':raise ValueError('bad response')
            return {'provider':provider,'state':'ok','candidates':[provider]}, {'request_id':provider}
        events=[]
        results,records=collect(['a','b','c','d'],fetch,workers=2,on_done=lambda p:events.append(p))
        self.assertEqual([r['provider'] for r in results],['a','b','c','d'])
        self.assertEqual(results[1]['state'],'processing_error')
        self.assertEqual(results[2]['candidates'],['c'])
        self.assertEqual(peak,2)
        self.assertEqual(len(events),4)
        self.assertEqual(len(records),4)

    def test_serial_and_parallel_preserve_payload(self):
        def fetch(p):return {'provider':p,'state':'ok','candidates':[{'title':p}]},{'request_id':p}
        self.assertEqual(collect(['a','b','c'],fetch,workers=1),collect(['a','b','c'],fetch,workers=3))

    def test_checkpoint_requires_matching_request_and_raw_hash(self):
        from ref_app.retrieval import valid_checkpoint
        from reference_identity.evidence import sha
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'raw.txt').write_text('evidence')
            r={'url':'https://example.org','body':None,'state':'ok','raw_response':'raw.txt','sha256':sha(root/'raw.txt')}
            self.assertTrue(valid_checkpoint(root,r,r['url'],None))
            self.assertFalse(valid_checkpoint(root,r,r['url'],{'q':'changed'}))
            (root/'raw.txt').write_text('tampered')
            self.assertFalse(valid_checkpoint(root,r,r['url'],None))

    def test_row_saves_bad_response_and_reuses_intact_evidence(self):
        from unittest.mock import patch
        from ref_app.retrieval import retrieve_row
        from reference_identity.evidence import sha
        calls=[]
        def request(tool,url,purpose,payload=None,secret=None):
            calls.append(purpose)
            raw=tool.output/'raw.txt';raw.parent.mkdir(parents=True,exist_ok=True)
            raw.write_text('malformed response' if purpose=='crossref' else '{}')
            return {'url':url,'body':payload,'state':'ok','raw_path':str(raw),'sha256':sha(raw)},b''
        with tempfile.TemporaryDirectory() as d,patch('reference_identity.tools.Tools.request',request):
            row={'id':'R1','input':{'book_route':False,'title_variants':['Example title'],
                 'qwen':{'title':'Example title','authors':[],'doi':[],'arxiv':[]}}}
            retrieve_row(row,Path(d),{},workers=3)
            self.assertEqual(row['providers'][0]['state'],'parse_error')
            self.assertEqual(len(row['requests']),6)
            self.assertTrue((Path(d)/'schedules/R1.json').exists())
            self.assertIn('malformed response',(Path(d)/row['requests'][0]['raw_response']).read_text())
            retrieve_row(row,Path(d),{},workers=3)
            self.assertEqual(len(calls),6)
            self.assertTrue(all(p['checkpoint_reused'] for p in row['providers']))
