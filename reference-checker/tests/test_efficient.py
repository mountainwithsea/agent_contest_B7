import unittest
import tempfile
from pathlib import Path
from ref_app.efficient import decide, mark_document, stages, source_urls,prepare

class EfficientTests(unittest.TestCase):
    def q(self, **kw):
        return dict(title='A reliable method for measuring reference quality', authors=[{'literal':'Alice Smith'}], year='2024', doi=[], arxiv=[], **kw)
    def e(self, **kw):
        data=dict(title='A reliable method for measuring reference quality', authors=['Alice Smith'], year='2024', identifiers={}, type='journal-article');data.update(kw)
        return {'id':'E001','kind':'metadata','usable':True,'data':data,'text':'','url':''}
    def test_exact_title_author_confirms(self):
        self.assertEqual(decide(self.q(),[self.e()])['existence']['status'],'confirmed')
    def test_same_title_wrong_author_not_confirmed_without_id(self):
        self.assertEqual(decide(self.q(),[self.e(authors=['Bob Jones'])])['existence']['status'],'candidate')
    def test_identifier_and_title_preserve_author_conflict(self):
        q=self.q();q['doi']=['10.1234/example']
        r=decide(q,[self.e(authors=['Bob Jones'],identifiers={'doi':'10.1234/example'})])
        self.assertEqual(r['existence']['status'],'confirmed')
        self.assertEqual(next(c for c in r['fields']['claims'] if c['field']=='authors')['status'],'conflict')
    def test_wrong_doi_does_not_confirm_other_title(self):
        q=self.q();q['doi']=['10.1234/example']
        r=decide(q,[self.e(title='Another unrelated article',identifiers={'doi':'10.1234/example'})])
        self.assertNotEqual(r['existence']['status'],'confirmed')
        self.assertTrue(r['fields']['identifier_issues'])
    def test_search_is_never_confirmation(self):
        e=self.e();e['kind']='search'
        self.assertNotEqual(decide(self.q(),[e])['existence']['status'],'confirmed')
    def test_dataset_cannot_stand_in_for_paper(self):
        self.assertNotEqual(decide(self.q(),[self.e(type='Dataset')])['existence']['status'],'confirmed')
    def test_year_difference_is_not_automatically_explained(self):
        r=decide(self.q(),[self.e(year='2025')])
        self.assertEqual(r['existence']['status'],'confirmed')
        self.assertEqual(next(c for c in r['fields']['claims'] if c['field']=='year')['status'],'conflict')
    def test_missing_authors_does_not_match_by_title_alone(self):
        q=self.q();q['authors']=[]
        self.assertNotEqual(decide(q,[self.e()])['existence']['status'],'confirmed')
    def test_empty_evidence_is_unknown_not_fake(self):
        self.assertEqual(decide(self.q(),[])['existence']['status'],'unknown')
    def test_routes_never_include_deepseek(self):
        for extra in ({},{'doi':['10.1/x']},{'arxiv':['2401.12345']},{'work_type':'book'},{'work_type':'webpage','urls':['https://example.org']}):
            q=self.q();q.update(extra)
            self.assertNotIn('deepseek',[p for group in stages(q) for p in group])
    def page(self,body,url='https://example.org/tools',final=None):
        q=self.q();q.update(title='Example documentation: Tool policies',urls=[url])
        e={'id':'E001','kind':'document','usable':True,'url':url,'request_id':'R001','data':{},'text':'Tool policies'}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'page.txt';p.write_text(body,encoding='utf8')
            mark_document(e,q,[{'id':'R001','url':url,'final_url':final or url,'raw_path':str(p)}])
        return q,e
    def test_original_page_title_confirms_without_team_byline(self):
        q,e=self.page('<title>Tool policies · Example</title>')
        self.assertEqual(decide(q,[e])['existence']['status'],'confirmed')
        self.assertEqual(next(c for c in decide(q,[e])['fields']['claims'] if c['field']=='authors')['status'],'unknown')
    def test_body_mention_does_not_confirm_page(self):
        q,e=self.page('<title>References to other works</title><p>Tool policies</p>')
        self.assertNotEqual(decide(q,[e])['existence']['status'],'confirmed')
    def test_redirect_to_home_does_not_confirm_page(self):
        q,e=self.page('<title>Tool policies</title>',final='https://example.org/')
        self.assertNotEqual(decide(q,[e])['existence']['status'],'confirmed')
    def test_numerical_title_difference_is_not_normalized_away(self):
        q=self.q();q['title']='A study of benchmark 2019'
        self.assertNotEqual(decide(q,[self.e(title='A study of benchmark 2024')])['existence']['status'],'confirmed')
    def test_transport_failure_is_separate_from_absence(self):
        r=decide(self.q(),[],[{'stage':'fetch','error':'HTTP 403'}])
        self.assertEqual(r['existence']['status'],'unknown')
        self.assertEqual(r['execution']['status'],'partial')
    def test_wrapped_host_and_path_are_restored_with_original_span(self):
        raw='Dataset. https://example. org/datasets/ MyDataset (accessed today).'
        urls=source_urls(raw)
        self.assertEqual(urls[0]['url'],'https://example.org/datasets/MyDataset')
        self.assertEqual(raw[urls[0]['start']:urls[0]['end']],urls[0]['quote'])
    def test_scheme_break_and_trailing_period(self):
        self.assertEqual(source_urls('Repository https:// github.com/example/project.')[0]['url'],'https://github.com/example/project')
    def test_does_not_join_next_prose_sentence(self):
        self.assertEqual(source_urls('https://example.org/article. Data available separately.')[0]['url'],'https://example.org/article')
    def test_wrong_explicit_identifier_survives_candidate_filter(self):
        import json
        from reference_identity.evidence import EvidenceStore,seed_evidence
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'requests').mkdir()
            (p/'raw.json').write_text(json.dumps({'message':{'DOI':'10.1234/example','title':['Completely unrelated title']}}))
            (p/'requests/r.json').write_text(json.dumps({'state':'ok','raw_response':'raw.json'}))
            q=self.q();q['doi']=['10.1234/example']
            candidate={'source':'crossref','title':'Completely unrelated title','authors':['Bob Jones'],'identifiers':{'doi':'10.1234/example'},'evidence_kind':'metadata','request_id':'r'}
            row={'input':{'qwen':q},'providers':[{'provider':'crossref','candidates':[candidate]}]}
            store=EvidenceStore(p)
            seed_evidence(row,p,store,include_input_identifiers=True)
            self.assertEqual(len(store.items),1)
            self.assertTrue(decide(q,store.items)['fields']['identifier_issues'])
    def test_explicit_code_link_not_promoted_to_work_url(self):
        raw='Alice Smith. Example research title. 2024. Code: https://example.org/code'
        qualified={'id':'R1','raw_text':raw,'status':'ready_offline','query':{'titles':['Example research title'],'identifiers':{'doi':[],'arxiv':[]}}}
        q=prepare(qualified)
        self.assertEqual(q['urls'],[])
        self.assertTrue(q['url_evidence'])

if __name__=='__main__':unittest.main()
