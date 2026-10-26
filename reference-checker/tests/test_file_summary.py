import unittest
from ref_app.visual_process import file_summary


class FileSummaryTests(unittest.TestCase):
    def test_categories_cover_all_extracted_entries_without_calling_absence_fake(self):
        def row(status, claims=(), execution='completed'):
            return {'result': {'dimensions': {'existence': {'status': status},
                    'fields': {'claims': [{'status': c} for c in claims]},
                    'execution': {'status': execution}}}}
        refs = [row('confirmed', ['match', 'conflict']), row('unknown', ['unknown'], 'partial'),
                row('candidate'), {'result': None, 'parsing': {'status': 'tool_failure'}}]
        s = file_summary(refs, {'state': 'completed'}, {'uncertain_groups': 2})
        self.assertEqual([s[k] for k in ('total', 'non_hallucinated', 'hallucinated', 'undetermined', 'unverified')], [4, 1, 0, 2, 1])
        self.assertEqual(s['field_differences'], 1)
        self.assertEqual(s['field_unverified'], 1)
        self.assertEqual(s['execution_issues'], 2)
        self.assertEqual(s['uncertain_groups'], 2)

    def test_missing_query_result_is_unverified_even_after_job_completion(self):
        s = file_summary([{'result': None}], {'state': 'completed'}, {})
        self.assertEqual(s['unverified'], 1)
        self.assertEqual(s['undetermined'], 0)
        self.assertEqual(s['hallucinated'], 0)


if __name__ == '__main__':
    unittest.main()
