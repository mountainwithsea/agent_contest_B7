import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ref_app.jobs import JobStore


class ContinuationTests(unittest.TestCase):
    def test_confirmed_result_survives_parser_failure_during_continuation(self):
        from ref_app.balanced import run_balanced,failed
        from ref_app.jobs import atomic
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);store=JobStore(root);job=store.create('example.txt',b'Known title')
            folder=store.folder(job['id']);old=failed({'id':'R001','input':{'raw_text':'Known title','qwen':{'title':'Known title','authors':[]}}},'old')
            old['dimensions']['existence']['status']='confirmed';old['dimensions']['execution']={'status':'completed','errors':[]};old['marker']='preserve-me'
            p=folder/'verification/references/R001/result.json';atomic(p,old)
            with patch('ref_app.balanced.prepare',side_effect=ValueError('parser unavailable')):
                run_balanced(folder,job,[{'raw_text':'Known title'}],[{}],{},None,store,lambda *a,**k:None,lambda s:None)
            self.assertEqual(json.loads(p.read_text('utf-8'))['marker'],'preserve-me')
            self.assertEqual(store.read(job['id'])['results'][0]['dimensions']['existence']['status'],'confirmed')
    def test_new_verification_attempt_does_not_overwrite_prior_evidence(self):
        from ref_app.efficient import verify
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);base=root/'out/references/R001';base.mkdir(parents=True)
            prior={'marker':'previous result'};(base/'result.json').write_text(json.dumps(prior))
            (base/'evidence.json').write_text('immutable previous evidence')
            row={'id':'R001','input':{'qwen':{'title':'Example title','authors':[],'doi':[],'arxiv':[],'urls':[]}}}
            with patch('ref_app.efficient.stages',return_value=[]):
                result=verify(row,root/'source',root/'out',{})
            self.assertEqual((base/'evidence.json').read_text(),'immutable previous evidence')
            self.assertEqual(json.loads(next((base/'history').glob('*.json')).read_text()),prior)
            self.assertEqual(json.loads((base/'result.json').read_text(encoding='utf-8'))['id'],'R001')
            self.assertEqual(len(list((base/'attempts').glob('*/result.json'))),1)

    def test_completed_job_can_continue_only_unresolved_or_failed_rows(self):
        from ref_app.continuation import retry_targets,resume_info
        def row(id,status,errors=[]):return {'id':id,'dimensions':{'existence':{'status':status},'execution':{'errors':errors}}}
        job={'state':'completed','verification_policy':'registry-first-v1','results':[
            row('R001','confirmed'),row('R002','unknown'),row('R003','confirmed',[{'error':'rate_limited'}])]}
        self.assertEqual(retry_targets(job),['R002'])
        self.assertTrue(resume_info(job)['resume_available'])
        self.assertFalse(resume_info({**job,'results':[row('R001','confirmed')]})['resume_available'])

    def test_launch_preserves_completed_results_before_requeue(self):
        from ref_app.__main__ import App
        with tempfile.TemporaryDirectory() as d:
            app=App(Path(d));job=app.store.create('example.txt',b'References')
            app.store.update(job['id'],state='completed',verification_policy='registry-first-v1',results=[{'id':'R001','dimensions':{'existence':{'status':'unknown'},'execution':{'errors':[]}}}])
            proc=type('Child',(),{'pid':123456,'poll':lambda s:None})()
            with patch('ref_app.__main__.subprocess.Popen',return_value=proc),patch('ref_app.__main__.threading.Thread.start'):
                app.launch(job['id'])
            current=app.store.read(job['id'])
            self.assertEqual(current['state'],'queued')
            self.assertEqual(current['resume_targets'],['R001'])
            old=json.loads((Path(d)/job['id']/'runs'/current['resume_run']/'job-before.json').read_text('utf-8'))
            self.assertEqual(old['state'],'completed');self.assertEqual(old['results'],current['results'])

    def test_cancelled_continuation_keeps_prior_unprocessed_results_visible(self):
        from ref_app.balanced import run_balanced,failed
        from ref_app.jobs import atomic
        with tempfile.TemporaryDirectory() as d:
            store=JobStore(Path(d));job=store.create('example.txt',b'two citations')
            folder=store.folder(job['id']);refs=[]
            for cid,title in [('R001','First title'),('R002','Second title')]:
                refs.append({'raw_text':title})
                old=failed({'id':cid,'input':{'raw_text':title,'qwen':{'title':title,'authors':[]}}},'prior query incomplete')
                old['marker']='keep-'+cid
                atomic(folder/'verification/references'/cid/'result.json',old)
            job['resume_targets']=['R001','R002']
            def verify(row,*args,**kw):
                if row['id']=='R002':raise KeyboardInterrupt('cancelled')
                return failed(row,'new failed query')
            def ordered(futures):return sorted(futures,key=lambda f:futures[f]['id'])
            with patch('ref_app.balanced.prepare',return_value={'title':'Test','authors':[]}), patch('ref_app.balanced.verify',side_effect=verify),patch('ref_app.balanced.concurrent.futures.as_completed',side_effect=ordered):
                with self.assertRaises(KeyboardInterrupt):
                    run_balanced(folder,job,refs,[{},{}],{},None,store,lambda *a,**k:None,lambda s:None)
            public=store.read(job['id'])['results']
            self.assertEqual([r['id'] for r in public],['R001','R002'])
            saved=json.loads((folder/'verification/result.json').read_text('utf-8'))['references']
            self.assertEqual(saved[1]['marker'],'keep-R002')

    def test_upgrade_continuation_records_new_code_without_replacing_original_manifest(self):
        from ref_app.continuation import record_manifest
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);old={'input_sha256':'same-input','code':{'x.py':'old'}}
            record_manifest(folder,old)
            current={'input_sha256':'same-input','code':{'x.py':'new'}}
            code,manifest=record_manifest(folder,current,'new-run')
            self.assertEqual(json.loads((folder/'manifest.json').read_text()),old)
            self.assertEqual(json.loads((folder/manifest).read_text())['code'],current['code'])
            self.assertEqual(str(code).replace('\\','/'),'runs/new-run/code')
            with self.assertRaises(ValueError):record_manifest(folder,{'input_sha256':'tampered'},'bad-run')

    def test_parser_resume_reuses_successful_transport_instead_of_recalling_services(self):
        from ref_app.local_parsers import parse_batch
        title='A study of reference parsing methods'
        refs=[{'raw_text':title,'pages':[1],'source_ids':['b1']}]
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            calls=[]
            def transport(url,body,headers):
                calls.append(url)
                if 'processCitationList' in url:return '<TEI><listBibl><biblStruct><analytic><title level="a">'+title+'</title></analytic><note type="raw_reference">'+title+'</note></biblStruct></listBibl></TEI>',200
                return json.dumps({'input':[title],'parsed_segments':[[['title',title]]],'csl':[{'title':title}],'version':'test'}),200
            first=parse_batch(refs,folder,{},lambda *a,**k:None,transport=transport)
            self.assertEqual(first[0]['status'],'ready_offline')
            second=parse_batch(refs,folder,{},lambda *a,**k:None,transport=transport)
            self.assertEqual(first,second)
            self.assertEqual(len(calls),2)


if __name__=='__main__':unittest.main()
