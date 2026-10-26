import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch,MagicMock
from reference_identity.client import Client
from reference_identity.client import ModelConfig, build_payload

class ModelRoutingTests(unittest.TestCase):
    def config(self):
        return ModelConfig.from_values({'DEEPSEEK_API_KEY':'text-test-secret','LLM_MODEL':'openai/qwen3.8-omni-flash','LLM_API_BASE':'https://dashscope.aliyuncs.com/compatible-mode/v1','LLM_API_KEY':'vision-test-secret'})

    def test_text_uses_deepseek(self):
        c=self.config();url,key,payload=build_payload(c,'hello',100)
        self.assertEqual(url,'https://api.deepseek.com/chat/completions')
        self.assertEqual(key,'text-test-secret')
        self.assertEqual(payload['model'],'deepseek-flash')
        self.assertEqual(payload['thinking'],{'type':'disabled'})
        self.assertNotIn('modalities',payload)

    def test_vision_is_opt_in(self):
        with self.assertRaises(ValueError):build_payload(self.config(),'hello',100,images=['not-read.png'])

    def test_secrets_hidden_in_repr(self):
        self.assertNotIn('test-secret',repr(self.config()))

    def test_missing_deepseek_key_fails(self):
        with self.assertRaises(ValueError):ModelConfig.from_values({'LLM_API_KEY':'vision-only'})

    def test_unexpected_validation_error_keeps_response_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=Client(self.config(),tmp)
            response=MagicMock();response.status=200
            opener=MagicMock();opener.open.return_value.__enter__.return_value=response
            with patch('reference_identity.client.urllib.request.build_opener',return_value=opener),patch('reference_identity.client.decode_sse',return_value=('{}',{'total_tokens':10})):
                with self.assertRaises(RuntimeError):
                    client.ask('test','prompt',lambda value:(_ for _ in ()).throw(AttributeError('malformed field')))
            self.assertEqual(len(client.calls),2)
            self.assertEqual(client.calls[0]['usage']['total_tokens'],10)
            self.assertTrue((Path(tmp)/'test-attempt-2.json').exists())

if __name__=='__main__':unittest.main()
