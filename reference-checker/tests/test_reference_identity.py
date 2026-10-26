import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request
from reference_identity.evidence import classify_content, title_score, author_coverage
from reference_identity.engine import validate_verdict, apply_guards
from reference_identity.tools import public_url
from reference_identity.tools import PublicRedirect


class IdentityTests(unittest.TestCase):
    def ev(self, kind='metadata', usable=True):
        return {'id': 'E1', 'kind': kind, 'usable': usable, 'text': 'Title: Sample Study\nAuthors: Alice Smith\nYear: 2020', 'data': {'title': 'Sample Study', 'authors': ['Alice Smith'], 'year': '2020'}}

    def verdict(self):
        return {'status': 'confirmed', 'reason': '题名作者对应', 'matched_title': 'Sample Study', 'evidence_ids': ['E1'], 'claims': [{'field': 'title', 'status': 'match', 'explanation': '相同', 'quotes': [{'evidence_id': 'E1', 'quote': 'Sample Study'}]}, {'field': 'authors', 'status': 'match', 'explanation': '相同', 'quotes': [{'evidence_id': 'E1', 'quote': 'Alice Smith'}]}, {'field':'year','status':'unknown','explanation':'待核','quotes':[]}, {'field':'identifiers','status':'unknown','explanation':'无编号','quotes':[]}], 'unresolved': []}

    def test_challenge_not_evidence(self):
        for body in ['Client Challenge\nEnable JavaScript', '正在确认你是不是机器人！', 'Making sure you are not a bot']:
            self.assertEqual(classify_content(body), 'challenge')

    def test_metadata_mention_captcha_not_blocked(self):
        self.assertEqual(classify_content('A Study of CAPTCHA Recognition by Alice. ' * 20), 'usable')

    def test_normalize_line_wrap(self):
        self.assertEqual(title_score('Hallucina- tion in Scientific Writing', 'Hallucination in Scientific Writing'), 1)

    def test_different_authors(self):
        self.assertEqual(author_coverage(['Alice Smith'], ['Bob Jones'])['coverage'], 0)
        self.assertEqual(author_coverage(['Alice Smith'], ['A. Smith'])['coverage'], 1)

    def test_false_quote_rejected(self):
        v=self.verdict();v['claims'][0]['quotes'][0]['quote']='A completely different study'
        with self.assertRaises(ValueError):validate_verdict(v,[self.ev()])

    def test_valid_quotes(self):
        validate_verdict(self.verdict(),[self.ev()])

    def test_null_claim_and_quote_are_validation_errors(self):
        v=self.verdict();v['claims']=[None]
        with self.assertRaises(ValueError):validate_verdict(v,[self.ev()])
        v=self.verdict();v['claims'][0]['quotes']=[None]
        with self.assertRaises(ValueError):validate_verdict(v,[self.ev()])

    def test_missing_cached_response_falls_back_and_logs(self):
        import json
        from reference_identity.evidence import EvidenceStore
        from reference_identity.tools import Tools
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'old'/'requests';old.mkdir(parents=True)
            (old/'R001.json').write_text(json.dumps({'url':'https://example.org','method':'GET','state':'ok','raw_path':str(root/'missing'),'sha256':'bad'}))
            tool=Tools(EvidenceStore(root/'new'),{},replay=root/'old')
            with patch('reference_identity.tools.public_url',return_value=False):
                log,body=tool.request('https://example.org','test')
            self.assertTrue(log['cache_errors'])
            self.assertEqual(log['state'],'transport_error')
            self.assertTrue(Path(log['raw_path']).exists())

    def test_search_alone_cannot_confirm(self):
        v=apply_guards(self.verdict(),[self.ev('search')],[],{'title':'Sample Study','authors':[{'literal':'Alice Smith'}]})
        self.assertEqual(v['status'],'uncertain')

    def test_blocked_cannot_confirm(self):
        with self.assertRaises(ValueError):validate_verdict(self.verdict(),[self.ev(usable=False)])

    def test_explicit_identifier_conflict(self):
        v=apply_guards(self.verdict(),[self.ev()],[{'state':'mismatch','origin':'input','doi':'10.1/wrong'}],{'title':'Sample Study','authors':[{'literal':'Alice Smith'}]})
        self.assertEqual(v['status'],'conflict')

    def test_wrong_candidate_doi_excluded_not_original_error(self):
        v=apply_guards(self.verdict(),[self.ev()],[{'state':'mismatch','origin':'candidate','doi':'10.1/wrong'}],{'title':'Sample Study','authors':[{'literal':'Alice Smith'}]})
        self.assertEqual(v['status'],'confirmed')
        self.assertTrue(v['identifier_issues'])

    def test_author_mismatch_not_title_only(self):
        v=apply_guards(self.verdict(),[self.ev()],[],{'title':'Sample Study','authors':[{'literal':'Bob Jones'}]})
        self.assertNotEqual(v['status'],'confirmed')

    def test_explained_does_not_bypass_author_check(self):
        v=self.verdict();v['claims'][1]['status']='explained'
        value=apply_guards(v,[self.ev()],[],{'title':'Sample Study','authors':[{'literal':'Bob Jones'}]})
        self.assertNotEqual(value['status'],'confirmed')

    def test_document_does_not_bypass_author_check(self):
        value=apply_guards(self.verdict(),[self.ev('document')],[],{'title':'Sample Study','authors':[{'literal':'Bob Jones'}]})
        self.assertNotEqual(value['status'],'confirmed')

    def test_unrelated_title_cannot_confirm(self):
        value=apply_guards(self.verdict(),[self.ev()],[],{'title':'Unrelated Quantum Physics','authors':[{'literal':'Alice Smith'}]})
        self.assertNotEqual(value['status'],'confirmed')

    def test_secret_not_forwarded_on_redirect(self):
        req=Request('https://api.deepseek.com/v1/tools/search',headers={'Authorization':'Bearer fake-test-key'})
        with patch('reference_identity.tools.public_url',return_value=True):
            with self.assertRaises(ValueError):PublicRedirect().redirect_request(req,None,302,'Found',{},'https://other.example/capture')

    def test_proxy_dns_explicit_option(self):
        from reference_identity import tools
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('198.18.2.69',443))]):
            self.assertFalse(public_url('https://api.crossref.org/works'))
            with patch.object(tools,'FAKE_DNS_NETWORK',__import__('ipaddress').ip_network('198.18.0.0/15'),create=True):
                self.assertTrue(public_url('https://api.crossref.org/works'))
                self.assertFalse(public_url('https://198.18.2.69/works'))

    def test_arxiv_error_not_another_work(self):
        from reference_identity.evidence import EvidenceStore
        from reference_identity.tools import Tools
        with tempfile.TemporaryDirectory() as tmp:
            store=EvidenceStore(Path(tmp));tools=Tools(store,{})
            tools.input_identifiers.add('2401.11111')
            xml=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/api/errors#bad_id</id><title>Error</title></entry></feed>'
            with patch.object(tools,'request',return_value=({'id':'R001','state':'ok','purpose':'arxiv_lookup','url':'https://export.arxiv.org/api/query','raw_path':str(Path(tmp)/'raw.txt')},xml)):
                tools.arxiv('2401.11111','Sample Study','input')
            self.assertEqual(tools.identifiers[0]['state'],'unresolved')
            self.assertFalse(any(e['usable'] for e in store.items))

    def test_required_identity_fields(self):
        v=self.verdict();v['claims']=v['claims'][:2]
        with self.assertRaises(ValueError):validate_verdict(v,[self.ev()])

    def test_public_url(self):
        for url in ['file:///etc/passwd','http://127.0.0.1/x','http://localhost/x','http://192.168.1.2','https://u:p@example.com']:
            self.assertFalse(public_url(url,resolve=False))
        self.assertTrue(public_url('https://doi.org/10.123/x',resolve=False))

if __name__=='__main__':unittest.main()
