import tempfile
import unittest
from pathlib import Path
from ref_app.balanced import build_report, failed


class BalancedReportTests(unittest.TestCase):
    def test_processing_error_without_http_url_still_has_a_report(self):
        row = failed({'id': 'R001', 'input': {'raw_text': 'Citation.', 'qwen': {'title': 'A study'}}}, 'Query failed')
        row['initial_requests'] = [{'state': 'processing_error', 'error_type': 'PermissionError', 'provider': 'openalex'}]
        summary = dict(references=1, existence={'unknown': 1}, query_seconds=0, requests=1, identity_model_attempts=0)
        with tempfile.TemporaryDirectory() as tmp:
            build_report(Path(tmp), [row], summary)
            page = (Path(tmp) / 'index.html').read_text('utf-8')
        self.assertIn('openalex', page)
        self.assertIn('PermissionError', page)
        self.assertIn('未形成请求地址', page)
        self.assertNotIn('href=""', page)


if __name__ == '__main__':
    unittest.main()
