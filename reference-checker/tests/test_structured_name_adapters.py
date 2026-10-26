import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from ref_app.parser_adapters import grobid_rows, any_rows
from ref_app.local_parsers import parse_batch


class AdapterTests(unittest.TestCase):
    def test_source_validated_cached_model_title_does_not_replace_new_parser_fields(self):
        from ref_app.local_parsers import run_local
        from ref_app.qualification import qualify
        raw='Smith A. A complete study title[J]. Journal, 2020.'
        draft=qualify({'id':'R001','raw_text':raw,'tools':{}})
        draft['native_parsers']={'grobid':{'fields':{'authors':[{'literal':'A Smith','given':'A','family':'Smith'}]},'evidence':'new'}}
        old={**draft,'status':'ready_llm','native_parsers':{},'model_output':{'title':'A complete study title[J]'},'model_trace':'model/old'}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'result.json').write_text(json.dumps([old]))
            with patch('ref_app.local_parsers.parse_batch',return_value=[draft]),patch('ref_app.local_parsers.report',return_value={}),patch('reference_identity.client.Client.ask',side_effect=AssertionError('Unexpected paid model request')):
                rows,_=run_local([{'raw_text':raw}],root,{},lambda *a,**k:None,None)
            self.assertEqual(rows[0]['query']['titles'],['A complete study title'])
            self.assertEqual(rows[0]['native_parsers']['grobid']['evidence'],'new')
            self.assertEqual(rows[0]['model_trace'],'model/old')

    def test_grobid_retains_given_and_family(self):
        record={'ids':['R001'],'input':[{'raw_text':'source'}], 'raw_response':
                '<TEI><biblStruct><analytic><author><persName><forename>I</forename><surname>Kamp-Becker</surname></persName></author></analytic><note type="raw_reference">source</note></biblStruct></TEI>'}
        name=grobid_rows(record)[0]['authors'][0]
        self.assertEqual(name['given'],'I');self.assertEqual(name['family'],'Kamp-Becker')

    def test_anystyle_retains_surname_particles(self):
        record={'ids':['R001'],'input':[{'raw_text':'source'}], 'parsed_segments':[[['title','source']]],
                'raw_export':json.dumps([{'author':[{'given':'J','family':'Meer','non-dropping-particle':'van der'}]}])}
        name=any_rows(record)[0]['authors'][0]
        self.assertEqual(name['family'],'Meer');self.assertEqual(name['given'],'J')
        self.assertEqual(name['non-dropping-particle'],'van der')

    def test_native_cache_can_be_readapted_without_network_or_overwriting_raw(self):
        refs=[{'raw_text':'An actual research title'}]
        inputs=[{'id':'R001',**refs[0]}]
        g={'ok':True,'tool':'grobid','ids':['R001'],'input':inputs,'endpoint':'http://127.0.0.1:8070/api/processCitationList',
           'raw_response':'<TEI><biblStruct><analytic><title>An actual research title</title><author><persName><forename>A</forename><surname>Smith</surname></persName></author></analytic><note type="raw_reference">An actual research title</note></biblStruct></TEI>',
           'normalized':[{'legacy':'shape'}]}
        a={'ok':True,'tool':'anystyle','ids':['R001'],'input':inputs,'endpoint':'http://127.0.0.1:8071/parse',
           'parsed_segments':[[['title',refs[0]['raw_text']]]], 'raw_export':json.dumps([{'title':refs[0]['raw_text']}]),'normalized':[{'legacy':'shape'}]}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            paths=[]
            for tool,r in [('grobid',g),('anystyle',a)]:
                p=root/'transport'/tool/'001-old.json';p.parent.mkdir(parents=True);p.write_text(json.dumps(r));paths.append(p)
            before=[p.read_bytes() for p in paths]
            def fail(*args):self.fail('Cached native response must not trigger HTTP')
            out=parse_batch(refs,root,{},lambda *a,**k:None,transport=fail)
            self.assertEqual(out[0]['status'],'ready_offline')
            self.assertEqual([p.read_bytes() for p in paths],before)
            self.assertEqual(out[0]['native_parsers']['grobid']['fields']['authors'][0]['family'],'Smith')
            self.assertIn('derivation',out[0]['native_parsers']['grobid'])


if __name__=='__main__':unittest.main()
