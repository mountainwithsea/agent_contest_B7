import unittest
from ref_app.visual_process import geometry

class VisualProcessTests(unittest.TestCase):
    def test_only_reference_pages_and_exact_boxes(self):
        doc={'input_type':'pdf','pages':[{'page':1,'blocks':[{'id':'a','bbox':[1,2,3,4]}]}, {'page':2,'blocks':[{'id':'b','text':'citation','bbox':[10,20,80,40]},{'id':'c','bbox':[10,50,80,70]}]}]}
        result={'references':[{'raw_text':'citation','source_ids':['b'],'pages':[2]}]}
        d=geometry(result,doc)
        self.assertEqual([p['page'] for p in d['pages']],[2])
        self.assertEqual(d['pages'][0]['boxes'][0]['bbox'],[10,20,80,40])
        self.assertEqual(d['pages'][0]['boxes'][0]['ref_id'],'R001')
    def test_cross_page_reference_keeps_one_id(self):
        d=geometry({'references':[{'raw_text':'x','source_ids':['a','b'],'pages':[2,3]}]}, {'input_type':'pdf','pages':[{'page':2,'blocks':[{'id':'a','bbox':[1,2,30,40]}]},{'page':3,'blocks':[{'id':'b','bbox':[2,3,30,40]}]}]})
        self.assertEqual([p['boxes'][0]['ref_id'] for p in d['pages']],['R001','R001'])
    def test_text_document_has_no_fake_coordinates(self):
        d=geometry({'references':[{'raw_text':'x','source_ids':['a'],'pages':[1]}]}, {'input_type':'docx','pages':[{'page':1,'blocks':[{'id':'a','text':'x','bbox':None}]}]})
        self.assertFalse(d['pages'][0]['boxes'])
        self.assertEqual(d['pages'][0]['text_blocks'][0]['ref_id'],'R001')
    def test_missing_block_is_visible_warning(self):
        d=geometry({'references':[{'raw_text':'x','source_ids':['absent'],'pages':[1]}]}, {'input_type':'pdf','pages':[]})
        self.assertTrue(d['warnings'])
    def test_image_without_ocr_coordinates_is_not_presented_as_boxed(self):
        d=geometry({'references':[{'raw_text':'x','source_ids':['a'],'pages':[1]}]}, {'input_type':'png','pages':[{'page':1,'blocks':[{'id':'a','text':'x','bbox':None}]}]})
        self.assertTrue(d['warnings'])
        self.assertFalse(d['pages'][0]['boxes'])

if __name__=='__main__':unittest.main()
