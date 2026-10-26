import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from reference_extractor.rules import analyze
from reference_extractor.pipeline import extract
from reference_extractor.config import Config
from reference_extractor.api import Client


def block(i,text,x=180,y=None,page=1,right=820):
    y=y if y is not None else 80+i*16
    return {'id':f'p{page}-b{i}','page':page,'text':text,'bbox':[x,y,right,y+12]}


def document(blocks):
    return {'input_type':'pdf','pages':[{'page':p,'blocks':[b for b in blocks if b['page']==p]} for p in sorted({b['page'] for b in blocks})]}


class RuleTests(unittest.TestCase):
    def test_boundary_shortcut_cannot_ignore_remote_unnumbered_references(self):
        from reference_extractor.pipeline import review_boundary
        bs=[block(1,'References'),block(2,'[1] Alice Smith. Imaging. Journal of AI, 2023.'),
            block(3,'[2] Bo Wang. Imaging. Journal of AI, 2022.'),
            block(4,'A Unlisted Topic'),block(5,'We report additional experiments here.'),
            block(1,'Ordinary appendix prose.',page=2),
            block(1,'Jane Doe. Appendix source. Journal of AI, 2021.',page=3)]
        for b in bs:b['font_size']=10
        bs[3]['font_size']=12
        proposal=analyze(document(bs))
        with tempfile.TemporaryDirectory() as tmp:
            from unittest.mock import Mock
            client=Mock()
            self.assertFalse(review_boundary(document(bs),proposal,client,Path(tmp)))
            client.ask.assert_not_called()
    def test_only_typographic_boundary_can_use_small_model_review(self):
        bs=[block(1,'References'),block(2,'[1] Alice Smith. Imaging. Journal of AI, 2023.'),
            block(3,'[2] Bo Wang. Imaging. Journal of AI, 2022.'),
            block(4,'A Unlisted Topic'),block(5,'We report additional experiments here.')]
        for b in bs:b['font_size']=10
        bs[3]['font_size']=12
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'input.pdf';source.write_bytes(b'fake')
            calls=[]
            def ask(client,stage,prompt,validator,**kw):
                calls.append(stage)
                value={'decision':'section_heading','reason':'Heading followed by appendix prose, not a citation continuation'}
                validator(value);return value
            with patch('reference_extractor.pipeline.read_document',return_value=document(bs)),patch.object(Client,'ask',ask):
                r=extract(source,Path(tmp)/'run',Config('https://example.test','m','m',''),progress=lambda *a,**kw:None)
            self.assertEqual(r['status'],'流程完成',r)
            self.assertEqual(r['extraction_method'],'rules_boundary_review')
            self.assertEqual(calls,['audit-boundary'])
            self.assertEqual(len(r['references']),2)

    def test_alphanumeric_bibliography_labels_are_unique_not_numeric_sequences(self):
        bs=[block(1,'References'),block(2,'[AB+19] Alice Smith. Imaging. Journal of AI, 2019.'),
            block(3,'[CD20] Bo Wang. Imaging. Journal of AI, 2020.'),
            block(4,'[EF21] Jane Doe. Imaging. Journal of AI, 2021.')]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(len(r['partition']['references']),3)
        bs[-1]['text']=bs[-1]['text'].replace('[EF21]','[CD20]')
        self.assertFalse(analyze(document(bs))['accepted'])

    def test_small_caps_appendix_with_strong_spacing_can_end_region(self):
        bs=[block(1,'References',y=80),block(2,'[1] Alice Smith. Imaging. Journal of AI, 2023.',y=120),
            block(3,'[2] Bo Wang. Imaging. Journal of AI, 2022.',y=145),
            block(4,'A AN UNLISTED RESEARCH TOPIC',y=190),block(5,'We report additional experiments here.',y=220)]
        for b in bs:b['font_size']=10
        bs[3]['font_size']=9.5
        r=analyze(document(bs));self.assertFalse(r['accepted'],r)
        self.assertEqual(r['boundaries']['last_source_id'],'p1-b3')
        self.assertIn('ambiguous_typographic_boundary',r['issues'])

    def test_second_alphanumeric_reference_list_is_not_dropped(self):
        bs=[block(1,'References'),block(2,'[AB20] Alice Smith. Study. Journal of AI, 2020.'),
            block(3,'[CD21] Bo Wang. Study. Journal of AI, 2021.'),block(4,'Appendix A'),
            block(5,'References'),block(6,'[EF22] Jane Doe. Study. Journal of AI, 2022.'),
            block(7,'[GH23] Chen Li. Study. Journal of AI, 2023.')]
        self.assertFalse(analyze(document(bs))['accepted'])

    def test_typographic_title_after_venue_cannot_be_silently_excluded(self):
        bs=[block(1,'References'),block(2,'[1] Alice Smith. First study. Journal of AI, 2020.'),
            block(3,'[2] Bo Wang. Second study. Journal of AI, 2021.',y=140),
            block(4,'A NEW APPROACH TO MEDICAL LEARNING',y=180),block(5,'Proceedings of AI, pages 1–20.',y=205)]
        for b in bs:b['font_size']=10
        r=analyze(document(bs));self.assertFalse(r['accepted'],r)

    def test_appendix_heading_uses_local_reference_font_not_body_font(self):
        bs=[block(i,'A long body paragraph describing experimental observations and their limitations.',page=1,y=80+i*15) for i in range(1,20)]
        for b in bs:b['font_size']=11
        tail=[block(1,'References',page=2),block(2,'[1] Alice Smith. Imaging. Journal of AI, 2023.',page=2),
              block(3,'[2] Bo Wang. Imaging. Journal of AI, 2022.',page=2),
              block(4,'A Unlisted Topic',page=2),block(5,'The appendix contains experimental observations.',page=2)]
        for b in tail:b['font_size']=10
        tail[3]['font_size']=12
        r=analyze(document(bs+tail));self.assertFalse(r['accepted'],r)
        self.assertEqual(r['boundaries']['last_source_id'],'p2-b3')

    def test_same_visual_line_fragments_read_left_to_right(self):
        from reference_extractor.rules import reading_order
        bs=[block(1,'OpenAI. 2023. A substantial technical report.',x=100,y=200,right=350),
            block(2,'ArXiv,',x=360,y=199.8,right=450)]
        ordered,_=reading_order(document(bs))
        self.assertEqual([b['id'] for b in ordered],['p1-b1','p1-b2'])

    def test_corporate_author_with_letter_year_suffix_starts_new_entry(self):
        bs=[block(1,'References')]
        for j,name in enumerate(['Alice Smith. 2023. First study.', 'OpenAI. 2023a. Second study.', 'OpenAI. 2023b. Third study.']):
            bs += [block(j*2+2,name,y=120+j*50),block(j*2+3,'Journal of AI, pages 10–20.',x=215,y=134+j*50)]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(len(r['partition']['references']),3)

    def test_abbreviated_and_ampersand_authors_have_bibliographic_features(self):
        from reference_extractor.rules import features
        for text in ['CDC. A substantial laboratory assay protocol. Department of Health. 2007.',
                     'Vinyals & Kaiser, Jones, and Wang. A substantial research study. In Advances in Learning, 2015.']:
            self.assertTrue(features(text)['bibliographic'],text)
        self.assertFalse(features('We found a substantial improvement in accuracy in 2023.')['bibliographic'])

    def test_explicit_heading_is_preferred_over_long_body_enumeration(self):
        bs=[block(1,'[18] Alice Smith. Study. Journal of AI, 2020.',page=1),
            block(2,'[19] Bo Wang. Study. Journal of AI, 2021.',page=1),
            block(3,'[20] Jane Doe. Study. Journal of AI, 2022.',page=1),
            block(1,'References',page=2),block(2,'[1] Alice Smith. Study. Journal of AI, 2020.',page=2),
            block(3,'[2] Bo Wang. Study. Journal of AI, 2021.',page=2)]
        r=analyze(document(bs));self.assertEqual(r['boundaries']['first_source_id'],'p2-b2')
        # Still flag the other bibliographic-looking list: preference cannot hide it.
        self.assertFalse(r['accepted'])
        self.assertIn('other_bibliographic_markers_outside_region',r['issues'])

    def test_repeated_year_and_capitalized_journal_not_an_author_marker(self):
        bs=[block(1,'References'),block(2,'1. Smith A. Important medical research.'),
            block(3,'2019. CA Cancer J Clin. 2019; 69:438–451. https://doi.org/10.1000/example',x=210),
            block(4,'2. Wang B. A second study. Journal of AI, 2023.')]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(r['original_numbers'],[1,2])

    def test_reference_title_that_looks_like_appendix_is_not_silently_lost(self):
        for title in ['A Case Study of Reliable Machine Learning','Learning Reliable Representations']:
            bs=[block(1,'References'),block(2,'[1] Alice Smith. First study. Journal of AI, 2021.'),
                block(3,'[2] Bo Wang. Second study. Journal of AI, 2022.'),
                block(4,'[3] Alice Smith, Bo Wang, Jane Doe, and Chen Li. 2023.'),
                block(5,title),block(6,'Proceedings of the International AI Conference, pages 10–20.')]
            for b in bs:b['font_size']=10
            if not title.startswith('A '):bs[4]['font_size']=12
            r=analyze(document(bs))
            self.assertFalse(r['accepted'])
            self.assertIn('ambiguous_end',r['issues'])

    def test_shifted_last_reference_marker_triggers_review(self):
        bs=[block(1,'References'),block(2,'[1] Alice Smith. Imaging. Journal of AI, 2021.',x=100),
            block(3,'[2] Bo Wang. Imaging. Journal of AI, 2022.',x=100),
            block(4,'[3] Jane Doe. Imaging. Journal of AI, 2023.',x=115)]
        r=analyze(document(bs));self.assertFalse(r['accepted'])
        self.assertIn('misaligned_reference_marker',r['issues'])

    def test_repeated_marginal_venue_is_not_assumed_to_be_a_footer(self):
        bs=[block(1,'References'),block(2,'[1] Alice Smith. A substantial first imaging study, 2021.',y=900),
            block(1,'Proceedings of the International AI Conference, 2023.',y=60,page=2),
            block(2,'[2] Bo Wang. A substantial second imaging study, 2022.',y=900,page=2),
            block(1,'Proceedings of the International AI Conference, 2023.',y=60,page=3),
            block(2,'[3] Jane Doe. Imaging. Journal of AI, 2023.',y=100,page=3)]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        ref_ids={i for r in r['partition']['references'] for i in r['source_ids']}
        self.assertIn('p2-b1',ref_ids);self.assertIn('p3-b1',ref_ids)

    def test_old_book_and_comma_after_initials_are_bibliographic(self):
        bs=[block(1,'References'),block(2,'1. Kant I. Kritik der reinen Vernunft. Riga: Johann Friedrich Hartknoch; 1781.'),
            block(3,'2. Ananda S., & Rabinowitz S. (2000). The High Stakes of HIGH-STAKES Testing. Policy Brief.')]
        self.assertTrue(analyze(document(bs))['accepted'])

    def test_single_organization_name_starts_an_unnumbered_entry(self):
        bs=[]
        for i,name in enumerate(['Alice Smith','OpenAI','Jane Doe']):
            title=name+('. 2023. A substantial study of medical images.' if name=='OpenAI' else '. A substantial study of medical images.')
            bs += [block(i*2+1,title,y=100+i*65),block(i*2+2,'Journal of Medicine, pages 10–20, 2023.',x=215,y=115+i*65)]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(len(r['partition']['references']),3)

    def test_large_font_section_heading_ends_bibliography(self):
        bs=[block(1,'References'),block(2,'[1] Alice Smith. Imaging. Journal of AI, 2023.'),block(3,'[2] Bo Wang. Imaging. Journal of AI, 2023.'),
            block(4,'A Unseen Topic Details'),block(5,'Experimental observations are discussed here.')]
        for b in bs:b['font_size']=10
        bs[3]['font_size']=13
        r=analyze(document(bs));self.assertFalse(r['accepted'],r)
        self.assertIn('ambiguous_typographic_boundary',r['issues'])
        self.assertEqual(r['partition']['references'][-1]['source_ids'],['p1-b3'])

    def test_column_gutter_ignores_short_fragments_in_the_middle(self):
        bs=[block(1,'References',x=110,y=100,right=230)]
        for j in range(3):
            bs += [block(2+j*2,f'[{j+1}] Alice Smith. Imaging. Journal of AI, 2023.',x=110,y=140+j*30,right=480),
                   block(3+j*2,f'[{j+4}] Bo Wang. Imaging. Journal of AI, 2023.',x=520,y=140+j*30,right=890)]
        # A short page ornament is not evidence that the gutter has disappeared.
        bs.append(block(10,'7',x=495,y=940,right=505))
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(r['original_numbers'],[1,2,3,4,5,6])

    def test_plain_page_range_and_year_continuations_are_not_entries(self):
        bs=[block(1,'References'),block(2,'1. Smith A. Medical imaging. Journal of AI, 2022; 15:'),
            block(3,'5661. https://doi.org/10.1000/a-long-persistent-identifier',x=210),
            block(4,'2. Wang B. A second study. Journal of AI, 2023.')]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(r['original_numbers'],[1,2])

    def test_repeated_publisher_doi_footer_not_added_to_references(self):
        bs=[block(1,'References'),block(2,'[1] Alice Smith. Imaging. Journal of AI, 2023.'),
            block(3,'[2] Bo Wang. Imaging. Journal of AI, 2023.'),
            block(4,'Publisher | https://doi.org/10.1000/article December 2023',y=960),
            block(1,'[3] Jane Doe. Imaging. Journal of AI, 2023.',page=2),
            block(2,'Publisher | https://doi.org/10.1000/article December 2023',y=960,page=2)]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertNotIn('p1-b4',[i for x in r['partition']['references'] for i in x['source_ids']])

    def test_titled_appendix_is_not_citation_text(self):
        texts=['References','[1] Alice Smith. Imaging methods. Journal of AI, 2022.',
               '[2] Bo Wang. Language methods. Journal of AI, 2023.',
               'Appendix A: Experimental Details','Additional experiments are presented here.']
        bs=[{'id':str(i),'page':1,'text':t,'bbox':None} for i,t in enumerate(texts)]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(r['partition']['references'][-1]['source_ids'],['2'])

    def test_two_column_unnumbered_list_has_six_entries(self):
        bs=[]
        for column,x in enumerate([100,540]):
            for j,name in enumerate(['Alice Smith','Bo Wang','Jane Doe']):
                k=column*6+j*2
                bs += [block(k+1,name+'. A substantial study of medical images.',x=x,y=100+j*65,right=x+350),
                       block(k+2,'Journal of Medicine, pages 10–20, 2023.',x=x+35,y=115+j*65,right=x+350)]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(len(r['partition']['references']),6)

    def test_lowercase_surname_prefix_is_not_silently_dropped(self):
        bs=[block(1,'de Vries, A. A substantial study. Journal of Medicine, 2020,',y=100),
            block(2,'pages 10–20.',x=215,y=115)]
        for j,name in enumerate(['Alice Smith','Bo Wang','Jane Doe']):
            bs += [block(j*2+3,name+'. A substantial study of medical images.',y=165+j*65),
                   block(j*2+4,'Journal of Medicine, pages 10–20, 2023.',x=215,y=180+j*65)]
        self.assertFalse(analyze(document(bs))['accepted'])

    def test_plain_text_conclusion_is_excluded_not_merged(self):
        texts=['References','[1] Alice Smith. Imaging methods. Journal of AI, 2022.',
               '[2] Bo Wang. Language methods. Journal of AI, 2023.','Conclusion',
               'We found that our approach outperforms all competing systems.']
        bs=[{'id':str(i),'page':1,'text':t,'bbox':None} for i,t in enumerate(texts)]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(r['partition']['references'][-1]['source_ids'],['2'])

    def test_plain_number_style_and_parentheses(self):
        for fmt in ('{}.','({})'):
            bs=[block(1,'References')]+[block(i+1,fmt.format(i)+' Alice Smith. Imaging methods. Journal of AI, 2023.') for i in range(1,4)]
            r=analyze(document(bs));self.assertTrue(r['accepted'],r)
            self.assertEqual(r['original_numbers'],[1,2,3])

    def test_duplicate_numbers_fall_back(self):
        bs=[block(1,'References')]+[block(i+2,f'[{n}] Alice Smith. Study. Journal of AI, 2023.') for i,n in enumerate([1,2,2,3])]
        self.assertFalse(analyze(document(bs))['accepted'])

    def test_prose_after_references_is_not_swallowed_as_clean_success(self):
        bs=[block(1,'References',y=50),block(2,'[1] Alice Smith. Study. Journal of AI, 2023.',y=100),
            block(3,'[2] Bo Wang. Study. Journal of AI, 2022.',y=140),
            block(4,'We performed additional experiments to evaluate the proposed method.',y=190)]
        self.assertFalse(analyze(document(bs))['accepted'])

    def test_two_distinct_lists_require_review(self):
        bs=[block(1,'References'),block(2,'[1] Alice Smith. Study. Journal of AI, 2023.'),
            block(3,'[2] Bo Wang. Study. Journal of AI, 2022.'),block(4,'Appendix A'),
            block(5,'References'),block(6,'[1] Jane Doe. Study. Journal of AI, 2021.'),
            block(7,'[2] Chen Li. Study. Journal of AI, 2020.')]
        self.assertFalse(analyze(document(bs))['accepted'])

    def test_year_at_start_of_continuation_is_not_a_reference_marker(self):
        bs=[block(1,'References'),block(2,'[1] Alice Smith. Imaging methods. Journal of AI,'),
            block(3,'2006. doi: 10.1000/example.',x=210),
            block(4,'[2] Bo Wang. Study. Journal of AI, 2022.')]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(r['original_numbers'],[1,2])
        self.assertIn('p1-b3',r['partition']['references'][0]['source_ids'])

    def test_pipeline_skips_api_when_rules_are_sufficient(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'refs.txt'
            source.write_text('References\n[1] Alice Smith. Imaging methods. Journal of AI, 2022.\n[2] Bo Wang. Language methods. Journal of AI, 2023.',encoding='utf-8')
            with patch.object(Client,'ask',side_effect=AssertionError('must not call API')):
                result=extract(source,Path(d)/'run',Config('https://example.test','m','m','secret'),progress=lambda *a,**k:None)
            self.assertEqual(result['status'],'流程完成',result)
            self.assertEqual(result['extraction_method'],'rules')
            self.assertEqual(result['api_attempts'],0)
            self.assertEqual(result['references'][1]['original_number'],2)

    def test_model_only_mode_still_runs_original_partition(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'refs.txt';source.write_text('Alice Smith. A citation title. Journal of AI, 2023.',encoding='utf-8')
            config=Config('https://example.test','m','m','secret');config.extraction_mode='model'
            def ask(client,name,prompt,validator,**kw):
                value={'references':[{'source_ids':['p1-b1']}],'excluded':[],'uncertain':[]};validator(value);return value
            with patch.object(Client,'ask',ask) as mocked:
                result=extract(source,Path(d)/'run',config,progress=lambda *a,**k:None)
            self.assertEqual(result['extraction_method'],'model')
            self.assertEqual(result['references'][0]['raw_text'],'Alice Smith. A citation title. Journal of AI, 2023.')

    def test_numbered_region_preserves_every_source_and_appendix_boundary(self):
        bs=[block(1,'We conclude that our method is effective.'),block(2,'References'),
            block(3,'[1] Alice Smith. Study of images. Scientific Data, 2021.'),
            block(4,'doi: 10.1000/example.',x=210),
            block(5,'[2] Bo Wang. Language methods. Journal of AI, 2023.'),
            block(6,'Appendix A'),block(7,'Additional experiments are presented here.')]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(r['partition']['references'][0]['source_ids'],['p1-b3','p1-b4'])
        self.assertEqual(r['original_numbers'],[1,2])
        self.assertTrue(r['checks']['all_input_blocks_assigned_once'])
        self.assertIn('p1-b7',[i for e in r['partition']['excluded'] for i in e['source_ids']])

    def test_cropped_no_heading_can_start_at_non_one_number(self):
        bs=[block(i,f'[{i+6}] Alice Smith. Study number {i}. Journal of AI, 2023.') for i in range(1,5)]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(r['original_numbers'],[7,8,9,10])

    def test_missing_number_triggers_fallback_not_silent_success(self):
        bs=[block(1,'References')]+[block(i+2,f'[{n}] Alice Smith. Study. Journal of AI, 2023.') for i,n in enumerate([1,2,4])]
        r=analyze(document(bs));self.assertFalse(r['accepted']);self.assertIn('number_sequence',r['issues'])

    def test_body_enumeration_is_not_a_bibliography(self):
        bs=[block(i,f'{i}. We evaluated the system in 2023 and observed a significant improvement.') for i in range(1,5)]
        self.assertFalse(analyze(document(bs))['accepted'])

    def test_repeated_reference_heading_does_not_drop_first_page(self):
        bs=[block(1,'References'),block(2,'[1] Alice Smith. Study. Journal of AI, 2023.'),
            block(3,'[2] Bo Wang. Study. Journal of AI, 2022.'),
            block(1,'References',page=2),block(2,'[3] Jane Doe. Study. Journal of AI, 2021.',page=2)]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(r['original_numbers'],[1,2,3])

    def test_two_columns_read_left_then_right(self):
        bs=[block(1,'References',y=50),block(2,'[1] Alice Smith. Study. Journal of AI, 2023.',x=100,y=100,right=460),
            block(3,'[3] Jane Doe. Study. Journal of AI, 2021.',x=540,y=100,right=900),
            block(4,'[2] Bo Wang. Study. Journal of AI, 2022.',x=100,y=180,right=460),
            block(5,'[4] Chen Li. Study. Journal of AI, 2020.',x=540,y=180,right=900)]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(r['original_numbers'],[1,2,3,4])

    def test_hanging_indent_without_heading_or_numbers(self):
        bs=[]
        for i,name in enumerate(['Alice Smith','Bo Wang','Jane Doe']):
            bs += [block(i*2+1,name+'. A substantial study of medical images.',x=180,y=100+i*65),
                   block(i*2+2,'Journal of Medicine, pages 10–20, 2023.',x=215,y=115+i*65)]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(len(r['partition']['references']),3)

    def test_number_in_citation_does_not_create_a_new_reference(self):
        bs=[block(1,'References'),block(2,'[1] Alice Smith. Study. Journal of AI, 2023.'),
            block(3,'Comparing methods [9] and [10].',x=210),block(4,'[2] Bo Wang. Study. Journal of AI, 2022.')]
        r=analyze(document(bs));self.assertTrue(r['accepted'],r)
        self.assertEqual(r['partition']['references'][0]['source_ids'],['p1-b2','p1-b3'])

    def test_plain_unnumbered_text_is_left_to_model(self):
        bs=[{'id':'p1-b1','page':1,'text':'An ambiguous fragment','bbox':None}]
        self.assertFalse(analyze(document(bs))['accepted'])


if __name__=='__main__':unittest.main()
