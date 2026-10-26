"""Adversarial reader tests: recover a heading without searching substrings."""
import unittest
from reference_extractor.readers import word_blocks
from reference_extractor.rules import HEADING

def word(text,x0,x1,y,size=8,font='Body'):
    return dict(text=text,x0=x0,x1=x1,top=y,bottom=y+size,chars=[{'size':size,'fontname':font}])

class HeadingLayoutTests(unittest.TestCase):
    def context(self):
        return [word('Paragraph above the heading.',108,400,15),
                word('Another body line above.',108,400,29),
                word('1. Alice Smith. A study. Journal of AI, 2023.',108,420,80),
                word('Continuation line below the reference.',108,420,94)]

    def test_larger_heading_in_another_column_is_separated(self):
        words=self.context()+[word('Sidebar',10,95,50),word('Reference',108,168,51,12,'Body-Bold')]
        blocks=word_blocks(words,1,600,800)
        self.assertTrue(any(HEADING.fullmatch(b['text']) for b in blocks),blocks)
        self.assertTrue(any(b['text']=='Sidebar' for b in blocks))
        self.assertEqual(sorted(' '.join(b['text'] for b in blocks).split()),sorted(' '.join(w['text'] for w in words).split()))

    def test_large_inline_word_references_is_not_promoted(self):
        words=self.context()+[word('See',80,105,50),word('References',108,168,50,12,'Body-Bold'),word('for details.',171,220,50)]
        blocks=word_blocks(words,1,600,800)
        self.assertFalse(any(HEADING.fullmatch(b['text']) for b in blocks),blocks)

    def test_same_size_inline_bold_word_is_not_promoted(self):
        words=self.context()+[word('See',10,95,50),word('References',108,168,50,8,'Body-Bold')]
        blocks=word_blocks(words,1,600,800)
        self.assertFalse(any(HEADING.fullmatch(b['text']) for b in blocks),blocks)

    def test_no_column_alignment_evidence_keeps_ambiguous_run_together(self):
        words=[word('Sidebar',10,95,50),word('Reference',108,168,51,12,'Body-Bold')]
        self.assertFalse(any(HEADING.fullmatch(b['text']) for b in word_blocks(words,1,600,800)))

    def test_multiword_heading_and_chinese_heading_can_be_separated(self):
        for heading_words in [[word('Works',108,140,51,12,'Body-Bold'),word('Cited',143,175,51,12,'Body-Bold')],
                              [word('参考文献',108,168,51,12,'Body-Bold')]]:
            words=self.context()+[word('Sidebar',10,95,50)]+heading_words
            self.assertTrue(any(HEADING.fullmatch(b['text']) for b in word_blocks(words,1,600,800)))

if __name__=='__main__':unittest.main()
