import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ref_app.retrieval import retrieve_row
from reference_identity.evidence import sha


class OpenAlexConfigurationTests(unittest.TestCase):
    def test_shared_key_is_sent_in_header_slot_not_persisted(self):
        seen = []
        def request(tool, url, purpose, payload=None, secret=None):
            seen.append((url, secret))
            raw = tool.output/'raw.txt'; raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text('{"results": []}', encoding='utf-8')
            return {'url': url, 'body': payload, 'state': 'ok', 'raw_path': str(raw), 'sha256': sha(raw)}, b''
        row = {'id': 'R1', 'input': {'title_variants': ['Example title'], 'qwen': {'title': 'Example title'}, 'book_route': False}}
        with tempfile.TemporaryDirectory() as d, patch('reference_identity.tools.Tools.request', request):
            retrieve_row(row, Path(d), {'OPENALEX_API_KEY': 'example-private-test'}, selected=['openalex'])
            self.assertEqual(seen[0][1], 'example-private-test')
            self.assertNotIn('example-private-test', seen[0][0])
            records=list(Path(d).glob('request-index/*.json'))+list(Path(d).glob('records/*/*.json'))
            self.assertTrue(records)
            for record in records:self.assertNotIn('example-private-test',record.read_text('utf-8'))


if __name__ == '__main__': unittest.main()
