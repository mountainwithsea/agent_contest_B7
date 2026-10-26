import unittest
import tempfile
from pathlib import Path
from ref_app.local_parsers import local_url, parse_batch, downstream


class LocalParserTests(unittest.TestCase):
    def test_remote_or_redirect_target_rejected(self):
        for url in ('https://example.org', 'http://127.0.0.1@evil.com', 'http://localhost:8070?q=x'):
            with self.assertRaises(ValueError): local_url(url)
        self.assertEqual(local_url('http://127.0.0.1:8070/'), 'http://127.0.0.1:8070')

    def test_service_failure_saved_without_model_substitution(self):
        def failed(*args): raise OSError('service unavailable')
        with tempfile.TemporaryDirectory() as d:
            refs=[{'raw_text':'A. Smith. Example title. 2020.', 'pages':[1], 'source_ids':['p1']}]
            out=parse_batch(refs,Path(d),{},lambda *a,**k:None,transport=failed)
            self.assertEqual(out[0]['status'],'tool_failure')
            self.assertEqual(len(list(Path(d).glob('transport/**/*.json'))),2)

    def test_unknown_title_is_not_invented_for_legacy_contract(self):
        with self.assertRaises(ValueError):
            downstream({'status':'ready_offline','query':{'titles':[]}})

    def test_disagreed_soft_fields_are_not_promoted(self):
        q={'id':'R001','raw_text':'A title here. 2020.', 'status':'ready_offline',
           'query':{'titles':['A title here'],'identifiers':{'doi':[],'arxiv':[]}},
           'soft_fields':{'year':{'state':'pending','candidates':{'grobid':'2020','anystyle':'2021'}}}}
        self.assertIsNone(downstream(q)['year'])


if __name__=='__main__':unittest.main()
