import unittest
from ref_app.visual_process import project_fields

class FieldProjectionTests(unittest.TestCase):
    def project(self,parts,chosen):
        pages=[];sids=[]
        for n,text in enumerate(parts,1):
            sid=f'b{n}';sids.append(sid)
            chars=[{'text':c,'bbox':[i*4,10,i*4+3,20]} for i,c in enumerate(text)]
            pages.append({'page':n,'boxes':[{'ref_id':'R001','source_id':sid,'chars':chars}]})
        r={'id':'R001','source_ids':sids,'chosen':chosen};project_fields(r,pages);return r
    def test_cross_page_title_uses_real_glyph_bounds(self):
        r=self.project(['A. Author. A long','title. 2024.'],{'title':'A long title','year':'2024'})
        title=[b for b in r['field_boxes'] if b['field']=='title']
        self.assertEqual([b['page'] for b in title],[1,2])
        self.assertEqual(title[1]['bbox'],[0,10,19,20])
    def test_ambiguous_year_is_not_guessed(self):
        r=self.project(['2024. Example. Accessed 2024.'],{'year':'2024'})
        self.assertFalse(r['field_boxes']);self.assertEqual(len(r['unmapped_fields']),1)
    def test_no_image_coordinates_means_no_projection(self):
        r={'id':'R001','source_ids':['x'],'chosen':{'title':'Example'}};project_fields(r,[])
        self.assertFalse(r['field_boxes']);self.assertTrue(r['unmapped_fields'])
    def test_other_reference_cannot_supply_field(self):
        r=self.project(['Actual title.'],{'title':'Missing title'})
        self.assertFalse(r['field_boxes'])
    def test_unicode_and_hyphenated_line_match(self):
        r=self.project(['An efﬁcient algo-','rithm.'],{'title':'An efficient algorithm'})
        self.assertEqual(len(r['field_boxes']),2)
