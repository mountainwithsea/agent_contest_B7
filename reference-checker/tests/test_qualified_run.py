import unittest
from ref_app.run_qualified import validate_authors


class AuthorBridgeTests(unittest.TestCase):
    def test_requires_raw_author_evidence(self):
        raw='J. Doe and A. Smith. Example title.'
        validate_authors({'authors':[{'literal':'J. Doe','kind':'person'}],'authors_truncated':False},raw)
        with self.assertRaises(ValueError):
            validate_authors({'authors':[{'literal':'John Doe','kind':'person'}],'authors_truncated':False},raw)
        with self.assertRaises(ValueError):
            validate_authors({'authors':[], 'authors_truncated':'no'},raw)

    def test_allows_unattributed_material_without_inventing_author(self):
        validate_authors({'authors':[],'authors_truncated':False},'Official documentation. 2024.')
