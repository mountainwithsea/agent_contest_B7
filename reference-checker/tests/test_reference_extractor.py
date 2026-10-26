import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reference_extractor.config import Config
from reference_extractor.schema import validate_partition, validate_pages, validate_ocr, normalize_ocr
from reference_extractor.api import Client, decode_sse
from reference_extractor.readers import word_blocks, read_document
from reference_extractor.pipeline import order_entries
from reference_extractor.pipeline import extract


class ContractTests(unittest.TestCase):
    def test_selection_conflicts_include_second_list_outside_chosen_rule_region(self):
        from reference_extractor.pipeline import selection_conflicts
        from reference_extractor.rules import analyze
        pages=[{'page':1,'blocks':[{'id':'a','page':1,'bbox':None,'text':'References'},
            {'id':'b','page':1,'bbox':None,'text':'[1] Alice Smith. Study. Journal of AI, 2020.'},
            {'id':'c','page':1,'bbox':None,'text':'[2] Bo Wang. Study. Journal of AI, 2021.'},
            {'id':'d','page':1,'bbox':None,'text':'Appendix A'}]},
            {'page':2,'blocks':[{'id':'e','page':2,'bbox':None,'text':'References'},
            {'id':'f','page':2,'bbox':None,'text':'[1] Jane Doe. Study. Journal of AI, 2022.'},
            {'id':'g','page':2,'bbox':None,'text':'[2] Chen Li. Study. Journal of AI, 2023.'}]}]
        proposal=analyze({'pages':pages})
        self.assertTrue(selection_conflicts(pages,proposal,[1]))

    def test_recovered_table_labels_are_not_bibliography_success(self):
        from reference_extractor.pipeline import audit_group_fragments
        blocks=[{'id':'a','text':'Reasoning','page':1},
                {'id':'b','text':'Alice Smith. A substantial study. Journal of AI, 2023.','page':1}]
        value,flags=audit_group_fragments({'references':[{'source_ids':['a']},{'source_ids':['b']}],
                                        'excluded':[],'uncertain':[]},blocks)
        self.assertTrue(flags);self.assertEqual(len(value['references']),1)
        self.assertEqual(value['uncertain'][0]['source_ids'],['a'])

    def test_page_selection_conflict_detects_rule_references_on_omitted_page(self):
        from reference_extractor.pipeline import selection_conflicts
        pages=[{'page':2,'blocks':[{'id':'a','page':2,'text':'Alice Smith. A substantial study. Journal of AI, 2021.'}]}]
        proposal={'partition':{'references':[{'source_ids':['a']}]}}
        self.assertTrue(selection_conflicts(pages,proposal,[1]))

    def test_article_self_citation_metadata_is_not_clean_bibliography_success(self):
        from reference_extractor.pipeline import audit_group_fragments
        blocks=[{'id':'a','text':'Citation: Editors. A correction. Journal of AI, 2023.','page':1}]
        value,flags=audit_group_fragments({'references':[{'source_ids':['a']}],'excluded':[],'uncertain':[]},blocks)
        self.assertTrue(flags);self.assertEqual(len(value['uncertain']),1)
        self.assertEqual(value['references'],[])

    def test_model_scope_keeps_all_pages_after_supported_heading(self):
        from reference_extractor.pipeline import model_page_scope
        pages=[{'page':i,'blocks':[{'id':f'p{i}-b1','page':i,'bbox':None,'text':'References' if i==60 else 'Literal text'}]} for i in range(1,76)]
        proposal={'boundaries':{'first_source_id':'p61-b1'},'checks':{'outside_bibliographic_markers':[]}}
        chosen,evidence=model_page_scope(pages,proposal)
        self.assertEqual([p['page'] for p in chosen],list(range(60,76)))
        self.assertEqual(evidence['omitted_prefix_pages'],list(range(1,60)))
        proposal['checks']['outside_bibliographic_markers']=['p2-b1']
        self.assertEqual(len(model_page_scope(pages,proposal)[0]),75)

    def test_model_scope_keeps_unnumbered_bibliography_in_prefix(self):
        from reference_extractor.pipeline import model_page_scope
        pages=[{'page':1,'blocks':[{'id':'p1-b1','page':1,'bbox':None,'text':'Alice Smith. First chapter source. Journal of AI, 2020.'}]},
               {'page':2,'blocks':[{'id':'p2-b1','page':2,'bbox':None,'text':'References'},
                                   {'id':'p2-b2','page':2,'bbox':None,'text':'[1] Bo Wang. Second chapter source. Journal of AI, 2021.'}]}]
        proposal={'boundaries':{'first_source_id':'p2-b2'},'checks':{'outside_bibliographic_markers':[]}}
        self.assertEqual(len(model_page_scope(pages,proposal)[0]),2)

    def test_long_pdf_selection_batches_instead_of_rejecting_full_text(self):
        from reference_extractor.pipeline import select_pdf_pages
        pages=[{'page':i,'blocks':[{'text':'Body text '*10000}]} for i in range(1,4)]
        seen=[]
        def ask(stage,prompt,validator,**kw):
            seen.append(stage)
            # First batches contain no bibliography, which is a valid local answer.
            v={'reference_pages':[3] if '"page": 3' in prompt else [],'reason':'literal page evidence','uncertain':False}
            validator(v);return v
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            r=select_pdf_pages(pages,SimpleNamespace(ask=ask),Path(tmp))
            self.assertEqual(r['reference_pages'],[3]);self.assertGreater(len(seen),1)
            self.assertTrue((Path(tmp)/'page-selection-batches.json').is_file())

    def test_incomplete_author_list_pair_is_reviewed_instead_of_clean_success(self):
        from reference_extractor.pipeline import audit_group_fragments
        blocks=[{'id':'a','text':'Alice Smith, Bo Wang, Igor','page':1},
                {'id':'b','text':'Babuschkin, and Jane Doe. 2023. A study. ArXiv preprint.','page':2}]
        partition={'references':[{'source_ids':['a']},{'source_ids':['b']}],'excluded':[],'uncertain':[]}
        value,flags=audit_group_fragments(partition,blocks)
        self.assertTrue(flags);self.assertEqual(value['references'],[])
        self.assertEqual(value['uncertain'][0]['source_ids'],['a','b'])
        validate_partition(value,blocks,allow_empty=True)

    def test_pdf_over_40_pages_is_read_with_physical_page_ids(self):
        from unittest.mock import MagicMock
        page = MagicMock()
        page.width, page.height = 600, 800
        page.extract_words.return_value = [dict(text='References', x0=50, x1=150, top=50, bottom=60)]
        pdf = MagicMock()
        pdf.pages = [page] * 75
        pdf.__enter__.return_value = pdf
        with tempfile.TemporaryDirectory() as tmp, patch('pdfplumber.open', return_value=pdf):
            result = read_document(Path(tmp) / 'long.pdf', Path(tmp) / 'pages')
        self.assertEqual(len(result['pages']), 75)
        self.assertEqual(result['pages'][-1]['blocks'][0]['id'], 'p75-b1')

    def setUp(self):
        self.blocks = [{'id': 'p1-b1', 'text': 'References'},
                       {'id': 'p1-b2', 'text': 'A. Author. A title.'}]
        self.good = {'references': [{'source_ids': ['p1-b2']}],
                     'excluded': [{'source_ids': ['p1-b1'], 'reason': 'heading'}],
                     'uncertain': []}

    def test_valid_partition(self):
        validate_partition(self.good, self.blocks)

    def test_missing_source_is_rejected(self):
        self.good['excluded'] = []
        with self.assertRaises(ValueError):
            validate_partition(self.good, self.blocks)

    def test_duplicate_source_is_rejected(self):
        self.good['references'][0]['source_ids'].append('p1-b1')
        with self.assertRaises(ValueError):
            validate_partition(self.good, self.blocks)

    def test_unknown_source_is_rejected(self):
        self.good['references'][0]['source_ids'].append('invented')
        with self.assertRaises(ValueError):
            validate_partition(self.good, self.blocks)

    def test_string_reference_is_rejected(self):
        self.good['references'] = ['A title']
        with self.assertRaises(ValueError):
            validate_partition(self.good, self.blocks)

    def test_empty_reference_is_rejected(self):
        self.good['references'][0]['source_ids'] = []
        with self.assertRaises(ValueError):
            validate_partition(self.good, self.blocks)

    def test_all_noise_is_not_silently_success(self):
        self.good['references'] = []
        self.good['excluded'][0]['source_ids'].append('p1-b2')
        with self.assertRaises(ValueError):
            validate_partition(self.good, self.blocks)

    def test_exclusion_audit_can_confirm_all_noise(self):
        value = {'references': [], 'excluded': [{'source_ids': ['b1'], 'reason': 'body'}], 'uncertain': []}
        validate_partition(value, [{'id': 'b1', 'text': 'body'}], allow_empty=True)

    def test_page_number_must_be_in_input(self):
        with self.assertRaises(ValueError):
            validate_pages({'reference_pages': [3], 'reason': 'x'}, [1, 2])

    def test_bool_is_not_page_number(self):
        with self.assertRaises(ValueError):
            validate_pages({'reference_pages': [True], 'reason': 'x'}, [1])

    def test_ocr_coordinates_are_valid(self):
        with self.assertRaises(ValueError):
            validate_ocr({'blocks': [{'text': 'x', 'bbox': [900, 1, 20, 2]}]})

    def test_native_ocr_boxes_are_adapted_without_rewriting_text(self):
        value = [{'text': 'A literal ref-', 'bbox_2d': [10, 20, 400, 50]}]
        normalized = normalize_ocr(value)
        self.assertEqual(normalized['blocks'][0]['text'], 'A literal ref-')
        self.assertEqual(normalized['blocks'][0]['bbox'], [10, 20, 400, 50])
        self.assertTrue(normalized['blocks'][0]['uncertain'])
        validate_ocr(value)

    def test_native_ocr_invalid_coordinates_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_ocr([{'text': 'x', 'bbox_2d': [400, 2, 10, 20]}])

    def test_transcription_does_not_require_model_invented_coordinates(self):
        value = {'blocks': [{'text': 'A reference as printed', 'uncertain': False}]}
        validate_ocr(value)
        self.assertIsNone(normalize_ocr(value)['blocks'][0]['bbox'])

    def test_stream_requires_finish_stop(self):
        lines = [b'data: {"choices":[{"delta":{"content":"{}"},"finish_reason":"length"}]}\n',
                 b'data: [DONE]\n']
        with self.assertRaises(ValueError):
            decode_sse(lines)

    def test_stream_collects_content_and_usage(self):
        lines = [b'data: {"choices":[{"delta":{"content":"{}"},"finish_reason":"stop"}]}\n',
                 b'data: {"choices":[],"usage":{"total_tokens":9}}\n',
                 b'data: [DONE]\n']
        text, usage = decode_sse(lines)
        self.assertEqual(text, '{}')
        self.assertEqual(usage['total_tokens'], 9)


class ReaderTests(unittest.TestCase):
    def test_different_lines_with_overlapping_font_boxes_stay_separate(self):
        words=[{'text':'TITLE','x0':10,'x1':50,'top':100,'bottom':120},
               {'text':'next','x0':10,'x1':30,'top':114,'bottom':124},
               {'text':'line','x0':34,'x1':54,'top':114,'bottom':124}]
        self.assertEqual([b['text'] for b in word_blocks(words,1,200,300)],['TITLE','next line'])

    def test_subscript_stays_between_its_neighboring_words(self):
        words=[{'text':'CO','x0':10,'x1':25,'top':100,'bottom':110},
               {'text':'2','x0':25,'x1':30,'top':105,'bottom':112},
               {'text':'emissions','x0':35,'x1':80,'top':100,'bottom':110},
               {'text':'Climate','x0':10,'x1':50,'top':113,'bottom':123}]
        blocks=word_blocks(words,1,200,300)
        self.assertEqual([b['text'] for b in blocks],['CO 2 emissions','Climate'])

    def test_column_order_is_left_before_right_even_if_left_starts_lower(self):
        lookup = {'left': {'id': 'left', 'page': 1, 'bbox': [120, 500, 480, 520]},
                  'right': {'id': 'right', 'page': 1, 'bbox': [520, 90, 880, 110]}}
        items = [{'source_ids': ['right']}, {'source_ids': ['left']}]
        self.assertEqual(order_entries(items, lookup), list(reversed(items)))

    def test_single_column_keeps_vertical_order(self):
        lookup = {'top': {'id': 'top', 'page': 1, 'bbox': [120, 100, 800, 120]},
                  'bottom': {'id': 'bottom', 'page': 1, 'bbox': [125, 500, 800, 520]}}
        items = [{'source_ids': ['bottom']}, {'source_ids': ['top']}]
        self.assertEqual(order_entries(items, lookup), list(reversed(items)))

    def test_two_columns_remain_separate(self):
        words = [{'text': 'LEFT', 'x0': 10, 'x1': 40, 'top': 20, 'bottom': 30},
                 {'text': 'RIGHT', 'x0': 110, 'x1': 150, 'top': 20, 'bottom': 30}]
        blocks = word_blocks(words, 1, 200, 300)
        self.assertEqual([b['text'] for b in blocks], ['LEFT', 'RIGHT'])
        self.assertNotEqual(blocks[0]['id'], blocks[1]['id'])

    def test_text_has_unique_nonempty_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'refs.txt'
            p.write_text('References\n\n[1] A title\n continuation', encoding='utf-8')
            doc = read_document(p, Path(tmp) / 'work')
            blocks = doc['pages'][0]['blocks']
            self.assertEqual(len(blocks), 3)
            self.assertEqual(len({b['id'] for b in blocks}), 3)

    def test_unsupported_input_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'old.doc'
            p.write_bytes(b'x')
            with self.assertRaises(ValueError):
                read_document(p, Path(tmp) / 'work')


class ExecutionTests(unittest.TestCase):
    def test_invalid_model_schema_is_retried_and_both_attempts_saved(self):
        class Response:
            status = 200

            def __init__(self, answer):
                event = {'choices': [{'delta': {'content': answer}, 'finish_reason': 'stop'}]}
                self.lines = [('data: ' + json.dumps(event) + '\n').encode(), b'data: [DONE]\n']

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                return iter(self.lines)

        config = Config('https://example.test/compatible-mode/v1', 'm', 'm', 'SECRET_TEST_KEY')
        blocks = [{'id': 'b1', 'text': 'A reference'}]
        valid = {'references': [{'source_ids': ['b1']}], 'excluded': [], 'uncertain': []}
        with tempfile.TemporaryDirectory() as tmp:
            with patch('urllib.request.urlopen', side_effect=[Response('{"references":["wrong"]}'), Response(json.dumps(valid))]):
                client = Client(config, tmp, progress=lambda *a, **kw: None)
                result = client.ask('test', 'Return the schema', lambda v: validate_partition(v, blocks))
            self.assertEqual(result, valid)
            attempts = sorted(Path(tmp).glob('*.json'))
            self.assertEqual(len(attempts), 2)
            self.assertFalse(json.loads(attempts[0].read_text())['valid'])
            self.assertTrue(json.loads(attempts[1].read_text())['valid'])
            self.assertNotIn('SECRET_TEST_KEY', ''.join(p.read_text() for p in attempts))

    def test_single_command_text_pipeline_outputs_source_based_results(self):
        def ask(client, stage, prompt, validator, **kwargs):
            value = {'references': [{'source_ids': ['p1-b2']}],
                     'excluded': [{'source_ids': ['p1-b1'], 'reason': 'heading'}], 'uncertain': []}
            if stage == 'audit-excluded':
                value['references'] = []
            validator(value)
            return value

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'input.txt'
            source.write_text('References\nAlice Smith. A literal reference title. Journal of AI, 2023.', encoding='utf-8')
            config = Config('https://example.test/compatible-mode/v1', 'm', 'm', 'secret')
            output = Path(tmp) / 'run'
            with patch.object(Client, 'ask', ask):
                result = extract(source, output, config, progress=lambda *a, **kw: None)
            self.assertEqual(result['status'], '流程完成')
            self.assertEqual(result['references'][0]['raw_text'], 'Alice Smith. A literal reference title. Journal of AI, 2023.')
            self.assertTrue(result['code_unchanged_during_run'])
            self.assertTrue((output / 'index.html').exists())
            self.assertTrue((output / 'result.json').exists())
            with self.assertRaises(FileExistsError):
                extract(source, output, config)

    def test_exclusion_audit_recovers_a_misclassified_reference(self):
        def ask(client, stage, prompt, validator, **kwargs):
            if stage == 'partition':
                value = {'references': [{'source_ids': ['p1-b2']}],
                         'excluded': [{'source_ids': ['p1-b1', 'p1-b3'], 'reason': 'body'}], 'uncertain': []}
            else:
                value = {'references': [{'source_ids': ['p1-b3']}],
                         'excluded': [{'source_ids': ['p1-b1'], 'reason': 'heading'}], 'uncertain': []}
            validator(value)
            return value

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'input.txt'
            source.write_text('References\nAlice Smith. First citation title. Journal of AI, 2023.\nBo Wang. Second citation title. Journal of AI, 2022.', encoding='utf-8')
            config = Config('https://example.test/compatible-mode/v1', 'm', 'm', 'secret')
            with patch.object(Client, 'ask', ask):
                result = extract(source, Path(tmp) / 'run', config, progress=lambda *a, **kw: None)
            self.assertEqual([r['raw_text'] for r in result['references']], ['Alice Smith. First citation title. Journal of AI, 2023.', 'Bo Wang. Second citation title. Journal of AI, 2022.'])
            self.assertEqual(result['recovered_by_exclusion_audit'], 1)
            self.assertTrue(result['coverage']['all_assigned_once'])

    def test_failed_request_outputs_failure_not_empty_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'input.txt'
            source.write_text('A reference', encoding='utf-8')
            config = Config('https://example.test/compatible-mode/v1', 'm', 'm', 'secret')
            with patch.object(Client, 'ask', side_effect=RuntimeError('request failed')):
                result = extract(source, Path(tmp) / 'run', config)
            self.assertEqual(result['status'], '执行未完成')
            self.assertIn('request failed', result['error'])


if __name__ == '__main__':
    unittest.main()
