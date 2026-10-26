import unittest

from reference_extractor.rules import analyze
from reference_extractor.pipeline import audit_group_fragments
from test_extraction_rules import block, document


class NumberedRetentionTests(unittest.TestCase):
    def test_model_groups_with_missing_year_are_kept_in_numbered_context(self):
        for marker in ('[{}]', '({})', '{}.'):
            texts = ['Alice Smith. A useful study. Journal of Science, 2022.',
                     'Bo Wang. A second study. Conference on Learning Systems, 2021.',
                     'Jane Doe. A study without a date. In Conference on Learning Systems.',
                     'Anna Green. Another useful study. Journal of Science, 2020.']
            bs = [block(i, marker.format(i) + ' ' + text) for i, text in enumerate(texts, 1)]
            value = {'references': [{'source_ids': [b['id']]} for b in bs], 'excluded': [], 'uncertain': []}
            result, flags = audit_group_fragments(value, bs)
            self.assertEqual(len(result['references']), 4, marker)
            self.assertFalse(result['uncertain'], marker)
            self.assertFalse(flags, marker)

    def test_missing_year_is_not_a_grouping_failure_in_supported_numbered_list(self):
        bs = [block(1, 'References'),
              block(2, '[1] Alice Smith. A useful study. Journal of Science, 2022.'),
              block(3, '[2] Bo Wang. A second study. Conference on Learning Systems, 2021.'),
              block(4, '[3] Jane Doe and John Smith. A study without a year. In International Conference on Learning Systems.'),
              block(5, '[4] Anna Green. Another study without a date. ACM Transactions on Learning.'),
              block(6, 'Appendix')]
        r = analyze(document(bs))
        self.assertTrue(r['accepted'], r['issues'])
        self.assertEqual(r['original_numbers'], [1, 2, 3, 4])
        self.assertEqual(len(r['entry_notes']), 2)

    def test_numbered_non_bibliography_is_not_accepted(self):
        bs = [block(1, 'References'), block(2, '[1] Please open the program and choose a file.'),
              block(3, '[2] Then run the analysis and save the report.'), block(4, 'Appendix')]
        self.assertFalse(analyze(document(bs))['accepted'])

    def test_numbering_alone_does_not_rescue_unanchored_fragments(self):
        bs = [block(1, '[1] Alice Smith. An unfinished title without publication information.'),
              block(2, '[2] Jane Doe. Another incomplete author and title fragment.')]
        self.assertFalse(analyze(document(bs))['accepted'])

    def test_distinct_numbered_suspects_are_never_merged_together(self):
        bs = [block(1, '[1] Alice Smith. A title without publication information.'),
              block(2, '[2] Jane Doe. Another title without publication information.')]
        value = {'references': [{'source_ids': [b['id']]} for b in bs], 'excluded': [], 'uncertain': []}
        result, _ = audit_group_fragments(value, bs)
        self.assertEqual([x['source_ids'] for x in result['uncertain']], [['p1-b1'], ['p1-b2']])


if __name__ == '__main__':
    unittest.main()
