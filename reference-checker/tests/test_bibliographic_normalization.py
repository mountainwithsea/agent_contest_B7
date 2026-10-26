import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import json

from ref_app.qualification import qualify, resolve_model
from ref_app.efficient import prepare, stages, decide, verify
from reference_identity.assessment import name_matches


def qualified(raw, title, names):
    fields = {'title': title, 'authors': names}
    row = {'id': 'R001', 'raw_text': raw, 'tools': {
        'grobid': {'fields': fields}, 'anystyle': {'fields': fields}}}
    q = qualify(row)
    q['native_parsers'] = row['tools']
    return q


class NormalizationTests(unittest.TestCase):
    def test_hyphenated_surname_initials_and_particles(self):
        for a, b in [('Kamp-Becker I', 'I Kamp-Becker'),
                     ('Di Martino A', 'Adriana Di Martino'),
                     ('van der Meer J P', 'Jan Pieter van der Meer'),
                     ('Ho TK', 'Tin Kam Ho'), ('García A', 'A Garcia'),
                     ('Park H J','Hae-Jeong Park'), ('Yan C G','C-G Yan')]:
            with self.subTest(a=a): self.assertTrue(name_matches(a, b))
        for a, b in [('Kamp-Becker I', 'J Kamp-Becker'),
                     ('Di Martino A', 'A Martino'), ('Smith AB', 'Alice Smith'),
                     ('Jean Martin', 'Martin Jean'), ('Smith Alice', 'Bob Smith')]:
            with self.subTest(a=a): self.assertFalse(name_matches(a, b))

    def test_source_grounded_author_reversal_and_complete_coverage(self):
        raw = '[8] Kamp-Becker I, Albertowski K, Becker J, et al. A reliable diagnostic study[J]. A Journal, 2018.'
        q = prepare(qualified(raw, 'A reliable diagnostic study[J]', [
            {'literal': 'I Kamp-Becker', 'family': 'Kamp-Becker', 'given': 'I'},
            {'literal': 'K Albertowski', 'family': 'Albertowski', 'given': 'K'},
            {'literal': 'J Becker', 'family': 'Becker', 'given': 'J'}]))
        self.assertEqual(q['title'], 'A reliable diagnostic study')
        self.assertEqual([a['literal'] for a in q['authors']], ['Kamp-Becker I', 'Albertowski K', 'Becker J'])
        self.assertTrue(q['authors_truncated'])
        for a in q['authors']:
            s = a['source']; self.assertEqual(raw[s['start']:s['end']], s['quote'])

    def test_split_name_across_author_comma_is_not_accepted(self):
        raw = '[1] Di Martino A, Yan C G, Li Q. Brain architecture[J]. Journal, 2018.'
        q = prepare(qualified(raw, 'Brain architecture', [
            {'literal': 'Di Martino'}, {'literal': 'A Yan'},
            {'literal': 'C G Li'}, {'literal': 'Q'}]))
        self.assertEqual(q['authors'], [])

    def test_partial_author_list_does_not_silently_drop_explicit_authors(self):
        q = prepare(qualified('Alice Smith, Bob Jones. Example research title. 2024.',
                              'Example research title', [{'literal': 'Alice Smith'}]))
        self.assertEqual(q['authors'], [])

    def test_single_initial_is_not_a_separate_person(self):
        raw='Lord C, Le Couteur A. Example research title. 2024.'
        q=qualified(raw,'Example research title',[{'literal':'C Lord'},{'literal':'Le Couteur'},{'literal':'A'}])
        q['native_parsers']['anystyle']={'fields':{'authors':[{'literal':'C Lord'},{'literal':'A Le Couteur'}]}}
        self.assertEqual([a['literal'] for a in prepare(q)['authors']],['Lord C','Le Couteur A'])

    def test_two_chinese_authors_cannot_be_treated_as_one_comma_name(self):
        q=prepare(qualified('崔玲玲, 徐克. 一个真实的研究题目[J]. 期刊, 2020.',
                            '一个真实的研究题目',[{'literal':'崔玲玲, 徐克','kind':'literal'}]))
        self.assertEqual(q['authors'],[])

    def test_multiple_people_cannot_be_joined_into_one_author(self):
        for separator in (' & ', ' and ', ' / ', ', ', '、', ' + '):
            raw='John Smith'+separator+'Bob Jones. A reliable research title. 2024.'
            for literal in ('John Smith Bob Jones','John Smith'+separator+'Bob Jones'):
                q=prepare(qualified(raw,'A reliable research title',[{'literal':literal}]))
                with self.subTest(separator=separator,literal=literal):self.assertEqual(q['authors'],[])

    def test_native_given_family_can_ground_comma_order(self):
        q=prepare(qualified('Smith, Alice. A reliable research title. 2024.',
                            'A reliable research title',[{'literal':'Alice Smith','family':'Smith','given':'Alice'}]))
        self.assertEqual([a['literal'] for a in q['authors']],['Smith, Alice'])

    def test_missing_names_cannot_be_invented_by_parser(self):
        q = prepare(qualified('Smith A. Example research title. 2024.',
                              'Example research title', [{'literal': 'Alice Smith'}]))
        self.assertEqual(q['authors'], [])

    def test_terminal_type_marker_does_not_create_title_disagreement(self):
        row = {'id': 'R1', 'raw_text': 'Smith A. Actual title (SNAP)[EB/OL]. Journal. 2024.',
               'tools': {'grobid': {'fields': {'title': 'Actual title (SNAP)[EB/OL]'}},
                         'anystyle': {'fields': {'title': 'Actual title (SNAP)'}}}}
        q = qualify(row)
        self.assertEqual(q['query']['titles'], ['Actual title (SNAP)'])
        self.assertEqual(q['status'], 'ready_offline')
        self.assertTrue(q['title_evidence'][0]['transforms'])
        self.assertEqual(row['tools']['grobid']['fields']['title'], 'Actual title (SNAP)[EB/OL]')

    def test_incomplete_parser_marker_requires_complete_marker_in_source(self):
        q = qualified('Smith A. Actual paper title[C]. Proceedings, 2024.', 'Actual paper title[C', [])
        self.assertEqual(q['query']['titles'], ['Actual paper title'])
        q = qualified('Smith A. Actual paper title[C. Proceedings, 2024.', 'Actual paper title[C', [])
        self.assertEqual(q['query']['titles'], ['Actual paper title[C'])

    def test_actual_bracket_title_and_subtitle_are_preserved(self):
        for title in ('The role of [C] in programming', 'Learning (SNAP): a survey'):
            q = qualified('Smith A. ' + title + '. Journal, 2024.', title, [])
            self.assertEqual(q['query']['titles'], [title])
        q=qualified('Smith A. A study of [C]', 'A study of [C]', [])
        self.assertEqual(q['query']['titles'], ['A study of [C]'])

    def test_model_title_also_gets_source_supported_marker_separation(self):
        q = qualified('Smith A. Some complete title[J]. Journal, 2024.', 'Some complete title[J]', [])
        r = resolve_model(q, {'title': 'Some complete title[J]'})
        self.assertEqual(r['query']['titles'], ['Some complete title'])

    def test_full_parenthetical_title_before_type_marker_wins_over_truncated_parser(self):
        raw='Smith A. A complete research title (SNAP)[J]. Journal, 2024.'
        q=qualify({'id':'R001','raw_text':raw,'tools':{
            'grobid':{'fields':{'title':'A complete research title (SNAP)[J]'}},
            'anystyle':{'fields':{'title':'A complete research title'}}}})
        self.assertEqual(q['query']['titles'],['A complete research title (SNAP)'])
        self.assertEqual(q['status'],'ready_offline')

    def test_parenthetical_disagreement_without_type_boundary_stays_ambiguous(self):
        q=qualify({'id':'R001','raw_text':'Smith A. Research title (2020). Journal, 2024.', 'tools':{
            'grobid':{'fields':{'title':'Research title (2020)'}},
            'anystyle':{'fields':{'title':'Research title'}}}})
        self.assertEqual(q['status'],'needs_llm')


class CrossrefPriorityTests(unittest.TestCase):
    def test_correct_third_returned_record_is_not_discarded_before_author_check(self):
        from reference_identity.evidence import EvidenceStore,seed_evidence
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'requests').mkdir()
            (root/'raw.json').write_text(json.dumps({'message':{'items':[]}}))
            (root/'requests/r.json').write_text(json.dumps({'state':'ok','raw_response':'raw.json'}))
            q={'title':'An exact paper title','authors':[{'literal':'Alice Smith'}]}
            candidates=[{'source':'crossref','title':q['title'],'authors':[a],'url':'https://doi.org/10.1234/'+str(i), 'request_id':'r','evidence_kind':'metadata'} for i,a in enumerate(['Bob Jones','Charles Green','Alice Smith'])]
            row={'input':{'qwen':q},'providers':[{'provider':'crossref','candidates':candidates}]}
            store=EvidenceStore(root/'evidence');seed_evidence(row,root,store)
            self.assertEqual(decide(q,store.items)['existence']['status'],'confirmed')

    def test_crossref_alone_is_first_stage(self):
        for q in ({}, {'doi': ['10.1000/test']}, {'arxiv': ['2501.12345']}, {'work_type': 'book'}):
            self.assertEqual(stages(q)[0], ['crossref'])

    def test_crossref_confirmation_stops_all_supplementary_queries(self):
        evidence = {'id': 'E001', 'kind': 'metadata', 'source': 'crossref', 'usable': True,
                    'data': {'title': 'Example research title', 'authors': ['I Kamp-Becker'], 'identifiers': {}},
                    'text': '', 'url': '', 'artifacts': []}
        q = {'title': 'Example research title', 'authors': [{'literal': 'Kamp-Becker I'}], 'doi': [], 'arxiv': []}
        row = {'id': 'R001', 'input': {'qwen': q}}
        calls = []
        def retrieve(r, source, values, **kw):
            calls.append(kw['selected']); r.update(providers=[], requests=[])
        def seed(row, source, store, **kw): store.items.append(evidence)
        with tempfile.TemporaryDirectory() as tmp, patch('ref_app.retrieval.retrieve_row', side_effect=retrieve), patch('ref_app.efficient.seed_evidence', side_effect=seed):
            result = verify(row, Path(tmp)/'source', Path(tmp)/'out', {})
        self.assertEqual(result['dimensions']['existence']['status'], 'confirmed')
        self.assertEqual(calls, [['crossref']])
        self.assertEqual(result['model_calls'], [])

    def test_confirmed_crossref_does_not_fetch_even_original_url(self):
        q={'title':'An exact title','authors':[{'literal':'A Smith'}],'urls':['https://example.org/paper']}
        evidence={'id':'E001','kind':'metadata','source':'crossref','usable':True,'data':{'title':q['title'],'authors':['Alice Smith']},'text':'','url':'','artifacts':[]}
        def retrieve(row,*a,**kw):row.update(providers=[],requests=[])
        def seed(row,source,store,**kw):store.items.append(evidence)
        with tempfile.TemporaryDirectory() as d,patch('ref_app.retrieval.retrieve_row',side_effect=retrieve),patch('ref_app.efficient.seed_evidence',side_effect=seed),patch('ref_app.efficient.Tools.fetch') as fetch:
            verify({'id':'R001','input':{'qwen':q}},Path(d)/'source',Path(d)/'out',{})
        fetch.assert_not_called()

    def test_original_url_is_tried_after_inconclusive_crossref_then_stops(self):
        q={'title':'An exact title','authors':[],'urls':['https://example.org/paper']}
        order=[]
        def retrieve(row,*a,**kw):
            order.append(kw['selected']);row.update(providers=[],requests=[])
        def fetch(tool,url):
            order.append('fetch')
            tool.store.items.append({'id':'E001','kind':'document','source':'page','usable':True,'url':url,
                'data':{'title':q['title'],'input_url_title_anchor':True},'text':'','artifacts':[]})
        with tempfile.TemporaryDirectory() as d,patch('ref_app.retrieval.retrieve_row',side_effect=retrieve),patch('ref_app.efficient.seed_evidence'),patch('ref_app.efficient.Tools.fetch',fetch):
            result=verify({'id':'R001','input':{'qwen':q}},Path(d)/'source',Path(d)/'out',{})
        self.assertEqual(order,[['crossref'],'fetch'])
        self.assertEqual(result['dimensions']['existence']['status'],'confirmed')

    def test_confirmation_survives_unavailable_auxiliary_source(self):
        q = {'title': 'An exact paper title', 'authors': [{'literal': 'A Smith'}]}
        e = {'id': 'E001', 'kind': 'metadata', 'usable': True, 'data': {'title': q['title'], 'authors': ['Alice Smith']}, 'text': ''}
        d = decide(q, [e], [{'stage': 'openalex', 'error': 'rate_limited'}])
        self.assertEqual(d['existence']['status'], 'confirmed')
        self.assertEqual(d['execution']['status'], 'partial')


if __name__ == '__main__': unittest.main()
