import unittest
from ref_app import parsing


class ParsingTests(unittest.TestCase):
    def test_clear_author_year_needs_no_model(self):
        raw = 'Alice Smith and Bob Jones. 2021. Learning reliable representations. In Proceedings of Example Conference, pages 12–19.'
        q = parsing.parse_reference(raw)
        self.assertEqual(q['title'], 'Learning reliable representations')
        self.assertEqual([a['literal'] for a in q['authors']], ['Alice Smith', 'Bob Jones'])
        self.assertEqual(q['parse_status'], 'rules_complete')
        self.assertEqual(q['raw_text'], raw)

    def test_data_note_not_used_as_work_url(self):
        raw = 'Alice Smith. 2021. Learning reliable representations. In Proceedings of Example Conference. Data can be found at https://github.com/example/data/.'
        q = parsing.parse_reference(raw)
        self.assertEqual(q['links'][0]['role'], 'related_data')
        self.assertEqual(q['urls'], [])
        self.assertIn('Data can be found', q['notes'][0])
        self.assertEqual(q['links'][0]['url'], 'https://github.com/example/data/')

    def test_github_alone_is_not_automatically_code_or_paper(self):
        q = parsing.parse_reference('Example toolkit. https://github.com/example/tool')
        self.assertEqual(q['links'][0]['role'], 'unknown')
        self.assertEqual(q['parse_status'], 'needs_llm')

    def test_access_year_is_not_publication_year(self):
        q = parsing.parse_reference('Example website. Accessed 2024. https://example.org')
        self.assertIsNone(q['year'])
        self.assertEqual(q['parse_status'], 'needs_llm')

    def test_link_context_does_not_spill_to_next_sentence(self):
        q = parsing.parse_reference('Data available at https://example.org/data. Code available at https://example.org/code.')
        self.assertEqual([x['role'] for x in q['links']], ['related_data', 'related_code'])

    def test_model_invented_title_rejected(self):
        def fake(raw, draft):
            return {'title':'Invented title', 'authors':[], 'year':None}
        with self.assertRaises(ValueError):
            parsing.parse_reference('Unstructured citation with actual wording', fake)

    def test_fallback_preserves_source_and_grounded_model_fields(self):
        raw = 'Smith, A. (2020). Real work title. Example Press.'
        def fake(raw, draft):
            return {'title':'Real work title', 'authors':[{'literal':'Smith, A.', 'kind':'person'}], 'year':'2020'}
        q = parsing.parse_reference(raw, fake)
        self.assertEqual(q['parse_status'], 'llm_parsed')
        self.assertEqual(q['raw_text'], raw)
        ev = q['field_evidence']['title']
        self.assertEqual(raw[ev['start']:ev['end']], 'Real work title')

    def test_ambiguous_initials_and_title_period_fall_back(self):
        q = parsing.parse_reference('A. Smith. 2021. U.S. scientific policy. In Proceedings of Example Conference.')
        self.assertEqual(q['parse_status'], 'needs_llm')

    def test_et_al_is_not_a_person(self):
        q = parsing.parse_reference('Alice Smith, Bob Jones, et al. 2021. Learning reliable representations. In Proceedings of Example Conference.')
        self.assertTrue(q['authors_truncated'])
        self.assertEqual([a['literal'] for a in q['authors']], ['Alice Smith', 'Bob Jones'])

    def test_page_range_can_contain_pdf_whitespace(self):
        q = parsing.parse_reference('Alice Smith. 2021. Learning reliable representations. In Proceedings of Example Conference, pages 12– 19.')
        self.assertEqual(q['pages'], '12– 19')

    def test_numeric_volume_not_in_venue_name(self):
        q = parsing.parse_reference('Alice Smith. 2021. Learning reliable representations. Journal of Examples, 35:12–19.')
        self.assertEqual(q['container_title'], 'Journal of Examples')
        self.assertEqual(q['volume'], '35')
        self.assertEqual(q['pages'], '12–19')

    def test_dataset_doi_not_used_as_work_identifier(self):
        q = parsing.parse_reference('Example reference. Data available at https://doi.org/10.1234/dataset.')
        self.assertEqual(q['doi'], [])
        self.assertEqual(q['all_identifiers']['doi'], ['10.1234/dataset'])


if __name__ == '__main__':
    unittest.main()
