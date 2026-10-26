import unittest
from ref_app.anystyle_formatter import convert, runtime_paths

class FormatterTests(unittest.TestCase):
    def setUp(self):
        _,ruby,node=runtime_paths()
        if not ruby.is_file() or not node.is_file():
            self.skipTest('Optional local Ruby/Node formatter runtime is not installed')

    def test_names_dates_notes_and_unknown_fields_survive(self):
        rows=[[['author','Smith, John'],['date','2020'],['title','A study of reference parsing'],['note','Data at https://example.org/data'],['custom-field','Keep this exact field']]]
        result=convert(rows)
        c=result['csl'][0]
        self.assertEqual(c['title'],'A study of reference parsing')
        self.assertEqual(c['issued']['date-parts'],[[2020]])
        self.assertEqual(c['author'][0]['family'],'Smith')
        self.assertIn('example.org/data',c['note'])
        self.assertEqual(c['custom-field'],'Keep this exact field')
        self.assertIn('language',c)

    def test_repeated_segments_and_row_count_preserved(self):
        result=convert([[['title','First title'],['title','second part']],[['title','Another title'],['date','2019']]])
        self.assertEqual(len(result['csl']),2)
        self.assertIn('second part',result['csl'][0]['title'])

if __name__=='__main__':unittest.main()
