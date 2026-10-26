import json
import tempfile
import unittest
from pathlib import Path
from ref_app.public_parsers import PublicTransport


class PublicParserTests(unittest.TestCase):
    def test_local_failure_falls_back_with_original_labels_and_record(self):
        def send(opener,url,body,headers):
            if url.endswith('/'):return '<meta name="csrf-token" content="temporary">',200
            if '/parse?' in url:return json.dumps([[['title','Original title']]]),200
            self.assertIn(b'Original',body)
            return json.dumps([{'title':'Original title'}]),200
        def broken(segments):raise RuntimeError('native conversion failed')
        with tempfile.TemporaryDirectory() as d:
            t=PublicTransport(Path(d),send=send,format_mode='local',converter=broken)
            raw,status=t('https://anystyle.io/parse',json.dumps({'input':['Original title']}).encode(),{})
            self.assertEqual(json.loads(raw)['csl'][0]['title'],'Original title')
            record=json.loads(next(Path(d).glob('local-format/*.json')).read_text('utf-8'))
            self.assertFalse(record['ok'])
            self.assertEqual(record['segments'],[[['title','Original title']]])

    def test_local_format_avoids_remote_format_request(self):
        calls=[]
        def send(opener,url,body,headers):
            calls.append(url)
            if url.endswith('/'):return '<meta name="csrf-token" content="temporary">',200
            if '/parse?' in url:return json.dumps([[['title','Example title']]]),200
            self.fail('Local mode must not call remote /format')
        def converter(segments):return {'csl':[{'title':'Example title'}],'seconds':0.01}
        with tempfile.TemporaryDirectory() as d:
            transport=PublicTransport(Path(d),send=send,format_mode='local',converter=converter)
            raw,status=transport('https://anystyle.io/parse',json.dumps({'input':['Example title']}).encode(),{})
            self.assertEqual(json.loads(raw)['csl'][0]['title'],'Example title')
            self.assertEqual(len(calls),2)
            self.assertTrue(list(Path(d).glob('local-format/*.json')))

    def test_anystyle_export_preserves_segments_without_training(self):
        calls=[]
        def send(opener,url,body,headers):
            calls.append((url,body,headers))
            if url.endswith('/'):
                return '<meta name="csrf-token" content="secret-session-token">',200
            if '/parse?' in url:return json.dumps([[['title','Example title']]]),200
            return json.dumps([{'title':'Example title'}]),200
        with tempfile.TemporaryDirectory() as d:
            t=PublicTransport(Path(d),send=send)
            raw,status=t('https://anystyle.io/parse',json.dumps({'input':['Example title']}).encode(),{})
            self.assertEqual(json.loads(raw)['csl'][0]['title'],'Example title')
            self.assertEqual(len(calls),3)
            text=''.join(p.read_text('utf-8') for p in Path(d).rglob('*.json'))
            self.assertNotIn('secret-session-token',text)
            self.assertIn('Example title',text)
            self.assertFalse(any('/train' in c[0] for c in calls))

    def test_unapproved_host_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):PublicTransport(Path(d))('https://other.example/parse',b'{}',{})

if __name__=='__main__':unittest.main()
