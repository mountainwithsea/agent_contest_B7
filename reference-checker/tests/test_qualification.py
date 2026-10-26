import unittest
from ref_app.qualification import qualify, resolve_model

def row(raw,g=None,a=None):
    return {'id':'test','raw_text':raw,'tools':{'grobid':{'fields':g or {}},'anystyle':{'fields':a or {}}}}

class Tests(unittest.TestCase):
    def test_truncated_doi_with_visible_continuation_is_rejected(self):
        q=qualify(row('Unknown citation. https://doi.org/10.1234/journal. 2020.001'))
        self.assertEqual(q['query']['identifiers']['doi'],[])

    def test_title_dehyphenation_keeps_both_query_forms(self):
        q=qualify(row('Alice. Fine- tuning methods.',{'title':'Fine- tuning methods'},{'title':'Fine- tuning methods'}))
        self.assertIn('Finetuning methods',q['query']['title_variants'])
        self.assertIn('Fine- tuning methods',q['query']['titles'])

    def test_identifier_split_and_whitespace_repair(self):
        q=qualify(row('A work. https://doi.org/10.1234/ xyz PMID: 12345678.',{'doi':['10.1234/xyzPMID:12345678']}))
        self.assertEqual(q['query']['identifiers']['doi'],['10.1234/xyz'])
        self.assertEqual(q['query']['identifiers']['pmid'],['12345678'])
        self.assertEqual(q['status'],'ready_offline')

    def test_unsupported_native_doi_is_not_trusted(self):
        q=qualify(row('Unclear work',{'doi':['10.1234/invented']}))
        self.assertEqual(q['query']['identifiers']['doi'],[])
        self.assertEqual(q['status'],'needs_llm')

    def test_author_name_not_used_as_title(self):
        q=qualify(row('Alice Smith and Bob Jones. 2020. Reliable learning methods.',{'title':'Reliable learning methods','authors':[{'literal':'Bob Jones'}]},{'title':'Bob Jones'}))
        self.assertEqual(q['query']['titles'],['Reliable learning methods'])
        self.assertEqual(q['status'],'ready_offline')

    def test_field_disagreement_does_not_force_model(self):
        q=qualify(row('Alice Smith. 2020. Reliable methods.',{'title':'Reliable methods','year':'2020'},{'title':'Reliable methods','year':'1476'}))
        self.assertEqual(q['status'],'ready_offline')
        self.assertEqual(q['query']['hard_filters'],{})
        self.assertIn('year',q['pending_fields'])

    def test_title_conflict_without_id_goes_to_model(self):
        q=qualify(row('A real title. A conference name.',{'title':'A real title'},{'title':'A conference name'}))
        self.assertEqual(q['status'],'needs_llm')

    def test_model_cannot_invent_title(self):
        q=qualify(row('An actual title.'))
        with self.assertRaises(ValueError):resolve_model(q,{'title':'Invented work'})

    def test_model_can_abstain(self):
        q=resolve_model(qualify(row('Unclear material')),{'title':None})
        self.assertEqual(q['status'],'needs_review')

    def test_shortened_doi_is_not_kept_beside_complete_id(self):
        q=qualify(row('https://doi.org/10.1234/abc. def',{'doi':['10.1234/abc.def']},{'doi':['10.1234/abc']}))
        self.assertEqual(q['query']['identifiers']['doi'],['10.1234/abc.def'])

    def test_related_dataset_not_used_for_paper_identity(self):
        q=qualify(row('Unknown paper. Data available at https://doi.org/10.1234/data',{'doi':['10.1234/data']}))
        self.assertEqual(q['query']['identifiers']['doi'],[])

if __name__=='__main__':unittest.main()
