import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from reference_identity.assessment import assess, name_matches, recovery_needed


class DimensionTests(unittest.TestCase):
    def inputs(self):
        return {'title':'A study of river ecology','authors':[{'literal':'Alice B Smith'},{'literal':'R Jones'}],'year':'2021'}

    def evidence(self):
        return [{'id':'E1','kind':'metadata','usable':True,'text':'A study of river ecology Alice B Smith R Jones 2021',
                 'data':{'title':'A study of river ecology','authors':['Smith AB','Jones R'],'year':'2021'}}]

    def test_initials_and_order(self):
        self.assertTrue(name_matches('Alice B Smith','Smith AB'))
        self.assertTrue(name_matches('R Jones','Jones R.'))
        self.assertFalse(name_matches('Alice B Smith','Bob Smith'))
        self.assertFalse(name_matches('Alice B Smith','Alice C Smith'))
        self.assertFalse(name_matches('ANN SMITH','Alice Smith'))
        self.assertFalse(name_matches('LEE SMITH','Lucy Smith'))
        self.assertFalse(name_matches('LI Wang','Lucy Wang'))
        self.assertFalse(name_matches('Smith AB','Alice Smith'))

    def test_execution_failure_keeps_identity(self):
        result=assess(self.inputs(),self.evidence(),[],None,[{'stage':'review','error':'invalid JSON'}])
        self.assertEqual(result['existence']['status'],'confirmed')
        self.assertEqual(result['execution']['status'],'partial')
        self.assertEqual(result['fields']['status'],'unavailable')

    def test_year_conflict_separate_from_identity(self):
        verdict={'status':'probable','claims':[{'field':'year','status':'conflict','explanation':'different editions','quotes':[]}],'unresolved':['version uncertain']}
        result=assess(self.inputs(),self.evidence(),[],verdict,[])
        self.assertEqual(result['existence']['status'],'confirmed')
        self.assertEqual(result['fields']['status'],'issues')

    def test_series_number_difference_is_identity_gap(self):
        q=self.inputs();q['title']='A comprehensive survey of river ecology: Part II'
        ev=self.evidence();ev[0]['data']['title']='A comprehensive survey of river ecology: Part I'
        result=assess(q,ev,[],None,[])
        self.assertNotEqual(result['existence']['status'],'confirmed')

    def test_reviewed_identity_conflict_cannot_be_overridden(self):
        v={'status':'conflict','claims':[{'field':'authors','status':'conflict','quotes':[],'explanation':'different person'}]}
        result=assess(self.inputs(),self.evidence(),[],v,[],reviewed=True)
        self.assertNotEqual(result['existence']['status'],'confirmed')

    def test_fuzzy_title_without_review_is_only_candidate(self):
        ev=self.evidence();ev[0]['data']['title']='A study of river eclogy'
        self.assertNotEqual(assess(self.inputs(),ev,[],None,[])['existence']['status'],'confirmed')

    def test_search_and_wrong_authors_cannot_confirm(self):
        for kind,authors in [('search',['Smith AB','Jones R']),('metadata',['Bob Smith','Someone Else'])]:
            ev=self.evidence();ev[0]['kind']=kind;ev[0]['data']['authors']=authors
            result=assess(self.inputs(),ev,[],None,[])
            self.assertNotEqual(result['existence']['status'],'confirmed')
            self.assertTrue(recovery_needed(result))

    def test_wrong_input_doi_separate_and_not_identity_anchor(self):
        checks=[{'origin':'input','state':'mismatch','evidence_ids':['E1']}]
        result=assess(self.inputs(),self.evidence(),checks,None,[])
        self.assertNotEqual(result['existence']['status'],'confirmed')
        self.assertEqual(result['fields']['status'],'issues')

    def test_one_record_cannot_match_two_authors(self):
        q=self.inputs();q['authors']=[{'literal':'Alice Smith'},{'literal':'A Smith'}]
        ev=self.evidence();ev[0]['data']['authors']=['Alice Smith']
        self.assertNotEqual(assess(q,ev,[],None,[])['existence']['status'],'confirmed')

    def test_guard_gap_returns_to_tools_and_preserves_review_failure(self):
        from reference_identity.engine import run_one
        from reference_identity.client import ModelConfig
        stages=[]
        fixture=self
        class FakeClient:
            def __init__(self,*args):self.calls=[]
            def ask(self,stage,*args,**kwargs):
                stages.append(stage)
                if stage.startswith('recovery-plan'):
                    return {'assessment':'Need byline','actions':[{'tool':'fetch','argument':'https://example.org/work','reason':'byline'}]}
                if stage.startswith('plan'):return {'assessment':'Enough','actions':[]}
                if stage.endswith('review'):raise RuntimeError('invalid JSON')
                return {'status':'uncertain','reason':'Missing authors','matched_title':'','evidence_ids':[],'claims':[],'unresolved':[]}
        class FakeTools:
            def __init__(self,store,*args,**kwargs):
                self.store=store;self.logs=[];self.identifiers=[];self.allowed=set();self.done=set();self.limit=12
            def execute(self,action,title):
                self.store.items.extend(fixture.evidence());return {'state':'completed','request_ids':[]}
            def redact(self,text):return text
        with tempfile.TemporaryDirectory() as tmp,patch('reference_identity.engine.ReplayClient',FakeClient),patch('reference_identity.engine.Tools',FakeTools),patch('reference_identity.engine.seed_evidence'):
            result=run_one({'id':'synthetic','input':{'qwen':self.inputs()}},Path(tmp),Path(tmp),ModelConfig('https://example.org','test','secret'),{})
        self.assertIn('recovery-plan-1',stages)
        self.assertEqual(result['dimensions']['existence']['status'],'confirmed')
        self.assertEqual(result['dimensions']['execution']['status'],'partial')
        self.assertTrue(result['dimensions']['execution']['errors'])

if __name__=='__main__':unittest.main()
